"""Client code"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta

from . import (
    AnswerCodes,
    CommandCodes,
    CommandPacket,
    ResponseException,
    ResponsePacket,
    _read_packet,
    _write_packet
)
from .utils import Throttle, async_retry

_LOGGER = logging.getLogger(__name__)
_REQUEST_TIMEOUT = 3
_REQUEST_THROTTLE = 0.2


class Client:
    def __init__(self, host, port, loop=None) -> None:
        self._reader = None
        self._writer = None
        self._loop = loop if loop else asyncio.get_event_loop()
        self._task = None
        self._listen = set()
        self._host = host
        self._port = port
        self._lock = asyncio.Semaphore(2)  # limit to one outstanding request
        self._throttle = Throttle(_REQUEST_THROTTLE)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def _process(self):
        while True:
            try:
                packet = await _read_packet(self._reader)
                if packet is None:
                    _LOGGER.debug("Server disconnected")
                    return

                _LOGGER.debug("Packet received: %s", packet)
                for l in self._listen:
                    l(packet)
            except asyncio.CancelledError:
                raise
            except:
                _LOGGER.error("Error occured during packet processing", exc_info=1)
                raise
    @property
    def connected(self):
        return self._task is not None and not self._task.done()

    @property
    def started(self):
        return self._task is not None

    async def start(self):
        _LOGGER.debug("Starting client")
        if self._task:
            raise Exception("Already started")

        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port, loop=self._loop)

        self._task = asyncio.ensure_future(
            self._process(), loop=self._loop)

    async def stop(self):
        _LOGGER.debug("Stopping client")
        if self._task:
            self._task.cancel()
            asyncio.wait(self._task)
        self._writer.close()
        if (sys.version_info >= (3, 7)):
            await self._writer.wait_closed()

        self._writer = None
        self._reader = None

    @async_retry(2, asyncio.TimeoutError)
    async def _request(self, request: CommandPacket):
        result = None
        event  = asyncio.Event()

        def listen(response: ResponsePacket):
            if (response.zn == request.zn and 
                response.cc == request.cc):
                nonlocal result
                result = response
                event.set()

        await self._throttle.get()

        async with self._lock:
            _LOGGER.debug("Requesting %s", request)
            self._listen.add(listen)
            try:
                await _write_packet(self._writer, request)
                await asyncio.wait_for(event.wait(), _REQUEST_TIMEOUT)
            finally:
                self._listen.remove(listen)
        return result

    async def request(self, zn, cc, data):
        response = await self._request(CommandPacket(zn, cc, data))

        if response.ac == AnswerCodes.STATUS_UPDATE:
            return response.data

        raise ResponseException.from_response(response)
