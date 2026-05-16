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

_RETRY_INTERVAL = timedelta(milliseconds=500)   # per-attempt fast-retry timeout
_MAX_ATTEMPTS = 2                               # total sends per request
_HEARTBEAT_IDLE = timedelta(seconds=5)          # send POWER ping after this long with empty queue
_RECEIVE_TIMEOUT = _HEARTBEAT_IDLE * 2           # declare connection dead after this long of silence
_SEND_ONLY_DELAY = timedelta(milliseconds=200)  # post-write delay for SEND_ONLY commands
_REMOTE_SETTLE_DELAY = timedelta(milliseconds=5)  # post-receive pause before sending the next queue item (reduce the chance the device is in a state where it drops input)


@dataclass(order=True)
class _QueueItem:
    priority: int                                       # lower = first out
    seq: int                                            # FIFO tiebreaker
    packet: CommandPacket | AmxDuetRequest = field(compare=False)
    future: asyncio.Future[ResponsePacket | AmxDuetResponse | None] = field(compare=False)
    expect_response: bool = field(compare=False, default=True)


class ClientBase:
    def __init__(self) -> None:
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None
        self._listen: set[Callable] = set()
        self._queue: asyncio.PriorityQueue[_QueueItem] = asyncio.PriorityQueue()
        self._seq: int = 0

    @contextmanager
    def listen(self, listener: Callable):
        self._listen.add(listener)
        try:
            yield self
        finally:
            self._listen.remove(listener)

    async def _process_receive(self, reader: StreamReader) -> None:
        while True:
            try:
                async with asyncio.timeout(_RECEIVE_TIMEOUT.total_seconds()):
                    packet = await read_response(reader)
            except TimeoutError as exception:
                _LOGGER.debug("No data received within timeout")
                raise ConnectionFailed(
                    "No data received within timeout"
                ) from exception
            if packet is None:
                _LOGGER.debug("Server disconnected")
                raise ConnectionFailed("Server disconnected")
            _LOGGER.debug("Packet received: %s", packet)
            for listener in self._listen:
                listener(packet)

    async def _process_send(self, writer: StreamWriter) -> None:
        while True:
            try:
                async with asyncio.timeout(_HEARTBEAT_IDLE.total_seconds()):
                    item = await self._queue.get()
            except TimeoutError:
                _LOGGER.debug("Sending heartbeat ping")
                await self._send_heartbeat(writer)
                continue
            await self._send_command(writer, item)

    async def _send_heartbeat(self, writer: StreamWriter) -> None:
        packet = CommandPacket(1, CommandCodes.POWER, bytes([0xF0]))
        try:
            await self._send_request(writer, packet)
        except TimeoutError:
            # Receive-side liveness check is the real disconnect detector. We don't want to tear things down for this if other traffic is making it through.
            _LOGGER.debug("Heartbeat timed out")

    async def _send_command(
        self, writer: StreamWriter, item: _QueueItem,
    ) -> None:
        if not item.expect_response:
            try:
                await write_packet(writer, item.packet)
                await asyncio.sleep(_SEND_ONLY_DELAY.total_seconds())
            except BaseException as e:
                if not item.future.done():
                    item.future.set_exception(e)
                raise
            if not item.future.done():
                item.future.set_result(None)
            return

        try:
            response = await self._send_request(writer, item.packet)
        except TimeoutError as e:
            if not item.future.done():
                item.future.set_exception(e)
            return
        except BaseException as e:
            if not item.future.done():
                item.future.set_exception(e)
            raise
        if not item.future.done():
            item.future.set_result(response)

    @async_retry(_MAX_ATTEMPTS, TimeoutError)
    async def _send_request(
        self,
        writer: StreamWriter,
        packet: CommandPacket | AmxDuetRequest,
    ) -> ResponsePacket | AmxDuetResponse:
        future_response: asyncio.Future = asyncio.get_running_loop().create_future()

        def listen(response):
            if response.response_to(packet) and not future_response.done():
                future_response.set_result(response)

        with self.listen(listen):
            _LOGGER.debug("Sending %s", packet)
            await write_packet(writer, packet)
            response = await asyncio.wait_for(
                future_response,
                timeout=_RETRY_INTERVAL.total_seconds(),
            )
        await asyncio.sleep(_REMOTE_SETTLE_DELAY.total_seconds())
        return response

    async def process(self) -> None:
        assert self._writer, "Writer missing"
        assert self._reader, "Reader missing"

        reader = self._reader
        writer = self._writer

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(self._process_send(writer))
                group.create_task(self._process_receive(reader))
        except BaseExceptionGroup as exc:
            # convert to a non group exception to keep compatibility
            raise copy(exc.exceptions[0]).with_traceback(
                exc.exceptions[0].__traceback__
            )
        finally:
            while True:
                try:
                    item = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not item.future.done():
                    item.future.set_exception(
                        NotConnectedException("Connection closed")
                    )
            _LOGGER.debug("Process task shutting down")
            writer.close()

    @property
    def connected(self) -> bool:
        return self._reader is not None and not self._reader.at_eof()

    @property
    def started(self) -> bool:
        return self._writer is not None

    def _enqueue(
        self,
        packet: CommandPacket | AmxDuetRequest,
        priority: int,
        expect_response: bool,
    ) -> asyncio.Future:
        future = asyncio.get_running_loop().create_future()
        self._seq += 1
        self._queue.put_nowait(_QueueItem(
            priority, self._seq, packet, future, expect_response,
        ))
        return future

    @overload
    async def request_raw(self, request: CommandPacket, priority: int = 0) -> ResponsePacket: ...

    @overload
    async def request_raw(self, request: AmxDuetRequest, priority: int = 0) -> AmxDuetResponse: ...

    async def request_raw(
        self, request: CommandPacket | AmxDuetRequest, priority: int = 0
    ) -> ResponsePacket | AmxDuetResponse:
        if not self._writer:
            raise NotConnectedException()
        return await self._enqueue(request, priority, expect_response=True)

    async def send(
        self, zn: int, cc: CommandCodes, data: bytes, priority: int = 0,
    ) -> None:
        if not self._writer:
            raise NotConnectedException()
        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()
        await self._enqueue(
            CommandPacket(zn, cc, data), priority, expect_response=False,
        )

    async def request(
        self, zn: int, cc: CommandCodes, data: bytes, priority: int = 0,
    ):
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
