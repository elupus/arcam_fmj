"""Arcam AV Control"""
import asyncio
import attr
import logging
import enum
import sys
from typing import Union

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

class CommandCodes(enum.IntEnum):
    POWER = 0x00

@attr.s
class ResponsePacket(object):
    zn = attr.ib(type=int)
    cc = attr.ib(type=int)
    ac = attr.ib(type=int)
    data = attr.ib(type=bytes)

    @staticmethod
    def from_bytes(data: bytes) -> 'ResponsePacket':
        if len(data) < 6:
            raise InvalidPacket("Packet to short {}".format(data))

        if data[4] != len(data)-6:
            raise InvalidPacket("Invalid length in data {}".format(data))

        return ResponsePacket(
            data[1],
            data[2],
            data[3],
            data[5:5+data[4]])

    def to_bytes(self):
        return bytes([
            *PROTOCOL_STR,
            self.zn,
            self.cc,
            self.ac,
            len(self.data),
            *self.data,
            *PROTOCOL_ETR
        ])

@attr.s
class CommandPacket(object):
    zn   = attr.ib(type=int)
    cc   = attr.ib(type=int)
    data = attr.ib(type=bytes)

    def to_bytes(self):
        return bytes([
            *PROTOCOL_STR,
            self.zn,
            self.cc,
            len(self.data),
            *self.data,
            *PROTOCOL_ETR
        ])

    @staticmethod
    def from_bytes(data: bytes) -> 'CommandPacket':
        if len(data) < 5:
            raise InvalidPacket("Packet to short {}".format(data))

        if data[3] != len(data)-5:
            raise InvalidPacket("Invalid length in data {}".format(data))

        return CommandPacket(
            data[1],
            data[2],
            data[4:4+data[3]])

async def _read_delimited(reader: asyncio.StreamReader) -> bytes:
    eof = bytes()
    while True:
        start = await reader.read(1)
        _LOGGER.debug("start %s", start)
        if start == eof:
            return None
        if start == PROTOCOL_STR:
            break
    packet = await reader.readuntil(PROTOCOL_ETR)
    _LOGGER.debug("packet %s", packet)
    return bytes([*start, *packet])

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


async def _write_packet(writer: asyncio.StreamWriter, packet: Union[CommandPacket, ResponsePacket]) -> None:
    writer.write(packet.to_bytes())
    await writer.drain()
