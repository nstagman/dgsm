import re
from dgsm.controllers import AppController, cmd, stdout_handler


class ValheimController(AppController):
    VERSION    = re.compile(r'(?:Valheim version[:\s]+)([\w.]+)(?:\s|$)', re.IGNORECASE)
    ONLINE     = re.compile(r'(Game server connected)(?:\s|$)', re.IGNORECASE)
    CONNECT    = re.compile(r'(?:Got character ZDOID from )([\w]+)(?: : )(-?[0-9]{5,})(?::)', re.IGNORECASE)
    DISCONNECT = re.compile(r'(?:Destroying abandoned non persistent zdo -?[0-9]{5,}:\d+ owner )(-?[0-9]{5,})(?:\s|$)', re.IGNORECASE)
    def __init__(self, name:str, **kwargs) -> None:
        super().__init__(name, **kwargs)

    @classmethod
    def ID(cls) -> str: return 'valheim'

    # players attr needs to be a dict to handle this apps output
    def _init_vars(self) -> None:
        super()._init_vars()
        self._app_attrs['players'] = {}

    # Tag the four methods for handling app output with this apps regex patterns
    @stdout_handler(VERSION)
    def _handle_version(self, match: re.Match) -> None:
        return super()._handle_version(match)
    
    @stdout_handler(ONLINE)
    def _handle_online(self, match: re.Match) -> None:
        return super()._handle_online(match)
    
    # detecting players connections needs to be overridden.
    @stdout_handler(CONNECT)
    def _handle_connect(self, match:re.Match) -> None:
        self._app_attrs['players'][match.group(2)] = match.group(1)
        
    @stdout_handler(DISCONNECT)
    def _handle_disconnect(self, match:re.Match) -> None:
        self._app_attrs['players'].pop(match.group(1), None)

    # override query to handle dict of players instead of list
    @cmd('status')
    async def _query_status(self, *_) -> None:
        """
        Returns the status of the application
        """
        if not self._app_attrs['online']:
            await self.message_coordinator(f"{self.name} is Offline")
            return
        rstr = f'{self.name} - {self.app_type}\n' \
            f'  version: {self._app_attrs["version"]}\n'
        for k, v in self._app_attrs['app_info'].items():
            rstr += f'  {k}: {v}\n'
        rstr += f'  {len(self._app_attrs["players"])} player{"s" if len(self._app_attrs["players"]) != 1 else ""} online'
        if self._app_attrs['players']:
            rstr += ':'
            for player in self._app_attrs['players'].values():
                rstr += f'\n    {player}'
        cpu, mem = self._resource_calc()
        rstr += f'\n  CPU: {cpu}%'
        rstr += f'\n  Mem: {mem} GB'
        await self.message_coordinator(rstr)