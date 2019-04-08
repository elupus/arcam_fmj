"""Client code"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from contextlib import contextmanager
from aionursery import Nursery

from . import (
    AnswerCodes,
    CommandCodes,
    CommandPacket,
    ConnectionFailed,
    NotConnectedException,
    ResponseException,
    ResponsePacket,
    _read_packet,
    _write_packet
)
from .utils import Throttle, async_retry

_LOGGER = logging.getLogger(__name__)
_REQUEST_TIMEOUT = timedelta(seconds=3)
_REQUEST_THROTTLE = 0.2

_HEARTBEAT_INTERVAL = timedelta(seconds=5)
_HEARTBEAT_TIMEOUT  = _HEARTBEAT_INTERVAL + _HEARTBEAT_INTERVAL

class Client:
    def __init__(self, host, port, loop=None) -> None:
        self._reader = None
        self._writer = None
        self._loop = loop if loop else asyncio.get_event_loop()
        self._task = None
        self._listen = set()
        self._host = host
        self._port = port
        self._throttle = Throttle(_REQUEST_THROTTLE)
        self._timestamp = datetime.now()

    @property
    def host(self):
        return self._host

    @property
    def port(self):
        return self._port

    @property
    def loop(self):
        return self._loop

    @contextmanager
    def listen(self, listener):
        self._listen.add(listener)
        yield self
        self._listen.remove(listener)

    async def _process_heartbeat(self):
        while True:
            delay = self._timestamp + _HEARTBEAT_INTERVAL - datetime.now()
            if delay > timedelta():
                await asyncio.sleep(delay.total_seconds())
            else:
                _LOGGER.info("Sending ping")
                await _write_packet(
                    self._writer,
                    CommandPacket(1, CommandCodes.POWER, bytes([0xF0]))
                )
                self._timestamp = datetime.now()

    async def _process_data(self):
        try:
            while True:
                if not self._reader:
                    raise NotConnectedException()

                try:
                    packet = await asyncio.wait_for(
                        _read_packet(self._reader),
                        _HEARTBEAT_TIMEOUT.total_seconds()
                    )
                except asyncio.TimeoutError as exception:
                    _LOGGER.warning("Missed all pings")
                    raise ConnectionFailed() from exception

                if packet is None:
                    _LOGGER.debug("Server disconnected")
                    return

                _LOGGER.debug("Packet received: %s", packet)
                for listener in self._listen:
                    listener(packet)
        finally:
            self._reader = None

    async def process(self):
        async with Nursery() as nursery:
            nursery.start_soon(self._process_data())
            nursery.start_soon(self._process_heartbeat())

    @property
    def connected(self):
        return self._reader is not None and not self._reader.at_eof()

    @property
    def started(self):
        return self._writer is not None

    async def start(self):
        if self._writer:
            raise Exception("Already started")

        _LOGGER.debug("Starting client to %s:%d", self._host, self._port)
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self._host, self._port, loop=self._loop)
        except ConnectionError as exception:
            raise ConnectionFailed() from exception
        except OSError as exception:
            raise ConnectionFailed() from exception

    async def stop(self):
        if self._writer:
            try:
                _LOGGER.debug("Stopping client")
                self._writer.close()
                if sys.version_info >= (3, 7):
                    await self._writer.wait_closed()
                self._writer = None
                self._reader = None
            except ConnectionError as exception:
                raise ConnectionFailed() from exception
            except OSError as exception:
                raise ConnectionFailed() from exception

    @async_retry(2, asyncio.TimeoutError)
    async def _request(self, request: CommandPacket):
        if not self._writer:
            raise NotConnectedException()

        result = None
        event = asyncio.Event()

        def listen(response: ResponsePacket):
            if (response.zn == request.zn and
                    response.cc == request.cc):
                nonlocal result
                result = response
                event.set()

        await self._throttle.get()

        _LOGGER.debug("Requesting %s", request)
        with self.listen(listen):
            await _write_packet(self._writer, request)
            self._timestamp = datetime.now()
            await asyncio.wait_for(event.wait(), _REQUEST_TIMEOUT.total_seconds())

        return result

    async def request(self, zn, cc, data):
        response = await self._request(CommandPacket(zn, cc, data))

        if response.ac == AnswerCodes.STATUS_UPDATE:
            return response.data

        raise ResponseException.from_response(response)

class ClientContext:
    def __init__(self, client: Client):
        self._client = client
        self._task = None

    async def __aenter__(self):
        await self._client.start()
        self._task = asyncio.ensure_future(
            self._client.process(),
            loop=self._client.loop
        )
        return self._client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.stop()
