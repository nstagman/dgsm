import asyncio
from dataclasses import dataclass
from typing import Union
from disnake import Intents
from disnake.ext import commands
from disnake import ApplicationCommandInteraction
from disnake.http import LoginFailure, HTTPException, GatewayNotFound
import dgsm_bot.utils as nutil
import dgsm_bot.ssock as ssock


@dataclass
class AppInfo():
    name: str
    commands: list[str]
    status: str
    id: str
    
    # order by id then name - push 'default' to end of list
    def __lt__(self, other):
        if self.id == other.id: return self.name < other.name
        if self.id == 'default': return False
        if other.id == 'default': return True
        return self.id < other.id


class DBot(commands.Cog):
    def __init__(self, bot:commands.bot, token:str, address:str='localhost', port:int=8888, mac:str='', **kwargs) -> None:
        self._bot = bot
        self._token = token
        self._controller_ip = address
        self._port = port
        self._controller_mac = mac
        self._app_info:dict[str,AppInfo] = {}
        self._sock = ssock.SSock(
            type='c',
            host=self._controller_ip,
            port=self._port,
            req_handler=self._appcon_req_handler,
            on_connect=self._on_sock_connect,
            on_disconnect=self._on_sock_disconnect
        )
    
    def main_loop(self):
        # wrap discord interface coros - stop the event loop if they raise and exception
        async def start_bot():
            try:
                await self._bot.login(self._token)
                status = 'Connected to Discord\n'
                status += 'Waiting for connection to tDGSM\n' if not self._sock.connected else ''
                status += 'Use ctrl-c to stop'
                print(status)
                await self._bot.connect(reconnect=True) # this infinite loops
            except (LoginFailure, HTTPException, GatewayNotFound) as e:
                print('Improper Login Token\nUnable to Connect to Discord\nShutting Down')
                self._bot.loop.stop()
        self._bot.loop.create_task(start_bot()) # connect to discord
        self._sock.schedule(self._bot.loop) # connect to dgsm
        self._bot.loop.run_forever()
    
    # wait with timeout for the dgsm to connect
    async def _wait_for_connect(self, poll_intvl: int=5, timeout: int=200) -> bool:
        itrs = timeout // poll_intvl
        for _ in range(itrs):
            if self._sock.connected: return True
            await asyncio.sleep(poll_intvl)
        return False
    
    # schedule when connected to dgsm
    async def _on_sock_connect(self):
        print('Connected to DGSM')
    
    # reset app info when disconnected from dgsm
    async def _on_sock_disconnect(self):
        print('Disconnected from DGSM')
        self._app_info = {}
    
    # extracts necessary context from a discord interaction to send to the dgsm
    def _extract_context(self, ctx:Union[ApplicationCommandInteraction, commands.Context]):
        if type(ctx) == ApplicationCommandInteraction:
            return{
                'type': 'interaction',
                'interaction_id': ctx.id,
                'interaction_token': ctx.token,
                'responded': False,
                'channel_id': ctx.channel_id
            }
        elif type(ctx) == commands.Context:
            return{
                'type': 'channel',
                'channel_id': ctx.message.channel.id
            }
            
    # handle requests from the application controller - coroutine for the local socket callback
    async def _appcon_req_handler(self, sock:ssock.SSock, payload:bytes):
        if app_info := payload.get('app_info'): self._update_appcon_info(app_info)
        if payload.get('message'): await self._message_bot(payload)
    
    # updates app_info dict to match dgsm capability
    def _update_appcon_info(self, app_info:bytes):
        self._app_info = {}
        for name, info in app_info.items():
            self._app_info[name] = AppInfo(*info.values())
    
    # sends message to the discord server
    # uses messaging context to determine how to send the message
    async def _message_bot(self, payload):
        # leave if there is no context or message to send
        if not ((ctx := payload.get('context')) and (msg := payload.get('message'))): return
        for chunk in nutil.message_chunks(msg, 1950):
            chunk = f'```{chunk}```'
            # respond to any interaction that has not yet been responded to (satisfy the deferral)
            if (ctx.get('type', '') == 'interaction'
                and not ctx.get('responded', True)
                and (token := ctx.get('interaction_token'))):
                await self._bot.http.create_followup_message(
                    application_id=self._bot.application_id,
                    token=token,
                    content=chunk
                )
                ctx.update({'responded': True})
            # everything else is pushed to the original channel (long running apps may push status beyond the 15m window)
            elif cid := ctx.get('channel_id'): await self._bot.get_channel(cid).send(chunk)
    
    ### user command handling ###
    async def _wake(self, context):
        extracted_ctx = self._extract_context(context)
        if nutil.is_online(self._controller_ip):
            await self._message_bot({
                'context': extracted_ctx,
                'message': 'The host is already powered on.'
            })
            return
        if not nutil.wol(self._controller_mac): #unable to send WOL packet
            await self._message_bot({
                'context': extracted_ctx,
                'message': 'Unable to power on host. Try again later.'
                })
            return
        await self._message_bot({
            'context': extracted_ctx,
            'message': 'Powering on the host.  Please wait.'
        })
        extracted_ctx.update({'responded': True})
        if await self._wait_for_connect(): 
            await self._message_bot({
                'context': extracted_ctx,
                'message': 'The host is now powered on and connected.'
                })
        else: # the host is pingable, but the local socket is not connecting
            await self._message_bot({
                'context': extracted_ctx,
                'message': 'The host is unresponsive. Try again later.'
            })
    
    async def _sleep(self, context):
        await self._sock.write({
            'context': self._extract_context(context),
            'user_cmd': {'cmd': 'sleep'}
        })
    
    async def _start(self, context, app):
        if self._sock.connected: await self._sock.write({
            'context': self._extract_context(context),
            'user_cmd': {'cmd': 'start', 'app': app}
        })
        else: await self._message_bot({
            'context': self._extract_context(context), 
            'message': "The host is disconnected. Try 'wake' to turn it on."
        })
    
    async def _stop(self, context, app):
        if self._sock.connected: await self._sock.write({
            'context': self._extract_context(context),
            'user_cmd': {'cmd': 'stop', 'app': app}
        })
        else: await self._message_bot({
            'context': self._extract_context(context), 
            'message': "The host is disconnected. Try 'wake' to turn it on."
        })
    
    async def _status(self, context, app):
        if self._sock.connected: await self._sock.write({
            'context': self._extract_context(context),
            'user_cmd': {'cmd': 'status', 'app': app} if app else {'cmd': 'status'}
        })
        elif not nutil.is_online(self._controller_ip): await self._message_bot({
            'context': self._extract_context(context),
            'message': "The host is disconnected. Try 'wake' to turn it on."
        })
        elif nutil.is_online(self._controller_ip): await self._message_bot({
            'context': self._extract_context(context),
            'message': "The host is powered on but unresponsive. Try again later."
        })
    
    async def _help(self, context, app):
        if self._sock.connected: await self._sock.write({
            'context': self._extract_context(context),
            'user_cmd': {'cmd': 'help', 'app': app} if app else {'cmd': 'help'}
        })
        else: await self._message_bot({
            'context': self._extract_context(context),
            'message': "The host is disconnected. Try 'wake' to turn it on."
        })
    
    async def _extended(self, context, app, cmd, args):
        if self._sock.connected:
            ctx = self._extract_context(context)
            ctx['responded'] = True
            await self._sock.write({
                'context': ctx,
                'user_cmd': {'cmd': cmd, 'app': app, 'args': args} if args else {'cmd': cmd, 'app': app}
            })
        else: await self._message_bot({
            'context': self._extract_context(context),
            'message': "The host is disconnected. Try 'wake' to turn it on."
        })
        

    ### slash commands ###
    @commands.slash_command(name='wake', description='Turn on the host')
    async def _slash_wake(self, interaction:ApplicationCommandInteraction):
        await interaction.response.defer()
        await self._wake(interaction)
    
    @commands.slash_command(name='sleep', description='Turn off the host')
    async def _slash_sleep(self, interaction:ApplicationCommandInteraction):
        await interaction.response.defer()
        await self._sleep(interaction)
    
    @commands.slash_command(name ='start', description='Start the specified app')
    async def _slash_start(self, interaction:ApplicationCommandInteraction, app:str):
        """
        Parameters
        ----------
        app: The application to start
        """
        await interaction.response.defer()
        await self._start(interaction, app)
    
    @commands.slash_command(name='stop', description='Stop the specified app')
    async def _slash_stop(self, interaction:ApplicationCommandInteraction, app:str):
        """
        Parameters
        ----------
        app: The application to stop
        """
        await interaction.response.defer()
        await self._stop(interaction, app)
    
    @commands.slash_command(name='status', description='View status information')
    async def _slash_status(self, interaction:ApplicationCommandInteraction, app:str=None):
        """
        Parameters
        ----------
        app: The application to view
        """
        await interaction.response.defer()
        await self._status(interaction, app)
    
    @commands.slash_command(name='help', description='View the help message')
    async def _slash_help(self, interaction:ApplicationCommandInteraction, app:str=None):
        """
        Parameters
        ----------
        app: The application to view
        """
        await interaction.response.defer()
        await self._help(interaction, app)
    
    @commands.slash_command(name='ext', description='Execute an extended command')
    async def _slash_extended(self, interaction:ApplicationCommandInteraction, app:str, cmd:str, args:str=None):
        """
        Parameters
        ----------
        app: The application to send the command
        cmd: The extended command
        args Any arguments for this command
        """
        await interaction.send(content='working...', delete_after=1.0)
        await self._extended(interaction, app, cmd, args)
    
    ### autocomplete ###
    @_slash_start.autocomplete("app")
    @_slash_stop.autocomplete("app")
    @_slash_status.autocomplete("app")
    @_slash_help.autocomplete("app")
    @_slash_extended.autocomplete("app")
    async def _auto_comp_app(self, interaction:ApplicationCommandInteraction, input:str):
        return [app.name for app in sorted(self._app_info.values()) if input.casefold() in app.name.casefold()]

    @_slash_extended.autocomplete("cmd")
    async def _auto_comp_cmd(self, interaction:ApplicationCommandInteraction, input:str):
        if not (app := self._app_info.get(interaction.filled_options.get('app').casefold())): return
        return [cmd for cmd in sorted(app.commands) if input.casefold() in cmd.casefold()]
    
    ### channel message commands ###
    @commands.command(name='wake')
    async def _cmd_wake(self, context:commands.Context): await self._wake(context)
    @commands.command(name='sleep')
    async def _cmd_sleep(self, context:commands.Context): await self._sleep(context)
    @commands.command(name='start')
    async def _cmd_start(self, context:commands.Context, app:str): await self._start(context, app)
    @commands.command(name='stop')
    async def _cmd_stop(self, context:commands.Context, app:str): await self._stop(context, app)
    @commands.command(name='status')
    async def _cmd_status(self, context:commands.Context, app:str=None): await self._status(context, app)
    @commands.command(name='help')
    async def _cmd_help(self, context:commands.Context, app:str=None): await self._help(context, app)
    @commands.command(name='ext')
    async def _cmd_extended(self, context:commands.Context, app:str, cmd:str, *, args=None): await self._extended(context, app, cmd, args)


# configures and returns a DBot instance
def create_dbot(token:str, prefix=None, mac:str=None, address:str='localhost', port:int=8888) -> DBot:
    intent = Intents.default()
    if prefix:
        intent.message_content = True
        bot = commands.Bot(
            command_prefix=prefix,
            intents=intent,
            help_command=None
        )
    else:
        bot = commands.Bot(
            command_prefix=commands.when_mentioned,
            intents=intent,
            help_command=None
        )
        
    dbot = DBot(
        bot=bot,
        token=token,
        address=address,
        port=port,
        mac=mac
    )

    bot.add_cog(dbot)

    # deregister wake and sleep commands if the bot and dgsm are on the same host
    if address == 'localhost' or not mac:
        bot.remove_command('wake')
        bot.remove_command('sleep')
        bot.remove_slash_command('wake')
        bot.remove_slash_command('sleep')
        
    return dbot