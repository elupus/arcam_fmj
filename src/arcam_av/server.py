"""Fake server"""
import asyncio
import logging

from . import _read_command_packet

_LOGGER = logging.getLogger(__name__)

class Server():
    def __init__(self, host: str, port: int) -> None:
        self._server = None
        self._host = host
        self._port = port

    async def process(self, reader, writer):
        _LOGGER.debug("Client connected")
        while True:
            packet = await _read_command_packet(reader)
            if packet is None:
                _LOGGER.debug("Client disconnected")
                return
            
            _LOGGER.debug("Client command %s", packet)

    async def __aenter__(self):
        _LOGGER.debug("Starting server")
        self._server = await asyncio.start_server(
            self.process,
            self._host,
            self._port)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        _LOGGER.debug("Stopping server")
        self._server.close()
        await self._server.wait_closed()
        self._server = None
