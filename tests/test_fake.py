"""Test with a fake server"""

import asyncio
import contextlib
import logging
import pytest
from datetime import timedelta

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
async def server(request):
    s = Server("localhost", 8888, "AVR450")
    async with ServerContext(s):
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

    async def process(reader, writer):
        while True:
            if await reader.read(1) == bytes([]):
                break

    s.process_runner = process
    async with ServerContext(s):
        yield s


@pytest.fixture
async def client(request):
    c = Client("localhost", 8888)
    async with ClientContext(c):
        yield c


@pytest.fixture
async def speedy_client(mocker):
    mocker.patch("arcam.fmj.client._HEARTBEAT_IDLE", new=timedelta(seconds=1))
    mocker.patch("arcam.fmj.client._RECEIVE_TIMEOUT", new=timedelta(seconds=2))
    mocker.patch("arcam.fmj.client._RETRY_INTERVAL", new=timedelta(milliseconds=250))


async def test_power(server, client):
    data = await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))
    assert data == bytes([0x00])


async def test_multiple(server, client):
    data = await asyncio.gather(
        client.request(0x01, CommandCodes.POWER, bytes([0xF0])),
        client.request(0x01, CommandCodes.VOLUME, bytes([0xF0])),
    )
    assert data[0] == bytes([0x00])
    assert data[1] == bytes([0x01])


async def test_invalid_command(server, client):
    with pytest.raises(CommandNotRecognised):
        await client.request(0x01, CommandCodes.from_int(0xFF), bytes([0xF0]))


async def test_state(server, client):
    state = State(client, 0x01)
    await asyncio.gather(*await state.get_update_tasks())
    assert state.get(CommandCodes.POWER) == bytes([0x00])
    assert state.get(CommandCodes.VOLUME) == bytes([0x01])


async def test_silent_server_request(speedy_client, silent_server, client):
    with pytest.raises(asyncio.TimeoutError):
        await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))


async def test_unsupported_zone(speedy_client, silent_server, client):
    with pytest.raises(UnsupportedZone):
        await client.request(0x02, CommandCodes.DECODE_MODE_STATUS_2CH, bytes([0xF0]))


async def test_silent_server_disconnect(speedy_client, silent_server):
    from arcam.fmj.client import _RECEIVE_TIMEOUT

    c = Client("localhost", 8888)
    connected = True
    with pytest.raises(ConnectionFailed):
        async with ClientContext(c):
            await asyncio.sleep(_RECEIVE_TIMEOUT.total_seconds() + 0.5)
            connected = c.connected
    assert not connected


async def test_process_runs_update_providers(server):
    """When a State is started before process(), the client's update loop
    drives it via get_update_tasks() until state is populated."""
    c = Client("localhost", 8888)
    state = State(c, 0x01)

    await c.start()
    await state.start()
    try:
        process_task = asyncio.create_task(c.process())
        try:
            async with asyncio.timeout(5):
                while state.get_power() is None or state.get_volume() is None:
                    await asyncio.sleep(0.05)
            assert state.get_power() is False  # bytes([0x00]) → False
            assert state.get_volume() == 0x01
        finally:
            process_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await process_task
    finally:
        await state.stop()
        await c.stop()


async def test_heartbeat_keeps_connection_alive(speedy_client, server):
    """With no providers registered, _process_updates falls back to
    issuing a heartbeat once per _HEARTBEAT_IDLE — the connection
    survives past _RECEIVE_TIMEOUT."""
    from arcam.fmj.client import _RECEIVE_TIMEOUT

    c = Client("localhost", 8888)
    await c.start()
    try:
        process_task = asyncio.create_task(c.process())
        try:
            await asyncio.sleep(_RECEIVE_TIMEOUT.total_seconds() + 0.5)
            assert c.connected
        finally:
            process_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await process_task
    finally:
        await c.stop()


async def test_cancellation(silent_server):
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
    async with asyncio.timeout(5):
        await e.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
