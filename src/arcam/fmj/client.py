"""Client code"""

import asyncio
from asyncio.streams import StreamReader, StreamWriter
import logging
from datetime import datetime, timedelta
from arcam.fmj.priority_lock import PriorityLock
from contextlib import AsyncExitStack, contextmanager, suppress
from typing import overload
from collections.abc import Callable
from copy import copy
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
    read_response,
    write_packet,
)
from .utils import async_retry

_LOGGER = logging.getLogger(__name__)
_REQUEST_TIMEOUT = timedelta(seconds=3)
_REQUEST_THROTTLE = 0.2

_HEARTBEAT_INTERVAL = timedelta(seconds=5)
_HEARTBEAT_TIMEOUT = _HEARTBEAT_INTERVAL + _HEARTBEAT_INTERVAL


class ClientBase:
    def __init__(self) -> None:
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None
        self._task = None
        self._listen: set[Callable] = set()
        self._request_lock = PriorityLock()
        self._timestamp = datetime.now()

    @contextmanager
    def listen(self, listener: Callable):
        self._listen.add(listener)
        try:
            yield self
        finally:
            self._listen.remove(listener)

    async def _process_heartbeat(self):
        while True:
            delay = self._timestamp + _HEARTBEAT_INTERVAL - datetime.now()
            if delay > timedelta():
                await asyncio.sleep(delay.total_seconds())
            else:
                _LOGGER.debug("Sending ping")
                try:
                    await self.request(1, CommandCodes.POWER, bytes([0xF0]))
                except (ArcamException, TimeoutError):
                    _LOGGER.debug("Heartbeat failed")
                    return
                self._timestamp = datetime.now()

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
                group.create_task(self._process_heartbeat())
                group.create_task(self._process_data(reader))
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
    async def request_raw(self, request: CommandPacket, priority: int = 0) -> ResponsePacket: ...

    @overload
    async def request_raw(self, request: AmxDuetRequest, priority: int = 0) -> AmxDuetResponse: ...

    @async_retry(2, asyncio.TimeoutError)
    async def request_raw(
        self, request: CommandPacket | AmxDuetRequest, priority: int = 0
    ) -> ResponsePacket | AmxDuetResponse:
        if not self._writer:
            raise NotConnectedException()
        writer = self._writer  # keep copy around if stopped by another task
        future: asyncio.Future[ResponsePacket | AmxDuetResponse] = asyncio.Future()

        def listen(response: ResponsePacket | AmxDuetResponse):
            if response.respons_to(request):
                if not (future.cancelled() or future.done()):
                    future.set_result(response)

        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self._request_lock(priority))
            async with asyncio.timeout(_REQUEST_TIMEOUT.total_seconds()):
                with self.listen(listen):
                    _LOGGER.debug("Requesting %s", request)
                    await write_packet(writer, request)
                    self._timestamp = datetime.now()
                    with suppress(TimeoutError):
                        async with asyncio.timeout(_REQUEST_THROTTLE):
                            return await asyncio.shield(future)
                    await stack.aclose()
                    return await future
                    
    async def send(self, zn: int, cc: CommandCodes, data: bytes, priority: int = 0) -> None:
        if not self._writer:
            raise NotConnectedException()

        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        writer = self._writer
        request = CommandPacket(zn, cc, data)
        async with self._request_lock(priority):
            await write_packet(writer, request)
            await asyncio.sleep(_REQUEST_THROTTLE)

    async def request(self, zn: int, cc: CommandCodes, data: bytes, priority: int = 0):
        if not self._writer:
            raise NotConnectedException()

        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        if cc.flags & EnumFlags.SEND_ONLY:
            await self.send(zn, cc, data, priority)
            return

        response = await self.request_raw(CommandPacket(zn, cc, data), priority)

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
