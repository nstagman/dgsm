import asyncio
from dgsm.controllers.proc_controller import ProcController, cmd


# Implementation that can be used for any app
# No actual monitoring of app stdout takes place
# This acts as a generic handle to allow the coordinator to start and stop any process
#   without the need to define a concrete class with its own regex patterns
class DefaultController(ProcController):
    def __init__(self, name:str, **kwargs) -> None:
        super().__init__(name, **kwargs)

    def _init_vars(self) -> None:
        self._app_attrs = { 'online' : False }
    
    @classmethod
    def ID(cls) -> str: return 'default'

    @property
    def status(self) -> str: return 'Running' if self.running else 'Stopped'
    @property
    def app_type(self) -> str:
        return self._app_attrs.get('id').capitalize() if self._app_attrs.get('id', None) else 'Default'

    # do not monitor this app's stdout
    def _output_handler(self, msg: str) -> bool:
        return False

    # since we have no knowledge of app state, it is always okay to stop
    def _stop_ok(self) -> tuple[bool, str]:
        return (True, "OK to stop")

    # override start command to automatically set _start_comp after 3 seconds
    @cmd('start')
    async def _start(self, *_):
        """
        Start the application
        """
        asyncio.get_running_loop().create_task(super()._start())
        await asyncio.sleep(3)
        try: self._start_comp.set_result(True)
        except asyncio.InvalidStateError: pass
    
    # override start command message since we are setting started state in 3 seconds anyway
    async def _on_start_cmd(self) -> str:
        return ''

    # forward running status since it the only known app state
    @cmd('status')
    async def _query_status(self, *_) -> None:
        """
        Returns the status of the application
        """
        rstr = f'{self.name} is {self.status}'
        if self.running:
            cpu, mem = self._resource_calc()
            rstr += f'\n  CPU: {cpu}%'
            rstr += f'\n  Mem: {mem} GB'
        await self.message_coordinator(rstr)