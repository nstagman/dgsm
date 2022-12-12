import asyncio
import json
from typing import Any, Callable, Coroutine, Optional, Union


async def NOP(*a, **k): pass

# Simple socket class built using asyncio sockets designed for one-to-one communication
# each socket only communicates with one other socket - if the partner is offline, it will poll waiting for a connection
# when a request is received, the data is sent to the request handler function and added as a new task to the event loop
# server/client designation is strictly for initiating the connection - once connected, the functionality of each is identical
class SSock:
    _timeout = 5
    _sep     = b'\x17\x04'

    def __init__(
        self,
        type,
        host         :str,
        port         :Union[str,int],
        req_handler  :Callable[['SSock',bytes],Coroutine[Any,Any,None]],
        on_connect=NOP,
        on_disconnect=NOP,
    ) -> None:
        self._is_server     = type == 's'
        self._host          = host
        self._port          = port
        self._req_handler   = req_handler
        self._connected     = False
        self._closing       = False
        self._listen_task   = None
        self._on_connect    = on_connect
        self._on_disconnect = on_disconnect

    @property
    def connected(self) -> bool:
        return self._connected
    
    # schedules this socket to open as a new task in the event loop
    def schedule(self, loop: asyncio.AbstractEventLoop=None) -> None:
        if not loop: loop = asyncio.get_event_loop()
        loop.create_task(self.open())

    # open socket at/to host:port and poll for a connection
    # once connected, await listen method
    # if partner disconnects, resume polling or next connection
    async def open(self) -> None:
        self._closing = False
        if self._is_server:
            # client connection callback
            async def on_conn(r, w):
                if self._connected or self._closing: return
                self._rsock = r
                self._wsock = w
                self._connected = True
                
            self._server = await asyncio.start_server(on_conn, self._host, self._port)
            while not self._closing:
                while not self._connected: # poll for client connection
                    await asyncio.sleep(self._timeout)
                # schedule and await listening task
                self._listen_task = asyncio.get_event_loop().create_task(self.listen())
                try: await self._listen_task
                except asyncio.CancelledError: return
                await self._on_disconnect()
                self._connected = False
        else:
            while not self._connected and not self._closing:
                try: # attempt to connect to host
                    self._rsock, self._wsock = await asyncio.open_connection(self._host, self._port)
                    self._connected = True
                    self._listen_task = asyncio.get_event_loop().create_task(self.listen())
                    try: await self._listen_task
                    except asyncio.CancelledError: return
                    await self._on_disconnect()
                except: # wait polling period 
                    await asyncio.sleep(self._timeout)
                self._connected = False

    # listen across the socket
    # pass messages to request handler and schedule as a new task
    async def listen(self) -> None:
        asyncio.get_event_loop().create_task(self._on_connect())
        while self._connected and not self._closing:
            try:
                rdata = b''
                rdata = await self._rsock.readuntil(separator=self._sep)
            except:
                break # monitoring failed - return to connection phase
            if self._connected and not self._closing and rdata:
                asyncio.get_event_loop().create_task(self._req_handler(self, json.loads(rdata.strip(self._sep).decode())))
        self._connected = False

    # encodes msg, adds separator, and writes result to socket
    async def write(self, msg: Union[str,bytes]) -> None:
        if not self._connected: return
        self._wsock.write(json.dumps(msg).encode() + self._sep)
        await self._wsock.drain()

    # cancels the listening task, closes the socket, and ends the main loop
    # socket will need to be scheduled again to reconnect
    async def stop(self) -> None:
        self._closing = True
        if not self._listen_task.done():
            self._listen_task.cancel()
            try: await self._listen_task
            except asyncio.CancelledError: pass
        self._wsock.close()
        await self._wsock.wait_closed()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._connected = False
