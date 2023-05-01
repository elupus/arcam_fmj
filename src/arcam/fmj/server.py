"""Fake server"""
import logging
from typing import Callable, Dict, List, Optional, Tuple, Union
import anyio
import anyio.abc
import anyio.streams.buffered

from . import (
    AmxDuetRequest,
    AmxDuetResponse,
    AnswerCodes,
    CommandNotRecognised,
    CommandPacket,
    ResponseException,
    ResponsePacket,
    read_command,
    write_packet,
    ConnectionFailed,
)

_LOGGER = logging.getLogger(__name__)


class Server:
    def __init__(self, host: str, port: int, model: str) -> None:
        self._host = host
        self._port = port
        self._handlers: Dict[
            Union[Tuple[int, int], Tuple[int, int, bytes]], Callable
        ] = dict()
        self._amxduet = AmxDuetResponse(
            {
                "Device-SDKClass": "Receiver",
                "Device-Make": "ARCAM",
                "Device-Model": model,
                "Device-Revision": "x.y.z",
            }
        )

    async def process(self, stream: anyio.abc.SocketStream):
        _LOGGER.debug("Client connected")
        try:
            await self.process_runner(stream)
        except ConnectionFailed:
            pass
        finally:
            _LOGGER.debug("Client disconnected")

    async def process_runner(self, stream: anyio.abc.SocketStream):
        reader = anyio.streams.buffered.BufferedByteReceiveStream(stream)
        while True:
            request = await read_command(reader)
            if request is None:
                _LOGGER.debug("Client disconnected")
                return

            responses = await self.process_request(request)
            _LOGGER.debug("Client command %s -> %s", request, responses)
            for response in responses:
                await write_packet(stream, response)

    async def process_request(self, request: Union[CommandPacket, AmxDuetRequest]):
        if isinstance(request, AmxDuetRequest):
            return [self._amxduet]

        handler = self._handlers.get((request.zn, request.cc, request.data))
        if handler is None:
            handler = self._handlers.get((request.zn, request.cc))

        try:
            if handler:
                data = handler(zn=request.zn, cc=request.cc, data=request.data)

                if isinstance(data, bytes):
                    response = [
                        ResponsePacket(
                            request.zn, request.cc, AnswerCodes.STATUS_UPDATE, data
                        )
                    ]
                else:
                    response = data
            else:
                raise CommandNotRecognised()
        except ResponseException as e:
            response = [ResponsePacket(request.zn, request.cc, e.ac, e.data or bytes())]

        return response

    def register_handler(self, zn, cc, data, fun):
        if data:
            self._handlers[(zn, cc, data)] = fun
        else:
            self._handlers[(zn, cc)] = fun

    async def run(
        self, *, task_status: anyio.abc.TaskStatus = anyio.TASK_STATUS_IGNORED
    ):
        _LOGGER.debug("Starting server")
        self._listener = await anyio.create_tcp_listener(
            local_host=self._host, local_port=self._port
        )
        try:
            task_status.started()
            await self._listener.serve(self.process)
        finally:
            _LOGGER.debug("Stopping server")
            await self._listener.aclose()
