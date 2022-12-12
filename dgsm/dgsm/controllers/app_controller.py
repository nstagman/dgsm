import asyncio, re
from dgsm.controllers.proc_controller import ProcController, cmd
from dgsm.utils.intf_grouping import interface_tag
from dgsm.utils.log_util import make_logger


logger = make_logger()
stdout_handler = interface_tag('handlers')

# AppController abstract class
# default behavior for controlling a ProcController process
# concrete classes are expected to create regex patterns for detecting
# version, server connection, player connects/disconnects
# this is not compulsory, subclasses can override anything as needed
class AppController(ProcController):
    def __init__(self, name:str, **kwargs):
        super().__init__(name, **kwargs)

    @property
    def status(self) -> str: return 'Online' if self._app_attrs['online'] else 'Offline'
    @property
    def connected(self) -> bool: return self.running and self._app_attrs['online']
    @property # name of the app
    def app_type(self) -> str: return self._app_attrs.get('id', 'App').capitalize()

    ### Default Behavior ###
    def _init_vars(self) -> None:
        self._app_attrs.update({
            'online' : False,
            'players': []
        })

    # write version number to app_attrs
    def _handle_version(self, match:re.Match) -> None:
        self._app_attrs['version'] = match.group(1)
        
    # set online attr as true and set start completed future as true
    def _handle_online(self, match:re.Match) -> None:
        self._app_attrs['online'] = True
        try: self._start_comp.set_result(True)
        except asyncio.InvalidStateError: pass
        
    # add players to list when they connect
    def _handle_connect(self, match:re.Match) -> None:
        self._app_attrs['players'].append(match.group(1))
        
    # remove players from list when they disconnect
    def _handle_disconnect(self, match:re.Match) -> None:
        self._app_attrs['players'].remove(match.group(1))

    # run msg through re.search - if match then call associated handler function
    def _output_handler(self, msg:str) -> bool:
        for pattern, method in self.handlers.items():
            if match := re.search(pattern, msg):
                method(match)
                return True
        return False
    
    # customize message once app has started
    async def _on_start(self) -> str:
        rstr = f'{self.name} has started'
        if ep := self._app_attrs.get('app_info', {}).get('endpoint'):
            rstr += f'\nEndpoint: {ep}'
        if pw := self._app_attrs.get('app_info', {}).get('password'):
            rstr += f'\nPassword: {pw}'
        return rstr

    # verify no players are connected
    def _stop_ok(self) -> tuple[bool,str]:
        if not self._app_attrs['players']: return (True, "OK to stop")
        return (False, f"Cannot stop {self.name} with players connected")

    # return formatted status
    @cmd('status')
    async def _query_status(self, *_) -> None:
        """
        Returns the status of the application
        """
        if not self._app_attrs['online']:
            await self.message_coordinator(f"{self.name} is Offline")
            return
        rstr = f'{self.name} - {self.app_type}\n'
        if self._app_attrs.get('version'):
            rstr += f'  version: {self._app_attrs["version"]}\n'
        for k, v in self._app_attrs['app_info'].items():
            rstr += f'  {k}: {v}\n'
        rstr += f'  {len(self._app_attrs["players"])} player{"s" if len(self._app_attrs["players"]) != 1 else ""} online'
        if self._app_attrs['players']:
            rstr += ':'
            for player in self._app_attrs['players']:
                rstr += f'\n    {player}'
        cpu, mem = self._resource_calc()
        rstr += f'\n  CPU: {cpu}%'
        rstr += f'\n  Mem: {mem} GB'
        await self.message_coordinator(rstr)
