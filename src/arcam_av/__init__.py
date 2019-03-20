"""Arcam AV Control"""
import asyncio
import attr
import logging
import enum
import sys

PROTOCOL_STR = b'\x21'
PROTOCOL_ETR = b'\x0D'

_LOGGER = logging.getLogger(__name__)


class InvalidPacket(Exception):
    pass

class AnswerCodes(enum.IntEnum):
    STATUS_UPDATE = 0x00
    ZONE_INVALID = 0x82
    COMMAND_NOT_RECOGNISED = 0x83
    PARAMETER_NOT_RECOGNISED = 0x84
    COMMAND_INVALID_AT_THIS_TIME = 0x85
    INVALID_DATA_LENGTH = 0x86

@attr.s
class ResponsePacket(object):
    zn = attr.ib(type=int)
    cc = attr.ib(type=int)
    ac = attr.ib(type=int)
    data = attr.ib(type=bytes)

    @staticmethod
    def from_bytes(data: bytes) -> 'ResponsePacket':
        if len(data) < 5:
            raise InvalidPacket("Packet to short {}".format(data))

        if data[3] != len(data)-5:
            raise InvalidPacket("Invalid length in data {}".format(data))

        return ResponsePacket(
            data[0],
            data[1],
            data[2],
            data[4:4+data[3]])

@attr.s
class CommandPacket(object):
    zn   = attr.ib(type=int)
    cc   = attr.ib(type=int)
    data = attr.ib(type=bytes)

    def to_bytes(self):
        return bytes([
            self.zn,
            self.cc,
            len(self.data),
            *self.data
        ])

    @staticmethod
    def from_bytes(data: bytes) -> 'CommandPacket':
        if len(data) < 3:
            raise InvalidPacket("Packet to short {}".format(data))

        if data[2] != len(data)-4:
            raise InvalidPacket("Invalid length in data {}".format(data))

        return CommandPacket(
            data[0],
            data[1],
            data[3:3+data[2]])

async def _read_delimited(reader: asyncio.StreamReader) -> bytes:
    eof = bytes()
    while True:
        start = await reader.read(1)
        if start == eof:
            return None
        if start == PROTOCOL_STR:
            break
    return await reader.readuntil(PROTOCOL_ETR)

async def _read_packet(reader: asyncio.StreamReader) -> ResponsePacket:
    data = await _read_delimited(reader)
    if data:
        return ResponsePacket.from_bytes(data)
    else:
        return None


async def _read_command_packet(reader: asyncio.StreamReader) -> CommandPacket:
    data = await _read_delimited(reader)
    if data:
        return CommandPacket.from_bytes(data)
    else:
        return None



async def _write_packet(writer: asyncio.StreamWriter, packet: CommandPacket) -> None:
    writer.write(PROTOCOL_STR)
    writer.write(packet.to_bytes())
    writer.write(PROTOCOL_ETR)
    await writer.drain()


class Client:
    def __init__(self, reader, writer, loop) -> None:
        self._reader = reader
        self._writer = writer
        self._loop = loop
        self._task = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def _process(self):
        while True:
            packet = await _read_packet(self._reader)
            if packet is None:
                _LOGGER.debug("Server disconnected")
                return
            _LOGGER.debug("Packet received: %s", packet)

    @staticmethod
    async def connect(host: str, port: int, loop=None):
        reader, writer = await asyncio.open_connection(
            host, port, loop=loop)
        return Client(reader, writer, loop)

    async def start(self):
        _LOGGER.debug("Starting client")
        if self._task:
            raise Exception("Already started")
        self._task = asyncio.ensure_future(self._process())

    async def stop(self):
        _LOGGER.debug("Stopping client")
        if self._task:
            self._task.cancel()
            asyncio.wait(self._task)
        self._writer.close()
        if (sys.version_info >= (3, 7)):
            await self._writer.wait_closed()
