"""Arcam AV Control"""

import asyncio
import enum
import logging
import re
from asyncio.exceptions import IncompleteReadError
from typing import (
    Any,
    SupportsBytes,
    TypeVar,
    Union,
    Literal,
    SupportsIndex,
)
from collections.abc import Iterable

import attr

PROTOCOL_STR = b"\x21"
PROTOCOL_ETR = b"\x0d"
PROTOCOL_EOF = b""

_LOGGER = logging.getLogger(__name__)
_WRITE_TIMEOUT = 3
_READ_TIMEOUT = 3


class ArcamException(Exception):
    pass


class ConnectionFailed(ArcamException):
    pass


class NotConnectedException(ArcamException):
    pass


class UnsupportedZone(ArcamException):
    pass


class ResponseException(ArcamException):
    def __init__(self, ac=None, zn=None, cc=None, data=None):
        self.ac = ac
        self.zn = zn
        self.cc = cc
        self.data = data
        super().__init__(f"'ac':{ac}, 'zn':{zn}, 'cc':{cc}, 'data':{data}")

    @staticmethod
    def from_response(response: "ResponsePacket"):
        kwargs = {"zn": response.zn, "cc": response.cc, "data": response.data}
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
        super().__init__(ac=AnswerCodes.ZONE_INVALID, zn=zn, cc=cc, data=data)


class CommandNotRecognised(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.COMMAND_NOT_RECOGNISED, zn=zn, cc=cc, data=data)


class ParameterNotRecognised(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(
            ac=AnswerCodes.PARAMETER_NOT_RECOGNISED, zn=zn, cc=cc, data=data
        )


class CommandInvalidAtThisTime(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(
            ac=AnswerCodes.COMMAND_INVALID_AT_THIS_TIME, zn=zn, cc=cc, data=data
        )


class InvalidDataLength(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.INVALID_DATA_LENGTH, zn=zn, cc=cc, data=data)


class InvalidPacket(ArcamException):
    pass


class NullPacket(ArcamException):
    pass


APIVERSION_450_SERIES = {"AVR380", "AVR450", "AVR750"}
APIVERSION_860_SERIES = {
    "AV860",
    "AVR850",
    "AVR550",
    "AVR390",
    "SR250",
}
APIVERSION_LEXICON_SERIES = {"RV-6", "RV-9", "MC-10"}
APIVERSION_SA_SERIES = {"SA10", "SA20", "SA30", "SA750"}
APIVERSION_HDA_SERIES = {
    "AVR5",
    "AVR10",
    "AVR20",
    "AVR30",
    "AV40",
    "AVR11",
    "AVR21",
    "AVR31",
    "AV41",
    "SDP-55",
    "SDP-58",
}
APIVERSION_HDA_PREMIUM_SERIES = {
    "AVR10",
    "AVR20",
    "AVR30",
    "AV40",
    "AVR11",
    "AVR21",
    "AVR31",
    "AV41",
    "SDP-55",
    "SDP-58",
}
APIVERSION_HDA_MULTI_ZONE_SERIES = {
    "AVR20",
    "AVR30",
    "AV40",
    "AVR21",
    "AVR31",
    "AV41",
    "SDP-55",
    "SDP-58",
}
APIVERSION_PA_SERIES = {"PA720", "PA240", "PA410"}
APIVERSION_ST_SERIES = {"ST60"}

APIVERSION_DAB_SERIES = {"AVR450", "AVR750"}
APIVERSION_DAB_SERIES.update(
    "AV860", "AVR850", "AVR550", "AVR390"
)
APIVERSION_DAB_SERIES.update(APIVERSION_LEXICON_SERIES)
APIVERSION_DAB_SERIES.update(APIVERSION_HDA_SERIES)

APIVERSION_ZONE2_SERIES = set()
APIVERSION_ZONE2_SERIES.update(APIVERSION_450_SERIES)
APIVERSION_ZONE2_SERIES.update(APIVERSION_860_SERIES)
APIVERSION_ZONE2_SERIES.update(APIVERSION_LEXICON_SERIES)
APIVERSION_ZONE2_SERIES.update(APIVERSION_HDA_MULTI_ZONE_SERIES)

APIVERSION_DOLBY_PL_SERIES = APIVERSION_450_SERIES

APIVERSION_DOLBY_SURROUND_SERIES = set()
APIVERSION_DOLBY_SURROUND_SERIES.update(APIVERSION_860_SERIES)
APIVERSION_DOLBY_SURROUND_SERIES.update(APIVERSION_LEXICON_SERIES)
APIVERSION_DOLBY_SURROUND_SERIES.update(APIVERSION_HDA_SERIES)

APIVERSION_DOLBY_ATMOS_SERIES = set()
APIVERSION_DOLBY_ATMOS_SERIES.update(APIVERSION_860_SERIES)
APIVERSION_DOLBY_ATMOS_SERIES.update(APIVERSION_LEXICON_SERIES)
APIVERSION_DOLBY_ATMOS_SERIES.update(APIVERSION_HDA_SERIES)

APIVERSION_DOLBY_VIRT_H_SERIES = APIVERSION_HDA_SERIES

APIVERSION_DTS_X_SERIES = APIVERSION_DOLBY_SURROUND_SERIES

APIVERSION_AURO_SERIES = APIVERSION_HDA_PREMIUM_SERIES

APIVERSION_IMAX_SERIES = set()
APIVERSION_IMAX_SERIES.update(APIVERSION_860_SERIES)
APIVERSION_IMAX_SERIES.update(APIVERSION_LEXICON_SERIES)
APIVERSION_IMAX_SERIES.update(APIVERSION_HDA_PREMIUM_SERIES)

APIVERSION_AMP_DIAGNOSTICS_SERIES = set()
APIVERSION_AMP_DIAGNOSTICS_SERIES.update(APIVERSION_SA_SERIES)
APIVERSION_AMP_DIAGNOSTICS_SERIES.update(APIVERSION_PA_SERIES)

APIVERSION_CLASS_G_SERIES = {"PA720", "PA240", "SA20", "SA30", "SA750"}

APIVERSION_PHONO_SERIES = {"SA30", "SA750"}

APIVERSION_SIMPLE_IP_SERIES = {"PA720", "PA240", "SA10", "SA20"}

APIVERSION_APP_SAFETY_SERIES = {"SA30", "SA750"}

class ApiModel(enum.Enum):
    API450_SERIES = 1
    API860_SERIES = 2
    APISA_SERIES = 3
    APIHDA_SERIES = 4
    APIPA_SERIES = 5
    APIST_SERIES = 6
    APILEXICON_SERIES = 7


_T = TypeVar("_T", bound="IntOrTypeEnum")


class EnumFlags(enum.IntFlag):
    ZONE_SUPPORT = enum.auto()
    SEND_ONLY = enum.auto()


class IntOrTypeEnum(enum.IntEnum):
    version: set[str] | None
    flags: EnumFlags

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, int):
            return cls._create_member(value)
        return None

    @classmethod
    def _create_member(cls, value):
        pseudo_member = cls._value2member_map_.get(value, None)
        if pseudo_member is None:
            obj = int.__new__(cls, value)
            obj._name_ = f"CODE_{value}"
            obj._value_ = value
            obj.version = None
            obj.flags = EnumFlags(0)
            pseudo_member = cls._value2member_map_.setdefault(value, obj)
        return pseudo_member

    def __new__(cls, value: int, version: set[str] | None = None, flags=EnumFlags(0)):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.version = version
        obj.flags = flags
        return obj

    @classmethod
    def from_int(cls: type[_T], value: int) -> _T:
        return cls(value)

    @classmethod
    def from_bytes(
        cls: type[_T],
        bytes: Iterable[SupportsIndex] | SupportsBytes,
        byteorder: Literal["little", "big"] = "big",
        *,
        signed: bool = False,
    ) -> _T:  # type: ignore[override]
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
    POWER = 0x00, None, EnumFlags.ZONE_SUPPORT
    DISPLAY_BRIGHTNESS = 0x01
    HEADPHONES = 0x02
    FMGENRE = 0x03, None, EnumFlags.ZONE_SUPPORT
    SOFTWARE_VERSION = 0x04
    RESTORE_FACTORY_DEFAULT = 0x05
    SAVE_RESTORE_COPY_OF_SETTINGS = 0x06
    SIMULATE_RC5_IR_COMMAND = 0x08, None, EnumFlags.ZONE_SUPPORT | EnumFlags.SEND_ONLY
    DISPLAY_INFORMATION_TYPE = 0x09, None, EnumFlags.ZONE_SUPPORT
    CURRENT_SOURCE = 0x1D, None, EnumFlags.ZONE_SUPPORT  # Request
    HEADPHONES_OVERRIDE = 0x1F, None, EnumFlags.ZONE_SUPPORT

    # Input Commands
    VIDEO_SELECTION = 0x0A
    SELECT_ANALOG_DIGITAL = 0x0B
    VIDEO_INPUT_TYPE = 0x0C  # IMAX_ENHANCED on 860 and HDA Series (not AVR5)


    # Output Commands
    VOLUME = 0x0D, None, EnumFlags.ZONE_SUPPORT  # Set/Request
    MUTE = 0x0E, None, EnumFlags.ZONE_SUPPORT  # Request
    DIRECT_MODE_STATUS = 0x0F  # Request
    DECODE_MODE_STATUS_2CH = 0x10  # Request
    DECODE_MODE_STATUS_MCH = 0x11  # Request
    RDS_INFORMATION = 0x12, None, EnumFlags.ZONE_SUPPORT  # Request
    VIDEO_OUTPUT_RESOLUTION = 0x13  # Set/Request

    # Menu Command
    MENU = 0x14  # Request
    TUNER_PRESET = 0x15, None, EnumFlags.ZONE_SUPPORT  # Set/Request
    TUNE = 0x16, None, EnumFlags.ZONE_SUPPORT  # Set/Request
    DAB_STATION = 0x18, None, EnumFlags.ZONE_SUPPORT  # Set/Request
    DAB_PROGRAM_TYPE_CATEGORY = 0x19, None, EnumFlags.ZONE_SUPPORT  # Set/Request
    DLS_PDT_INFO = 0x1A, None, EnumFlags.ZONE_SUPPORT  # Request
    PRESET_DETAIL = 0x1B, None, EnumFlags.ZONE_SUPPORT  # Request
    NETWORK_PLAYBACK_STATUS = 0x1C, APIVERSION_HDA_SERIES  # Request

    # Network Command

    # Setup
    TREBLE_EQUALIZATION = 0x35, None, EnumFlags.ZONE_SUPPORT
    BASS_EQUALIZATION = 0x36, None, EnumFlags.ZONE_SUPPORT
    ROOM_EQUALIZATION = 0x37, None, EnumFlags.ZONE_SUPPORT
    DOLBY_VOLUME = 0x38, None, EnumFlags.ZONE_SUPPORT  # DOLBY_AUDIO on HDA series
    DOLBY_LEVELER = 0x39, None, EnumFlags.ZONE_SUPPORT
    DOLBY_VOLUME_CALIBRATION_OFFSET = 0x3A, None, EnumFlags.ZONE_SUPPORT
    BALANCE = 0x3B, None, EnumFlags.ZONE_SUPPORT

    DOLBY_PLII_X_MUSIC_DIMENSION = 0x3C
    DOLBY_PLII_X_MUSIC_CENTRE_WIDTH = 0x3D
    DOLBY_PLII_X_MUSIC_PANORAMA = 0x3E
    SUBWOOFER_TRIM = 0x3F, None, EnumFlags.ZONE_SUPPORT
    LIPSYNC_DELAY = 0x40, None, EnumFlags.ZONE_SUPPORT
    COMPRESSION = 0x41, None, EnumFlags.ZONE_SUPPORT

    INCOMING_VIDEO_PARAMETERS = 0x42, None, EnumFlags.ZONE_SUPPORT
    INCOMING_AUDIO_FORMAT = 0x43, None, EnumFlags.ZONE_SUPPORT
    INCOMING_AUDIO_SAMPLE_RATE = 0x44, None, EnumFlags.ZONE_SUPPORT

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
    VIDEO_OUTPUT_FRAME_RATE = 0x50  # Set/Request BLUETOOTH_STATUS on HDA series

    # 2.0 Commands
    INPUT_NAME = 0x20  # Set/Request
    FM_SCAN = 0x23
    DAB_SCAN = 0x24
    HEARTBEAT = 0x25
    REBOOT = 0x26
    SETUP = 0x27, APIVERSION_HDA_SERIES
    ROOM_EQ_NAMES = 0x34, APIVERSION_HDA_SERIES
    NOW_PLAYING_INFO = 0x64, APIVERSION_HDA_SERIES, EnumFlags.ZONE_SUPPORT
    INPUT_CONFIG = 0x28, APIVERSION_HDA_SERIES
    GENERAL_SETUP = 0x29, APIVERSION_HDA_SERIES
    SPEAKER_TYPES = 0x2A, APIVERSION_HDA_SERIES
    SPEAKER_DISTANCES = 0x2B, APIVERSION_HDA_SERIES
    SPEAKER_LEVELS = 0x2C, APIVERSION_HDA_SERIES
    VIDEO_INPUTS = 0x2D, APIVERSION_HDA_SERIES
    HDMI_SETTINGS = 0x2E, APIVERSION_HDA_SERIES
    ZONE_SETTINGS = 0x2F, APIVERSION_HDA_MULTI_ZONE_SERIES
    NETWORK_MENU_INFO = 0x30, APIVERSION_HDA_SERIES
    BLUETOOTH_MENU_INFO = 0x32, APIVERSION_HDA_SERIES
    ENGINEERING_MENU_INFO = 0x33, APIVERSION_HDA_SERIES

    # Amp Diagnostics
    DC_OFFSET = 0x51, APIVERSION_AMP_DIAGNOSTICS_SERIES
    SHORT_CIRCUIT_STATUS = 0x52, APIVERSION_CLASS_G_SERIES
    TIMEOUT_COUNTER = 0x55, APIVERSION_AMP_DIAGNOSTICS_SERIES
    LIFTER_TEMPERATURE = (
        0x56,
        APIVERSION_CLASS_G_SERIES,
    )  # Bug in PA720 1.8 firmware - does not return sensor id
    OUTPUT_TEMPERATURE = (
        0x57,
        APIVERSION_AMP_DIAGNOSTICS_SERIES,
    )  # Bug in PA720 1.8 firmware - does not return sensor id
    AUTO_SHUTDOWN_CONTROL = 0x58, APIVERSION_AMP_DIAGNOSTICS_SERIES

    # Status/Diagnostics
    FRIENDLY_NAME = 0x53, APIVERSION_SIMPLE_IP_SERIES
    IP_ADDRESS = 0x54, APIVERSION_SIMPLE_IP_SERIES
    PHONO_INPUT_TYPE = 0x59, APIVERSION_PHONO_SERIES
    INPUT_DETECT = 0x5A, APIVERSION_AMP_DIAGNOSTICS_SERIES
    PROCESSOR_MODE_INPUT = 0x5B, APIVERSION_SA_SERIES
    PROCESSOR_MODE_VOLUME = 0x5C, APIVERSION_SA_SERIES
    SYSTEM_STATUS = 0x5D, APIVERSION_AMP_DIAGNOSTICS_SERIES
    SYSTEM_MODEL = 0x5E, APIVERSION_AMP_DIAGNOSTICS_SERIES
    DAC_FILTER = 0x61, APIVERSION_SA_SERIES  # Clashes with AMPLIFIER_MODE on PA240
    MAXIMUM_TURN_ON_VOLUME = 0x65, APIVERSION_APP_SAFETY_SERIES
    MAXIMUM_VOLUME = 0x66, APIVERSION_APP_SAFETY_SERIES
    MAXIMUM_STREAMING_VOLUME = 0x67, APIVERSION_APP_SAFETY_SERIES


class SourceCodes(enum.Enum):
    FOLLOW_ZONE_1 = enum.auto()
    CD = enum.auto()
    BD = enum.auto()
    AV = enum.auto()
    SAT = enum.auto()
    PVR = enum.auto()
    VCR = enum.auto()
    AUX = enum.auto()
    DISPLAY = enum.auto()
    FM = enum.auto()
    DAB = enum.auto()
    NET = enum.auto()
    USB = enum.auto()
    STB = enum.auto()
    GAME = enum.auto()
    PHONO = enum.auto()
    ARC_ERC = enum.auto()
    UHD = enum.auto()
    BT = enum.auto()
    DIG1 = enum.auto()
    DIG2 = enum.auto()
    DIG3 = enum.auto()
    DIG4 = enum.auto()
    NET_USB = enum.auto()

    @classmethod
    def from_bytes(cls, data: bytes, model: ApiModel, zn: int) -> "SourceCodes":
        try:
            table = SOURCE_CODES[(model, zn)]
        except KeyError:
            raise ValueError(f"Unknown source map for model {model} and zone {zn}")
        for key, value in table.items():
            if value == data:
                return key
        raise ValueError(
            "Unknown source code for model {} and zone {} and value {!r}".format(
                model, zn, data
            )
        )

    def to_bytes(self, model: ApiModel, zn: int):
        try:
            table = SOURCE_CODES[(model, zn)]
        except KeyError:
            raise ValueError(f"Unknown source map for model {model} and zone {zn}")
        if data := table.get(self):
            return data
        raise ValueError(
            "Unknown byte code for model {} and zone {} and value {}".format(
                model, zn, self
            )
        )


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


class MenuNavigationCodes(IntOrTypeEnum):
    MENU = 0x52
    UP = 0x56
    DOWN = 0x55
    LEFT = 0x51
    RIGHT = 0x50
    OK = 0x57


class DecodeMode2CH(IntOrTypeEnum):
    STEREO = 0x01
    DOLBY_PLII_IIx_MOVIE = 0x02, APIVERSION_DOLBY_PL_SERIES
    DOLBY_PLII_IIx_MUSIC = 0x03, APIVERSION_DOLBY_PL_SERIES
    DOLBY_SURROUND = 0x04, APIVERSION_DOLBY_SURROUND_SERIES
    DOLBY_PLII_IIx_GAME = 0x05, APIVERSION_DOLBY_PL_SERIES
    DOLBY_PL = 0x06, APIVERSION_DOLBY_PL_SERIES
    DTS_NEO_6_CINEMA = 0x07
    DTS_NEO_6_MUSIC = 0x08
    MCH_STEREO = 0x09

    DTS_NEURAL_X = 0x0A, APIVERSION_DTS_X_SERIES
    LOGIC7_IMMERSION = 0x0B, APIVERSION_LEXICON_SERIES
    DTS_VIRTUAL_X = 0x0C, APIVERSION_DTS_X_SERIES

    DOLBY_VIRTUAL_HEIGHT = 0x0D, APIVERSION_DOLBY_VIRT_H_SERIES
    AURO_NATIVE = 0x0E, APIVERSION_AURO_SERIES
    AURO_MATIC_3D = 0x0F, APIVERSION_AURO_SERIES
    AURO_2D = 0x10, APIVERSION_AURO_SERIES


class DecodeModeMCH(IntOrTypeEnum):
    STEREO_DOWNMIX = 0x01
    MULTI_CHANNEL = 0x02

    # This is used for DTS_NEURAL_X on 860 series and HDA series
    DOLBY_D_EX_OR_DTS_ES = 0x03

    DOLBY_PLII_IIx_MOVIE = 0x04, APIVERSION_DOLBY_PL_SERIES
    DOLBY_PLII_IIx_MUSIC = 0x05, APIVERSION_DOLBY_PL_SERIES

    DOLBY_SURROUND = 0x06, APIVERSION_DOLBY_SURROUND_SERIES
    LOGIC7_IMMERSION = 0x0B, APIVERSION_LEXICON_SERIES
    DTS_VIRTUAL_X = 0x0C, APIVERSION_DTS_X_SERIES

    DOLBY_VIRTUAL_HEIGHT = 0x0D, APIVERSION_DOLBY_VIRT_H_SERIES
    AURO_NATIVE = 0x0E, APIVERSION_AURO_SERIES
    AURO_MATIC_3D = 0x0F, APIVERSION_AURO_SERIES
    AURO_2D = 0x10, APIVERSION_AURO_SERIES


POWER_WRITE_SUPPORTED = {
    ApiModel.APISA_SERIES,
    ApiModel.APIPA_SERIES,
    ApiModel.APIST_SERIES,
}

MUTE_WRITE_SUPPORTED = POWER_WRITE_SUPPORTED

SOURCE_WRITE_SUPPORTED = {
    ApiModel.APISA_SERIES,
}

VOLUME_STEP_SUPPORTED = {
    ApiModel.APIST_SERIES,
}

DEFAULT_SOURCE_MAPPING = {
    SourceCodes.FOLLOW_ZONE_1: bytes([0x00]),
    SourceCodes.CD: bytes([0x01]),
    SourceCodes.BD: bytes([0x02]),
    SourceCodes.AV: bytes([0x03]),
    SourceCodes.SAT: bytes([0x04]),
    SourceCodes.PVR: bytes([0x05]),
    SourceCodes.VCR: bytes([0x06]),
    SourceCodes.AUX: bytes([0x08]),
    SourceCodes.DISPLAY: bytes([0x09]),
    SourceCodes.FM: bytes([0x0B]),
    SourceCodes.DAB: bytes([0x0C]),
    SourceCodes.NET: bytes([0x0E]),
    SourceCodes.USB: bytes([0x0F]),
    SourceCodes.STB: bytes([0x10]),
    SourceCodes.GAME: bytes([0x11]),
    SourceCodes.PHONO: bytes([0x12]),
    SourceCodes.ARC_ERC: bytes([0x13]),
}

HDA_SOURCE_MAPPING = {
    SourceCodes.FOLLOW_ZONE_1: bytes([0x00]),
    SourceCodes.CD: bytes([0x01]),
    SourceCodes.BD: bytes([0x02]),
    SourceCodes.AV: bytes([0x03]),
    SourceCodes.SAT: bytes([0x04]),
    SourceCodes.PVR: bytes([0x05]),
    SourceCodes.UHD: bytes([0x06]),
    SourceCodes.AUX: bytes([0x08]),
    SourceCodes.DISPLAY: bytes([0x09]),
    SourceCodes.FM: bytes([0x0B]),
    SourceCodes.DAB: bytes([0x0C]),
    SourceCodes.NET: bytes([0x0E]),
    SourceCodes.USB: bytes([0x0F]),
    SourceCodes.STB: bytes([0x10]),
    SourceCodes.GAME: bytes([0x11]),
    SourceCodes.BT: bytes([0x12]),
}

SA_SOURCE_MAPPING = {
    SourceCodes.PHONO: bytes([0x01]),
    SourceCodes.AUX: bytes([0x02]),
    SourceCodes.PVR: bytes([0x03]),
    SourceCodes.AV: bytes([0x04]),
    SourceCodes.STB: bytes([0x05]),
    SourceCodes.CD: bytes([0x06]),
    SourceCodes.BD: bytes([0x07]),
    SourceCodes.SAT: bytes([0x08]),
    SourceCodes.GAME: bytes([0x09]),
    SourceCodes.NET: bytes([0x0B]),
    SourceCodes.USB: bytes([0x0B]),
    SourceCodes.ARC_ERC: bytes([0x0D]),
}

ST_SOURCE_MAPPING = {
    SourceCodes.DIG1: bytes([0x01]),
    SourceCodes.DIG2: bytes([0x02]),
    SourceCodes.DIG3: bytes([0x03]),
    SourceCodes.DIG4: bytes([0x04]),
    SourceCodes.NET_USB: bytes([0x05]),
}

SOURCE_CODES = {
    (ApiModel.API450_SERIES, 1): DEFAULT_SOURCE_MAPPING,
    (ApiModel.API450_SERIES, 2): DEFAULT_SOURCE_MAPPING,
    (ApiModel.API860_SERIES, 1): DEFAULT_SOURCE_MAPPING,
    (ApiModel.API860_SERIES, 2): DEFAULT_SOURCE_MAPPING,
    (ApiModel.APILEXICON_SERIES, 1): DEFAULT_SOURCE_MAPPING,
    (ApiModel.APILEXICON_SERIES, 2): DEFAULT_SOURCE_MAPPING,
    (ApiModel.APIHDA_SERIES, 1): HDA_SOURCE_MAPPING,
    (ApiModel.APIHDA_SERIES, 2): HDA_SOURCE_MAPPING,
    (ApiModel.APISA_SERIES, 1): SA_SOURCE_MAPPING,
    (ApiModel.APISA_SERIES, 2): SA_SOURCE_MAPPING,
    (ApiModel.APIST_SERIES, 1): ST_SOURCE_MAPPING,
}

RC5CODE_DECODE_MODE_MCH: dict[tuple[ApiModel, int], dict[DecodeModeMCH, bytes]] = {
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
    (ApiModel.APILEXICON_SERIES, 1): {
        DecodeModeMCH.STEREO_DOWNMIX: bytes([16, 107]),
        DecodeModeMCH.MULTI_CHANNEL: bytes([16, 106]),
        # We map to DTS_NEURAL_X
        DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES: bytes([16, 113]),
        DecodeModeMCH.DOLBY_SURROUND: bytes([16, 110]),
        DecodeModeMCH.LOGIC7_IMMERSION: bytes([16, 114]),
        DecodeModeMCH.DTS_VIRTUAL_X: bytes([16, 115]),
    },
    (ApiModel.APILEXICON_SERIES, 2): {},
    (ApiModel.APIHDA_SERIES, 1): {
        DecodeModeMCH.STEREO_DOWNMIX: bytes([16, 107]),
        DecodeModeMCH.MULTI_CHANNEL: bytes([16, 106]),
        # We map to DTS_NEURAL_X
        DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES: bytes([16, 113]),
        DecodeModeMCH.DOLBY_SURROUND: bytes([16, 110]),
        DecodeModeMCH.DOLBY_VIRTUAL_HEIGHT: bytes([16, 115]),
        DecodeModeMCH.AURO_NATIVE: bytes([16, 103]),
        DecodeModeMCH.AURO_MATIC_3D: bytes([16, 71]),
        DecodeModeMCH.AURO_2D: bytes([16, 104]),
    },
    (ApiModel.APIHDA_SERIES, 2): {},
    (ApiModel.APISA_SERIES, 1): {},
    (ApiModel.APISA_SERIES, 2): {},
    (ApiModel.APIPA_SERIES, 1): {},
    (ApiModel.APIPA_SERIES, 2): {},
}

RC5CODE_DECODE_MODE_2CH: dict[tuple[ApiModel, int], dict[DecodeMode2CH, bytes]] = {
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
    (ApiModel.APILEXICON_SERIES, 1): {
        DecodeMode2CH.STEREO: bytes([16, 107]),
        DecodeMode2CH.DTS_NEURAL_X: bytes([16, 113]),
        DecodeMode2CH.LOGIC7_IMMERSION: bytes([16, 114]),
        DecodeMode2CH.DTS_VIRTUAL_X: bytes([16, 115]),
        DecodeMode2CH.DOLBY_PL: bytes([16, 110]),
        DecodeMode2CH.DTS_NEO_6_CINEMA: bytes([16, 111]),
        DecodeMode2CH.DTS_NEO_6_MUSIC: bytes([16, 112]),
        DecodeMode2CH.MCH_STEREO: bytes([16, 69]),
    },
    (ApiModel.APILEXICON_SERIES, 2): {},
    (ApiModel.APIHDA_SERIES, 1): {
        DecodeMode2CH.STEREO: bytes([16, 107]),
        DecodeMode2CH.DOLBY_SURROUND: bytes([16, 110]),
        DecodeMode2CH.DTS_NEO_6_CINEMA: bytes([16, 111]),
        DecodeMode2CH.DTS_NEO_6_MUSIC: bytes([16, 112]),
        DecodeMode2CH.MCH_STEREO: bytes([16, 69]),
        DecodeMode2CH.DTS_NEURAL_X: bytes([16, 113]),
        DecodeMode2CH.DOLBY_VIRTUAL_HEIGHT: bytes([16, 115]),
        DecodeMode2CH.AURO_NATIVE: bytes([16, 103]),
        DecodeMode2CH.AURO_MATIC_3D: bytes([16, 71]),
        DecodeMode2CH.AURO_2D: bytes([16, 104]),
    },
    (ApiModel.APIHDA_SERIES, 2): {},
    (ApiModel.APISA_SERIES, 1): {},
    (ApiModel.APISA_SERIES, 2): {},
    (ApiModel.APIPA_SERIES, 1): {},
    (ApiModel.APIPA_SERIES, 2): {},
    (ApiModel.APIST_SERIES, 1): {},
    (ApiModel.APIST_SERIES, 2): {},
}

RC5CODE_SOURCE: dict[tuple[ApiModel, int], dict[SourceCodes, bytes]] = {
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
        SourceCodes.FOLLOW_ZONE_1: bytes([16, 20]),
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
        SourceCodes.SAT: bytes([23, 20]),
        SourceCodes.VCR: bytes([23, 21]),
        SourceCodes.FOLLOW_ZONE_1: bytes([16, 20]),
    },
    (ApiModel.APILEXICON_SERIES, 1): {
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
    (ApiModel.APILEXICON_SERIES, 2): {
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
        SourceCodes.SAT: bytes([23, 20]),
        SourceCodes.VCR: bytes([23, 21]),
        SourceCodes.FOLLOW_ZONE_1: bytes([16, 20]),
    },
    (ApiModel.APIHDA_SERIES, 1): {
        SourceCodes.STB: bytes([16, 100]),
        SourceCodes.AV: bytes([16, 94]),
        SourceCodes.DAB: bytes([16, 72]),
        SourceCodes.FM: bytes([16, 28]),
        SourceCodes.BD: bytes([16, 98]),
        SourceCodes.GAME: bytes([16, 97]),
        SourceCodes.UHD: bytes([16, 125]),
        SourceCodes.CD: bytes([16, 118]),
        SourceCodes.AUX: bytes([16, 99]),
        SourceCodes.DISPLAY: bytes([16, 58]),
        SourceCodes.SAT: bytes([16, 27]),
        SourceCodes.PVR: bytes([16, 96]),
        SourceCodes.NET: bytes([16, 92]),
        SourceCodes.BT: bytes([16, 122]),
    },
    (ApiModel.APIHDA_SERIES, 2): {
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
        SourceCodes.SAT: bytes([23, 20]),
        SourceCodes.UHD: bytes([23, 23]),
        SourceCodes.BT: bytes([23, 22]),
        SourceCodes.FOLLOW_ZONE_1: bytes([16, 20]),
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
        SourceCodes.ARC_ERC: bytes([16, 125]),
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
        SourceCodes.ARC_ERC: bytes([16, 125]),
    },
    (ApiModel.APIST_SERIES, 1): {
        SourceCodes.DIG1: bytes([21, 94]),
        SourceCodes.DIG2: bytes([21, 98]),
        SourceCodes.DIG3: bytes([21, 27]),
        SourceCodes.DIG4: bytes([21, 97]),
        SourceCodes.USB: bytes([21, 93]),
        SourceCodes.NET: bytes([21, 92]),
    },
    (ApiModel.APIST_SERIES, 2): {},
    (ApiModel.APIPA_SERIES, 1): {},
    (ApiModel.APIPA_SERIES, 2): {},
}

RC5CODE_POWER = {
    (ApiModel.API450_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.API450_SERIES, 2): {True: bytes([23, 123]), False: bytes([23, 124])},
    (ApiModel.API860_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.API860_SERIES, 2): {True: bytes([23, 123]), False: bytes([23, 124])},
    (ApiModel.APILEXICON_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.APILEXICON_SERIES, 2): {True: bytes([23, 123]), False: bytes([23, 124])},
    (ApiModel.APIHDA_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.APIHDA_SERIES, 2): {True: bytes([23, 123]), False: bytes([23, 124])},
    (ApiModel.APISA_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.APISA_SERIES, 2): {True: bytes([16, 123]), False: bytes([16, 124])},
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
    (ApiModel.APILEXICON_SERIES, 1): {
        True: bytes([16, 26]),
        False: bytes([16, 120]),
    },
    (ApiModel.APILEXICON_SERIES, 2): {
        True: bytes([23, 4]),
        False: bytes([23, 5]),
    },
    (ApiModel.APIHDA_SERIES, 1): {
        True: bytes([16, 26]),
        False: bytes([16, 120]),
    },
    (ApiModel.APIHDA_SERIES, 2): {
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
    },
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
    (ApiModel.APIHDA_SERIES, 1): {
        True: bytes([16, 16]),
        False: bytes([16, 17]),
    },
    (ApiModel.APIHDA_SERIES, 2): {
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
    },
    (ApiModel.APIST_SERIES, 1): {
        True: bytes([21, 86]),
        False: bytes([21, 85]),
    },
}

RC5CODE_MENU_NAVIGATION = {
    (ApiModel.API450_SERIES, 1): {
        MenuNavigationCodes.MENU: bytes([16, 82]),
        MenuNavigationCodes.UP: bytes([16, 86]),
        MenuNavigationCodes.DOWN: bytes([16, 85]),
        MenuNavigationCodes.LEFT: bytes([16, 81]),
        MenuNavigationCodes.RIGHT: bytes([16, 80]),
        MenuNavigationCodes.OK: bytes([16, 87]),
    },
    (ApiModel.API860_SERIES, 1): {
        MenuNavigationCodes.MENU: bytes([16, 82]),
        MenuNavigationCodes.UP: bytes([16, 86]),
        MenuNavigationCodes.DOWN: bytes([16, 85]),
        MenuNavigationCodes.LEFT: bytes([16, 81]),
        MenuNavigationCodes.RIGHT: bytes([16, 80]),
        MenuNavigationCodes.OK: bytes([16, 87]),
    },
    (ApiModel.APILEXICON_SERIES, 1): {
        MenuNavigationCodes.MENU: bytes([16, 82]),
        MenuNavigationCodes.UP: bytes([16, 86]),
        MenuNavigationCodes.DOWN: bytes([16, 85]),
        MenuNavigationCodes.LEFT: bytes([16, 81]),
        MenuNavigationCodes.RIGHT: bytes([16, 80]),
        MenuNavigationCodes.OK: bytes([16, 87]),
    },
    (ApiModel.APIHDA_SERIES, 1): {
        MenuNavigationCodes.MENU: bytes([16, 82]),
        MenuNavigationCodes.UP: bytes([16, 86]),
        MenuNavigationCodes.DOWN: bytes([16, 85]),
        MenuNavigationCodes.LEFT: bytes([16, 81]),
        MenuNavigationCodes.RIGHT: bytes([16, 80]),
        MenuNavigationCodes.OK: bytes([16, 87]),
    },
}


class IncomingVideoAspectRatio(IntOrTypeEnum):
    UNDEFINED = 0x00
    ASPECT_4_3 = 0x01
    ASPECT_16_9 = 0x02


class IncomingVideoColorspace(IntOrTypeEnum):
    NORMAL = 0x00
    HDR10 = 0x01
    DOLBY_VISION = 0x02
    HLG = 0x03
    HDR10_PLUS = 0x04


class IncomingAudioFormat(IntOrTypeEnum):
    PCM = 0x00
    ANALOGUE_DIRECT = 0x01
    DOLBY_DIGITAL = 0x02
    DOLBY_DIGITAL_EX = 0x03
    DOLBY_DIGITAL_SURROUND = 0x04
    DOLBY_DIGITAL_PLUS = 0x05
    DOLBY_DIGITAL_TRUE_HD = 0x06
    DTS = 0x07
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
    DOLBY_ATMOS = 0x16, APIVERSION_DOLBY_ATMOS_SERIES
    DTS_X = 0x17, APIVERSION_DTS_X_SERIES
    IMAX_ENHANCED = 0x18, APIVERSION_IMAX_SERIES
    AURO_3D = 0x19, APIVERSION_AURO_SERIES


class IncomingAudioConfig(IntOrTypeEnum):
    """List of possible audio configurations."""

    DUAL_MONO = 0x00
    MONO = 0x01
    CENTER_ONLY = 0x01
    STEREO_ONLY = 0x02
    STEREO_SURR_MONO = 0x03
    STEREO_SURR_LR = 0x04
    STEREO_SURR_LR_BACK_MONO = 0x05
    STEREO_SURR_LR_BACK_LR = 0x06
    STEREO_SURR_LR_BACK_MATRIX = 0x07
    STEREO_CENTER = 0x08
    STEREO_CENTER_SURR_MONO = 0x09
    STEREO_CENTER_SURR_LR = 0x0A
    STEREO_CENTER_SURR_LR_BACK_MONO = 0x0B
    STEREO_CENTER_SURR_LR_BACK_LR = 0x0C
    STEREO_CENTER_SURR_LR_BACK_MATRIX = 0x0D
    STEREO_DOWNMIX = 0x0E
    STEREO_ONLY_LO_RO = 0x0F
    DUAL_MONO_LFE = 0x10
    MONO_LFE = 0x11
    CENTER_LFE = 0x11
    STEREO_LFE = 0x12
    STEREO_SURR_MONO_LFE = 0x13
    STEREO_SURR_LR_LFE = 0x14
    STEREO_SURR_LR_BACK_MONO_LFE = 0x15
    STEREO_SURR_LR_BACK_LR_LFE = 0x16
    STEREO_SURR_LR_BACK_MATRIX_LFE = 0x17
    STEREO_CENTER_LFE = 0x18
    STEREO_CENTER_SURR_MONO_LFE = 0x19
    STEREO_CENTER_SURR_LR_LFE = 0x1A
    STEREO_CENTER_SURR_LR_BACK_MONO_LFE = 0x1B
    STEREO_CENTER_SURR_LR_BACK_LR_LFE = 0x1C
    STEREO_CENTER_SURR_LR_BACK_MATRIX_LFE = 0x1D
    STEREO_DOWNMIX_LFE = 0x1E
    STEREO_ONLY_LO_RO_LFE = 0x1F
    UNKNOWN = 0x20
    UNDETECTED = 0x21
    AURO_QUAD = 0x30
    AURO_5_0 = 0x31
    AURO_5_1 = 0x32
    AURO_2_2_2 = 0x33
    AURO_8_0 = 0x34
    AURO_9_1 = 0x35
    AURO_10_1 = 0x36
    AURO_11_1 = 0x37
    AURO_13_1 = 0x38


class PresetType(IntOrTypeEnum):
    """List of possible audio configurations."""

    AM_FREQUENCY = 0x00
    FM_FREQUENCY = 0x01
    FM_RDS_NAME = 0x02
    DAB = 0x03


@attr.s
class PresetDetail:
    index = attr.ib(type=int)
    type = attr.ib(type=Union[PresetType, int])
    name = attr.ib(type=str)

    @staticmethod
    def from_bytes(data: bytes) -> "PresetDetail":
        type = PresetType.from_int(data[1])
        if type == PresetType.FM_RDS_NAME or type == PresetType.DAB:
            name = data[2:].decode("utf8").rstrip()
        elif type == PresetType.FM_FREQUENCY:
            name = f"{data[2]}.{data[3]:2} MHz"
        elif type == PresetType.AM_FREQUENCY:
            name = f"{data[2]}{data[3]:2} kHz"
        else:
            name = str(data[2:])
        return PresetDetail(data[0], type, name)


@attr.s
class VideoParameters:
    horizontal_resolution = attr.ib(type=int)
    vertical_resolution = attr.ib(type=int)
    refresh_rate = attr.ib(type=int)
    interlaced = attr.ib(type=bool)
    aspect_ratio = attr.ib(type=IncomingVideoAspectRatio)
    colorspace = attr.ib(type=IncomingVideoColorspace)

    @staticmethod
    def from_bytes(data: bytes) -> "VideoParameters | None":
        # Guard against incomplete or missing data
        if data is None or len(data) < 8:
            return None
        try:
            return VideoParameters(
                horizontal_resolution=int.from_bytes(data[0:2], "big"),
                vertical_resolution=int.from_bytes(data[2:4], "big"),
                refresh_rate=data[4],
                interlaced=(data[5] == 0x01),
                aspect_ratio=IncomingVideoAspectRatio.from_int(data[6]),
                colorspace=IncomingVideoColorspace.from_int(data[7]),
            )
        except (ValueError, IndexError):
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizontal_resolution": self.horizontal_resolution,
            "vertical_resolution": self.vertical_resolution,
            "refresh_rate": self.refresh_rate,
            "interlaced": self.interlaced,
            "aspect_ratio": self.aspect_ratio,
            "colorspace": self.colorspace,
        }


@attr.s
class ResponsePacket:
    """Represent a response from device."""

    zn = attr.ib(type=int)
    cc = attr.ib(type=int)
    ac = attr.ib(type=int)
    data = attr.ib(type=bytes)

    def respons_to(self, request: Union["AmxDuetRequest", "CommandPacket"]):
        if not isinstance(request, CommandPacket):
            return False
        return self.zn == request.zn and self.cc == request.cc

    @staticmethod
    def from_bytes(data: bytes) -> "ResponsePacket":
        if len(data) < 6:
            raise InvalidPacket(f"Packet to short {data!r}")

        if data[4] != len(data) - 6:
            raise InvalidPacket(f"Invalid length in data {data!r}")

        return ResponsePacket(
            data[1],
            CommandCodes.from_int(data[2]),
            AnswerCodes.from_int(data[3]),
            data[5 : 5 + data[4]],
        )

    def to_bytes(self):
        return bytes(
            [
                *PROTOCOL_STR,
                self.zn,
                self.cc,
                self.ac,
                len(self.data),
                *self.data,
                *PROTOCOL_ETR,
            ]
        )


@attr.s
class CommandPacket:
    """Represent a command sent to device."""

    zn = attr.ib(type=int)
    cc = attr.ib(type=int)
    data = attr.ib(type=bytes)

    def to_bytes(self):
        return bytes(
            [*PROTOCOL_STR, self.zn, self.cc, len(self.data), *self.data, *PROTOCOL_ETR]
        )

    @staticmethod
    def from_bytes(data: bytes) -> "CommandPacket":
        if len(data) < 5:
            raise InvalidPacket(f"Packet to short {data!r}")

        if data[3] != len(data) - 5:
            raise InvalidPacket(f"Invalid length in data {data!r}")

        return CommandPacket(
            data[1], CommandCodes.from_int(data[2]), data[4 : 4 + data[3]]
        )


@attr.s
class AmxDuetRequest:
    @staticmethod
    def from_bytes(data: bytes) -> "AmxDuetRequest":
        if not data == b"AMX\r":
            raise InvalidPacket(f"Packet is not a amx request {data!r}")
        return AmxDuetRequest()

    def to_bytes(self):
        return b"AMX\r"


@attr.s
class AmxDuetResponse:
    values = attr.ib(type=dict)

    @property
    def device_class(self) -> str | None:
        return self.values.get("Device-SDKClass")

    @property
    def device_make(self) -> str | None:
        return self.values.get("Device-Make")

    @property
    def device_model(self) -> str | None:
        return self.values.get("Device-Model")

    @property
    def device_revision(self) -> str | None:
        return self.values.get("Device-Revision")

    def respons_to(self, packet: AmxDuetRequest | CommandPacket):
        if not isinstance(packet, AmxDuetRequest):
            return False
        return True

    @staticmethod
    def from_bytes(data: bytes) -> "AmxDuetResponse":
        if not data.startswith(b"AMXB"):
            raise InvalidPacket(f"Packet is not a amx response {data!r}")

        tags = re.findall(r"<(.+?)=(.+?)>", data[4:].decode("ASCII"))
        return AmxDuetResponse(dict(tags))

    def to_bytes(self):
        res = (
            "AMXB"
            + "".join([f"<{key}={value}>" for key, value in self.values.items()])
            + "\r"
        )
        return res.encode("ASCII")


async def _read_delimited(reader: asyncio.StreamReader, header_len) -> bytes | None:
    try:
        start = await reader.readexactly(1)
        if start == PROTOCOL_EOF:
            _LOGGER.debug("eof")
            return None

        if start == PROTOCOL_STR:
            header = await reader.readexactly(header_len - 1)
            data_len = await reader.readexactly(1)
            data = await reader.readexactly(int.from_bytes(data_len, "big"))
            etr = await reader.readexactly(1)

            if etr != PROTOCOL_ETR:
                raise InvalidPacket(f"unexpected etr byte {etr!r}")

            packet = bytes([*start, *header, *data_len, *data, *etr])
        elif start == b"\x01":
            """Sometime the AMX header seem to be sent as \x01^AMX"""
            header = await reader.readexactly(4)
            if header != b"^AMX":
                raise InvalidPacket(f"Unexpected AMX header: {header!r}")

            data = await reader.readuntil(PROTOCOL_ETR)
            packet = bytes([*b"AMX", *data])
        elif start == b"A":
            header = await reader.readexactly(2)
            if header != b"MX":
                raise InvalidPacket("Unexpected AMX header")

            data = await reader.readuntil(PROTOCOL_ETR)
            packet = bytes([*start, *header, *data])
        elif start == b"\x00":
            raise NullPacket()
        else:
            raise InvalidPacket(f"unexpected str byte {start!r}")

        return packet

    except TimeoutError as exception:
        raise ConnectionFailed() from exception
    except ConnectionError as exception:
        raise ConnectionFailed() from exception
    except OSError as exception:
        raise ConnectionFailed() from exception
    except IncompleteReadError as exception:
        raise ConnectionFailed() from exception


async def _read_response(
    reader: asyncio.StreamReader,
) -> ResponsePacket | AmxDuetResponse | None:
    data = await _read_delimited(reader, 4)
    if not data:
        return None

    if data.startswith(b"AMX"):
        return AmxDuetResponse.from_bytes(data)
    else:
        return ResponsePacket.from_bytes(data)


async def read_response(
    reader: asyncio.StreamReader,
) -> ResponsePacket | AmxDuetResponse | None:
    while True:
        try:
            data = await _read_response(reader)
        except InvalidPacket as e:
            _LOGGER.warning(str(e))
            continue
        except NullPacket:
            _LOGGER.debug("Ignoring 0x00 start byte sent from some devices")
            continue
        return data


async def _read_command(
    reader: asyncio.StreamReader,
) -> CommandPacket | AmxDuetRequest | None:
    data = await _read_delimited(reader, 3)
    if not data:
        return None
    if data.startswith(b"AMX"):
        return AmxDuetRequest.from_bytes(data)
    else:
        return CommandPacket.from_bytes(data)


async def read_command(
    reader: asyncio.StreamReader,
) -> CommandPacket | AmxDuetRequest | None:
    while True:
        try:
            data = await _read_command(reader)
        except InvalidPacket as e:
            _LOGGER.warning(str(e))
            continue
        return data


async def write_packet(
    writer: asyncio.StreamWriter,
    packet: CommandPacket | ResponsePacket | AmxDuetRequest | AmxDuetResponse,
) -> None:
    try:
        data = packet.to_bytes()
        writer.write(data)
        async with asyncio.timeout(_WRITE_TIMEOUT):
            await writer.drain()
    except TimeoutError as exception:
        raise ConnectionFailed() from exception
    except ConnectionError as exception:
        raise ConnectionFailed() from exception
    except OSError as exception:
        raise ConnectionFailed() from exception
