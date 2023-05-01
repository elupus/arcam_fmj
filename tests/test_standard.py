"""Standard tests for component"""
import anyio
import pytest
from anyio.streams.buffered import BufferedByteReceiveStream
from typing import Iterable

from arcam.fmj import (
    AmxDuetResponse,
    CommandPacket,
    InvalidPacket,
    ResponsePacket,
    _read_response,
    write_packet,
    IntOrTypeEnum,
    ConnectionFailed,
)


async def _stream_data(data: Iterable[bytes]):
    bytes_send, bytes_receive = anyio.create_memory_object_stream(100)
    for block in data:
        await bytes_send.send(block)
    await bytes_send.aclose()
    return BufferedByteReceiveStream(bytes_receive)


async def test_reader_valid(event_loop):
    reader = await _stream_data([b"\x21\x01\x08\x00\x02\x10\x10\x0D"])
    packet = await _read_response(reader)
    assert packet == ResponsePacket(1, 8, 0, b'\x10\x10')


async def test_reader_invalid_data(event_loop):
    reader = await _stream_data(
        [b"\x21\x01\x08\x00\x02\x10\x0D", b"\x00", b"\x00", b"\x00", b"\x00"]
    )
    with pytest.raises(InvalidPacket):
        await _read_response(reader)


async def test_reader_invalid_data_recover(event_loop):
    reader = await _stream_data(
        [b"\x21\x01\x08\x00\x02\x10\x0D\x00", b"\x21\x01\x08\x00\x02\x10\x10\x0D"]
    )
    with pytest.raises(InvalidPacket):
        packet = await _read_response(reader)
    packet = await _read_response(reader)
    assert packet == ResponsePacket(1, 8, 0, b'\x10\x10')


async def test_reader_short(event_loop):
    reader = await _stream_data([b"\x21\x10\x0D"])
    with pytest.raises(ConnectionFailed):
        await _read_response(reader)


async def test_writer_valid(event_loop):
    writer, bytes_receive = anyio.create_memory_object_stream(100)
    reader = BufferedByteReceiveStream(bytes_receive)
    await write_packet(writer, CommandPacket(1, 8, b"\x10\x10"))
    await writer.aclose()
    with anyio.fail_after(1):
        await reader.receive_exactly(7) == b"\x21\x01\x08\x02\x10\x10\x0D"
        with pytest.raises(anyio.EndOfStream):
            await reader.receive()


async def test_intenum(event_loop):
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


async def test_amx(event_loop):
    src = b"AMXB<Device-SDKClass=Receiver><Device-Make=ARCAM><Device-Model=AV860><Device-Revision=x.y.z>\r"
    res = AmxDuetResponse.from_bytes(src)
    assert res.device_class == "Receiver"
    assert res.device_make == "ARCAM"
    assert res.device_model == "AV860"
    assert res.device_revision == "x.y.z"

    assert res.to_bytes() == src
