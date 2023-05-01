"""Client code"""
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Callable, Optional, Set, Union, overload
import anyio
import anyio.abc
import anyio.streams.buffered

from . import (
    AmxDuetRequest,
    AmxDuetResponse,
    AnswerCodes,
    ArcamException,
    CommandCodes,
    CommandPacket,
    ConnectionFailed,
    NotConnectedException,
    ResponseException,
    ResponsePacket,
    read_response,
    write_packet,
)
from .utils import Throttle, async_retry

_LOGGER = logging.getLogger(__name__)
_REQUEST_TIMEOUT = timedelta(seconds=3)
_REQUEST_THROTTLE = 0.2

_HEARTBEAT_INTERVAL = timedelta(seconds=5)
_HEARTBEAT_TIMEOUT = _HEARTBEAT_INTERVAL + _HEARTBEAT_INTERVAL


class Client:
    def __init__(self, host: str, port: int) -> None:
        self._stream: Optional[anyio.abc.SocketStream] = None
        self._reader: Optional[anyio.streams.buffered.BufferedByteReceiveStream] = None
        self._task = None
        self._listen: Set[Callable] = set()
        self._host = host
        self._port = port
        self._throttle = Throttle(_REQUEST_THROTTLE)
        self._timestamp = datetime.now()
        self._lock = anyio.Lock()

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @contextmanager
    def listen(self, listener: Callable):
        self._listen.add(listener)
        yield self
        self._listen.remove(listener)

    async def _process_heartbeat(self):
        while True:
            delay = self._timestamp + _HEARTBEAT_INTERVAL - datetime.now()
            if delay > timedelta():
                await anyio.sleep(delay.total_seconds())
            else:
                _LOGGER.debug("Sending ping")
                async with self._lock:
                    await write_packet(
                        self._stream,
                        CommandPacket(1, CommandCodes.POWER, bytes([0xF0])),
                    )
                    self._timestamp = datetime.now()

    async def _process_data(self):
        while True:
            try:
                with anyio.fail_after(_HEARTBEAT_TIMEOUT.total_seconds()):
                    packet = await read_response(self._reader)
            except TimeoutError as exception:
                _LOGGER.warning("Missed all pings")
                raise ConnectionFailed("Missed all pings") from exception

            if packet is None:
                _LOGGER.info("Server disconnected")
                return

            _LOGGER.debug("Packet received: %s", packet)
            for listener in self._listen:
                listener(packet)

    async def process(self) -> None:
        assert self._stream, "Stream missing"

        async with anyio.create_task_group() as tg:
            tg.start_soon(self._process_heartbeat, name="Hearbeat")
            tg.start_soon(self._process_data, name="Reader")

    @property
    def connected(self) -> bool:
        return self._stream is not None

    @property
    def started(self) -> bool:
        return self._stream is not None

    async def start(self) -> None:
        if self._stream:
            raise ArcamException("Already started")

        _LOGGER.debug("Connecting to %s:%d", self._host, self._port)
        try:
            self._stream = await anyio.connect_tcp(self._host, self._port)
            self._reader = anyio.streams.buffered.BufferedByteReceiveStream(
                self._stream
            )
        except OSError as exception:
            raise ConnectionFailed(
                f"Unable to connect to server ({str(exception)})"
            ) from exception
        _LOGGER.info("Connected to %s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._stream:
            try:
                _LOGGER.info("Disconnecting from %s:%d", self._host, self._port)
                await self._stream.aclose()
            except OSError:
                pass
            finally:
                self._stream = None
                self._reader = None

    async def run(
        self, *, task_status: anyio.abc.TaskStatus = anyio.TASK_STATUS_IGNORED
    ):
        await self.start()
        try:
            task_status.started()
            await self.process()
        finally:
            await self.stop()

    @overload
    async def request_raw(self, request: CommandPacket) -> ResponsePacket:
        ...

    @overload
    async def request_raw(self, request: AmxDuetRequest) -> AmxDuetResponse:
        ...

    @async_retry(2, TimeoutError)
    async def request_raw(
        self, request: Union[CommandPacket, AmxDuetRequest]
    ) -> Union[ResponsePacket, AmxDuetResponse]:
        if not self._stream:
            raise NotConnectedException()
        stream = self._stream  # keep copy around if stopped by another task
        result: Union[ResponsePacket, AmxDuetResponse, None] = None
        event = anyio.Event()

        def listen(response: Union[ResponsePacket, AmxDuetResponse]):
            if response.respons_to(request):
                nonlocal result
                result = response
                event.set()

        await self._throttle.get()

        with anyio.fail_after(_REQUEST_TIMEOUT.total_seconds()):
            _LOGGER.debug("Requesting %s", request)
            with self.listen(listen):
                async with self._lock:
                    await write_packet(stream, request)
                    self._timestamp = datetime.now()
                await event.wait()
                assert result
                return result

    async def send(self, zn: int, cc: int, data: bytes) -> None:
        if not self._stream:
            raise NotConnectedException()
        stream = self._stream
        request = CommandPacket(zn, cc, data)
        async with self._lock:
            await self._throttle.get()
            await write_packet(stream, request)

    async def request(self, zn: int, cc: int, data: bytes) -> bytes:
        response = await self.request_raw(CommandPacket(zn, cc, data))

        if response.ac == AnswerCodes.STATUS_UPDATE:
            return response.data

        raise ResponseException.from_response(response)


class ClientContext:
    def __init__(self, client: Client):
        self._client = client
        self._group = anyio.create_task_group()

    async def __aenter__(self) -> Client:
        await self._group.__aenter__()
        self._group.start_soon(self._client.run)
        return self._client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._group.cancel_scope.cancel()
        await self._group.__aexit__(exc_type, exc_val, exc_tb)
