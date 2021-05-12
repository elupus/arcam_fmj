"""Test with a fake server"""

import asyncio
import logging
import unittest
import pytest
from datetime import timedelta
from unittest.mock import ANY

from arcam.fmj import (
    CommandCodes,
    CommandNotRecognised,
    ConnectionFailed,
)
from arcam.fmj.client import Client, ClientContext
from arcam.fmj.server import Server, ServerContext
from arcam.fmj.state import State

_LOGGER = logging.getLogger(__name__)

# pylint: disable=redefined-outer-name

@pytest.fixture
async def server(loop, request):
    s = Server('localhost', 8888)
    async with ServerContext(s):
        s.register_handler(
            0x01, CommandCodes.POWER, bytes([0xF0]),
            lambda **kwargs: bytes([0x00])
        )
        s.register_handler(
            0x01, CommandCodes.VOLUME, bytes([0xF0]),
            lambda **kwargs: bytes([0x01])
        )
        yield s


@pytest.fixture
async def silent_server(loop, request):
    s = Server('localhost', 8888)
    async def process(reader, writer):
        while True:
            if await reader.read(1) == bytes([]):
                break
    s.process_runner = process
    async with ServerContext(s):
        yield s


@pytest.fixture
async def client(loop, request):
    c = Client("localhost", 8888)
    async with ClientContext(c):
        yield c


@pytest.fixture
async def speedy_client(mocker):
    mocker.patch('arcam.fmj.client._HEARTBEAT_INTERVAL', new=timedelta(seconds=1))
    mocker.patch('arcam.fmj.client._HEARTBEAT_TIMEOUT', new=timedelta(seconds=2))
    mocker.patch('arcam.fmj.client._REQUEST_TIMEOUT', new=timedelta(seconds=0.5))


async def test_power(loop, server, client):
    data = await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))
    assert data == bytes([0x00])


async def test_multiple(loop, server, client):
    data = await asyncio.gather(
        client.request(0x01, CommandCodes.POWER, bytes([0xF0])),
        client.request(0x01, CommandCodes.VOLUME, bytes([0xF0])),
    )
    assert data[0] == bytes([0x00])
    assert data[1] == bytes([0x01])


async def test_invalid_command(loop, server, client):
    with pytest.raises(CommandNotRecognised):
        await client.request(0x01, 0xff, bytes([0xF0]))


async def test_state(loop, server, client):
    state = State(client, 0x01)
    await state.update()
    assert state.get(CommandCodes.POWER) == bytes([0x00])
    assert state.get(CommandCodes.VOLUME) == bytes([0x01])


async def test_silent_server_request(loop, speedy_client, silent_server, client):
    with pytest.raises(asyncio.TimeoutError):
        await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))


async def test_silent_server_disconnect(loop, speedy_client, silent_server):
    from arcam.fmj.client import _HEARTBEAT_TIMEOUT

    c = Client("localhost", 8888)
    connected = True
    with pytest.raises(ConnectionFailed):
        async with ClientContext(c):
            await asyncio.sleep(_HEARTBEAT_TIMEOUT.total_seconds()+0.5)
            connected = c.connected
    assert not connected


async def test_heartbeat(loop, speedy_client, server, client):
    from arcam.fmj.client import _HEARTBEAT_INTERVAL

    with unittest.mock.patch.object(
            server,
            'process_request',
            wraps=server.process_request) as req:
        await asyncio.sleep(_HEARTBEAT_INTERVAL.total_seconds()+0.5)
        req.assert_called_once_with(ANY)
