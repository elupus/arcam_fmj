"""Test with a fake server"""

import asyncio
import logging
import asynctest
import pytest
from datetime import timedelta

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

@pytest.mark.asyncio
@pytest.fixture
async def server(event_loop):
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

@pytest.mark.asyncio
@pytest.fixture
async def silent_server(event_loop):
    s = Server('localhost', 8888)

    async def process(reader, writer):
        while True:
            if await reader.read(1) == bytes([]):
                break
    s.process_runner = process
    async with ServerContext(s):
        yield s

@pytest.mark.asyncio
@pytest.fixture
async def client(event_loop):
    c = Client("localhost", 8888, loop=event_loop)
    async with ClientContext(c):
        yield c

@pytest.mark.asyncio
@pytest.fixture
async def speedy_client(mocker):
    mocker.patch('arcam.fmj.client._HEARTBEAT_INTERVAL', new=timedelta(seconds=1))
    mocker.patch('arcam.fmj.client._HEARTBEAT_TIMEOUT', new=timedelta(seconds=2))
    mocker.patch('arcam.fmj.client._REQUEST_TIMEOUT', new=timedelta(seconds=0.5))

@pytest.mark.asyncio
async def test_power(event_loop, server, client):
    data = await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))
    assert data == bytes([0x00])

@pytest.mark.asyncio
async def test_multiple(event_loop, server, client):
    data = await asyncio.gather(
        client.request(0x01, CommandCodes.POWER, bytes([0xF0])),
        client.request(0x01, CommandCodes.VOLUME, bytes([0xF0])),
    )
    assert data[0] == bytes([0x00])
    assert data[1] == bytes([0x01])

@pytest.mark.asyncio
async def test_invalid_command(event_loop, server, client):
    with pytest.raises(CommandNotRecognised):
        await client.request(0x01, 0xff, bytes([0xF0]))

@pytest.mark.asyncio
async def test_state(event_loop, server, client):
    state = State(client, 0x01)
    await state.update()
    assert state.get(CommandCodes.POWER) == bytes([0x00])
    assert state.get(CommandCodes.VOLUME) == bytes([0x01])

@pytest.mark.asyncio
async def test_silent_server_request(event_loop, speedy_client, silent_server, client):
    with pytest.raises(asyncio.TimeoutError):
        await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))

@pytest.mark.asyncio
async def test_silent_server_disconnect(event_loop, speedy_client, silent_server):
    from arcam.fmj.client import _HEARTBEAT_TIMEOUT

    c = Client("localhost", 8888, loop=event_loop)
    connected = True
    with pytest.raises(ConnectionFailed):
        async with ClientContext(c):
            await asyncio.sleep(_HEARTBEAT_TIMEOUT.total_seconds()+1.0)
            connected = c.connected
    assert not connected

@pytest.mark.asyncio
async def test_heartbeat(event_loop, speedy_client, server, client):
    with asynctest.mock.patch.object(
            server,
            'process_request',
            wraps=server.process_request) as req:
        from arcam.fmj.client import _HEARTBEAT_INTERVAL
        await asyncio.sleep(_HEARTBEAT_INTERVAL.total_seconds()+1.0)
        req.assert_called_once()
