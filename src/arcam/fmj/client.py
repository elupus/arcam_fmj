"""Client code"""

import asyncio
from asyncio.streams import StreamReader
import logging
from datetime import datetime, timedelta
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
        self._task = None
        self._write_task: asyncio.Task | None = None
        self._listen: set[Callable] = set()
        self._timestamp = datetime.now()
        self._write_queue: asyncio.PriorityQueue[
            tuple[int, int, CommandPacket | AmxDuetRequest, asyncio.Future | None]
        ] = asyncio.PriorityQueue()
        self._write_seq = 0

    @contextmanager
    def listen(self, listener: Callable):
        self._listen.add(listener)
        try:
            yield self
        finally:
            self._listen.remove(listener)

    async def _process_write_queue(self, writer):
        try:
            while True:
                _priority, _seq, request, result = await self._write_queue.get()

                if result is None:
                    _LOGGER.debug("Sending %s", request)
                    await write_packet(writer, request)
                    self._timestamp = datetime.now()
                    await asyncio.sleep(_REQUEST_THROTTLE)
                    continue

                if result.cancelled():
                    continue

                def listen(packet: ResponsePacket | AmxDuetResponse):
                    if packet.respons_to(request):
                        if not (result.cancelled() or result.done()):
                            result.set_result(packet)

                try:
                    async with asyncio.timeout(_REQUEST_TIMEOUT.total_seconds()):
                        with self.listen(listen):
                            _LOGGER.debug("Requesting %s", request)
                            await write_packet(writer, request)
                            self._timestamp = datetime.now()
                            await asyncio.shield(result)
                except Exception as exc:
                    if not result.done():
                        result.set_exception(exc)
        finally:
            writer.close()

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
        assert self._reader, "Reader missing"

        _process_heartbeat = asyncio.create_task(self._process_heartbeat())
        try:
            await self._process_data(self._reader)
        finally:
            _process_heartbeat.cancel()
            try:
                await _process_heartbeat
            except asyncio.CancelledError:
                pass

    @property
    def connected(self) -> bool:
        return self._reader is not None and not self._reader.at_eof()

    @property
    def started(self) -> bool:
        return self._write_task is not None

    @overload
    async def request_raw(self, request: CommandPacket, priority: int = 0) -> ResponsePacket: ...

    @overload
    async def request_raw(self, request: AmxDuetRequest, priority: int = 0) -> AmxDuetResponse: ...

    @async_retry(2, asyncio.TimeoutError)
    async def request_raw(
        self, request: CommandPacket | AmxDuetRequest, priority: int = 0
    ) -> ResponsePacket | AmxDuetResponse:
        future: asyncio.Future[ResponsePacket | AmxDuetResponse] = asyncio.Future()
        self._write_seq += 1
        self._write_queue.put_nowait((priority, self._write_seq, request, future))
        return await future

    async def send(self, zn: int, cc: CommandCodes, data: bytes, priority: int = 0) -> None:
        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        self._write_seq += 1
        self._write_queue.put_nowait((priority, self._write_seq, CommandPacket(zn, cc, data), None))

    async def request(self, zn: int, cc: CommandCodes, data: bytes, priority: int = 0):
        if not self._write_task:
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
        if self._write_task:
            raise ArcamException("Already started")

        _LOGGER.debug("Connecting to %s:%d", self._host, self._port)
        try:
            self._reader, writer = await asyncio.open_connection(
                self._host, self._port
            )
        except ConnectionError as exception:
            raise ConnectionFailed() from exception
        except OSError as exception:
            raise ConnectionFailed() from exception
        _LOGGER.info("Connected to %s:%d", self._host, self._port)
        self._write_task = asyncio.create_task(self._process_write_queue(writer))

    async def stop(self) -> None:
        if self._write_task:
            self._write_task.cancel()
            try:
                await self._write_task
            except asyncio.CancelledError:
                pass
            self._write_task = None
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
