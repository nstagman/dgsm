import asyncio
import contextvars
from functools import reduce
import os

import aioconsole
import colorama
import psutil

from dgsm.utils import ssock
from dgsm.utils.log_util import make_logger, start_logging, stop_logging
from dgsm.utils.intf_grouping import IGI, interface_tag
from dgsm.utils.upnp_util import get_router, open_ports
from dgsm.controllers import CONTROLLERS, DEFAULT_ID, ProcController


logger = make_logger()
cmd = interface_tag('cmds')
console_cmd = interface_tag('console_cmds')
msg_ctx = contextvars.ContextVar('msg_ctx', default={})

colorama.init()
red = colorama.Fore.LIGHTRED_EX
blu = colorama.Fore.LIGHTBLUE_EX
grn = colorama.Fore.LIGHTGREEN_EX
yel = colorama.Fore.LIGHTYELLOW_EX
res = colorama.Fore.RESET
color_table = (red, ''), (blu, ''), (grn, ''), (yel, ''), (res, '') # used for stripping color sequences

# Coordinates interactions between the discord bot, console, and game server applications
# creates a socket at 'host':'port' to communicate with the bot
# composes ProcController implementations to control server applications listen in the configuration
class DGSM_Coordinator(IGI):
    def __init__(self, apps:dict[str,dict], default_apps:list[str]=[], address='localhost', port=8888) -> None:
        self._apps: dict[str, ProcController] = {}
        self._init_apps(apps, default_apps)
        self._apply_upnp(apps, address)
        self._sock = ssock.SSock(
            type='s',
            host=address,
            port=port,
            req_handler=self._req_handler,
            on_connect=self._on_sock_connect,
            on_disconnect=self._on_sock_disconnect
        )
    
    # populates _apps dictionary with all specified instances of AppControllers in server_table dict
    # starts apps specified in default_apps list
    def _init_apps(self, app_table:dict[str,dict], default_apps:list[str]=[]) -> None:
        for app_name, kwargs in app_table.items():
            if not kwargs.get('prg'):
                print(f"{grn}{app_name}{res} is {red}missing{res} key {yel}'prg'{res} in its configuration. {grn}{app_name}{res} will be unavailable to use.")
                logger.warning(f"{app_name} is missing key 'prg'.")
                continue
            app = CONTROLLERS.get(kwargs.get('id'), CONTROLLERS[DEFAULT_ID])
            self._apps[app_name.casefold()] = app(app_name, msg_cb=self._app_message_handler, **kwargs)
        for app_name in default_apps:
            if app_name.casefold() in self._apps.keys():
                asyncio.get_event_loop().create_task(self._apps[app_name.casefold()].cmds.start())
    
    # open ports specified in the upnp config
    def _apply_upnp(self, app_cfg:dict[str,dict], def_addr):
        router = None
        for name, cfg in app_cfg.items():
            if upnp := cfg.get('opts', {}).get('upnp'):
                if ports := upnp.get('ports'):
                    addr = upnp.get('address', '')
                    if not addr and def_addr != 'localhost': addr = def_addr
                    if not router:
                        print('Applying UPnP configuration')
                        router = get_router()
                    
                    for port, proto in ports.items():
                        port_range = str(port).split('-')
                        start_port = int(port_range[0])
                        end_port = start_port if len(port_range) == 1 else int(port_range[1])
                        open_ports(
                            desc=name,
                            port_start=start_port,
                            port_end=end_port,
                            proto=proto,
                            addr=addr,
                            router=router
                        )

    # main entry point - schedules long lived tasks and begins event loop
    def start(self) -> None:
        try:
            self.loop = asyncio.new_event_loop()
            main = self.loop.create_task(self._main())
            # run the 2 main monitoring tasks
            self.loop.run_until_complete(main)
            
            # collect any residual tasks and wait for complete to shutdown cleanly
            tasks = asyncio.all_tasks()
            all = asyncio.gather(*tasks)
            self.loop.run_until_complete(all)
        except BaseException as e:
            logger.exception(f"stopped due to unrecoverble error: {e.with_traceback}")
        finally:
            stop_logging()
    
    # main loop
    async def _main(self):
        self.tasks:list[asyncio.Task] = []
        start_logging()
        loop = asyncio.get_running_loop()
        self.tasks.append(self._sock.schedule(loop))
        print(f'The following applications have been added to the configuration:')
        for app in self._apps.values():
            print(f'  {blu}{app.name}{res} - {app.ID()}')
        print(f'Waiting for the Discord Bot to connect\nUse {yel}exit{res} to stop')
        self.tasks.append(loop.create_task(self._monitor_console()))
        self.tasks = set(self.tasks)
        psutil.cpu_percent()
        for task in self.tasks: await task
    
    # return help information to the user
    @cmd('help')
    async def _help(self) -> None:
        await self._app_message_handler(self._help_msg())

    # get app status - write response to socket
    @cmd('status')
    async def _status_all(self) -> None:
        res = 'Apps:\n'
        for app in self._apps.values():
            res += f'  {app.name}: {app.status}\n'
        res += 'System:\n'
        res += f'  CPU: {int(psutil.cpu_percent())}% {round(psutil.cpu_freq().current/1000, 2)} GHz\n'
        res += f'  Mem: {round(psutil.virtual_memory().used / 1024**3, 1)}/{round(psutil.virtual_memory().total / 1024**3, 1)} GB ({psutil.virtual_memory().percent}%)'
        await self._app_message_handler(res)

    # turn off host if possible
    @cmd('sleep')
    async def _sleep(self) -> None:
        await self._app_message_handler("Attempting to power off the host")
        for app in self._apps.values():
            if app.running:
                await app.cmds.stop()
        for app in self._apps.values():
            if app.running:
                await self._app_message_handler(f"{app.name} is preventing the host from powering off")
                return
        await self._app_message_handler("Powering off the host")
        await self._sock.stop()
        asyncio.get_event_loop().stop()
        if os.name == 'nt': shtdwn = "shutdown /s /t 15"
        else: shtdwn = "shutdown -h now"
        os.system(shtdwn)

    async def _on_sock_connect(self):
        await self.print_message(f'{grn}Connected{res} to the Discord Bot')
        logger.info('The Discord Bot has Connected')
        await self._app_message_handler(app_info=self._aggregate_apps())
    
    async def _on_sock_disconnect(self):
        await self.print_message(f'{red}Disconnected{res} from the Discord Bot')
        logger.info('The Discord Bot has Disconnected')
    
    def _help_msg(self) -> str:
        msg = 'Available Apps:\n'
        list_by_app = {}
        for app in self._apps.values():
            l = list_by_app.get(app.app_type, [])
            l.append(app.name)
            list_by_app[app.app_type] = l
        for type, apps in list_by_app.items():
            for app in apps:
                msg += f'  {blu}{app}{res} - {type}\n'
        msg += 'Commands:\n'\
            f'  {yel}start{res}, {yel}stop{res}, {yel}status{res}, {yel}help{res}, {yel}sleep{res}\n'\
            f'Usage:\n' \
            f'  \'{yel}start{res} {blu}{l[0]}{res}\' will start the {l[0]} application\n'\
            f'  \'{yel}status{res} {blu}{l[0]}{res}\' returns the status of {l[0]}\n'
        return msg

    # handle messages sent from app controllers - uses messaging context to respond to the approprite interface
    async def _app_message_handler(self, message:str=None, **kwargs):
        ctx = msg_ctx.get()
        # command originated from the console
        if ctx.get('console_cmd'):
            await self.print_message(message, spotlight=ctx.get('spotlight', False))
            return
        
        payload = {'context': ctx} if ctx else {}
        if message: payload['message'] = reduce(lambda a, kv: a.replace(*kv), color_table, message)
        payload.update(kwargs)
        await self._sock.write(payload)
        ctx.update({'responded': True})
        msg_ctx.set(ctx)

    # handle requests received from the socket
    async def _req_handler(self, sock:ssock.SSock, payload:dict) -> None:
        token = msg_ctx.set(payload.get('context', {}))
        if user_cmd := payload.get('user_cmd'):
            asyncio.get_event_loop().create_task(self._user_cmd_handler(user_cmd))
        if payload.get('app_info_req'):
            asyncio.get_event_loop().create_task(self._app_message_handler(app_info=self._aggregate_apps()))
        msg_ctx.reset(token)
    
    # handle commands sent from users
    async def _user_cmd_handler(self, user_cmd:dict):
        command = {k: v.casefold() for k, v in user_cmd.items()}
        match command:
            case {'cmd': cmd, 'app': app, **kwargs}:
                if not (target := self._apps.get(app)):
                    await self._app_message_handler(f"'{user_cmd['app']}' is not a recognized application")
                    logger.warning(f"user supplied unrecognized application: '{user_cmd['app']}'")
                elif not (cmd_func := target.cmds.get(cmd)):
                    await self._app_message_handler(f"{target.name} does not support the command '{user_cmd['cmd']}'")
                    logger.warning(f"user supplied unrecognized command: '{user_cmd['cmd']}'")
                else: # execute command
                    try:
                        if args := kwargs.get('args'): # args exist
                            logger.info(f"calling {target.name}.{user_cmd['cmd']}({args})")
                            await cmd_func(args)
                        else: # no args
                            logger.info(f"calling {target.name}.{user_cmd['cmd']}()")
                            await cmd_func()
                    except TypeError:
                        await self._app_message_handler(f"Incorrect number of arguments were given for {target.name}.{user_cmd['cmd']}")
                        logger.warning(f"user supplied incorrect number of args for {target.name}.{user_cmd['cmd']}")
            case {'cmd': cmd, **kwargs}:
                if not (cmd_func := self.cmds.get(cmd)):
                    if cmd in ProcController.cmds.keys():
                        await self._app_message_handler(f"Must specify an application with '{user_cmd['cmd']}'")
                    else:
                        await self._app_message_handler(f"Unknown command '{user_cmd['cmd']}'. Try 'help' for more information")
                    logger.warning(f"user supplied unactionable command: '{user_cmd['cmd']}'")
                else: # execute command
                    try:
                        if args := kwargs.get('args'): # args exist
                            logger.info(f"calling {user_cmd['cmd']}({args})")
                            await cmd_func(args)
                        else: # no args
                            logger.info(f"calling {user_cmd['cmd']}()")
                            await cmd_func()
                    except TypeError:
                        await self._app_message_handler(f"Incorrect number of arguments were given for {user_cmd['cmd']}")
                        logger.warning(f"user supplied incorrect number of args for {user_cmd['cmd']}")
            case _:
                await self._app_message_handler(f"Sorry, I do not understand")
                logger.warning("user supplied unrecognizable command structure")

    # collect information about all apps
    def _aggregate_apps(self):
        return {
            name: {
                'name': app.name,
                'commands': [cmd for cmd in app.cmds],
                'status': app.status,
                'id': app.ID()
            } for name, app in self._apps.items()
        }

    ###
    ### Console Input Handling
    ###
    
    @console_cmd('help')
    async def _console_help_msg(self):
        msg = self._help_msg()
        msg += 'Console Only Commands:\n'
        msg += f'  {yel}focus{res}, {yel}unfocus{res}, {yel}exit{res}\n'
        msg += f'Use {yel}focus{res} *{blu}app{res}* to enter direct input mode for *{blu}app{res}*\n'\
            f'Use {yel}--{res} to escape the input and {yel}--unfocus{res} to exit direct input mode'
        await self.print_message(msg)
    
    @console_cmd('focus')
    async def _focus_app(self, app:ProcController=None) -> None:
        if not app: await self.print_message(f"Must specify and app to focus")
        if spotlight.name: self._app_message_handler(f"{spotlight.name} is already focussed")
        spotlight.focus(app)
        await self.print_message(f"Focussing {blu}{app.name}{res}, all input is fed directly to {blu}{app.name}{res}. Use {yel}'--unfocus'{res} to exit this mode", spotlight=True)
    
    @console_cmd('unfocus')
    async def _unfocus(self) -> None:
        if not spotlight.name: return
        name = spotlight.name
        spotlight.unfocus()
        await self.print_message(f'{blu}{name}{res} is no longer focussed', spotlight=False)
    
    @console_cmd('exit')
    async def _exit(self) -> None:
        await self._sock.stop()
        for app in self._apps.values():
            if app.running: await app.force_stop()
        await asyncio.sleep(1)
        for task in (asyncio.all_tasks() - self.tasks - {asyncio.current_task()}): task.cancel()
        for task in (asyncio.all_tasks() - self.tasks - {asyncio.current_task()}): await asyncio.shield(task)
        for task in asyncio.all_tasks() - {asyncio.current_task()}: task.cancel()
        for task in asyncio.all_tasks() - {asyncio.current_task()}: await asyncio.shield(task)
    
    async def _monitor_console(self) -> None:
        while True:
            prompt = f'{blu}{spotlight.name}{res}$ ' if spotlight.name else f'{grn}dgsm{res}$ '
            line = ''
            try: line = await aioconsole.ainput(f'{prompt}')
            except: break
            asyncio.get_running_loop().create_task(self._console_input_handler(line))
    
    async def _console_input_handler(self, input:str) -> None:
        spotlight_esc_seq = '--'
        input = input.strip(f' \t\r\n')
        if not input: return
        if spotlight.name:
            if input.startswith(spotlight_esc_seq):
                input = input.lstrip(spotlight_esc_seq)
            else:
                if not spotlight.app.running: await self.print_message(f'{spotlight.name} must be started first')
                else: await spotlight.to_app(input)
                return
        try:
            cmd = input.split()
            context = { 'console_cmd': { 'cmd': cmd.pop(0) }}
            if cmd: context['console_cmd']['app'] = cmd.pop(0)
            if cmd: context['console_cmd']['args'] = ' '.join(arg for arg in cmd)
        except:
            await self.print_message('Malformed Command')
            return
        token = msg_ctx.set(context)
        asyncio.get_event_loop().create_task(self._console_cmd_handler(context['console_cmd']))
        msg_ctx.reset(token)
    
    # handles commands sent from console - if no match, send command to user command handler
    async def _console_cmd_handler(self, console_cmd:dict):
        command = {k: v.casefold() for k, v in console_cmd.items()}
        match command:
            case {'cmd': 'focus', 'app': app}: # special behavior for focussing...
                if not (target := self._apps.get(app)):
                    await self._app_message_handler(f"'{console_cmd['app']}' is not a recognized application")
                else: await self._focus_app(target)
            case {'cmd': cmd, **kwargs} if cmd in self.console_cmds.keys() and not self._apps.get(kwargs.get('app', '')):
                await self.console_cmds.get(cmd)()
            case _: await self._user_cmd_handler(console_cmd)
    
    # async print to console, pref is inserted at the beginning of each line
    async def print_message(self, message:str | bytes, **kwargs) -> None:
        pref = f'{blu}[{spotlight.name}]{res}: ' if kwargs.get('spotlight') else ''
        suff = f'\n{blu}{spotlight.name}{res}$ ' if spotlight.name else f'\n{grn}dgsm{res}$ '
        if isinstance(type(message), bytes): message = message.decode()
        message = f'\n{pref}'.join(line for line in message.strip(os.linesep).split('\n'))
        # clear the current line, place cursor at beginning, then print
        await aioconsole.aprint(f'\033[2K\033[1G{pref}{message}{suff}', end='')


# encapsulate 'spotlighting' behavior
# spotlight an app - only one app can be spotlighted at a time
# all console input is passed directly, as-is, to the apps stdin
# all app stdout is printed to console
class spotlight:
    name:str = ''
    app:ProcController = None
    wstream:asyncio.StreamWriter = None
    context:contextvars.ContextVar[dict]
    stop_app_worker = None

    @classmethod
    def focus(cls, app:ProcController):
        cls.name = app.name
        cls.app = app
        cls.wstream = app._writestream
        ctx = msg_ctx.get()
        ctx['spotlight'] = True
        cls.context = ctx
        cls.stop_app_worker = cls.app.output_worker(cls.to_console)
   
    @classmethod
    def unfocus(cls):
        cls.name = ''
        cls.app = None
        cls.wstream = None
        cls.context = None
        if cls.stop_app_worker: cls.stop_app_worker()
        cls.stop_app_worker = None
   
    @classmethod
    async def to_app(cls, msg:str|bytes):
        cls.wstream = cls.app._writestream
        if type(msg) is str: msg = (msg.strip(' \t\r\n') + os.linesep).encode()
        elif type(msg) is bytes: msg = msg.strip(b' \t\r\n') + f'{os.linesep}'.encode()
        cls.wstream.write(msg)
        await cls.wstream.drain()
    
    # the output_worker fn needs a callable not coro - schedule message with cached context
    @classmethod
    def to_console(cls, msg:str|bytes):
        if type(msg) is bytes: msg = msg.decode()
        async def _aprint(msg:str): await cls.app.message_coordinator(msg)
        tkn = msg_ctx.set(cls.context)
        asyncio.get_event_loop().create_task(_aprint(msg))
        msg_ctx.reset(tkn)
