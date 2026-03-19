"""Standard tests for component"""

import asyncio
from unittest.mock import MagicMock, call

import pytest

from arcam.fmj import (
    AmxDuetResponse,
    AnswerCodes,
    CommandCodes,
    CommandInvalidAtThisTime,
    CommandNotRecognised,
    CommandPacket,
    ConnectionFailed,
    InvalidDataLength,
    InvalidPacket,
    InvalidZoneException,
    ParameterNotRecognised,
    ResponseException,
    ResponsePacket,
    _read_response,
    write_packet,
    IntOrTypeEnum,
)


async def test_reader_valid():
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x21\x01\x08\x00\x02\x10\x10\x0d")
    reader.feed_eof()
    packet = await _read_response(reader)
    assert packet == ResponsePacket(1, 8, 0, b"\x10\x10")


async def test_reader_invalid_data():
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x21\x01\x08\x00\x02\x10\x0d\x00")
    reader.feed_eof()
    with pytest.raises(InvalidPacket):
        await _read_response(reader)


async def test_reader_invalid_data_recover():
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x21\x01\x08\x00\x02\x10\x0d\x00")
    reader.feed_data(b"\x21\x01\x08\x00\x02\x10\x10\x0d")
    reader.feed_eof()
    with pytest.raises(InvalidPacket):
        packet = await _read_response(reader)
    packet = await _read_response(reader)
    assert packet == ResponsePacket(1, 8, 0, b"\x10\x10")


async def test_reader_short():
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x21\x10\x0d")
    reader.feed_eof()
    with pytest.raises(ConnectionFailed):
        await _read_response(reader)


async def test_writer_valid():
    writer = MagicMock()
    writer.write.return_value = None
    writer.drain.return_value = asyncio.Future()
    writer.drain.return_value.set_result(None)
    await write_packet(writer, CommandPacket(1, 8, b"\x10\x10"))
    writer.write.assert_has_calls(
        [
            call(b"\x21\x01\x08\x02\x10\x10\x0d"),
        ]
    )


async def test_intenum():
    class TestClass1(IntOrTypeEnum):
        TEST = 55
        TEST_VERSION = 23, {1}

    res = TestClass1.from_int(55)
    assert res.name == "TEST"
    assert res.value == 55
    assert res.version == None

    res = TestClass1.from_int(23)
    assert res.name == "TEST_VERSION"
    assert res.value == 23
    assert res.version == {1}

    res = TestClass1.from_int(1)
    assert res.name == "CODE_1"
    assert res.value == 1
    assert res.version == None


async def test_amx():
    src = b"AMXB<Device-SDKClass=Receiver><Device-Make=ARCAM><Device-Model=AV860><Device-Revision=x.y.z>\r"
    res = AmxDuetResponse.from_bytes(src)
    assert res.device_class == "Receiver"
    assert res.device_make == "ARCAM"
    assert res.device_model == "AV860"
    assert res.device_revision == "x.y.z"

    assert res.to_bytes() == src


def test_response_packet_roundtrip():
    original = ResponsePacket(1, CommandCodes.VOLUME, AnswerCodes.STATUS_UPDATE, bytes([42]))
    rebuilt = ResponsePacket.from_bytes(original.to_bytes())
    assert rebuilt == original


def test_command_packet_roundtrip():
    original = CommandPacket(1, CommandCodes.POWER, bytes([0xF0]))
    rebuilt = CommandPacket.from_bytes(original.to_bytes())
    assert rebuilt == original


@pytest.mark.parametrize("ac, expected_type", [
    (AnswerCodes.ZONE_INVALID, InvalidZoneException),
    (AnswerCodes.COMMAND_NOT_RECOGNISED, CommandNotRecognised),
    (AnswerCodes.PARAMETER_NOT_RECOGNISED, ParameterNotRecognised),
    (AnswerCodes.COMMAND_INVALID_AT_THIS_TIME, CommandInvalidAtThisTime),
    (AnswerCodes.INVALID_DATA_LENGTH, InvalidDataLength),
])
def test_response_exception_from_response(ac, expected_type):
    response = ResponsePacket(1, CommandCodes.POWER, ac, b"")
    exc = ResponseException.from_response(response)
    assert isinstance(exc, expected_type)
