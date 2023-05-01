"""Test with a fake server"""

import logging
import unittest
import pytest
from datetime import timedelta
from unittest.mock import ANY
import anyio
import anyio.abc

from arcam.fmj import (
    CommandCodes,
    CommandNotRecognised,
    ConnectionFailed,
)
from arcam.fmj.client import Client
from arcam.fmj.server import Server
from arcam.fmj.state import State

_LOGGER = logging.getLogger(__name__)

# pylint: disable=redefined-outer-name

@pytest.fixture
async def server(request):
    s = Server("localhost", 8888, "AVR450")
    s.register_handler(
        0x01, CommandCodes.POWER, bytes([0xF0]), lambda **kwargs: bytes([0x00])
    )
    s.register_handler(
        0x01, CommandCodes.VOLUME, bytes([0xF0]), lambda **kwargs: bytes([0x01])
    )
    yield s


@pytest.fixture
async def silent_server(request):
    s = Server("localhost", 8888, "AVR450")

    async def process(stream: anyio.abc.SocketStream):
        while True:
            try:
                await stream.receive()
            except anyio.EndOfStream:
                break
    s.process_runner = process
    yield s


@pytest.fixture
async def client(request):
    c = Client("localhost", 8888)
    yield c


@pytest.fixture
async def speedy_client(mocker):
    mocker.patch('arcam.fmj.client._HEARTBEAT_INTERVAL', new=timedelta(seconds=1))
    mocker.patch('arcam.fmj.client._HEARTBEAT_TIMEOUT', new=timedelta(seconds=2))
    mocker.patch('arcam.fmj.client._REQUEST_TIMEOUT', new=timedelta(seconds=0.5))


async def test_power(server, client):
    async with anyio.create_task_group() as tg:
        await tg.start(server.run)
        await tg.start(client.run)

        data = await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))
        assert data == bytes([0x00])

        tg.cancel_scope.cancel()


async def test_multiple(server: Server, client: Client):
    async with anyio.create_task_group() as tg:
        await tg.start(server.run)
        await tg.start(client.run)

        async def read1():
            assert await client.request(
                0x01, CommandCodes.POWER, bytes([0xF0])
            ) == bytes([0x00])

        async def read2():
            assert await client.request(
                0x01, CommandCodes.VOLUME, bytes([0xF0])
            ) == bytes([0x01])

        with anyio.fail_after(1):
            async with anyio.create_task_group() as tg2:
                tg2.start_soon(read1)
                tg2.start_soon(read2)

        tg.cancel_scope.cancel()


async def test_invalid_command(server, client):
    async with anyio.create_task_group() as tg:
        await tg.start(server.run)
        await tg.start(client.run)

        with pytest.raises(CommandNotRecognised):
            await client.request(0x01, 0xFF, bytes([0xF0]))

        tg.cancel_scope.cancel()


async def test_state(server, client):
    async with anyio.create_task_group() as tg:
        await tg.start(server.run)
        await tg.start(client.run)

        state = State(client, 0x01)
        await state.update()
        assert state.get(CommandCodes.POWER) == bytes([0x00])
        assert state.get(CommandCodes.VOLUME) == bytes([0x01])

        tg.cancel_scope.cancel()


async def test_silent_server_request(speedy_client, silent_server, client):
    async with anyio.create_task_group() as tg:
        await tg.start(silent_server.run)
        await tg.start(client.run)

        with pytest.raises(TimeoutError):
            await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))

        tg.cancel_scope.cancel()


async def test_silent_server_disconnect(speedy_client, silent_server):
    from arcam.fmj.client import _HEARTBEAT_TIMEOUT

    c = Client("localhost", 8888)

    with pytest.raises(ConnectionFailed):
        async with anyio.create_task_group() as tg:
            await tg.start(silent_server.run)
            await tg.start(c.run)
            await anyio.sleep(_HEARTBEAT_TIMEOUT.total_seconds() + 0.5)
            assert False, "Should have been cancelled by now"


async def test_heartbeat(speedy_client, server: Server, client: Client):
    from arcam.fmj.client import _HEARTBEAT_INTERVAL

    with unittest.mock.patch.object(
        server, "process_request", wraps=server.process_request
    ) as req:
        async with anyio.create_task_group() as tg:
            await tg.start(server.run)
            await tg.start(client.run)

            await anyio.sleep(_HEARTBEAT_INTERVAL.total_seconds() + 0.5)
            req.assert_called_once_with(ANY)
            tg.cancel_scope.cancel()


async def test_cancellation(event_loop, silent_server: Server):
    c = Client("localhost", 8888)
    async with anyio.create_task_group() as tg:
        await tg.start(silent_server.run)
        await tg.start(c.run)
        assert c.started
        tg.cancel_scope.cancel()

    assert not c.started
