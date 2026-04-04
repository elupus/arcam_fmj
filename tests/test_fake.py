"""Test with a fake server"""

import asyncio
import logging
import time
import unittest
import pytest
from datetime import timedelta
from unittest.mock import ANY

from arcam.fmj import (
    CommandCodes,
    CommandNotRecognised,
    CommandPacket,
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
    mocker.patch("arcam.fmj.client._HEARTBEAT_INTERVAL", new=timedelta(seconds=1))
    mocker.patch("arcam.fmj.client._HEARTBEAT_TIMEOUT", new=timedelta(seconds=2))
    mocker.patch("arcam.fmj.client._REQUEST_TIMEOUT", new=timedelta(seconds=0.5))


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
    await state.update()
    assert state.get(CommandCodes.POWER) == bytes([0x00])
    assert state.get(CommandCodes.VOLUME) == bytes([0x01])


async def test_silent_server_request(speedy_client, silent_server, client):
    with pytest.raises(asyncio.TimeoutError):
        await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))


async def test_unsupported_zone(speedy_client, silent_server, client):
    with pytest.raises(UnsupportedZone):
        await client.request(0x02, CommandCodes.DECODE_MODE_STATUS_2CH, bytes([0xF0]))


async def test_silent_server_disconnect(speedy_client, silent_server):
    from arcam.fmj.client import _HEARTBEAT_TIMEOUT

    c = Client("localhost", 8888)
    connected = True
    with pytest.raises(ConnectionFailed):
        async with ClientContext(c):
            await asyncio.sleep(_HEARTBEAT_TIMEOUT.total_seconds() + 0.5)
            connected = c.connected
    assert not connected


async def test_heartbeat(speedy_client, server, client):
    from arcam.fmj.client import _HEARTBEAT_INTERVAL

    with unittest.mock.patch.object(
        server, "process_request", wraps=server.process_request
    ) as req:
        await asyncio.sleep(_HEARTBEAT_INTERVAL.total_seconds() + 0.5)
        req.assert_called_once_with(ANY)


async def test_cancellation(silent_server):
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
    async with asyncio.timeout(5):
        await e.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


# --- Rate limiting tests ---


async def test_commands_are_serialized(server, client):
    """Commands must execute one at a time — no pipelining to the device."""
    timestamps = []
    original_request = server.process_request

    async def tracking_request(request):
        timestamps.append(time.monotonic())
        return await original_request(request)

    server.process_request = tracking_request

    # Fire 3 concurrent requests — they should be serialized by the lock
    await asyncio.gather(
        client.request(0x01, CommandCodes.POWER, bytes([0xF0])),
        client.request(0x01, CommandCodes.VOLUME, bytes([0xF0])),
        client.request(0x01, CommandCodes.POWER, bytes([0xF0])),
    )

    assert len(timestamps) == 3
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i - 1]
        # Default command_delay is 50ms; use a smaller threshold for CI
        assert gap >= 0.03, f"Gap between commands {i-1} and {i} was only {gap:.3f}s"


async def test_configurable_command_delay(server):
    """command_delay property controls the inter-command quiet period."""
    c = Client("localhost", 8888)
    c.command_delay = 0.15  # 150ms
    async with ClientContext(c):
        timestamps = []
        original_request = server.process_request

        async def tracking_request(request):
            timestamps.append(time.monotonic())
            return await original_request(request)

        server.process_request = tracking_request

        await c.request(0x01, CommandCodes.POWER, bytes([0xF0]))
        await c.request(0x01, CommandCodes.VOLUME, bytes([0xF0]))

        assert len(timestamps) == 2
        gap = timestamps[1] - timestamps[0]
        assert gap >= 0.12, f"Gap was only {gap:.3f}s, expected >= 0.12s with 150ms delay"


async def test_command_delay_default():
    """Default command_delay should be 50ms."""
    c = Client("localhost", 8888)
    assert c.command_delay == 0.05


async def test_command_delay_cannot_be_negative():
    """Setting a negative delay should clamp to 0."""
    c = Client("localhost", 8888)
    c.command_delay = -1.0
    assert c.command_delay == 0.0
