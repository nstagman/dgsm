import asyncio
import os
import sys
import dgsm.controllers.tee_proc as tee


TEE_SCRIPT = tee.__file__
P2CR = tee.P2CR
C2PW = tee.C2PW
IS_WINDOWS = os.name == 'nt'

if IS_WINDOWS:
    from asyncio import windows_utils
    import _winapi

def NOP(*a, **k): pass

# returns a 5-tuple - subprocess, readstream, writestream, close_readstream_fn, close_writestream_fn
# if new_console is false this simply returns a Process, Process.stdout, Process.stdin, NOP, NOP
# if new_console is true, 2 new streams are created and returned instead of Process.stdin and Process.stdout - leaving stdin/stdout in-tact
# this is used for 'teeing' the application input/output from/to a new terminal window as well as the main ProcController
async def create_sub_proc(args:list[str], loop=None, new_console=False, **kwargs):
    if not loop: loop = asyncio.get_running_loop()
    if not new_console: return await get_sub_proc(args)
    if IS_WINDOWS: return await windows_piped_proc(' '.join(arg for arg in args), loop, **kwargs)
    return await linux_piped_proc(' '.join(arg for arg in args), loop, **kwargs)

# simply create a subprocess and return it along with its stdin and stdout
async def get_sub_proc(args:list[str]):
    sub_proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    return sub_proc, sub_proc.stdout, sub_proc.stdin, NOP, NOP

# create a subprocess with 2 inherited File Handles prepared for overlapped I/O
async def windows_piped_proc(args:str, loop, **kwargs):
    p2cr, p2cw = windows_utils.pipe(duplex=True, overlapped=(True, True))
    c2pr, c2pw = windows_utils.pipe(duplex=True, overlapped=(True, True))

    env = os.environ.copy()
    name = kwargs.get('name', '_'.join(arg for arg in args))
    # the subprocess needs knowledge of these keys at 'compile' time
    env[P2CR] = str(p2cr)
    env[C2PW] = str(c2pw)
    env['proc_name'] = name
    os.set_handle_inheritable(p2cr, True)
    os.set_handle_inheritable(c2pw, True)

    sub_proc = await asyncio.create_subprocess_shell(
        cmd=f'start "{name}" /wait cmd /K {sys.executable} {TEE_SCRIPT} {args}',
        shell=True,
        env=env,
        close_fds=False
    )

    ## Detach File Handles used by child process in *this* process
    _winapi.CloseHandle(p2cr)
    _winapi.CloseHandle(c2pw)
   
    ## Child to Parent Stream
    c2p_stream = asyncio.StreamReader()
    c2p_pipe_handle = windows_utils.PipeHandle(c2pr)
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(c2p_stream),
        c2p_pipe_handle
    )

    ## Parent to Child Stream
    rs = asyncio.StreamReader()
    p2c_pipe_handle = windows_utils.PipeHandle(p2cw)
    transport, proto = await loop.connect_write_pipe(
        lambda: asyncio.StreamReaderProtocol(rs),
        p2c_pipe_handle
    )
    p2c_stream = asyncio.StreamWriter(transport, proto, rs, loop)

    ## Verify the PipeHandles (File Handles) are closed
    def close_read_stream():
        try:
            c2p_pipe_handle.close()
        except OSError: pass
    def close_write_stream():
        try:
            p2c_stream.close()
            p2c_pipe_handle.close()
        except OSError: pass
   
    return sub_proc, c2p_stream, p2c_stream, close_read_stream, close_write_stream

# create subprocess with inheritable pipes for linux systems
async def linux_piped_proc(args:str, loop, **kwargs):
    p2cr, p2cw = os.pipe()
    c2pr, c2pw = os.pipe()

    env = os.environ.copy()
    name = kwargs.get('name', '_'.join(arg for arg in args))
    # the subprocess needs knowledge of these keys at 'compile' time
    env[P2CR] = str(p2cr)
    env[C2PW] = str(c2pw)
    env['proc_name'] = name
    os.set_inheritable(p2cr, True)
    os.set_inheritable(c2pw, True)

    sub_proc = await asyncio.create_subprocess_shell(
        # xterm is not guaranteed to exist...
        cmd=f'xterm -T {name} -e {sys.executable} {TEE_SCRIPT} {args}',
        shell=True,
        env=env,
        close_fds=False
    )

    ## Detach File Handles used by child process in *this* process
    os.close(p2cr)
    os.close(c2pw)
   
    ## Child to Parent Stream
    c2p_stream = asyncio.StreamReader()
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(c2p_stream),
        os.fdopen(c2pr)
    )

    ## Parent to Child Stream
    rs = asyncio.StreamReader()
    transport, proto = await loop.connect_write_pipe(
        lambda: asyncio.StreamReaderProtocol(rs),
        os.fdopen(p2cw)
    )
    p2c_stream = asyncio.StreamWriter(transport, proto, rs, loop)

    ## Verify the PipeHandles are closed
    def close_read_stream():
        try:
            os.close(c2pr)
        except OSError: pass
    def close_write_stream():
        try:
            p2c_stream.close()
            os.close(p2cw)
        except OSError: pass
   
    return sub_proc, c2p_stream, p2c_stream, close_read_stream, close_write_stream

