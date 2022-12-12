import re
from dgsm.controllers import AppController, cmd, stdout_handler


class MineCraftController(AppController):
    VERSION    = re.compile(r'(?:Starting minecraft server version )([\w.]+)', re.IGNORECASE)
    ONLINE     = re.compile(r'(Done \([\w.]+s\)!)', re.IGNORECASE)
    CONNECT    = re.compile(r'([\w]+)(?: joined the game)', re.IGNORECASE)
    DISCONNECT = re.compile(r'([\w]+)(?: left the game)', re.IGNORECASE)
    def __init__(self, name:str, **kwargs) -> None:
        super().__init__(name, **kwargs)

    @classmethod
    def ID(cls) -> str: return 'minecraft'

    # Tag the four methods for handling app output with this apps regex patterns
    @stdout_handler(VERSION)
    def _handle_version(self, match: re.Match) -> None:
        return super()._handle_version(match)
    
    @stdout_handler(ONLINE)
    def _handle_online(self, match: re.Match) -> None:
        return super()._handle_online(match)
    
    @stdout_handler(CONNECT)
    def _handle_connect(self, match: re.Match) -> None:
        return super()._handle_connect(match)
    
    @stdout_handler(DISCONNECT)
    def _handle_disconnect(self, match: re.Match) -> None:
        return super()._handle_disconnect(match)
    
    @cmd('echo')
    async def _echo(self, *args) -> None:
        """
        Echo a message back to the user
        """
        if args: await self.message_coordinator(' '.join(arg for arg in args))
        else: await self.message_coordinator('nothing but silence')
    
    @cmd('seed')
    async def _seed(self, *args) -> None:
        """
        Returns the seed of the server
        """
        waiter = self.output_waiter(pattern=re.compile(r'(?:Seed: \[)(-?\d+)(?:\])', re.IGNORECASE))
        if not waiter: return
        await self.message_app('seed')
        match = await waiter()
        await self.message_coordinator(f'{self.name} Seed: {match.group(1)}')
    
    @cmd('input')
    async def _input(self, *args) -> None:
        """
        Sends input directly to the app
        """
        if not args: return
        waiter = self.output_waiter(wait_time=1.0)
        if not waiter: return
        await self.message_app(' '.join(arg for arg in args))
        output = await waiter()
        await self.message_coordinator(output)
