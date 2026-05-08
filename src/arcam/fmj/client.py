"""Client code"""

import asyncio
from asyncio.streams import StreamReader, StreamWriter
from copy import copy
import logging
from datetime import timedelta
from contextlib import contextmanager
from typing import overload
from collections.abc import Callable
from serialx import open_serial_connection

from . import (
    AmxDuetRequest,
    AmxDuetResponse,
    AnswerCodes,
    ArcamException,
    CommandCodes,
    CommandPacket,
    ConnectionFailed,
    EnumFlags,
    NotConnectedException,
    ResponseException,
    ResponsePacket,
    UnsupportedZone,
    GenericRequest,
    GenericResponse,
    read_response,
    write_packet,
)
from .utils import async_retry

_LOGGER = logging.getLogger(__name__)
_REQUEST_TIMEOUT = timedelta(seconds=3)
_REQUEST_THROTTLE = 0.2

_HEARTBEAT_INTERVAL = timedelta(seconds=5)
_HEARTBEAT_TIMEOUT = _HEARTBEAT_INTERVAL + _HEARTBEAT_INTERVAL

def _schedule_timeout(future: asyncio.Future, message: str):
    """Schedule a timeout on a future."""
    def _timeout_future():
        if future.done():
            return
        future.set_exception(TimeoutError(message))

    loop = asyncio.get_running_loop()
    handle = loop.call_later(
        _REQUEST_TIMEOUT.total_seconds(),
        _timeout_future)
    future.add_done_callback(lambda _: handle.cancel())

class RequestQueue:
    """Manages the prioritized request queue."""
    def __init__(self):
        self._queue: asyncio.PriorityQueue[tuple[int, int, asyncio.Future[GenericResponse], GenericRequest]] | None = asyncio.PriorityQueue()
        self._count = 0

    def close(self) -> None:
        """Shut down all pending and queued requests."""
        while not self._queue.empty():
            _, _, future, _ = self._queue.get_nowait()
            future.set_exception(NotConnectedException("Connected was closed"))
        self._queue = None

    def put_nowait(self, future: asyncio.Future[GenericResponse], request: GenericRequest, priority: int = 0):
        if not self._queue:
            raise NotConnectedException()

        self._count = self._count + 1
        self._queue.put_nowait((priority, self._count, future, request))

    async def get(self) -> tuple[asyncio.Future[GenericResponse], GenericRequest]:
        """Get a request that is not finished already."""
        if not self._queue:
            raise NotConnectedException()

        while True:
            _, _, future, request = await self._queue.get()
            if not future.done():
                break
        return future, request
    
class RequestPending:
    """Manages pending requests and clean up when done."""
    def __init__(self):
        self._pending: dict[asyncio.Future[GenericResponse], GenericRequest] = {}
    
    def close(self):
        for future in self._pending:
            future.set_exception(NotConnectedException("Connected was closed"))

    def add(self, future: asyncio.Future[GenericResponse], request: GenericRequest):
        self._pending[future] = request
        future.add_done_callback(self._pending.pop)

    def process(self, response: GenericResponse):
        for future, request in self._pending.items():
            if future.done():
                continue
            if response.respons_to(request):
                future.set_result(response)

class ClientBase:
    def __init__(self) -> None:
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None
        self._request_queue = RequestQueue()
        self._request_pending = RequestPending()
        self._listen: set[Callable] = {self._request_pending.process}

    @contextmanager
    def listen(self, listener: Callable):
        self._listen.add(listener)
        try:
            yield self
        finally:
            self._listen.remove(listener)

    async def _process_request_single(self, writer: StreamWriter):
        """Process a single request from queue queue."""
        try:
            async with asyncio.timeout(_HEARTBEAT_INTERVAL.total_seconds()):
                future, request = await self._request_queue.get()
        except TimeoutError:
            _LOGGER.debug("Sending ping")
            request = CommandPacket(1, CommandCodes.POWER, bytes([0xF0]))
            await write_packet(writer, request)
            return

        self._request_pending.add(future, request)

        await write_packet(writer, request)
        _schedule_timeout(future, "Request timed out")

    async def _process_request(self, writer: StreamWriter):
        """Process the request queue."""
        try:
            while True:
                await self._process_request_single(writer)
                await asyncio.sleep(_REQUEST_THROTTLE)
        finally:
            self._request_queue.close()
            self._request_pending.close()

    async def _process_data(self, reader: StreamReader):
        while True:
            try:
                async with asyncio.timeout(_HEARTBEAT_TIMEOUT.total_seconds()):
                    packet = await read_response(reader)
            except TimeoutError as exception:
                _LOGGER.debug("Missed all pings")
                raise ConnectionFailed("Missed all pings") from exception

            if packet is None:
                _LOGGER.debug("Server disconnected")
                raise ConnectionFailed("Server disconnected")

            _LOGGER.debug("Packet received: %s", packet)
            for listener in self._listen:
                listener(packet)

    async def process(self) -> None:
        assert self._writer, "Writer missing"
        assert self._reader, "Reader missing"

        reader = self._reader
        writer = self._writer

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(self._process_data(reader))
                group.create_task(self._process_request(writer))
        except BaseExceptionGroup as exc:
            # convert to a non group exception to keep compatibility
            raise copy(exc.exceptions[0]).with_traceback(exc.exceptions[0].__traceback__)
        finally:
            _LOGGER.debug("Process task shutting down")
            writer.close()

    @property
    def connected(self) -> bool:
        return self._reader is not None and not self._reader.at_eof()

    @property
    def started(self) -> bool:
        return self._writer is not None

    @overload
    async def request_raw(self, request: CommandPacket, *, priority: int = 0) -> ResponsePacket: ...

    @overload
    async def request_raw(self, request: AmxDuetRequest, *, priority: int = 0) -> AmxDuetResponse: ...

    @async_retry(2, asyncio.TimeoutError)
    async def request_raw(self, request: GenericRequest, *, priority: int = 0) -> GenericResponse:
        future = asyncio.Future[GenericResponse]()
        try:
            self._request_queue.put_nowait(future, request, priority=priority)
            return await future
        finally:
            future.cancel()
                    
    async def send(self, zn: int, cc: CommandCodes, data: bytes, *, priority: int = 0) -> None:
        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        future = asyncio.Future[GenericResponse]()
        request = CommandPacket(zn, cc, data)
        self._request_queue_add(priority, future, request)

    async def request(self, zn: int, cc: CommandCodes, data: bytes, priority: int = 0):
        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        if cc.flags & EnumFlags.SEND_ONLY:
            await self.send(zn, cc, data, priority=priority)
            return

        response = await self.request_raw(CommandPacket(zn, cc, data))

        if response.ac == AnswerCodes.STATUS_UPDATE:
            return response.data

        raise ResponseException.from_response(response)

    @property
    def peer(self) -> str:
        raise NotImplementedError()  

    async def _open(self) -> tuple[StreamReader, StreamWriter]:
        raise NotImplementedError()    

    async def start(self) -> None:
        if self._writer:
            raise ArcamException("Already started")

        _LOGGER.debug("Connecting to %s", self.peer)
        self._reader, self._writer = await self._open()
        _LOGGER.info("Connected to %s", self.peer)

    async def stop(self) -> None:
        if writer := self._writer:
            try:
                _LOGGER.info("Disconnecting from %s", self.peer)
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            finally:
                self._writer = None
                self._reader = None

class Client(ClientBase):
    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def peer(self) -> str:
        return f"{self.host}:{self.port}"

    async def _open(self) -> tuple[StreamReader, StreamWriter]:
        return await asyncio.open_connection(
            self._host, self._port
        )

class ClientSerial(ClientBase):
    def __init__(self, url: str, baudrate=38400) -> None:
        super().__init__()
        self._url = url
        self._baudrate = baudrate

    @property
    def peer(self) -> str:
        return self._url

    async def _open(self) -> tuple[StreamReader, StreamWriter]:
        return await open_serial_connection(
            self._url, self._baudrate
        )

class ClientContext:
    def __init__(self, client: Client):
        self._client = client
        self._task: asyncio.Task | None = None

    async def __aenter__(self) -> Client:
        await self._client.start()
        self._task = asyncio.create_task(self._client.process())
        return self._client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.stop()
