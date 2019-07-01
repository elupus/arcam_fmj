"""Standard tests for component"""
import asyncio
from unittest.mock import MagicMock, call

import pytest

from arcam.fmj import (
    CommandPacket,
    InvalidPacket,
    ResponsePacket,
    _read_packet,
    _read_delimited,
    _write_packet
)


async def test_reader_valid(loop):
    reader = asyncio.StreamReader(loop=loop)
    reader.feed_data(b'\x21\x01\x08\x00\x02\x10\x10\x0D')
    reader.feed_eof()
    packet = await _read_packet(reader)
    assert packet == ResponsePacket(1, 8, 0, b'\x10\x10')


async def test_reader_invalid_data(loop):
    reader = asyncio.StreamReader(loop=loop)
    reader.feed_data(b'\x21\x01\x08\x00\x02\x10\x0D')
    reader.feed_eof()
    with pytest.raises(InvalidPacket):
        await _read_delimited(reader, 4)


async def test_reader_short(loop):
    reader = asyncio.StreamReader(loop=loop)
    reader.feed_data(b'\x21\x10\x0D')
    reader.feed_eof()
    with pytest.raises(InvalidPacket):
        await _read_delimited(reader, 4)


async def test_writer_valid(loop):
    writer = MagicMock()
    writer.write.return_value = None
    writer.drain.return_value = asyncio.Future()
    writer.drain.return_value.set_result(None)
    await _write_packet(writer, CommandPacket(1, 8, b'\x10\x10'))
    writer.write.assert_has_calls([
        call(b'\x21\x01\x08\x02\x10\x10\x0D'),
    ])
