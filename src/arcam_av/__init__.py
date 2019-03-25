"""Arcam AV Control"""
import asyncio
import enum
import logging
import sys
from typing import Union

import attr

PROTOCOL_STR = b'\x21'
PROTOCOL_ETR = b'\x0D'
PROTOCOL_EOF = b''

_LOGGER = logging.getLogger(__name__)

class ArcamException(Exception):
    pass

class ResponseException(Exception):
    def __init__(self, response: 'ResponsePacket'):
        self.response = response
        super().__init__("{}".format(response))

    @staticmethod
    def from_response(response: 'ResponsePacket'):
        if response.ac == AnswerCodes.ZONE_INVALID:
            return InvalidZoneException(response)
        elif response.ac == AnswerCodes.COMMAND_NOT_RECOGNISED:
            return CommandNotRecognised(response)
        elif response.ac == AnswerCodes.PARAMETER_NOT_RECOGNISED:
            return ParameterNotRecognised(response)
        elif response.ac == AnswerCodes.COMMAND_INVALID_AT_THIS_TIME:
            return CommandInvalidAtThisTime(response)
        elif response.ac == AnswerCodes.INVALID_DATA_LENGTH:
            return InvalidDataLength(response)
        else:
            return ResponseException(response)

class InvalidZoneException(ResponseException):
    pass

class CommandNotRecognised(ResponseException):
    pass

class ParameterNotRecognised(ResponseException):
    pass

class CommandInvalidAtThisTime(ResponseException):
    pass

class InvalidDataLength(ResponseException):
    pass

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
    CURRENT_SOURCE = 0x1D  # Request
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
    MENU = 0x14  # Request
    TUNER_PRESET = 0x15  # Set/Request
    TUNE = 0x16  # Set/Request
    DAB_STATION = 0x17  # Set/Request
    DAB_PROGRAM_TYPE_CATEGORY = 0x18  # Set/Request
    DLS_PDT_INFO = 0x1A  # Request
    PRESET_DETAIL = 0x1B # Request


    # Network Command


    # Setup
    TREBLE_EQUALIZATION = 0x35
    BASS_EQUALIZATION = 0x36
    ROOM_EQUALIZATION = 0x37
    DOLBY_VOLUME = 0x38
    DOLBY_LEVELER = 0x39
    DOLBY_VOLUME_CALIBRATION_OFFSET = 0x3A
    BALANCE = 0x3B

    DOLBY_PLII_X_MUSIC_DIMENSION = 0x3C
    DOLBY_PLII_X_MUSIC_CENTRE_WIDTH = 0x3D
    DOLBY_PLII_X_MUSIC_PANORAMA = 0x3E
    SUBWOOFER_TRIM = 0x3F
    LIPSYNC_DELAY = 0x40
    COMPRESSION = 0x41

    INCOMING_VIDEO_FORMAT = 0x42
    INCOMING_AUDIO_FORMAT = 0x43
    INCOMING_AUDIO_SAMPLERATE = 0x44

    SUB_STEREO_TRIM = 0x45  # Set/Request
    VIDEO_BRIGHTNESS = 0x46  # Set/Request
    VIDEO_CONTRAST = 0x47  # Set/Request
    VIDEO_COLOUR = 0x48  # Set/Request
    VIDEO_FILM_MODE = 0x49  # Set/Request
    VIDEO_EDGE_ENHANCEMENT = 0x4A  # Set/Request
    VIDEO_NOISE_REDUCTION = 0x4C  # Set/Request
    VIDEO_MPEG_NOISE_REDUCTION = 0x4D  # Set/Request
    ZONE_1_OSD_ON_OFF = 0x4E  # Set/Request
    VIDEO_OUTPUT_SWITCHING = 0x4F  # Set/Request
    VIDEO_OUTPUT_FRAME_RATE = 0x50  # Set/Request

    # 2.0 Commands
    INPUT_NAME = 0x20  # Set/Request
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

class SourceCodes(enum.IntEnum):
    FOLLOW_ZONE_1 = 0x00
    CD = 0x01
    BD = 0x02
    AV = 0x03
    SAT = 0x04
    PVR = 0x05
    VCR = 0x06
    AUX = 0x08
    DISPLAY = 0x09
    TUNER_FM = 0x0B
    TUNER_DAB = 0x0C
    NET = 0x0E
    USB = 0x0F
    STB = 0x10
    GAME = 0x11

    @staticmethod
    def from_int(v: int):
        try:
            return SourceCodes(v)
        except ValueError:
            return v

    @staticmethod
    def from_bytes(v: bytes):
        return SourceCodes.from_int(int.from_bytes(v, 'big'))


class MenuCodes(enum.IntEnum):
    NONE = 0x00
    SETUP = 0x02
    TRIM = 0x03
    BASS = 0x04
    TREBLE = 0x05
    SYNC = 0x06
    SUB = 0x07
    TUNER = 0x08
    NETWORK = 0x09
    USB = 0x0A

    @staticmethod
    def from_int(v: int):
        try:
            return MenuCodes(v)
        except ValueError:
            return v

    @staticmethod
    def from_bytes(v: bytes):
        return MenuCodes.from_int(int.from_bytes(v, 'big'))


class DecodeMode2CH(enum.IntEnum):
    STEREO = 0x01
    DOLBY_PLII_X_MOVIE = 0x02
    DOLBY_PLII_X_MUSIC = 0x03
    DOLBY_PLII_X_GAME = 0x05
    DOLBY_PL = 0x06
    NEO_6_CINEMA = 0x07
    NEO_6_MUSIC = 0x08
    MCH_STEREO = 0x09

    @staticmethod
    def from_int(v: int):
        try:
            return DecodeMode2CH(v)
        except ValueError:
            return v

    @staticmethod
    def from_bytes(v: bytes):
        return DecodeMode2CH.from_int(int.from_bytes(v, 'big'))


class DecodeModeMCH(enum.IntEnum):
    STEREO_DOWNMIX = 0x01
    MULTI_CHANNEL = 0x02
    DOLBY_D_EX_OR_DTS_ES = 0x03
    DOLBY_PLIIx_MOVIE = 0x04
    DOLBY_PLIIx_MUSIC = 0x05

    @staticmethod
    def from_int(v: int):
        try:
            return DecodeModeMCH(v)
        except ValueError:
            return v

    @staticmethod
    def from_bytes(v: bytes):
        return DecodeModeMCH.from_int(int.from_bytes(v, 'big'))


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

async def _read_delimited(reader: asyncio.StreamReader, header_len: int) -> bytes:
    while True:
        start = await reader.read(1)
        if start == PROTOCOL_EOF:
            _LOGGER.debug("eof")
            return None

        if start != PROTOCOL_STR:
            _LOGGER.warning("unexpected str byte %s", start)
            continue

        header   = await reader.read(header_len-1)
        data_len = await reader.read(1)
        data     = await reader.read(int.from_bytes(data_len, 'big'))
        etr      = await reader.read(1)

        if etr != PROTOCOL_ETR:
            _LOGGER.warning("unexpected etr byte %s", etr)
            continue

        packet = bytes([*start, *header, *data_len, *data, *etr])
        return packet

async def _read_packet(reader: asyncio.StreamReader) -> ResponsePacket:
    data = await _read_delimited(reader, 4)
    if data:
        return ResponsePacket.from_bytes(data)
    else:
        return None


async def _read_command_packet(reader: asyncio.StreamReader) -> CommandPacket:
    data = await _read_delimited(reader, 3)
    if data:
        return CommandPacket.from_bytes(data)
    else:
        return None


async def _write_packet(writer: asyncio.StreamWriter, packet: Union[CommandPacket, ResponsePacket]) -> None:
    b = packet.to_bytes()
    writer.write(b)
    await writer.drain()
