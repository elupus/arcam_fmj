"""Client code for Arcam IP control.

Rate limiting design
--------------------
Arcam receivers have a single-threaded IP control processor that can only
handle one command at a time. Sending a second command before the first
response arrives can cause the device to drop commands, return corrupted
responses, or become unresponsive.

This module enforces strict serial command execution:

1. A single ``asyncio.Lock`` (``_request_lock``) ensures only one command
   is in-flight at any time. The lock is held for the **entire**
   request-response cycle — it is NOT released early.

2. After each command completes (response received or timeout), a
   configurable ``command_delay`` pause (default 50 ms) gives the device
   breathing room before the next command. This delay runs while the lock
   is still held, so no other command can sneak in.

3. For fire-and-forget commands (``SEND_ONLY``), the same lock and delay
   apply, but there is no response to wait for.

Callers that need more aggressive pacing (e.g. 300 ms for older models)
can set ``client.command_delay = 0.3`` after construction.
"""

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
from .utils import async_retry

_LOGGER = logging.getLogger(__name__)
_REQUEST_TIMEOUT = timedelta(seconds=3)

# Default inter-command cooldown in seconds. This is the minimum quiet
# period between consecutive commands on the wire. 50 ms is safe for all
# known Arcam/JBL models; increase via ``client.command_delay`` if needed.
_DEFAULT_COMMAND_DELAY = 0.05

_HEARTBEAT_INTERVAL = timedelta(seconds=5)
_HEARTBEAT_TIMEOUT = _HEARTBEAT_INTERVAL + _HEARTBEAT_INTERVAL


class ClientBase:
    def __init__(self) -> None:
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None
        self._task = None
        self._listen: set[Callable] = set()
        self._request_lock = asyncio.Lock()
        self._timestamp = datetime.now()
        self._command_delay: float = _DEFAULT_COMMAND_DELAY

    @property
    def command_delay(self) -> float:
        """Minimum quiet period in seconds between consecutive commands.

        The Arcam IP control interface is single-threaded — it can only
        process one command at a time. This delay is enforced after each
        command completes (response received or timeout) to give the
        device time to settle before the next command.

        Default is 0.05 s (50 ms). The Crestron SDK recommends >= 0.25 s.
        The Unfolded Circle integration uses 0.3–0.4 s for extra safety.
        Adjust based on your device's behavior.
        """
        return self._command_delay

    @command_delay.setter
    def command_delay(self, value: float) -> None:
        self._command_delay = max(0.0, float(value))

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

        _process_heartbeat = asyncio.create_task(self._process_heartbeat())
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
        """Send a command and wait for its response.

        The request lock is held for the entire request-response cycle
        to prevent pipelining commands to the single-threaded receiver.
        After the response arrives (or times out), a ``command_delay``
        pause runs before the lock is released.
        """
        if not self._writer:
            raise NotConnectedException()
        writer = self._writer  # keep copy around if stopped by another task
        future: asyncio.Future[ResponsePacket | AmxDuetResponse] = asyncio.Future()

        def listen(response: ResponsePacket | AmxDuetResponse):
            if response.respons_to(request):
                if not (future.cancelled() or future.done()):
                    future.set_result(response)

        # Hold the lock for the full request-response cycle. This ensures
        # the device never receives a second command while processing the
        # first. The previous implementation released the lock after 200 ms
        # even if no response had arrived, allowing command pipelining that
        # overwhelmed single-threaded receivers.
        async with self._request_lock:
            async with asyncio.timeout(_REQUEST_TIMEOUT.total_seconds()):
                with self.listen(listen):
                    _LOGGER.debug("Requesting %s", request)
                    await write_packet(writer, request)
                    self._timestamp = datetime.now()
                    result = await future
            # Enforce a quiet period after the response before releasing
            # the lock, so the device has time to settle.
            if self._command_delay > 0:
                await asyncio.sleep(self._command_delay)
            return result

    async def send(self, zn: int, cc: CommandCodes, data: bytes) -> None:
        """Send a fire-and-forget command (no response expected).

        Used for RC5 IR simulation and other SEND_ONLY commands. The lock
        is held and command_delay is enforced just like request_raw().
        """
        if not self._writer:
            raise NotConnectedException()

        if not (cc.flags & EnumFlags.ZONE_SUPPORT) and zn != 1:
            raise UnsupportedZone()

        writer = self._writer
        request = CommandPacket(zn, cc, data)
        async with self._request_lock:
            await write_packet(writer, request)
            if self._command_delay > 0:
                await asyncio.sleep(self._command_delay)

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
