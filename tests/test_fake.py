"""Test with a fake server"""

import asyncio
from arcam_av import CommandCodes, AnswerCodes, ResponseException
from arcam_av.server import Server
from arcam_av.client import Client
import pytest
import logging
from unittest.mock import MagicMock, call

_LOGGER = logging.getLogger(__name__)

@pytest.mark.asyncio
@pytest.fixture
async def server(event_loop):
    async with Server('localhost', 8888) as s:
        s.register_handler(0x01, CommandCodes.POWER, bytes([0xF0]),
            lambda **kwargs: (AnswerCodes.STATUS_UPDATE, bytes([0x00]))
        )
        yield s

@pytest.mark.asyncio
@pytest.fixture
async def client(event_loop):
    async with Client("localhost", 8888, loop=event_loop) as c:
        yield c

@pytest.mark.asyncio
async def test_power(event_loop, server, client):
    data = await client.request(0x01, CommandCodes.POWER, bytes([0xF0]))
    assert data == bytes([0x00])

@pytest.mark.asyncio
async def test_invalid_command(event_loop, server, client):
    with pytest.raises(ResponseException) as exc_info:
        await client.request(0x01, 0xff, bytes([0xF0]))
    assert exc_info.value.response.ac == AnswerCodes.COMMAND_NOT_RECOGNISED
