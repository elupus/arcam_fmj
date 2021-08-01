"""Fake server"""
import asyncio
import logging
from typing import Callable, Dict, List, Optional, Tuple, Union

from . import (
    AmxDuetRequest,
    AmxDuetResponse,
    AnswerCodes,
    CommandNotRecognised,
    CommandPacket,
    ResponseException,
    ResponsePacket,
    read_command,
    write_packet
)

_LOGGER = logging.getLogger(__name__)

class Server():
    def __init__(self, host: str, port: int, model: str) -> None:
        self._server: Optional[asyncio.AbstractServer] = None
        self._host = host
        self._port = port
        self._handlers: Dict[Union[Tuple[int, int], Tuple[int, int, bytes]], Callable] = dict()
        self._tasks: List[asyncio.Task] = list()
        self._amxduet = AmxDuetResponse({
            "Device-SDKClass": "Receiver",
            "Device-Make": "ARCAM",
            "Device-Model": model,
            "Device-Revision": "x.y.z"
        })

    async def process(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        _LOGGER.debug("Client connected")
        task = asyncio.current_task()
        assert task
        self._tasks.append(task)
        try:
            await self.process_runner(reader, writer)
        finally:
            _LOGGER.debug("Client disconnected")
            self._tasks.remove(task)

    async def process_runner(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while True:
            request = await read_command(reader)
            if request is None:
                _LOGGER.debug("Client disconnected")
                return

            responses = await self.process_request(request)
            _LOGGER.debug("Client command %s -> %s", request, responses)
            for response in responses:
                await write_packet(writer, response)

    async def process_request(self, request: Union[CommandPacket, AmxDuetRequest]):
        if isinstance(request, AmxDuetRequest):
            return [self._amxduet]

        handler = self._handlers.get((request.zn, request.cc, request.data))
        if handler is None:
            handler = self._handlers.get((request.zn, request.cc))

        try:
            if handler:
                data = handler(
                    zn=request.zn,
                    cc=request.cc,
                    data=request.data)

                if isinstance(data, bytes):
                    response = [
                        ResponsePacket(
                            request.zn,
                            request.cc,
                            AnswerCodes.STATUS_UPDATE,
                            data)
                    ]
                else:
                    response = data
            else:
                raise CommandNotRecognised()
        except ResponseException as e:
            response = [
                ResponsePacket(
                    request.zn,
                    request.cc,
                    e.ac,
                    e.data or bytes()
                )
            ]

        return response

    def register_handler(self, zn, cc, data, fun):
        if data:
            self._handlers[(zn, cc, data)] = fun
        else:
            self._handlers[(zn, cc)] = fun

    async def start(self):
        _LOGGER.debug("Starting server")
        self._server = await asyncio.start_server(
            self.process,
            self._host,
            self._port)
        return self

    async def stop(self):
        if self._server:
            _LOGGER.debug("Stopping server")
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if self._tasks:
            _LOGGER.debug("Cancelling clients %s", self._tasks)
            for task in self._tasks:
                task.cancel()
            await asyncio.wait(self._tasks)


class ServerContext():
    def __init__(self, server: Server):
        self._server = server

    async def __aenter__(self):
        await self._server.start()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._server.stop()
