"""Test with a fake server"""

import asyncio
import logging
import asynctest
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

async def run_context(loop, request, context):

    def fun():
        loop.run_until_complete(context.__aexit__(None, None, None))

    request.addfinalizer(fun)
    await context.__aenter__()


@pytest.mark.asyncio
@pytest.fixture
async def server(loop, request):
    s = Server('localhost', 8888)
    context = ServerContext(s)
    await run_context(loop, request, context)
    s.register_handler(
        0x01, CommandCodes.POWER, bytes([0xF0]),
        lambda **kwargs: bytes([0x00])
    )
    s.register_handler(
        0x01, CommandCodes.VOLUME, bytes([0xF0]),
        lambda **kwargs: bytes([0x01])
    )
    return s

@pytest.mark.asyncio
@pytest.fixture
async def silent_server(loop, request):
    s = Server('localhost', 8888)
    async def process(reader, writer):
        while True:
            if await reader.read(1) == bytes([]):
                break
    s.process_runner = process
    context = ServerContext(s)
    await run_context(loop, request, context)
    return s

@pytest.mark.asyncio
@pytest.fixture
async def client(loop, request):
    c = Client("localhost", 8888, loop=loop)
    context = ClientContext(c)
    await run_context(loop, request, context)
    return c

@pytest.mark.asyncio
@pytest.fixture
async def speedy_client(mocker):
    mocker.patch('arcam.fmj.client._HEARTBEAT_INTERVAL', new=timedelta(seconds=1))
    mocker.patch('arcam.fmj.client._HEARTBEAT_TIMEOUT', new=timedelta(seconds=2))
    mocker.patch('arcam.fmj.client._REQUEST_TIMEOUT', new=timedelta(seconds=0.5))

@pytest.mark.asyncio
async def test_power(loop, server, client):
    data = await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))
    assert data == bytes([0x00])

@pytest.mark.asyncio
async def test_multiple(loop, server, client):
    data = await asyncio.gather(
        client.request(0x01, CommandCodes.POWER, bytes([0xF0])),
        client.request(0x01, CommandCodes.VOLUME, bytes([0xF0])),
    )
    assert data[0] == bytes([0x00])
    assert data[1] == bytes([0x01])

@pytest.mark.asyncio
async def test_invalid_command(loop, server, client):
    with pytest.raises(CommandNotRecognised):
        await client.request(0x01, 0xff, bytes([0xF0]))

@pytest.mark.asyncio
async def test_state(loop, server, client):
    state = State(client, 0x01)
    await state.update()
    assert state.get(CommandCodes.POWER) == bytes([0x00])
    assert state.get(CommandCodes.VOLUME) == bytes([0x01])

@pytest.mark.asyncio
async def test_silent_server_request(loop, speedy_client, silent_server, client):
    with pytest.raises(asyncio.TimeoutError):
        await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))

@pytest.mark.asyncio
async def test_silent_server_disconnect(loop, speedy_client, silent_server):
    from arcam.fmj.client import _HEARTBEAT_TIMEOUT

    c = Client("localhost", 8888, loop=loop)
    connected = True
    with pytest.raises(ConnectionFailed):
        async with ClientContext(c):
            await asyncio.sleep(_HEARTBEAT_TIMEOUT.total_seconds()+1.0)
            connected = c.connected
    assert not connected

@pytest.mark.asyncio
async def test_heartbeat(loop, speedy_client, server, client):
    with asynctest.mock.patch.object(
            server,
            'process_request',
            wraps=server.process_request) as req:
        from arcam.fmj.client import _HEARTBEAT_INTERVAL
        await asyncio.sleep(_HEARTBEAT_INTERVAL.total_seconds()+1.0)
        req.assert_called_once_with(ANY)
