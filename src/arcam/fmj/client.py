"""Client code"""

import asyncio
from asyncio.streams import StreamReader, StreamWriter
import logging
from datetime import timedelta
from contextlib import contextmanager
from typing import overload
from collections.abc import Callable

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

class ClientBase:
    def __init__(self) -> None:
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None
        self._listen: set[Callable] = {self._process_request_pending}
        self._request_queue = asyncio.PriorityQueue[tuple[int, int, asyncio.Future[GenericResponse], GenericRequest]]()
        self._request_pending: dict[asyncio.Future[GenericResponse], GenericRequest] = {}
        self._request_count = 0

    @contextmanager
    def listen(self, listener: Callable):
        self._listen.add(listener)
        try:
            yield self
        finally:
            self._listen.remove(listener)

    def _process_request_pending(self, response: GenericResponse):
        for future, request in self._request_pending.items():
            if future.done():
                continue
            if response.respons_to(request):
                future.set_result(response)

    async def _process_request_single(self, writer: StreamWriter):
        """Process a single request from queue queue."""

        try:
            async with asyncio.timeout(_HEARTBEAT_INTERVAL.total_seconds()):
                while True:
                    _, _, future, request = await self._request_queue.get()
                    if not future.done():
                        break
        except TimeoutError:
            _LOGGER.debug("Sending ping")
            request = CommandPacket(1, CommandCodes.POWER, bytes([0xF0]))
            await write_packet(writer, request)
            return

        self._request_pending[future] = request
        future.add_done_callback(self._request_pending.pop)

        await write_packet(writer, request)
        _schedule_timeout(future, "Request timed out")

    async def _process_request(self, writer: StreamWriter):
        """Process the request queue."""
        try:
            while True:
                await self._process_request_single(writer)
                await asyncio.sleep(_REQUEST_THROTTLE)
        finally:
            self._request_queue_close(NotConnectedException("Connected was closed"))

    async def _process_data(self, reader: StreamReader):
        try:
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
        finally:
            self._reader = None

    async def process(self) -> None:
        assert self._writer, "Writer missing"
        assert self._reader, "Reader missing"

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(self._process_data(self._reader))
                group.create_task(self._process_request(self._writer))
        finally:
            _LOGGER.debug("Process task shutting down")
            self._writer.close()
            self._request_queue_close(NotConnectedException("Connected was closed"))

    @property
    def connected(self) -> bool:
        return self._reader is not None and not self._reader.at_eof()

    @property
    def started(self) -> bool:
        return self._writer is not None

    def _request_queue_close(self, exception: Exception) -> None:
        """Shut down all pending and queued requests."""
        for future in self._request_pending:
            future.set_exception(exception)

        while not self._request_queue.empty():
            _, _, future, _ = self._request_queue.get_nowait()
            future.set_exception(exception)

    def _request_queue_add(self, priority: int, future: asyncio.Future[GenericResponse], request: GenericRequest) -> None:
        """Adds a request in priority order to the queue."""
        if not self._writer:
            raise NotConnectedException()

        self._request_count = self._request_count + 1
        self._request_queue.put_nowait((priority, self._request_count, future, request))

    @overload
    async def request_raw(self, request: CommandPacket, *, priority: int = 0) -> ResponsePacket: ...

    @overload
    async def request_raw(self, request: AmxDuetRequest, *, priority: int = 0) -> AmxDuetResponse: ...

    @async_retry(2, asyncio.TimeoutError)
    async def request_raw(self, request: GenericRequest, *, priority: int = 0) -> GenericResponse:
        future = asyncio.Future[GenericResponse]()
        try:
            self._request_queue_add(priority, future, request)
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

    async def start(self) -> None:
        if self._writer:
            raise ArcamException("Already started")

        _LOGGER.debug("Connecting to %s:%d", self._host, self._port)
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self._host, self._port
            )
        except ConnectionError as exception:
            raise ConnectionFailed() from exception
        except OSError as exception:
            raise ConnectionFailed() from exception
        _LOGGER.info("Connected to %s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._writer:
            try:
                _LOGGER.info("Disconnecting from %s:%d", self._host, self._port)
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            finally:
                self._writer = None
                self._reader = None


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
