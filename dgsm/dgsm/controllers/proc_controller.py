from abc import ABC, abstractclassmethod, abstractmethod, abstractproperty
import asyncio
from functools import singledispatchmethod
import os
import re
from typing import Any, Callable, Coroutine, overload
import uuid
import psutil
from dgsm.utils.intf_grouping import IGI, AIGI, interface_tag
from dgsm.controllers import piped_proc
from dgsm.utils.log_util import make_logger


logger = make_logger()
cmd = interface_tag('cmds')

# ProcController abstract class
# executes program located at kwargs['prg'] and monitors the new process's stdout
# exposes start and stop methods to start and stop the process
class ProcController(ABC, IGI, metaclass=AIGI):
    def __init__(self, name:str, **kwargs) -> None:
        self._app_attrs = {}
        self._app_attrs.update(kwargs)
        self._name = name
        self._prg = kwargs['prg']
        self._msg_cb = kwargs['msg_cb']
        self._run = False
        self._proc = None
        self._proc_children = []
        self._readstream = None
        self._writestream = None
        self._close_rs = None
        self._close_ws = None
        self._start_comp = None
        self._monitor_task = None
        self._stop_commanded = False
        self._output_workers:dict[int,Callable] = {}
        self._init_vars()
    
    @abstractclassmethod
    def ID(cls) -> str: pass
    @abstractproperty
    def status(self) -> str: pass
    @abstractproperty
    def app_type(self) -> str: pass
    @abstractmethod
    def _init_vars(self) -> None: pass
    @abstractmethod # each line read from stdout is passed as msg
    def _output_handler(self, msg:str) -> bool: pass
    @abstractmethod # return true if app is okay to stop
    def _stop_ok(self) -> tuple[bool,str]: pass
    @abstractmethod
    async def _query_status(self, *_) -> None: pass

    @property
    def name(self) -> str: return self._name
    @property
    def running(self) -> bool: return self._run

    # spawn app in new subprocess if it isn't already running. verify app starts and connects
    @cmd('start')
    async def _start(self, *_) -> None:
        """
        Start the application
        """
        if self._run or (self._proc and self._proc.returncode is None):
            await self.message_coordinator(f"{self.name} is already running")
            return
        self._init_vars()
        loop = asyncio.get_event_loop()
        self._start_comp = loop.create_future()
        # start the app
        if msg := await self._on_start_cmd(): await self.message_coordinator(msg)
        loop.create_task(self._spawn_subprocess())
        await self._wait_for_start()

    # tries to stop app if possible. verify app has stopped running
    @cmd('stop')
    async def _stop(self, *_) -> None:
        """
        Stop the application
        """
        if not self._run: # app is already stopped
            await self.message_coordinator(f'{self.name} is not running')
            return
        stop_ok, code = self._stop_ok()
        if not stop_ok: # implementation determined app cannot be stopped
            await self.message_coordinator(code)
            return
        self._run = False
        # stop the app
        self._stop_commanded = True
        if msg := await self._on_stop_cmd(): await self.message_coordinator(msg)
        if not self._monitor_task.done(): self._monitor_task.cancel()
        await self._wait_for_stop()
    
    @cmd('help')
    async def _help(self, *_) -> None:
        """
        Displays this help message
        """
        strch = '\r\n\t '
        msg = f'{self.name} Supported Commands:\n'
        for name, meth in self.cmds.items():
            msg += f'  {name}'
            if meth.__doc__: msg += f' - {meth.__doc__.strip(strch)}'
            msg += '\n'
        await self.message_coordinator(msg)
    
    # indescriminately stop the app
    async def force_stop(self) -> None:
        if not self._run: # app is already stopped
            return
        self._run = False
        self._stop_commanded = True
        if not self._monitor_task.done(): self._monitor_task.cancel()
        try: # wait until the process has ended
            await asyncio.wait_for(self._proc.wait(), 5)
            logger.info(f"{self.name} has been force stopped")
        except asyncio.TimeoutError: pass
        await asyncio.sleep(0)

    # write a message to the coordinator
    async def message_coordinator(self, message, **kwargs) -> None:
        await self._msg_cb(message, **kwargs)

    # spawn a new subprocess to run the app - await the monitor_task until it is cancelled
    async def _spawn_subprocess(self) -> None:
        self._run = True
        try:
            args = self._prg if type(self._prg) is list else [self._prg]
            self._proc, self._readstream, self._writestream, self._close_rs, self._close_ws = await piped_proc.create_sub_proc(
                args,
                new_console=self._app_attrs.get('opts', {}).get('new_console', False),
                name=self.name,
                **self._app_attrs
            )
        except FileNotFoundError:
            await self.message_coordinator(f"{self.name} did not start - unable to locate the executable.")
            logger.warning(f"unable to locate the executable {self._prg} for {self.name}")
            self._proc = self._readstream = self._writestream = self._close_rs = self._close_ws = None
            self._run = False
            self._proc_children = []
            self._output_workers = {}
            self._stop_commanded = False
            self._init_vars()
            return

        # schedule the monitoring and wait until task has ended
        self._monitor_task = asyncio.get_event_loop().create_task(self._monitor_stdout())
        try: await self._monitor_task # this will infinite loop until task is cancelled or subprocess ends
        except asyncio.CancelledError: pass

        # monitoring has stopped or been cancelled - terminate
        await self._terminate_proc()

    # read stdout line by line and send to active output workers to be processed
    async def _monitor_stdout(self) -> None:
        # create an output worker to send app output to the output_handler implementation
        self.output_worker(self._output_handler)
        if self._readstream:
            logger.info(f"{self.name} output monitoring has started")
            while self._run:
                line = b''
                try: line = await self._readstream.readline()
                except: break
                if not line or not self._run: break
                for worker in self._output_workers.values(): worker(line.decode())

    # attempt to stop the process running the app
    async def _terminate_proc(self) -> None:
        self._close_rs()
        self._close_ws()
        try: # add any more child processes to the list before termination
            if self._proc:
                self._proc_children.extend(psutil.Process(self._proc.pid).children(recursive=True))
        except psutil.NoSuchProcess: pass

        # stop all child processes
        for child in self._proc_children:
            try: child.terminate()
            except psutil.NoSuchProcess: pass
        
        self._readstream = self._writestream = self._close_rs = self._close_ws = None
        self._run = False
        self._proc_children = []
        self._output_workers = {}
        if not self._stop_commanded:
            logger.warning(f"{self.name} was terminated unexpectedly")
            if (msg := await self._on_stop()): await self.message_coordinator(msg)
        self._stop_commanded = False
        self._init_vars()
        self._proc = None

    # check app started with timeout
    async def _wait_for_start(self):
        try: # wait for the implementation to determine app has started successfully
            await asyncio.wait_for(self._start_comp, 90)
            # snapshot the children processes now since the app is fully started
            self._proc_children = psutil.Process(self._proc.pid).children(recursive=True)
            for p in self._proc_children:
                p.cpu_percent()
        except asyncio.TimeoutError: # app did not start
            if msg := await self._on_start_fail(): await self.message_coordinator(msg)
            logger.warning(f"{self.name} failed to start")
            return
        logger.info(f"{self.name} has been started")
        if msg := await self._on_start(): await self.message_coordinator(msg)

    # check process terminated with timeout
    async def _wait_for_stop(self):
        try: # wait until the process has ended
            await asyncio.wait_for(self._proc.wait(), 30)
            if msg := await self._on_stop(): await self.message_coordinator(msg)
            logger.info(f"{self.name} has been stopped")
        except asyncio.TimeoutError: # could not stop the subprocess for some reason
            if msg := await self._on_stop_fail(): await self.message_coordinator(msg)
            logger.warning(f"{self.name} failed to stop")
            self._run = True
            self._stop_commanded = False
    
    # returns a tuple containing cpu usage (%), mem usage (GB)
    def _resource_calc(self) -> tuple:
        if not self._proc: return ''
        mem = 0
        cpu = 0
        for p in self._proc_children:
            mem += p.memory_info().rss
            cpu += p.cpu_percent()
        mem = round(mem / 1024**3, 1)
        cpu = round(cpu/psutil.cpu_count())
        return cpu, mem
    
    # awaited when app starts successfully
    # return message as string
    async def _on_start(self) -> str:
        return f"{self.name} has started"

    # awaited when the app does not start in alloted time
    # return message as string
    async def _on_start_fail(self) -> str:
        return f"{self.name} is unable to start"
    
    # awaited immediately before the app process is spawned
    # return message as string
    async def _on_start_cmd(self) -> str:
        return f"Starting {self.name}"

    # awaited when app stops successfully
    async def _on_stop(self) -> str:
        await asyncio.sleep(2)
        return f"{self.name} has stopped"

    # awaited when app fails to stop in alloted time
    async def _on_stop_fail(self) -> str:
        return f"{self.name} is unable to stop"
    
    # awaited immediately before app process is terminated
    async def _on_stop_cmd(self) -> str:
        return '' # default to no message since the termination happens almost immediately
    
    # sends msg to the app stdin
    # returns True if successful, False otherwise
    async def message_app(self, msg) -> bool:
        if not self.running: return False
        if type(msg) is bytes: msg = msg.decode()
        msg = msg.strip(' \t\r\n')
        self._writestream.write(f'{msg}{os.linesep}'.encode())
        await self._writestream.drain()
        return True
    
    # creates an output worker to process app output
    # fn defines the functionality of the worker - a callable that accepts a single string as input
    # returns a function that will cancel the worker when called
    def output_worker(self, fn:Callable[[str], None]):
        def _worker(output:str):
            fn(output)
        
        # add worker to the active workers dict
        key = uuid.uuid4().hex
        self._output_workers[key] = _worker

        def _cancel_worker():
            self._output_workers.pop(key, None)
        
        return _cancel_worker
    
    ### overloaded functions that handle creating and deleting workers - returning a coroutine to await for the work to be complete ###
    
    # following 4 defs are for linting purposes
    @overload
    def output_waiter(self, output_count:int, return_partial=True, timeout:float=3.0) -> Coroutine[Any, Any, str]:
        """
        Parse output and return the string or Match object when the waiting parameters have been satisfied, or a timeout occurs
        """
        pass
    @overload
    def output_waiter(self, wait_time:float) -> Coroutine[Any, Any, str]: pass
    @overload
    def output_waiter(self, sub_string:str, aggregate=False, return_partial=False, timeout:float=3.0) -> Coroutine[Any, Any, str]: pass
    @overload
    def output_waiter(self, pattern:re.Pattern, timeout:float=3.0) -> Coroutine[Any, Any, re.Match]: pass
    
    # returns dispatched method if app is running
    def output_waiter(self, *args, **kwargs) -> Coroutine[Any, Any, str] | None:
        if not self.running: return None
        return self.output_waiter_imp(*args, **kwargs)
    
    # wait until a specified number of responses have been received
    # all output responses are concatenated and returned as a string once the specified number is reached or a timeout occurs
    # if return_partial is True then the current aggregated output is returned when a timeout occurs - otherwise an empty string is returned
    # set timeout <=0 to run this without a time constraint
    @singledispatchmethod
    def output_waiter_imp(self, output_count:int, return_partial=True, timeout:float=3.0) -> Coroutine[Any, Any, str]:
        if output_count <= 0: raise ValueError("output_count must be greater than zero")
        fut = asyncio.get_event_loop().create_future()
        aggregated_str = ''
        count = 0
        # aggregate all strings until the output count is reached
        def worker(output:str):
            nonlocal aggregated_str
            nonlocal count
            aggregated_str += output
            count += 1
            if count >= output_count: fut.set_result(True)
        
        # add worker to the active workers dict
        stop_worker = self.output_worker(worker)
        
        # awaitable coro for the result
        async def awaiter():
            nonlocal aggregated_str
            if timeout > 0.0:
                try: await asyncio.wait_for(fut, timeout)
                except asyncio.TimeoutError:
                    if not return_partial: aggregated_str = ''
                finally: stop_worker()
            else:
                await fut
                stop_worker()
            return aggregated_str
        return awaiter
    
    # collect and aggregate output for a specified amount of time
    # after time has elapsed, return the aggregated output as a string
    # @overload
    @output_waiter_imp.register
    def _(self, wait_time:float) -> Coroutine[Any, Any, str]:
        if wait_time <= 0: raise ValueError("wait_time must be greater than zero")
        fut = asyncio.get_event_loop().create_future()
        aggregated_str = ''
        # aggregate all output
        def worker(output:str):
            nonlocal aggregated_str
            aggregated_str += output
        
        # add worker to the active workers dict
        stop_worker = self.output_worker(worker)
        
        # awaitable coro for the result
        async def awaiter():
            try: await asyncio.wait_for(fut, wait_time)
            except asyncio.TimeoutError: pass
            finally: stop_worker()
            return aggregated_str
        return awaiter
    
    # wait until a specifed sub string is found in app output
    # if aggregate is true, all output from the time this is called will be concatenated and returned once the sub string is found
    #   otherwise just the specific output response containing the substring is returned
    # if return_partial is True then the current aggregated output is returned when a timeout occurs (aggregate must also be True)
    #   otherwise an empty string is returned
    # set timeout <= 0 to run this without a time constraint
    # @overload
    @output_waiter_imp.register
    def _(self, sub_string:str, aggregate=False, return_partial=False, timeout:float=3.0) -> Coroutine[Any, Any, str]:
        if not sub_string: raise ValueError("sub_string must be a non-empty string")
        fut = asyncio.get_event_loop().create_future()
        aggregated_str = ''
        # only return the output if it contains sub_string
        def worker(output:str):
            nonlocal aggregated_str
            if sub_string in output:
                aggregated_str = f'{output}{os.linesep}'
                fut.set_result(True)
        # aggregate all strings until the sub_string is found
        def worker_agg(output:str):
            nonlocal aggregated_str
            aggregated_str += output
            if sub_string in output: fut.set_result(True)
        
        # add worker to the active workers dict
        stop_worker = self.output_worker(worker if not aggregate else worker_agg)
        
        # awaitable coro for the result
        async def awaiter():
            nonlocal aggregated_str
            if timeout > 0.0:
                try: await asyncio.wait_for(fut, timeout)
                except asyncio.TimeoutError:
                    if not return_partial: aggregated_str = ''
                finally: stop_worker()
            else:
                await fut
                stop_worker()
            return aggregated_str
        return awaiter
    
    # wait until the pattern matches app output
    # return match object when found or None if timeout occurs
    # set timeout <= 0 to run this without a time constraint
    # @overload
    @output_waiter_imp.register
    def _(self, pattern:re.Pattern, timeout:float=3.0) -> Coroutine[Any, Any, str]:
        if not pattern: raise ValueError("pattern cannot be None")
        fut = asyncio.get_event_loop().create_future()
        match = None
        def worker(output:str):
            nonlocal match
            if match := re.search(pattern, output):
                fut.set_result(True)
        
        # add worker to the active workers dict
        stop_worker = self.output_worker(worker)
        
        # awaitable coro for the result
        async def awaiter():
            if timeout > 0.0:
                try: await asyncio.wait_for(fut, timeout)
                except asyncio.TimeoutError: pass
                finally: stop_worker()
            else:
                await fut
                stop_worker()
            return match
        return awaiter
