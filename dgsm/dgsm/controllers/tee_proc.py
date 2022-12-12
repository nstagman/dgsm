from aioconsole import ainput, aprint
import asyncio
import os
import sys

from dgsm.utils.log_util import make_logger, init_logging, start_logging, stop_logging


P2CR = 'p2cr'
C2PW = 'c2pw'
IS_WINDOWS = os.name == 'nt'

if IS_WINDOWS:
    from asyncio import windows_utils

def get_descriptor(key:str):
    if not os.environ.get(key): raise KeyError(f'{key} does not exist in this env')
    return int(os.environ[key])

class TeeProc:
    def __init__(self, subproc_args:list[str]) -> None:
        init_logging(fname=os.environ.get('proc_name', ''))
        self.logger = make_logger()
        start_logging()
        self.loop = asyncio.new_event_loop()
        try:
            self._p2c_rp = get_descriptor('p2cr')
            self._c2p_wp = get_descriptor('c2pw')
        except KeyError as e:
            self.logger.warning(f'Unable to tee process - inheritable pipe not found')
            raise e
        self._subproc_args = subproc_args
        self.start()
   
    def start(self):
        self.loop.create_task(self._main())
        try: self.loop.run_forever()
        except BaseException as e:
            self.logger.error(f"app stopped due to error: {e.with_traceback}")
        finally:
            stop_logging()
            self._shutdown()
   
    async def _main(self):
        self._proc = await asyncio.create_subprocess_exec(
            *self._subproc_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=os.environ.copy()
        )
        await self._open_parent_read_stream()
        await self._open_parent_write_stream()
        self._tasks = []
        self._tasks.append(self.loop.create_task(self._monitor_subproc_output()))
        self._tasks.append(self.loop.create_task(self._monitor_console_input()))
        self._tasks.append(self.loop.create_task(self._monitor_parent_input()))
        for task in self._tasks: await task
   
    async def _open_parent_read_stream(self):
        self._p2c_stream = asyncio.StreamReader()
        await self.loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(self._p2c_stream),
            windows_utils.PipeHandle(self._p2c_rp) if IS_WINDOWS
            else os.fdopen(self._p2c_rp)
        )
   
    async def _open_parent_write_stream(self):
        rs = asyncio.StreamReader()
        transport, proto = await self.loop.connect_write_pipe(
            lambda: asyncio.StreamReaderProtocol(rs),
            windows_utils.PipeHandle(self._c2p_wp) if IS_WINDOWS
            else os.fdopen(self._c2p_wp)
        )
        self._c2p_stream = asyncio.StreamWriter(transport, proto, rs, self.loop)

    async def _monitor_parent_input(self):
        while True:
            line = b''
            try: line = await self._p2c_stream.readline()
            except: break
            if not line: break
            await self._handle_parent_input(self._normalize_message(line))
        self._shutdown()
   
    async def _monitor_console_input(self):
        while True:
            line = ''
            try: line = await ainput()
            except: break
            await self._handle_console_input(self._normalize_message(line))
        self._shutdown()

    async def _monitor_subproc_output(self) -> None:
        if self._proc.stdout:
            while True:
                line = b''
                try: line = await self._proc.stdout.readline()
                except: break
                if not line: break
                await self._tee_subproc_output(self._normalize_message(line))
        self._shutdown()
    
    async def _handle_parent_input(self, input):
        self._proc.stdin.write(f'{input}{os.linesep}'.encode())
        await self._proc.stdin.drain()

    async def _tee_subproc_output(self, output):
        self._c2p_stream.write(f'{output}{os.linesep}'.encode())
        await self._c2p_stream.drain()
        await aprint(f'{output}')

    async def _handle_console_input(self, input):
        self._proc.stdin.write(f'{input}{os.linesep}'.encode())
        await self._proc.stdin.drain()
   
    # returns msg as a string with newline character removed
    def _normalize_message(self, msg):
        if type(msg) is str: return msg.strip(os.linesep)
        return msg.decode().strip(os.linesep)

    def _shutdown(self):
        sys.exit(0)


if __name__ == '__main__':
    TeeProc(sys.argv[1:])