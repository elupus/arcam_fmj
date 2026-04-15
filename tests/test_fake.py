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
from arcam.fmj.state import State, UpdateConfig

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
        # Default command_delay is 100ms; use a smaller threshold for CI
        assert gap >= 0.07, f"Gap between commands {i-1} and {i} was only {gap:.3f}s"


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
    """Default command_delay should be 100ms."""
    c = Client("localhost", 8888)
    assert c.command_delay == 0.1


async def test_command_delay_cannot_be_negative():
    """Setting a negative delay should clamp to 0."""
    c = Client("localhost", 8888)
    c.command_delay = -1.0
    assert c.command_delay == 0.0


# --- Sequential update tests ---


async def test_state_update_sequential(server, client):
    """State.update() must query commands sequentially, not concurrently."""
    request_log = []
    original_request = server.process_request

    async def logging_process(request):
        request_log.append(time.monotonic())
        return await original_request(request)

    server.process_request = logging_process

    # Register handler for MUTE so update() gets at least some responses
    server.register_handler(
        0x01, CommandCodes.MUTE, bytes([0xF0]), lambda **kw: bytes([0x00])
    )

    state = State(client, 0x01)
    async with state:
        await state.update()

    # Verify requests arrived sequentially with gaps (not burst)
    assert len(request_log) >= 2
    for i in range(1, len(request_log)):
        gap = request_log[i] - request_log[i - 1]
        # Each request should have at least command_delay gap
        assert gap >= 0.07, f"Gap {i}: {gap:.4f}s — requests may be concurrent"


async def test_state_update_skip_presets(server, client):
    """UpdateConfig.skip_presets=True should skip PRESET_DETAIL queries."""
    preset_queried = False
    original_request = server.process_request

    async def tracking_process(request):
        nonlocal preset_queried
        if isinstance(request, CommandPacket) and request.cc == CommandCodes.PRESET_DETAIL:
            preset_queried = True
        return await original_request(request)

    server.process_request = tracking_process

    state = State(client, 0x01)
    config = UpdateConfig(skip_presets=True)
    async with state:
        await state.update(config=config)

    assert not preset_queried, "PRESET_DETAIL was queried despite skip_presets=True"


async def test_state_update_skip_now_playing(server, client):
    """UpdateConfig.skip_now_playing=True should skip NOW_PLAYING_INFO queries."""
    now_playing_queried = False
    original_request = server.process_request

    async def tracking_process(request):
        nonlocal now_playing_queried
        if isinstance(request, CommandPacket) and request.cc == CommandCodes.NOW_PLAYING_INFO:
            now_playing_queried = True
        return await original_request(request)

    server.process_request = tracking_process

    state = State(client, 0x01)
    config = UpdateConfig(skip_now_playing=True)
    async with state:
        await state.update(config=config)

    assert not now_playing_queried, "NOW_PLAYING_INFO was queried despite skip_now_playing=True"


async def test_state_update_priority_essential(server, client):
    """PRIORITY_ESSENTIAL flag should only query power, volume, mute, source."""
    from arcam.fmj import EnumFlags

    queried_commands = []
    original_request = server.process_request

    async def tracking_process(request):
        if isinstance(request, CommandPacket):
            queried_commands.append(request.cc)
        return await original_request(request)

    server.process_request = tracking_process

    # Register handlers for essential commands
    server.register_handler(
        0x01, CommandCodes.MUTE, bytes([0xF0]), lambda **kw: bytes([0x00])
    )
    server.register_handler(
        0x01, CommandCodes.CURRENT_SOURCE, bytes([0xF0]), lambda **kw: bytes([0x01])
    )

    state = State(client, 0x01)
    async with state:
        await state.update(flags=EnumFlags.PRIORITY_ESSENTIAL)

    # Should have queried only the essential commands
    assert CommandCodes.POWER in queried_commands
    assert CommandCodes.VOLUME in queried_commands
    assert CommandCodes.MUTE in queried_commands
    assert CommandCodes.CURRENT_SOURCE in queried_commands
    # Should NOT have queried non-essential commands
    assert CommandCodes.HEADPHONES not in queried_commands
    assert CommandCodes.TREBLE_EQUALIZATION not in queried_commands
    assert CommandCodes.PRESET_DETAIL not in queried_commands


async def test_user_command_interleaves_during_update(server, client):
    """A user command (e.g. volume set) should slot in between update queries.

    This proves that the lock is per-command, not per-update-cycle, so user
    commands experience at most one command's worth of latency.
    """
    from arcam.fmj import EnumFlags

    # Register handlers for several commands so update() has work to do
    server.register_handler(
        0x01, CommandCodes.MUTE, bytes([0xF0]), lambda **kw: bytes([0x00])
    )
    server.register_handler(
        0x01, CommandCodes.CURRENT_SOURCE, bytes([0xF0]), lambda **kw: bytes([0x01])
    )

    state = State(client, 0x01)
    user_cmd_done = asyncio.Event()
    update_started = asyncio.Event()

    # Track when the user command actually executes on the wire
    user_cmd_timestamps = []
    original_request = server.process_request

    async def tracking_process(request):
        if isinstance(request, CommandPacket) and request.cc == CommandCodes.POWER:
            if not update_started.is_set():
                update_started.set()
        if isinstance(request, CommandPacket) and request.cc == CommandCodes.VOLUME:
            if request.data != bytes([0xF0]):  # distinguish set from query
                user_cmd_timestamps.append(time.monotonic())
        return await original_request(request)

    server.process_request = tracking_process

    # Register a handler for the volume SET command
    server.register_handler(
        0x01, CommandCodes.VOLUME, bytes([50]), lambda **kw: bytes([50])
    )

    async def run_update():
        async with state:
            await state.update(flags=EnumFlags.FULL_UPDATE)

    async def send_user_command():
        # Wait until the update has started processing commands
        await update_started.wait()
        # Fire a user command — this should interleave, not wait for full update
        t0 = time.monotonic()
        await client.request(0x01, CommandCodes.VOLUME, bytes([50]))
        elapsed = time.monotonic() - t0
        user_cmd_done.set()
        return elapsed

    # Run update and user command concurrently
    update_task = asyncio.create_task(run_update())
    user_task = asyncio.create_task(send_user_command())

    await asyncio.gather(update_task, user_task)
    user_elapsed = user_task.result()

    # User command should have completed in well under 1 second
    # (one command round-trip + command_delay, not the full update duration)
    assert user_elapsed < 1.0, (
        f"User command took {user_elapsed:.2f}s — may be blocked behind full update"
    )
    assert len(user_cmd_timestamps) == 1, "User volume SET command should have executed"


async def test_command_delay_zero_skips_sleep(server):
    """command_delay=0 should not add any inter-command pause."""
    c = Client("localhost", 8888)
    c.command_delay = 0.0
    async with ClientContext(c):
        timestamps = []
        original_request = server.process_request

        async def tracking_request(request):
            timestamps.append(time.monotonic())
            return await original_request(request)

        server.process_request = tracking_request

        await c.request(0x01, CommandCodes.POWER, bytes([0xF0]))
        await c.request(0x01, CommandCodes.VOLUME, bytes([0xF0]))
        await c.request(0x01, CommandCodes.POWER, bytes([0xF0]))

        assert len(timestamps) == 3
        total = timestamps[-1] - timestamps[0]
        # With zero delay, the only gap is the response round-trip time.
        # Should be well under 100ms total for 3 local loopback commands.
        assert total < 0.1, f"Total time {total:.3f}s — delay=0 should have no sleeps"


async def test_max_presets_limits_query_count(server, client):
    """max_presets=3 should probe exactly 3 preset slots when all are populated."""
    preset_queries = []
    original_request = server.process_request

    async def tracking_process(request):
        if isinstance(request, CommandPacket) and request.cc == CommandCodes.PRESET_DETAIL:
            preset_queries.append(request.data[0])
        return await original_request(request)

    server.process_request = tracking_process

    # Register handlers for preset slots 1-5 (all populated)
    for slot in range(1, 6):
        name = f"Station {slot}".encode("utf8")
        resp = bytes([slot, 0x03]) + name  # slot, type=DAB, name
        server.register_handler(
            0x01, CommandCodes.PRESET_DETAIL, bytes([slot]),
            lambda resp=resp, **kw: resp,
        )

    state = State(client, 0x01)
    config = UpdateConfig(max_presets=3, skip_now_playing=True, stop_on_empty_preset=False)
    async with state:
        await state.update(config=config)

    # Should have queried exactly slots 1, 2, 3
    assert preset_queries == [1, 2, 3], (
        f"Expected presets [1, 2, 3] but got {preset_queries}"
    )
