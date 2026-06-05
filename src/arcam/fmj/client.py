"""Client code"""

import asyncio
from asyncio.streams import StreamReader, StreamWriter
import logging
from collections.abc import Callable
from contextlib import contextmanager
from copy import copy
from dataclasses import dataclass, field
from datetime import timedelta
from typing import overload

from serialx import open_serial_connection

from .codecs import AnswerCodes
from .commands import CommandCodes, CommandFlags
from .errors import (
    ArcamException,
    ConnectionFailed,
    NotConnectedException,
    ResponseException,
    UnsupportedZone,
)
from .packets import (
    AmxDuetRequest,
    AmxDuetResponse,
    CommandPacket,
    ResponsePacket,
    read_response,
    write_packet,
)
from .utils import async_retry

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = timedelta(milliseconds=500)
_REQUEST_RETRY_COUNT = 2
_REQUEST_SETTLE_TIME = timedelta(milliseconds=5)

_HEARTBEAT_INTERVAL = timedelta(seconds=5)
_HEARTBEAT_TIMEOUT = _HEARTBEAT_INTERVAL + _HEARTBEAT_INTERVAL

_USER_PRIORITY = 0
_HEARTBEAT_PRIORITY = 100


@dataclass(order=True)
class _QueueItem:
    priority: int
    seq: int
    packet: CommandPacket | AmxDuetRequest = field(compare=False)
    future: asyncio.Future[ResponsePacket | AmxDuetResponse] = field(compare=False)


class ClientBase:
    def __init__(self) -> None:
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None
        self._listen: set[Callable] = set()
        self._queue: asyncio.PriorityQueue[_QueueItem] | None = None
        self._seq: int = 0

    @property
    def peer(self) -> str:
        raise NotImplementedError()

    async def _open(self) -> tuple[StreamReader, StreamWriter]:
        raise NotImplementedError()

    @property
    def connected(self) -> bool:
        return self._reader is not None and not self._reader.at_eof()

    @property
    def started(self) -> bool:
        return self._writer is not None

    @contextmanager
    def listen(self, listener: Callable):
        self._listen.add(listener)
        try:
            yield self
        finally:
            self._listen.remove(listener)

    async def start(self) -> None:
        if self._writer:
            raise ArcamException("Already started")

        _LOGGER.debug("Connecting to %s", self.peer)
        self._reader, self._writer = await self._open()
        self._queue = asyncio.PriorityQueue()
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
                self._queue = None

    @overload
    async def request_raw(self, request: CommandPacket, priority: int = _USER_PRIORITY) -> ResponsePacket: ...

    @overload
    async def request_raw(self, request: AmxDuetRequest, priority: int = _USER_PRIORITY) -> AmxDuetResponse: ...

    async def request_raw(
        self, request: CommandPacket | AmxDuetRequest, priority: int = _USER_PRIORITY
    ) -> ResponsePacket | AmxDuetResponse:
        if self._queue is None:
            raise NotConnectedException()
        future: asyncio.Future[ResponsePacket | AmxDuetResponse] = asyncio.get_running_loop().create_future()
        self._seq += 1
        self._queue.put_nowait(_QueueItem(priority, self._seq, request, future))
        return await future

    async def request(self, zn: int, cc: CommandCodes, data: bytes, priority: int = _USER_PRIORITY):
        if self._queue is None:
            raise NotConnectedException()

        if not (cc.flags & CommandFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        response = await self.request_raw(CommandPacket(zn, cc, data), priority)

        if response.ac == AnswerCodes.STATUS_UPDATE:
            return response.data

        raise ResponseException.from_response(response)

    async def _process_receive(self, reader: StreamReader):
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

    @async_retry(_REQUEST_RETRY_COUNT, TimeoutError)
    async def _write_and_wait(
        self,
        writer: StreamWriter,
        packet: CommandPacket | AmxDuetRequest,
    ) -> ResponsePacket | AmxDuetResponse:
        future: asyncio.Future[ResponsePacket | AmxDuetResponse] = (
            asyncio.get_running_loop().create_future()
        )

        def listen(response):
            if response.response_to(packet) and not future.done():
                future.set_result(response)

        _LOGGER.debug("Sending %s", packet)
        with self.listen(listen):
            await write_packet(writer, packet)
            async with asyncio.timeout(_REQUEST_TIMEOUT.total_seconds()):
                return await future

    async def _process_send(self, writer: StreamWriter):
        try:
            while True:
                item = await self._queue.get()
                try:
                    try:
                        response = await self._write_and_wait(writer, item.packet)
                    except TimeoutError as e:
                        if not item.future.done():
                            item.future.set_exception(e)
                        continue
                    if not item.future.done():
                        item.future.set_result(response)
                finally:
                    if not item.future.done():
                        item.future.set_exception(
                            NotConnectedException("Send aborted")
                        )
                await asyncio.sleep(_REQUEST_SETTLE_TIME.total_seconds())
        finally:
            # Clear this to prevent more commands from being queued
            queue = self._queue
            self._queue = None
            # Drain what's already in the queue to unblock all waiters
            while not queue.empty():
                pending = queue.get_nowait()
                if not pending.future.done():
                    pending.future.set_exception(
                        NotConnectedException("Connection closed")
                    )

    async def _process_heartbeat(self):
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL.total_seconds())
            _LOGGER.debug("Sending heartbeat ping")
            try:
                await self.request(1, CommandCodes.POWER, bytes([0xF0]), _HEARTBEAT_PRIORITY)
            except (ArcamException, TimeoutError):
                _LOGGER.debug("Heartbeat ping timed out")

    async def process(self) -> None:
        assert self._writer, "Writer missing"
        assert self._reader, "Reader missing"

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(self._process_receive(self._reader))
                group.create_task(self._process_send(self._writer))
                group.create_task(self._process_heartbeat())
        except BaseExceptionGroup as exc:
            # convert to a non group exception to keep compatibility
            raise copy(exc.exceptions[0]).with_traceback(exc.exceptions[0].__traceback__)
        finally:
            _LOGGER.debug("Process task shutting down")
            self._writer.close()

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
