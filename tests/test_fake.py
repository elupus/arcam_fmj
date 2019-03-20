"""Test with a fake server"""

import asyncio
import arcam_av
import pytest
import logging
from unittest.mock import MagicMock, call

_LOGGER = logging.getLogger(__name__)

@pytest.mark.asyncio
@pytest.fixture
async def server(event_loop):
    async def handle_server(reader, writer):
        while True:
            packet = await arcam_av._read_command_packet(reader)
            if packet is None:
                _LOGGER.debug("Client disconnected")
                return
            
            print(packet)

    s = await asyncio.start_server(handle_server, 'localhost', 8888, loop=event_loop)
    yield s
    s.close()
    await s.wait_closed()

@pytest.mark.asyncio
@pytest.fixture
async def client(event_loop):
    c = await arcam_av.Client.connect("localhost", 8888, loop=event_loop)
    async with c:
        yield c

@pytest.mark.asyncio
async def test_volume(event_loop, server, client):
    print(server, client)
    #await client.stop()

