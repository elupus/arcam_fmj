"""Arcam AV Control"""
import asyncio
import enum
import logging
import re
from asyncio.exceptions import IncompleteReadError
from typing import Dict, Iterable, Optional, SupportsBytes, Tuple, Type, TypeVar, Union

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

APIVERSION_450_SERIES = {"AVR380", "AVR450", "AVR750"}
APIVERSION_860_SERIES = {"AV860", "AVR850", "AVR550", "AVR390", "SR250"}
APIVERSION_DAB_SERIES = {"AVR450", "AVR750"}
APIVERSION_SA_SERIES = {"SA10", "SA20", "SA30"}

class ApiModel(enum.Enum):
    API450_SERIES = 1
    API860_SERIES = 2
    APISA_SERIES = 3

_T = TypeVar("_T", bound="IntOrTypeEnum")
class IntOrTypeEnum(enum.IntEnum):

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, int):
            return cls._create_pseudo_member_(value)
        return None

    @classmethod
    def _create_pseudo_member_(cls, value):
        pseudo_member = cls._value2member_map_.get(value, None)
        if pseudo_member is None:
            obj = int.__new__(cls, value)
            obj._name_ = f"CODE_{value}"
            obj._value_ = value
            obj.version = None
            pseudo_member = cls._value2member_map_.setdefault(value, obj)
        return pseudo_member

    def __new__(cls, value: int, version: Optional[tuple] = None):
             obj = int.__new__(cls, value)
             obj._value_ = value
             obj.version = version
             return obj

    @classmethod
    def from_int(cls: Type[_T], value: int) -> _T:
        return cls(value)

    @classmethod
    def from_bytes(cls: Type[_T], bytes: Union[Iterable[int], SupportsBytes], byteorder: str = 'big', *, signed: bool = False) -> _T:
        return cls.from_int(int.from_bytes(bytes, byteorder=byteorder, signed=signed))


class AnswerCodes(IntOrTypeEnum):
    STATUS_UPDATE = 0x00
    ZONE_INVALID = 0x82
    COMMAND_NOT_RECOGNISED = 0x83
    PARAMETER_NOT_RECOGNISED = 0x84
    COMMAND_INVALID_AT_THIS_TIME = 0x85
    INVALID_DATA_LENGTH = 0x86


class CommandCodes(IntOrTypeEnum):
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


class SourceCodes(IntOrTypeEnum):
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
    DAB = 0x0C, APIVERSION_DAB_SERIES
    NET = 0x0E
    USB = 0x0F
    STB = 0x10
    GAME = 0x11
    PHONO = 0x12
    ARC_ERC = 0x13


class MenuCodes(IntOrTypeEnum):
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


class DecodeMode2CH(IntOrTypeEnum):
    STEREO = 0x01
    DOLBY_PLII_IIx_MOVIE = 0x02, APIVERSION_450_SERIES
    DOLBY_PLII_IIx_MUSIC = 0x03, APIVERSION_450_SERIES
    DOLBY_PLII_IIx_GAME = 0x05, APIVERSION_450_SERIES
    DOLBY_PL = 0x06, APIVERSION_450_SERIES
    DTS_NEO_6_CINEMA = 0x07
    DTS_NEO_6_MUSIC = 0x08
    MCH_STEREO = 0x09

    DTS_NEURAL_X = 0x0A, APIVERSION_860_SERIES
    DTS_VIRTUAL_X = 0x0C, APIVERSION_860_SERIES


class DecodeModeMCH(IntOrTypeEnum):
    STEREO_DOWNMIX = 0x01
    MULTI_CHANNEL = 0x02

    # This is used for DTS_NEURAL_X on 860 series
    DOLBY_D_EX_OR_DTS_ES = 0x03

    DOLBY_PLII_IIx_MOVIE = 0x04, APIVERSION_450_SERIES
    DOLBY_PLII_IIx_MUSIC = 0x05, APIVERSION_450_SERIES

    DOLBY_SURROUND = 0x06, APIVERSION_860_SERIES
    DTS_VIRTUAL_X = 0x0C, APIVERSION_860_SERIES


POWER_WRITE_SUPPORTED = {
    ApiModel.APISA_SERIES
}

RC5CODE_DECODE_MODE_MCH: Dict[Tuple[ApiModel, int], Dict[DecodeModeMCH, bytes]] = {
    (ApiModel.API450_SERIES, 1): {
        DecodeModeMCH.STEREO_DOWNMIX: bytes([16, 107]),
        DecodeModeMCH.MULTI_CHANNEL: bytes([16, 106]),
        DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES: bytes([16, 118]),
        DecodeModeMCH.DOLBY_PLII_IIx_MOVIE: bytes([16, 103]),
        DecodeModeMCH.DOLBY_PLII_IIx_MUSIC: bytes([16, 104]),
    },
    (ApiModel.API450_SERIES, 2): {},
    (ApiModel.API860_SERIES, 1): {
        DecodeModeMCH.STEREO_DOWNMIX: bytes([16, 107]),
        DecodeModeMCH.MULTI_CHANNEL: bytes([16, 106]),

        # We map to DTS_NEURAL_X
        DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES: bytes([16, 113]),

        DecodeModeMCH.DOLBY_SURROUND: bytes([16, 110]),
        DecodeModeMCH.DTS_VIRTUAL_X: bytes([16, 115]),
    },
    (ApiModel.API860_SERIES, 2): {},
    (ApiModel.APISA_SERIES, 1): {},
    (ApiModel.APISA_SERIES, 2): {},
}

RC5CODE_DECODE_MODE_2CH: Dict[Tuple[ApiModel, int], Dict[DecodeMode2CH, bytes]]  = {
    (ApiModel.API450_SERIES, 1): {
        DecodeMode2CH.STEREO: bytes([16, 107]),
        DecodeMode2CH.DOLBY_PLII_IIx_MOVIE: bytes([16, 103]),
        DecodeMode2CH.DOLBY_PLII_IIx_MUSIC: bytes([16, 104]),
        DecodeMode2CH.DOLBY_PLII_IIx_GAME: bytes([16, 102]),
        DecodeMode2CH.DOLBY_PL: bytes([16, 110]),
        DecodeMode2CH.DTS_NEO_6_CINEMA: bytes([16, 111]),
        DecodeMode2CH.DTS_NEO_6_MUSIC: bytes([16, 112]),
        DecodeMode2CH.MCH_STEREO: bytes([16, 69]),
    },
    (ApiModel.API450_SERIES, 2): {},
    (ApiModel.API860_SERIES, 1): {
        DecodeMode2CH.STEREO: bytes([16, 107]),
        DecodeMode2CH.DTS_NEURAL_X: bytes([16, 113]),
        DecodeMode2CH.DTS_VIRTUAL_X: bytes([16, 115]),
        DecodeMode2CH.DOLBY_PL: bytes([16, 110]),
        DecodeMode2CH.DTS_NEO_6_CINEMA: bytes([16, 111]),
        DecodeMode2CH.DTS_NEO_6_MUSIC: bytes([16, 112]),
        DecodeMode2CH.MCH_STEREO: bytes([16, 69]),
    },
    (ApiModel.API860_SERIES, 2): {},
    (ApiModel.APISA_SERIES, 1): {},
    (ApiModel.APISA_SERIES, 2): {},

}

RC5CODE_SOURCE = {
    (ApiModel.API450_SERIES, 1): {
        SourceCodes.STB: bytes([16, 1]),
        SourceCodes.AV: bytes([16, 2]),
        SourceCodes.DAB: bytes([16, 72]),
        SourceCodes.FM: bytes([16, 54]),
        SourceCodes.BD: bytes([16, 4]),
        SourceCodes.GAME: bytes([16, 5]),
        SourceCodes.VCR: bytes([16, 6]),
        SourceCodes.CD: bytes([16, 7]),
        SourceCodes.AUX: bytes([16, 8]),
        SourceCodes.DISPLAY: bytes([16, 9]),
        SourceCodes.SAT: bytes([16, 0]),
        SourceCodes.PVR: bytes([16, 34]),
        SourceCodes.USB: bytes([16, 18]),
        SourceCodes.NET: bytes([16, 11]),
    },
    (ApiModel.API450_SERIES, 2): {
        SourceCodes.STB: bytes([23, 8]),
        SourceCodes.AV: bytes([23, 9]),
        SourceCodes.DAB: bytes([23, 16]),
        SourceCodes.FM: bytes([23, 14]),
        SourceCodes.BD: bytes([23, 7]),
        SourceCodes.GAME: bytes([23, 11]),
        SourceCodes.CD: bytes([23, 6]),
        SourceCodes.AUX: bytes([23, 13]),
        SourceCodes.PVR: bytes([23, 15]),
        SourceCodes.USB: bytes([23, 18]),
        SourceCodes.NET: bytes([23, 19]),
        SourceCodes.FOLLOW_ZONE_1: bytes([16, 20])
    },
    (ApiModel.API860_SERIES, 1): {
        SourceCodes.STB: bytes([16, 100]),
        SourceCodes.AV: bytes([16, 94]),
        SourceCodes.DAB: bytes([16, 72]),
        SourceCodes.FM: bytes([16, 28]),
        SourceCodes.BD: bytes([16, 98]),
        SourceCodes.GAME: bytes([16, 97]),
        SourceCodes.VCR: bytes([16, 119]),
        SourceCodes.CD: bytes([16, 118]),
        SourceCodes.AUX: bytes([16, 99]),
        SourceCodes.DISPLAY: bytes([16, 58]),
        SourceCodes.SAT: bytes([16, 27]),
        SourceCodes.PVR: bytes([16, 96]),
        SourceCodes.USB: bytes([16, 93]),
        SourceCodes.NET: bytes([16, 92]),
    },
    (ApiModel.API860_SERIES, 2): {
        SourceCodes.STB: bytes([23, 8]),
        SourceCodes.AV: bytes([23, 9]),
        SourceCodes.DAB: bytes([23, 16]),
        SourceCodes.FM: bytes([23, 14]),
        SourceCodes.BD: bytes([23, 7]),
        SourceCodes.GAME: bytes([23, 11]),
        SourceCodes.CD: bytes([23, 6]),
        SourceCodes.AUX: bytes([23, 13]),
        SourceCodes.PVR: bytes([23, 15]),
        SourceCodes.USB: bytes([23, 18]),
        SourceCodes.NET: bytes([23, 19]),
        SourceCodes.SAT: bytes([16, 20]),
        SourceCodes.VCR: bytes([16, 21]),
        SourceCodes.FOLLOW_ZONE_1: bytes([16, 20])
    },
    (ApiModel.APISA_SERIES, 1): {
        SourceCodes.PHONO: bytes([16, 117]),
        SourceCodes.CD: bytes([16, 118]),
        SourceCodes.BD: bytes([16, 98]),
        SourceCodes.SAT: bytes([16, 27]),
        SourceCodes.PVR: bytes([16, 96]),
        SourceCodes.AV: bytes([16, 94]),
        SourceCodes.AUX: bytes([16, 99]),
        SourceCodes.STB: bytes([16, 100]),
        SourceCodes.NET: bytes([16, 92]),
        SourceCodes.USB: bytes([16, 93]),
        SourceCodes.GAME: bytes([16, 97]),
        SourceCodes.ARC_ERC: bytes([16, 125])
    },
    (ApiModel.APISA_SERIES, 2): {
        SourceCodes.PHONO: bytes([16, 117]),
        SourceCodes.CD: bytes([16, 118]),
        SourceCodes.BD: bytes([16, 98]),
        SourceCodes.SAT: bytes([16, 27]),
        SourceCodes.PVR: bytes([16, 96]),
        SourceCodes.AV: bytes([16, 94]),
        SourceCodes.AUX: bytes([16, 99]),
        SourceCodes.STB: bytes([16, 100]),
        SourceCodes.NET: bytes([16, 92]),
        SourceCodes.USB: bytes([16, 93]),
        SourceCodes.GAME: bytes([16, 97]),
        SourceCodes.ARC_ERC: bytes([16, 125])
    }
}

RC5CODE_POWER = {
    (ApiModel.API450_SERIES, 1): {
        True: bytes([16, 123]),
        False: bytes([16, 124])
    },
    (ApiModel.API450_SERIES, 2): {
        True: bytes([23, 123]),
        False: bytes([23, 124])
    },
    (ApiModel.API860_SERIES, 1): {
        True: bytes([16, 123]),
        False: bytes([16, 124])
    },
    (ApiModel.API860_SERIES, 2): {
        True: bytes([23, 123]),
        False: bytes([23, 124])
    },
    (ApiModel.APISA_SERIES, 1): {
        True: bytes([16, 123]),
        False: bytes([16, 124])
    },
    (ApiModel.APISA_SERIES, 2): {
        True: bytes([16, 123]),
        False: bytes([16, 124])
    }
}

RC5CODE_MUTE = {
    (ApiModel.API450_SERIES, 1): {
        True: bytes([16, 119]),
        False: bytes([16, 120]),
    },
    (ApiModel.API450_SERIES, 2): {
        True: bytes([23, 4]),
        False: bytes([23, 5]),
    },
    (ApiModel.API860_SERIES, 1): {
        True: bytes([16, 26]),
        False: bytes([16, 120]),
    },
    (ApiModel.API860_SERIES, 2): {
        True: bytes([23, 4]),
        False: bytes([23, 5]),
    },
    (ApiModel.APISA_SERIES, 1): {
        True: bytes([16, 26]),
        False: bytes([16, 120]),
    },
    (ApiModel.APISA_SERIES, 2): {
        True: bytes([16, 26]),
        False: bytes([16, 120]),
    }
}

RC5CODE_VOLUME = {
    (ApiModel.API450_SERIES, 1): {
        True: bytes([16, 16]),
        False: bytes([16, 17]),
    },
    (ApiModel.API450_SERIES, 2): {
        True: bytes([23, 1]),
        False: bytes([23, 2]),
    },
    (ApiModel.API860_SERIES, 1): {
        True: bytes([16, 16]),
        False: bytes([16, 17]),
    },
    (ApiModel.API860_SERIES, 2): {
        True: bytes([23, 1]),
        False: bytes([23, 2]),
    },
    (ApiModel.APISA_SERIES, 1): {
        True: bytes([16, 16]),
        False: bytes([16, 17]),
    },
    (ApiModel.APISA_SERIES, 2): {
        True: bytes([16, 16]),
        False: bytes([16, 17]),
    }
}

class IncomingAudioFormat(IntOrTypeEnum):
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


class IncomingAudioConfig(IntOrTypeEnum):
    """List of possible audio configurations."""
    MONO = 0x01
    CENTER_ONLY = 0x01
    STEREO_ONLY = 0x02
    # Incomplete list...


class PresetType(IntOrTypeEnum):
    """List of possible audio configurations."""
    AM_FREQUENCY = 0x00
    FM_FREQUENCY = 0x01
    FM_RDS_NAME = 0x02
    DAB = 0x03

@attr.s
class PresetDetail():
    index = attr.ib(type=int)
    type = attr.ib(type=Union[PresetType, int])
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

    def respons_to(self, request: Union['AmxDuetRequest', 'CommandPacket']):
        if not isinstance(request, CommandPacket):
            return False
        return (self.zn == request.zn and
            self.cc == request.cc)

    @staticmethod
    def from_bytes(data: bytes) -> 'ResponsePacket':
        if len(data) < 6:
            raise InvalidPacket("Packet to short {!r}".format(data))

        if data[4] != len(data)-6:
            raise InvalidPacket("Invalid length in data {!r}".format(data))

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
            raise InvalidPacket("Packet to short {!r}".format(data))

        if data[3] != len(data)-5:
            raise InvalidPacket("Invalid length in data {!r}".format(data))

        return CommandPacket(
            data[1],
            CommandCodes.from_int(data[2]),
            data[4:4+data[3]])

@attr.s
class AmxDuetRequest():
    
    @staticmethod
    def from_bytes(data: bytes) -> 'AmxDuetRequest':
        if not data == b"AMX\r":
            raise InvalidPacket("Packet is not a amx request {!r}".format(data))
        return AmxDuetRequest()

    def to_bytes(self):
        return b"AMX\r"

@attr.s
class AmxDuetResponse():

    values = attr.ib(type=dict)

    @property
    def device_class(self) -> Optional[str]:
        return self.values.get("Device-SDKClass")

    @property
    def device_make(self) -> Optional[str]:
        return self.values.get("Device-Make")

    @property
    def device_model(self) -> Optional[str]:
        return self.values.get("Device-Model")

    @property
    def device_revision(self) -> Optional[str]:
        return self.values.get("Device-Revision")

    def respons_to(self, packet: Union[AmxDuetRequest, CommandPacket]):
        if not isinstance(packet, AmxDuetRequest):
            return False
        return True

    @staticmethod
    def from_bytes(data: bytes) -> 'AmxDuetResponse':
        if not data.startswith(b"AMXB"):
            raise InvalidPacket("Packet is not a amx response {!r}".format(data))

        tags = re.findall(r"<(.+?)=(.+?)>", data[4:].decode("ASCII"))
        return AmxDuetResponse(dict(tags))

    def to_bytes(self):
        res = "AMXB" + "".join([
            f"<{key}={value}>"
            for key, value in self.values.items() 
        ]) + "\r"
        return res.encode("ASCII")


async def _read_delimited(reader: asyncio.StreamReader, header_len) -> Optional[bytes]:
    try:
        start = await reader.read(1)
        if start == PROTOCOL_EOF:
            _LOGGER.debug("eof")
            return None

        if start == PROTOCOL_STR:
            header = await reader.read(header_len-1)
            data_len = await reader.read(1)
            data = await reader.read(int.from_bytes(data_len, 'big'))
            etr = await reader.read(1)

            if etr != PROTOCOL_ETR:
                raise InvalidPacket("unexpected etr byte {!r}".format(etr))

            packet = bytes([*start, *header, *data_len, *data, *etr])
        elif start == b"\x01":
            """Sometime the AMX header seem to be sent as \x01^AMX"""
            header = await reader.read(4)
            if header != b"^AMX":
                raise InvalidPacket("Unexpected AMX header: {!r}".format(header))
        
            data = await reader.readuntil(PROTOCOL_ETR)
            packet =  bytes([*b"AMX", *data])
        elif start == b"A":
            header = await reader.read(2)
            if header != b"MX":
                raise InvalidPacket("Unexpected AMX header")

            data = await reader.readuntil(PROTOCOL_ETR)
            packet =  bytes([*start, *header, *data])
        else:
            raise InvalidPacket("unexpected str byte {!r}".format(start))

        return packet

    except TimeoutError as exception:
        raise ConnectionFailed() from exception
    except ConnectionError as exception:
        raise ConnectionFailed() from exception
    except OSError as exception:
        raise ConnectionFailed() from exception
    except IncompleteReadError as exception:
        raise ConnectionFailed() from exception


async def _read_response(reader: asyncio.StreamReader) -> Optional[Union[ResponsePacket, AmxDuetResponse]]:
    data = await _read_delimited(reader, 4)
    if not data:
        return None

    if data.startswith(b"AMX"):
        return AmxDuetResponse.from_bytes(data)
    else:
        return ResponsePacket.from_bytes(data)


async def read_response(reader: asyncio.StreamReader) -> Optional[Union[ResponsePacket, AmxDuetResponse]]:
    while True:
        try:
            data = await _read_response(reader)
        except InvalidPacket as e:
            _LOGGER.warning(str(e))
            continue
        return data


async def _read_command(reader: asyncio.StreamReader) -> Optional[Union[CommandPacket, AmxDuetRequest]]:
    data = await _read_delimited(reader, 3)
    if not data:
        return None
    if data.startswith(b"AMX"):
        return AmxDuetRequest.from_bytes(data)
    else:
        return CommandPacket.from_bytes(data)


async def read_command(reader: asyncio.StreamReader) -> Optional[Union[CommandPacket, AmxDuetRequest]]:
    while True:
        try:
            data = await _read_command(reader)
        except InvalidPacket as e:
            _LOGGER.warning(str(e))
            continue
        return data


async def write_packet(writer: asyncio.StreamWriter,
                       packet: Union[CommandPacket,
                                     ResponsePacket,
                                     AmxDuetRequest,
                                     AmxDuetResponse]) -> None:
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
