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
    from arcam_av.server import Server
    async with Server('localhost', 8888) as s:
        yield s

@pytest.mark.asyncio
@pytest.fixture
async def client(event_loop):
    async with arcam_av.Client("localhost", 8888, loop=event_loop) as c:
        yield c

@pytest.mark.asyncio
async def test_volume(event_loop, server, client):
    print(server, client)
    #await client.stop()

