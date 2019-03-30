"""Fake server"""
import asyncio
import logging

from . import AnswerCodes, ResponsePacket, _read_command_packet, _write_packet, CommandNotRecognised, ResponseException

_LOGGER = logging.getLogger(__name__)

class Server():
    def __init__(self, host: str, port: int) -> None:
        self._server = None
        self._host = host
        self._port = port
        self._handlers = dict()

    async def process(self, reader, writer):
        _LOGGER.debug("Client connected")
        while True:
            request = await _read_command_packet(reader)
            if request is None:
                _LOGGER.debug("Client disconnected")
                return
            
            response = await self.process_request(request)
            _LOGGER.debug("Client command %s -> %s", request, response)
            await _write_packet(writer, response)

    async def process_request(self, request):
            handler = self._handlers.get((request.zn, request.cc, request.data))
            if handler is None:
                handler = self._handlers.get((request.zn, request.cc))

            try:
                if handler:
                    ac, data = handler(
                        zn=request.zn,
                        cc=request.cc,
                        data=request.data)

                    response = ResponsePacket(
                        request.zn,
                        request.cc,
                        ac,
                        data)
                else:
                    raise CommandNotRecognised()
            except ResponseException as e:
                response = ResponsePacket(
                    request.zn,
                    request.cc,
                    e.ac,
                    e.data or bytes(),
                )

            return response

    def register_handler(self, zn, cc, data, fun):
        if data:
            self._handlers[(zn, cc, data)] = fun
        else:
            self._handlers[(zn, cc)] = fun

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
