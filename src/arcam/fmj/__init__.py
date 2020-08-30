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
_WRITE_TIMEOUT = 3
_READ_TIMEOUT = 3

class ArcamException(Exception):
    pass

class ConnectionFailed(ArcamException):
    pass

class NotConnectedException(ArcamException):
    pass

class ResponseException(ArcamException):
    def __init__(self, ac=None, zn=None, cc=None, data=None):
        self.ac = ac
        self.zn = zn
        self.cc = cc
        self.data = data
        super().__init__("'ac':{}, 'zn':{}, 'cc':{}, 'data':{}".format(
            ac, zn, cc, data
        ))

    @staticmethod
    def from_response(response: 'ResponsePacket'):
        kwargs = {
            'zn': response.zn,
            'cc': response.cc,
            'data': response.data
        }
        if response.ac == AnswerCodes.ZONE_INVALID:
            return InvalidZoneException(**kwargs)
        elif response.ac == AnswerCodes.COMMAND_NOT_RECOGNISED:
            return CommandNotRecognised(**kwargs)
        elif response.ac == AnswerCodes.PARAMETER_NOT_RECOGNISED:
            return ParameterNotRecognised(**kwargs)
        elif response.ac == AnswerCodes.COMMAND_INVALID_AT_THIS_TIME:
            return CommandInvalidAtThisTime(**kwargs)
        elif response.ac == AnswerCodes.INVALID_DATA_LENGTH:
            return InvalidDataLength(**kwargs)
        else:
            return ResponseException(ac=response.ac, **kwargs)

class InvalidZoneException(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.ZONE_INVALID,
                         zn=zn, cc=cc, data=data)

class CommandNotRecognised(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.COMMAND_NOT_RECOGNISED,
                         zn=zn, cc=cc, data=data)

class ParameterNotRecognised(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.PARAMETER_NOT_RECOGNISED,
                         zn=zn, cc=cc, data=data)

class CommandInvalidAtThisTime(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.COMMAND_INVALID_AT_THIS_TIME,
                         zn=zn, cc=cc, data=data)

class InvalidDataLength(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.INVALID_DATA_LENGTH,
                         zn=zn, cc=cc, data=data)

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
    def from_int(value: int):
        try:
            return AnswerCodes(value)
        except ValueError:
            return value


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
    DAB_STATION = 0x18  # Set/Request
    DAB_PROGRAM_TYPE_CATEGORY = 0x19  # Set/Request
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
    def from_int(value: int):
        try:
            return CommandCodes(value)
        except ValueError:
            return value

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
    FM = 0x0B
    DAB = 0x0C
    NET = 0x0E
    USB = 0x0F
    STB = 0x10
    GAME = 0x11

    @staticmethod
    def from_int(value: int):
        try:
            return SourceCodes(value)
        except ValueError:
            return value

    @staticmethod
    def from_bytes(value: bytes):
        return SourceCodes.from_int(int.from_bytes(value, 'big'))


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
    def from_int(value: int):
        try:
            return MenuCodes(value)
        except ValueError:
            return value

    @staticmethod
    def from_bytes(value: bytes):
        return MenuCodes.from_int(int.from_bytes(value, 'big'))


class DecodeMode2CH(enum.IntEnum):
    STEREO = 0x01
    DOLBY_PLII_IIx_MOVIE = 0x02
    DOLBY_PLII_IIx_MUSIC = 0x03
    DOLBY_PLII_IIx_GAME = 0x05
    DOLBY_PL = 0x06
    DTS_NEO_6_CINEMA = 0x07
    DTS_NEO_6_MUSIC = 0x08
    MCH_STEREO = 0x09

    @staticmethod
    def from_int(value: int):
        try:
            return DecodeMode2CH(value)
        except ValueError:
            return value

    @staticmethod
    def from_bytes(value: bytes):
        return DecodeMode2CH.from_int(int.from_bytes(value, 'big'))


class DecodeModeMCH(enum.IntEnum):
    STEREO_DOWNMIX = 0x01
    MULTI_CHANNEL = 0x02
    DOLBY_D_EX_OR_DTS_ES = 0x03
    DOLBY_PLII_IIx_MOVIE = 0x04
    DOLBY_PLII_IIx_MUSIC = 0x05

    @staticmethod
    def from_int(value: int):
        try:
            return DecodeModeMCH(value)
        except ValueError:
            return value

    @staticmethod
    def from_bytes(value: bytes):
        return DecodeModeMCH.from_int(int.from_bytes(value, 'big'))

class RC5Codes(enum.Enum):
    SELECT_STB = bytes([16, 1])
    SELECT_AV = bytes([16, 2])
    SELECT_TUNER = bytes([16, 3])
    SELECT_BD = bytes([16, 4])
    SELECT_GAME = bytes([16, 5])
    SELECT_VCR = bytes([16, 6])
    SELECT_CD = bytes([16, 7])
    SELECT_AUX = bytes([16, 8])
    SELECT_DISPLAY = bytes([16, 9])
    SELECT_SAT = bytes([16, 0])
    SELECT_PVR = bytes([16, 34])
    SELECT_USB = bytes([16, 18])
    SELECT_NET = bytes([16, 11])
    SELECT_DAB = bytes([16, 72])
    SELECT_FM = bytes([16, 54])
    INC_VOLUME = bytes([16, 16])
    DEC_VOLUME = bytes([16, 17])
    MUTE_ON = bytes([16, 119])
    MUTE_OFF = bytes([16, 120])
    DIRECT_MODE_ON = bytes([16, 78])
    DIRECT_MODE_OFF = bytes([16, 79])
    DOLBY_PLII_IIx_GAME = bytes([16, 102])
    DOLBY_PLII_IIx_MOVIE = bytes([16, 103])
    DOLBY_PLII_IIx_MUSIC = bytes([16, 104])
    MULTI_CHANNEL = bytes([16, 106])
    STEREO = bytes([16, 107])
    DOLBY_PL = bytes([16, 110])
    DTS_NEO_6_CINEMA = bytes([16, 111])
    DTS_NEO_6_MUSIC = bytes([16, 112])
    MCH_STEREO = bytes([16, 69])
    DOLBY_D_EX = bytes([16, 118])
    POWER_ON = bytes([16, 123])
    POWER_OFF = bytes([16, 124])
    FOLLOW_ZONE_1 = bytes([16, 20])

    MUTE_ON_ZONE2 = bytes([23, 4])
    MUTE_OFF_ZONE2 = bytes([23, 5])
    INC_VOLUME_ZONE2 = bytes([23, 1])
    DEC_VOLUME_ZONE2 = bytes([23, 2])

    SELECT_CD_ZONE2 = bytes([23, 6])
    SELECT_BD_ZONE2 = bytes([23, 7])
    SELECT_STB_ZONE2 = bytes([23, 8])
    SELECT_AV_ZONE2 = bytes([23, 9])
    SELECT_GAME_ZONE2 = bytes([23, 11])
    SELECT_AUX_ZONE2 = bytes([23, 13])
    SELECT_PVR_ZONE2 = bytes([23, 15])
    SELECT_FM_ZONE2 = bytes([23, 14])
    SELECT_DAB_ZONE2 = bytes([23, 16])
    SELECT_USB_ZONE2 = bytes([23, 18])
    SELECT_NET_ZONE2 = bytes([23, 19])
    POWER_ON_ZONE2 = bytes([23, 123])
    POWER_OFF_ZONE2 = bytes([23, 124])

SOURCECODE_TO_RC5CODE_ZONE1 = {
    SourceCodes.STB: RC5Codes.SELECT_STB,
    SourceCodes.AV: RC5Codes.SELECT_AV,
    SourceCodes.DAB: RC5Codes.SELECT_DAB,
    SourceCodes.FM: RC5Codes.SELECT_FM,
    SourceCodes.BD: RC5Codes.SELECT_BD,
    SourceCodes.GAME: RC5Codes.SELECT_GAME,
    SourceCodes.VCR: RC5Codes.SELECT_VCR,
    SourceCodes.CD: RC5Codes.SELECT_CD,
    SourceCodes.AUX: RC5Codes.SELECT_AUX,
    SourceCodes.DISPLAY: RC5Codes.SELECT_DISPLAY,
    SourceCodes.SAT: RC5Codes.SELECT_SAT,
    SourceCodes.PVR: RC5Codes.SELECT_PVR,
    SourceCodes.USB: RC5Codes.SELECT_USB,
    SourceCodes.NET: RC5Codes.SELECT_NET,
}

SOURCECODE_TO_RC5CODE_ZONE2 = {
    SourceCodes.STB: RC5Codes.SELECT_STB_ZONE2,
    SourceCodes.AV: RC5Codes.SELECT_AV_ZONE2,
    SourceCodes.DAB: RC5Codes.SELECT_DAB_ZONE2,
    SourceCodes.FM: RC5Codes.SELECT_FM_ZONE2,
    SourceCodes.BD: RC5Codes.SELECT_BD_ZONE2,
    SourceCodes.GAME: RC5Codes.SELECT_GAME_ZONE2,
    SourceCodes.CD: RC5Codes.SELECT_CD_ZONE2,
    SourceCodes.AUX: RC5Codes.SELECT_AUX_ZONE2,
    SourceCodes.PVR: RC5Codes.SELECT_PVR_ZONE2,
    SourceCodes.USB: RC5Codes.SELECT_USB_ZONE2,
    SourceCodes.NET: RC5Codes.SELECT_NET_ZONE2,
    SourceCodes.FOLLOW_ZONE_1: RC5Codes.FOLLOW_ZONE_1
}

class IncomingAudioFormat(enum.IntEnum):
    PCM = 0x00
    ANALOGUE_DIRECT = 0x01
    DOLBY_DIGITAL = 0x02
    DOLBY_DIGITAL_EX = 0x03
    DOLBY_DIGITAL_SURROUND = 0x04
    DOLBY_DIGITAL_PLUS = 0x05
    DOLBY_DIGITAL_TRUE_HD = 0x07
    DTS_96_24 = 0x08
    DTS_ES_MATRIX = 0x09
    DTS_ES_DISCRETE = 0x0A
    DTS_ES_MATRIX_96_24 = 0x0B
    DTS_ES_DISCRETE_96_24 = 0x0C
    DTS_HD_MASTER_AUDIO = 0x0D
    DTS_HD_HIGH_RES_AUDIO = 0x0E
    DTS_LOW_BIT_RATE = 0x0F
    DTS_CORE = 0x10
    PCM_ZERO = 0x13
    UNSUPPORTED = 0x14
    UNDETECTED = 0x15

    @staticmethod
    def from_int(value: int):
        try:
            return IncomingAudioFormat(value)
        except ValueError:
            return value

class IncomingAudioConfig(enum.IntEnum):
    """List of possible audio configurations."""
    MONO = 0x01
    CENTER_ONLY = 0x01
    STEREO_ONLY = 0x02
    # Incomplete list...

    @staticmethod
    def from_int(value: int):
        try:
            return IncomingAudioConfig(value)
        except ValueError:
            return value


class PresetType(enum.IntEnum):
    """List of possible audio configurations."""
    AM_FREQUENCY = 0x00
    FM_FREQUENCY = 0x01
    FM_RDS_NAME = 0x02
    DAB = 0x03

    @staticmethod
    def from_int(value: int):
        try:
            return PresetType(value)
        except ValueError:
            return value

@attr.s
class PresetDetail():
    index = attr.ib(type=int)
    type = attr.ib(type=PresetType)
    name = attr.ib(type=str)

    @staticmethod
    def from_bytes(data: bytes) -> 'PresetDetail':
        type = PresetType.from_int(data[1])
        if type == PresetType.FM_RDS_NAME or type == PresetType.DAB:
            name = data[2:].decode('utf8').rstrip()
        elif type == PresetType.FM_FREQUENCY:
            name = f"{data[2]}.{data[3]:2} MHz"
        elif type == PresetType.AM_FREQUENCY:
            name = f"{data[2]}{data[3]:2} kHz"
        else:
            name = str(data[2:])
        return PresetDetail(data[0], type, name)

@attr.s
class ResponsePacket():
    """Represent a response from device."""
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
class CommandPacket():
    """Represent a command sent to device."""
    zn = attr.ib(type=int)
    cc = attr.ib(type=int)
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
    try:
        start = await reader.read(1)
        if start == PROTOCOL_EOF:
            _LOGGER.debug("eof")
            return None

        if start != PROTOCOL_STR:
            raise InvalidPacket("unexpected str byte {}".format(start))

        header = await reader.read(header_len-1)
        data_len = await reader.read(1)
        data = await reader.read(int.from_bytes(data_len, 'big'))
        etr = await reader.read(1)

        if etr != PROTOCOL_ETR:
            raise InvalidPacket("unexpected etr byte {}".format(etr))

        packet = bytes([*start, *header, *data_len, *data, *etr])
        return packet
    except TimeoutError as exception:
        raise ConnectionFailed() from exception
    except ConnectionError as exception:
        raise ConnectionFailed() from exception
    except OSError as exception:
        raise ConnectionFailed() from exception


async def _read_delimited_retried(reader: asyncio.StreamReader, header_len: int) -> bytes:
    while True:
        try:
            data = await _read_delimited(reader, header_len)
        except InvalidPacket as e:
            _LOGGER.warning(str(e))
            continue
        return data

async def _read_packet(reader: asyncio.StreamReader) -> ResponsePacket:
    data = await _read_delimited_retried(reader, 4)
    if not data:
        return None
    return ResponsePacket.from_bytes(data)


async def _read_command_packet(reader: asyncio.StreamReader) -> CommandPacket:
    data = await _read_delimited_retried(reader, 3)
    if not data:
        return None
    return CommandPacket.from_bytes(data)


async def _write_packet(writer: asyncio.StreamWriter,
                        packet: Union[CommandPacket,
                                      ResponsePacket]) -> None:
    try:
        data = packet.to_bytes()
        writer.write(data)
        await asyncio.wait_for(writer.drain(), _WRITE_TIMEOUT)
    except asyncio.TimeoutError as exception:
        raise ConnectionFailed() from exception
    except ConnectionError as exception:
        raise ConnectionFailed() from exception
    except OSError as exception:
        raise ConnectionFailed() from exception
