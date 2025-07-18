"""Client code"""

import asyncio
from asyncio.streams import StreamReader, StreamWriter
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Union, overload
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
    read_response,
    write_packet,
)
from .utils import Throttle, async_retry

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
        self._throttle = Throttle(_REQUEST_THROTTLE)
        self._timestamp = datetime.now()

    @contextmanager
    def listen(self, listener: Callable):
        self._listen.add(listener)
        yield self
        self._listen.remove(listener)

    async def _process_heartbeat(self, writer: StreamWriter):
        while True:
            delay = self._timestamp + _HEARTBEAT_INTERVAL - datetime.now()
            if delay > timedelta():
                await asyncio.sleep(delay.total_seconds())
            else:
                _LOGGER.debug("Sending ping")
                await write_packet(
                    writer, CommandPacket(1, CommandCodes.POWER, bytes([0xF0]))
                )
                self._timestamp = datetime.now()

    async def _process_data(self, reader: StreamReader):
        try:
            while True:
                try:
                    async with asyncio.timeout(_HEARTBEAT_TIMEOUT.total_seconds()):
                        packet = await read_response(reader)
                except TimeoutError as exception:
                    _LOGGER.debug("Missed all pings")
                    raise ConnectionFailed() from exception

                if packet is None:
                    _LOGGER.info("Server disconnected")
                    return

                _LOGGER.debug("Packet received: %s", packet)
                for listener in self._listen:
                    listener(packet)
        finally:
            self._reader = None

    async def process(self) -> None:
        assert self._writer, "Writer missing"
        assert self._reader, "Reader missing"

        _process_heartbeat = asyncio.create_task(self._process_heartbeat(self._writer))
        try:
            await self._process_data(self._reader)
        finally:
            _process_heartbeat.cancel()
            try:
                await _process_heartbeat
            except asyncio.CancelledError:
                pass
            self._writer.close()

    @property
    def connected(self) -> bool:
        return self._reader is not None and not self._reader.at_eof()

    @property
    def started(self) -> bool:
        return self._writer is not None

    @overload
    async def request_raw(self, request: CommandPacket) -> ResponsePacket: ...

    @overload
    async def request_raw(self, request: AmxDuetRequest) -> AmxDuetResponse: ...

    @async_retry(2, asyncio.TimeoutError)
    async def request_raw(
        self, request: CommandPacket | AmxDuetRequest
    ) -> ResponsePacket | AmxDuetResponse:
        if not self._writer:
            raise NotConnectedException()
        writer = self._writer  # keep copy around if stopped by another task
        future: asyncio.Future[ResponsePacket | AmxDuetResponse] = asyncio.Future()

        def listen(response: ResponsePacket | AmxDuetResponse):
            if response.respons_to(request):
                if not (future.cancelled() or future.done()):
                    future.set_result(response)

        await self._throttle.get()

        async with asyncio.timeout(_REQUEST_TIMEOUT.total_seconds()):
            _LOGGER.debug("Requesting %s", request)
            with self.listen(listen):
                await write_packet(writer, request)
                self._timestamp = datetime.now()
                return await future

    async def send(self, zn: int, cc: CommandCodes, data: bytes) -> None:
        if not self._writer:
            raise NotConnectedException()

        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        writer = self._writer
        request = CommandPacket(zn, cc, data)
        await self._throttle.get()
        await write_packet(writer, request)

    async def request(self, zn: int, cc: CommandCodes, data: bytes):
        if not self._writer:
            raise NotConnectedException()

        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        if cc.flags & EnumFlags.SEND_ONLY:
            await self.send(zn, cc, data)
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
