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
    UnsupportedZone,
)
from arcam.fmj.client import Client, ClientContext
from arcam.fmj.server import Server, ServerContext
from arcam.fmj.state import State

_LOGGER = logging.getLogger(__name__)

# pylint: disable=redefined-outer-name

@pytest.fixture
async def server(event_loop, request):
    s = Server('localhost', 8888, "AVR450")
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
async def silent_server(event_loop, request):
    s = Server('localhost', 8888, "AVR450")
    async def process(reader, writer):
        while True:
            if await reader.read(1) == bytes([]):
                break
    s.process_runner = process
    async with ServerContext(s):
        yield s


@pytest.fixture
async def client(event_loop, request):
    c = Client("localhost", 8888)
    async with ClientContext(c):
        yield c


@pytest.fixture
async def speedy_client(mocker):
    mocker.patch('arcam.fmj.client._HEARTBEAT_INTERVAL', new=timedelta(seconds=1))
    mocker.patch('arcam.fmj.client._HEARTBEAT_TIMEOUT', new=timedelta(seconds=2))
    mocker.patch('arcam.fmj.client._REQUEST_TIMEOUT', new=timedelta(seconds=0.5))


async def test_power(event_loop, server, client):
    data = await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))
    assert data == bytes([0x00])


async def test_multiple(event_loop, server, client):
    data = await asyncio.gather(
        client.request(0x01, CommandCodes.POWER, bytes([0xF0])),
        client.request(0x01, CommandCodes.VOLUME, bytes([0xF0])),
    )
    assert data[0] == bytes([0x00])
    assert data[1] == bytes([0x01])


async def test_invalid_command(event_loop, server, client):
    with pytest.raises(CommandNotRecognised):
        await client.request(0x01, CommandCodes.from_int(0xff), bytes([0xF0]))


async def test_state(event_loop, server, client):
    state = State(client, 0x01)
    await state.update()
    assert state.get(CommandCodes.POWER) == bytes([0x00])
    assert state.get(CommandCodes.VOLUME) == bytes([0x01])


async def test_silent_server_request(event_loop, speedy_client, silent_server, client):
    with pytest.raises(asyncio.TimeoutError):
        await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))

async def test_unsupported_zone(event_loop, speedy_client, silent_server, client):
    with pytest.raises(UnsupportedZone):
        await client.request(0x02, CommandCodes.DECODE_MODE_STATUS_2CH, bytes([0xF0]))

async def test_silent_server_disconnect(event_loop, speedy_client, silent_server):
    from arcam.fmj.client import _HEARTBEAT_TIMEOUT

    c = Client("localhost", 8888)
    connected = True
    with pytest.raises(ConnectionFailed):
        async with ClientContext(c):
            await asyncio.sleep(_HEARTBEAT_TIMEOUT.total_seconds()+0.5)
            connected = c.connected
    assert not connected


async def test_heartbeat(event_loop, speedy_client, server, client):
    from arcam.fmj.client import _HEARTBEAT_INTERVAL

    with unittest.mock.patch.object(
            server,
            'process_request',
            wraps=server.process_request) as req:
        await asyncio.sleep(_HEARTBEAT_INTERVAL.total_seconds()+0.5)
        req.assert_called_once_with(ANY)


async def test_cancellation(event_loop, silent_server):
    from arcam.fmj.client import _HEARTBEAT_TIMEOUT

    e = asyncio.Event()
    c = Client("localhost", 8888)

    async def runner():
        await c.start()
        try:
            e.set()
            await c.process()
        finally:
            await c.stop()

    task = asyncio.create_task(runner())
    await asyncio.wait_for(e.wait(), 5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
