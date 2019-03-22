"""Arcam AV Control"""
import asyncio
import enum
import logging
import sys
from typing import Union

import attr

PROTOCOL_STR = b'\x21'
PROTOCOL_ETR = b'\x0D'

_LOGGER = logging.getLogger(__name__)

class ArcamException(Exception):
    pass

class ResponseException(Exception):
    def __init__(self, response: 'ResponsePacket'):
        self.response = response
        super().__init__("Answer code: {} {}".format(AnswerCodes(response.ac).name, response))

class InvalidPacket(ArcamException):
    pass

class AnswerCodes(enum.IntEnum):
    STATUS_UPDATE = 0x00
    ZONE_INVALID = 0x82
    COMMAND_NOT_RECOGNISED = 0x83
    PARAMETER_NOT_RECOGNISED = 0x84
    COMMAND_INVALID_AT_THIS_TIME = 0x85
    INVALID_DATA_LENGTH = 0x86

    @staticmethod
    def from_int(v: int):
        try:
            return AnswerCodes(v)
        except ValueError:
            return v


class CommandCodes(enum.IntEnum):
    # System Commands
    POWER = 0x00
    DISPLAY_BRIGHTNESS = 0x01
    HEADPHONES = 0x02
    FMGENRE = 0x03
    SOFTWARE_VERSION = 0x04
    RESTORE_FACTORY_DEFAULT = 0x05
    SAVE_RESTORE_COPY_OF_SETTINGS = 0x06
    SIMULATE_RC5_IR_COMMAND = 0x08
    DISPLAY_INFORMATION_TYPE = 0x09
    REQUEST_CURRENT_SOURCE = 0x1D
    HEADPHONES_OVERRIDE = 0x1F


    # Input Commands
    VIDEO_SELECTION = 0x0A
    SELECT_ANALOG_DIGITAL = 0x0B
    VIDEO_INPUT_TYPE = 0x0C


    # Output Commands
    VOLUME = 0x0D  # Set/Request
    MUTE = 0x0E  # Request
    DIRECT_MODE_STATUS = 0x0F  # Request
    DECODE_MODE_STATUS_2CH = 0x10  # Request
    DECODE_MODE_STATUS_MCH = 0x11  # Request
    RDS_INFORMATION = 0x12  # Request
    VIDEO_OUTPUT_RESOLUTION = 0x13 # Set/Request


    # Menu Command


    # Network Command


    # 2.0 Commands
    INPUT_NAME = 0x20 # Set/Request
    FM_SCAN = 0x23
    DAB_SCAN = 0x24
    HEARTBEAT = 0x25
    REBOOT = 0x26


    @staticmethod
    def from_int(v: int):
        try:
            return CommandCodes(v)
        except ValueError:
            return v

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
            CommandCodes.from_int(data[2]),
            AnswerCodes.from_int(data[3]),
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
            CommandCodes.from_int(data[2]),
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
