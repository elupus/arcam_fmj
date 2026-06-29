"""Codec enums, source codes, dataclasses, lookup maps.

Typed values exchanged with the device over the wire. Each enum or struct
corresponds to the data payload of one or more command codes (CC); see the
individual docstrings for the mapping. Definitions are ordered by CC.
"""
from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, Union

import attr

from .models import (
    APIVERSION_AURO_SERIES,
    APIVERSION_AVR_860_ONWARD_SERIES,
    APIVERSION_DOLBY_PL_SERIES,
    APIVERSION_HDA_SERIES,
    APIVERSION_IMAX_SERIES,
    ApiModel,
    IntOrTypeEnum,
)

# === Codecs ===
# Codec[T] maps a command's data payload to/from a typed value; commands.py
# attaches one to each Command and State.get/set delegate to decode/encode.
# decode may return None for sentinel or out-of-range bytes. The generic codecs
# live here; command-specific ones live with their CC below.

_T = TypeVar("_T")
_E = TypeVar("_E", bound=IntOrTypeEnum)


def _get_scaled_negative(
    data: bytes | None, min_value: float, max_value: float, scale: float
) -> float | None:
    if data is None:
        return None
    neg_limit = round(-min_value / scale) + 0x80
    pos_limit = round(max_value / scale)
    byte_val = int.from_bytes(data, "big")
    if 0x81 <= byte_val <= neg_limit:
        return -(byte_val - 0x80) * scale
    if 0x00 <= byte_val <= pos_limit:
        return byte_val * scale
    return None


def _set_scaled(value: float, min_value: float, max_value: float, scale: float) -> int:
    value = max(min_value, min(max_value, value))
    iv = round(value / scale)
    return iv if iv >= 0 else 0x80 - iv


class Codec(Generic[_T]):
    """Maps a command payload to/from a typed value."""

    def decode(self, data: bytes) -> _T | None:
        raise NotImplementedError

    def encode(self, value: _T) -> bytes:
        raise NotImplementedError


@dataclass(frozen=True)
class BoolCodec(Codec[bool]):
    """1 byte ↔ bool. inverted=True flips the mapping (MUTE)."""

    inverted: bool = False

    def decode(self, data: bytes) -> bool:
        v = int.from_bytes(data, "big")
        return v == 0x00 if self.inverted else v == 0x01

    def encode(self, value: bool) -> bytes:
        if self.inverted:
            return bytes([0x00 if value else 0x01])
        return bytes([0x01 if value else 0x00])


class IntCodec(Codec[int]):
    """1 byte ↔ int."""

    def decode(self, data: bytes) -> int:
        return int.from_bytes(data, "big")

    def encode(self, value: int) -> bytes:
        return bytes([value])


@dataclass(frozen=True)
class EnumCodec(Codec[_E]):
    """1 byte ↔ IntOrTypeEnum via from_bytes / value. set_map supplies the
    asymmetric write codes for IMAX_ENHANCED and ZONE_1_OSD_ON_OFF."""

    enum_cls: type[_E]
    set_map: dict[_E, int] | None = None

    def decode(self, data: bytes) -> _E:
        return self.enum_cls.from_bytes(data)

    def encode(self, value: _E) -> bytes:
        if self.set_map is not None:
            return bytes([self.set_map[value]])
        return bytes([int(value)])


@dataclass(frozen=True)
class ScaledCodec(Codec[float]):
    """Negative-biased scaled float; out-of-range bytes decode to None."""

    min_value: float
    max_value: float
    scale: float

    def decode(self, data: bytes) -> float | None:
        return _get_scaled_negative(data, self.min_value, self.max_value, self.scale)

    def encode(self, value: float) -> bytes:
        return bytes([_set_scaled(value, self.min_value, self.max_value, self.scale)])


@dataclass(frozen=True)
class StringCodec(Codec[str]):
    """N bytes ↔ str, decoded with errors='replace' and trailing whitespace stripped."""

    encoding: str = "utf-8"

    def decode(self, data: bytes) -> str:
        return data.decode(self.encoding, errors="replace").rstrip()

    def encode(self, value: str) -> bytes:
        return value.encode(self.encoding)


@dataclass(frozen=True)
class StructCodec(Codec[_T]):
    """Multi-byte struct via a from_bytes callable (read-only)."""

    parse: Callable[[bytes], _T]

    def decode(self, data: bytes) -> _T:
        return self.parse(data)


# --- AC byte (all responses) ---

class AnswerCodes(IntOrTypeEnum):
    """Response status byte (AC) present in every device response.

    See: all specs, "Answer codes" section.
    """

    STATUS_UPDATE = 0x00
    ZONE_INVALID = 0x82
    COMMAND_NOT_RECOGNISED = 0x83
    PARAMETER_NOT_RECOGNISED = 0x84
    COMMAND_INVALID_AT_THIS_TIME = 0x85
    INVALID_DATA_LENGTH = 0x86

# --- CC 0x01: DISPLAY_BRIGHTNESS ---

class DisplayBrightness(IntOrTypeEnum):
    """Front-panel display brightness level.

    Used by DISPLAY_BRIGHTNESS (0x01).

    See: SH289E "Display Brightness (0x01)".
    """

    OFF = 0x00
    L1 = 0x01
    L2 = 0x02

# --- CC 0x06: SAVE_RESTORE_COPY_OF_SETTINGS ---

class SaveRestoreSubCommand(enum.IntEnum):
    """Sub-command for SAVE_RESTORE_COPY_OF_SETTINGS (0x06).

    Data1 selects save (0x00) or restore (0x01); Data2-3 must be the
    confirmation pattern (0x55, 0x55); Data4-7 carry PIN digits.

    See: SH289E "Save/Restore secure copy of settings (0x06)";
         SH256E "Save/Restore secure copy of settings (0x06)".
    """

    SAVE = 0x00
    RESTORE = 0x01

#: Confirmation pattern (Data2-3) required by SAVE_RESTORE_COPY_OF_SETTINGS
#: (0x06). See: SH289E "Save/Restore secure copy of settings (0x06)".
SAVE_RESTORE_CONFIRMATION = bytes([0x55, 0x55])

# --- CC 0x0A: VIDEO_SELECTION ---

class VideoSelection(IntOrTypeEnum):
    """Video input routing for pre-HDA AVRs.

    Used by VIDEO_SELECTION (0x0A).

    See: SH256E "Video selection (0x0A)".
    """

    BD = 0x00
    SAT = 0x01
    AV = 0x02
    PVR = 0x03
    VCR = 0x04
    GAME = 0x05
    STB = 0x06

# --- CC 0x0C: IMAX_ENHANCED ---

class ImaxEnhancedMode(IntOrTypeEnum):
    """IMAX Enhanced processing mode (read values).

    Used by IMAX_ENHANCED (0x0C). The read response uses 0x00-0x02; the
    set command uses different values — see IMAX_ENHANCED_SET_MAP.

    See: SH289E "IMAX Enhanced (0x0C)".
    """

    OFF = 0x00
    ON = 0x01
    AUTO = 0x02

#: Write-side byte values for IMAX_ENHANCED (0x0C). The set command uses
#: 0xF1/F2/F3 rather than the 0x00-0x02 values returned in read responses.
#: See: SH289E "IMAX Enhanced (0x0C)".
IMAX_ENHANCED_SET_MAP: dict[ImaxEnhancedMode, int] = {
    ImaxEnhancedMode.AUTO: 0xF1,
    ImaxEnhancedMode.ON: 0xF2,
    ImaxEnhancedMode.OFF: 0xF3,
}

# --- CC 0x10: DECODE_MODE_STATUS_2CH ---

class DecodeMode2CH(IntOrTypeEnum):
    """Stereo (2-channel) decode mode.

    Used by DECODE_MODE_STATUS_2CH (0x10). HDA adds Auro modes (0x0E-0x10);
    450 series has Dolby PLIIx variants (0x02/0x03/0x05/0x06) instead of
    Dolby Surround (0x04).

    See: SH289E "Request decode mode status — 2ch (0x10)";
         SH256E "Request decode mode status — 2ch (0x10)".
    """

    STEREO = 0x01
    DOLBY_PLII_IIx_MOVIE = 0x02, APIVERSION_DOLBY_PL_SERIES
    DOLBY_PLII_IIx_MUSIC = 0x03, APIVERSION_DOLBY_PL_SERIES
    DOLBY_SURROUND = 0x04, APIVERSION_AVR_860_ONWARD_SERIES
    DOLBY_PLII_IIx_GAME = 0x05, APIVERSION_DOLBY_PL_SERIES
    DOLBY_PL = 0x06, APIVERSION_DOLBY_PL_SERIES
    DTS_NEO_6_CINEMA = 0x07
    DTS_NEO_6_MUSIC = 0x08
    MCH_STEREO = 0x09

    DTS_NEURAL_X = 0x0A, APIVERSION_AVR_860_ONWARD_SERIES
    DTS_VIRTUAL_X = 0x0C, APIVERSION_AVR_860_ONWARD_SERIES

    DOLBY_VIRTUAL_HEIGHT = 0x0D, APIVERSION_HDA_SERIES
    AURO_NATIVE = 0x0E, APIVERSION_AURO_SERIES
    AURO_MATIC_3D = 0x0F, APIVERSION_AURO_SERIES
    AURO_2D = 0x10, APIVERSION_AURO_SERIES

# --- CC 0x11: DECODE_MODE_STATUS_MCH ---

class DecodeModeMCH(IntOrTypeEnum):
    """Multi-channel decode mode.

    Used by DECODE_MODE_STATUS_MCH (0x11). Value 0x03 means Dolby D-EX /
    DTS-ES on the 450 series but DTS Neural:X on 860/HDA.

    See: SH289E "Request Decode mode status — MCH (0x11)";
         SH256E "Request Decode mode status — MCH (0x11)".
    """

    STEREO_DOWNMIX = 0x01
    MULTI_CHANNEL = 0x02

    # This is used for DTS_NEURAL_X on 860 series and HDA series
    DOLBY_D_EX_OR_DTS_ES = 0x03

    DOLBY_PLII_IIx_MOVIE = 0x04, APIVERSION_DOLBY_PL_SERIES
    DOLBY_PLII_IIx_MUSIC = 0x05, APIVERSION_DOLBY_PL_SERIES

    DOLBY_SURROUND = 0x06, APIVERSION_AVR_860_ONWARD_SERIES
    DTS_VIRTUAL_X = 0x0C, APIVERSION_AVR_860_ONWARD_SERIES

    DOLBY_VIRTUAL_HEIGHT = 0x0D, APIVERSION_HDA_SERIES
    AURO_NATIVE = 0x0E, APIVERSION_AURO_SERIES
    AURO_MATIC_3D = 0x0F, APIVERSION_AURO_SERIES
    AURO_2D = 0x10, APIVERSION_AURO_SERIES

# --- CC 0x14: MENU ---

class MenuCodes(IntOrTypeEnum):
    """On-screen menu state.

    Used by MENU (0x14).

    See: SH289E "Request menu status (0x14)".
    """

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

# --- CC 0x15: TUNER_PRESET ---

class TunerPresetCodec(Codec[int]):
    """1 byte ↔ preset number; 0xff (no preset selected) decodes to None."""

    def decode(self, data: bytes) -> int | None:
        if data == b"\xff":
            return None
        return int.from_bytes(data, "big")

    def encode(self, value: int) -> bytes:
        return bytes([value])

# --- CC 0x1B: PRESET_DETAIL ---

class PresetType(IntOrTypeEnum):
    """Tuner preset type (Data2 of the response).

    Used by PRESET_DETAIL (0x1B). Determines how Data3+ is interpreted:
    FM_FREQUENCY stores MHz/10kHz digits; FM_RDS_NAME and DAB store an
    ASCII station name.

    See: SH256E "Request preset details (0x1B)".
    """

    AM_FREQUENCY = 0x00
    FM_FREQUENCY = 0x01
    FM_RDS_NAME = 0x02
    DAB = 0x03

@attr.s
class PresetDetail:
    """Decoded response for PRESET_DETAIL (0x1B).

    Data1: preset index (1-50). Data2: PresetType. Data3+: frequency digits
    or ASCII station name depending on type.

    See: SH289E "Request preset details (0x1B)";
         SH256E "Request preset details (0x1B)".
    """

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

# --- CC 0x1C: NETWORK_PLAYBACK_STATUS ---

class NetworkPlaybackStatus(IntOrTypeEnum):
    """Network/USB playback transport state.

    Used by NETWORK_PLAYBACK_STATUS (0x1C).

    See: SH289E "Network playback status (0x1C)".
    """

    STOPPED = 0x00
    TRANSITIONING = 0x01
    PLAYING = 0x02
    PAUSED = 0x03

# --- CC 0x1D: CURRENT_SOURCE ---

class SourceCodes(enum.Enum):
    """Logical input-source identifiers.

    The byte encoding is model-dependent — use ``from_bytes`` / ``to_bytes``
    with a ``(model, zone)`` pair rather than casting directly.
    Used by CURRENT_SOURCE (0x1D) and the RC5 source tables.

    See: SH289E "Request current source (0x1D)";
         SH256E "Request current source (0x1D)".
    """

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

#: SourceCodes -> wire byte for 450/860 series (both zones).
#: See: SH256E/SH274E "Request current source (0x1D)".
DEFAULT_SOURCE_MAPPING: dict[SourceCodes, bytes] = {
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

#: SourceCodes -> wire byte for HDA series (both zones).
#: Differs from DEFAULT: UHD (0x06) replaces VCR, BT (0x12) replaces PHONO.
#: See: SH289E "Request current source (0x1D)".
HDA_SOURCE_MAPPING: dict[SourceCodes, bytes] = {
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

#: SourceCodes -> wire byte for SA series. Completely different byte
#: layout from AVR models. See: SH306E "Request current source (0x1D)".
SA_SOURCE_MAPPING: dict[SourceCodes, bytes] = {
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

#: SourceCodes -> wire byte for ST60. Digital-only inputs with a
#: combined NET_USB source. See: SH309 "Request current source (0x1D)".
ST_SOURCE_MAPPING: dict[SourceCodes, bytes] = {
    SourceCodes.DIG1: bytes([0x01]),
    SourceCodes.DIG2: bytes([0x02]),
    SourceCodes.DIG3: bytes([0x03]),
    SourceCodes.DIG4: bytes([0x04]),
    SourceCodes.NET_USB: bytes([0x05]),
}

#: Master lookup: (ApiModel, zone) -> source mapping table.
SOURCE_CODES: dict[tuple[ApiModel, int], dict[SourceCodes, bytes]] = {
    (ApiModel.API450_SERIES, 1): DEFAULT_SOURCE_MAPPING,
    (ApiModel.API450_SERIES, 2): DEFAULT_SOURCE_MAPPING,
    (ApiModel.API860_SERIES, 1): DEFAULT_SOURCE_MAPPING,
    (ApiModel.API860_SERIES, 2): DEFAULT_SOURCE_MAPPING,
    (ApiModel.APIHDA_SERIES, 1): HDA_SOURCE_MAPPING,
    (ApiModel.APIHDA_SERIES, 2): HDA_SOURCE_MAPPING,
    (ApiModel.APISA_SERIES, 1): SA_SOURCE_MAPPING,
    (ApiModel.APISA_SERIES, 2): SA_SOURCE_MAPPING,
    (ApiModel.APIST_SERIES, 1): ST_SOURCE_MAPPING,
}

# --- CC 0x34: ROOM_EQ_NAMES ---

class RoomEqNamesCodec(Codec[list[str]]):
    """Concatenated 20-byte ASCII records → list of names (read-only)."""

    def decode(self, data: bytes) -> list[str]:
        return [
            data[i:i + 20].decode("ascii", errors="replace").rstrip("\x00").strip()
            for i in range(0, len(data), 20)
        ]

# --- CC 0x37: ROOM_EQUALIZATION ---

class RoomEqMode(IntOrTypeEnum):
    """Room equalisation preset selection.

    Used by ROOM_EQUALIZATION (0x37).

    See: SH289E "Room Equalisation (0x37)".
    """

    OFF = 0x00
    EQ1 = 0x01
    EQ2 = 0x02
    EQ3 = 0x03
    NOT_CALCULATED = 0x04

# --- CC 0x38: DOLBY_AUDIO ---

class DolbyAudioMode(IntOrTypeEnum):
    """Dolby Audio processing mode.

    Used by DOLBY_AUDIO (0x38). Named "Dolby Volume" in the 450/860 specs
    where only OFF/MOVIE ("On") exist; HDA adds MUSIC and NIGHT.

    See: SH289E "Dolby Audio (0x38)";
         SH274E "Dolby Volume (0x38)".
    """

    OFF = 0x00
    MOVIE = 0x01  # "On" on 860 series
    MUSIC = 0x02, APIVERSION_HDA_SERIES
    NIGHT = 0x03, APIVERSION_HDA_SERIES

# --- CC 0x41: COMPRESSION ---

class CompressionMode(IntOrTypeEnum):
    """Dynamic range compression level.

    Used by COMPRESSION (0x41).

    See: SH289E "Compression (0x41)".
    """

    OFF = 0x00
    MEDIUM = 0x01
    HIGH = 0x02

# --- CC 0x42: INCOMING_VIDEO_PARAMETERS ---

class IncomingVideoAspectRatio(IntOrTypeEnum):
    """Detected video aspect ratio (Data7 of INCOMING_VIDEO_PARAMETERS).

    Used by INCOMING_VIDEO_PARAMETERS (0x42).

    See: SH289E "Request incoming video parameters (0x42)".
    """

    UNDEFINED = 0x00
    ASPECT_4_3 = 0x01
    ASPECT_16_9 = 0x02

class IncomingVideoColorspace(IntOrTypeEnum):
    """Detected video HDR colorspace (Data8 of INCOMING_VIDEO_PARAMETERS).

    HDA only — pre-HDA responses are 7 bytes and omit this field.
    Used by INCOMING_VIDEO_PARAMETERS (0x42).

    See: SH289E "Request incoming video parameters (0x42)".
    """

    NORMAL = 0x00
    HDR10 = 0x01
    DOLBY_VISION = 0x02
    HLG = 0x03
    HDR10_PLUS = 0x04

@attr.s
class VideoParameters:
    """Decoded response for INCOMING_VIDEO_PARAMETERS (0x42).

    Data1-2: horizontal resolution (MSB, LSB).
    Data3-4: vertical resolution (MSB, LSB).
    Data5: refresh rate. Data6: interlaced flag.
    Data7: aspect ratio. Data8: colorspace (HDA only, 8-byte response).
    Pre-HDA responses are 7 bytes (DL=0x07) and omit colorspace.

    See: SH289E "Request incoming video parameters (0x42)";
         SH274E "Request incoming video parameters (0x42)".
    """

    horizontal_resolution = attr.ib(type=int)
    vertical_resolution = attr.ib(type=int)
    refresh_rate = attr.ib(type=int)
    interlaced = attr.ib(type=bool)
    aspect_ratio = attr.ib(type=IncomingVideoAspectRatio)
    colorspace = attr.ib(type=IncomingVideoColorspace | None, default=None)

    @staticmethod
    def from_bytes(data: bytes) -> "VideoParameters":
        return VideoParameters(
            horizontal_resolution=int.from_bytes(data[0:2], "big"),
            vertical_resolution=int.from_bytes(data[2:4], "big"),
            refresh_rate=data[4],
            interlaced=(data[5] == 0x01),
            aspect_ratio=IncomingVideoAspectRatio.from_int(data[6]),
            # Colorspace is not reported pre-HDA
            colorspace=IncomingVideoColorspace.from_int(data[7]) if len(data) >= 8 else None,
        )

    def to_bytes(self) -> bytes:
        data = (
            self.horizontal_resolution.to_bytes(2, "big")
            + self.vertical_resolution.to_bytes(2, "big")
            + bytes([
                self.refresh_rate,
                0x01 if self.interlaced else 0x00,
                int(self.aspect_ratio),
            ])
        )
        if self.colorspace is not None:
            data += bytes([int(self.colorspace)])
        return data

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizontal_resolution": self.horizontal_resolution,
            "vertical_resolution": self.vertical_resolution,
            "refresh_rate": self.refresh_rate,
            "interlaced": self.interlaced,
            "aspect_ratio": self.aspect_ratio,
            "colorspace": self.colorspace,
        }

# --- CC 0x43: INCOMING_AUDIO_FORMAT ---

class IncomingAudioFormat(IntOrTypeEnum):
    """Detected audio stream codec/format (Data1 of the response).

    Used by INCOMING_AUDIO_FORMAT (0x43). HDA adds Auro 3D (0x19);
    860+ adds Dolby Atmos (0x16), DTS:X (0x17), IMAX Enhanced (0x18).

    See: SH289E "Request incoming audio format (0x43)".
    """

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
    DOLBY_ATMOS = 0x16, APIVERSION_AVR_860_ONWARD_SERIES
    DTS_X = 0x17, APIVERSION_AVR_860_ONWARD_SERIES
    IMAX_ENHANCED = 0x18, APIVERSION_IMAX_SERIES
    AURO_3D = 0x19, APIVERSION_AURO_SERIES

class IncomingAudioConfig(IntOrTypeEnum):
    """Detected audio channel configuration (Data2 of the response).

    Used by INCOMING_AUDIO_FORMAT (0x43) — same command as IncomingAudioFormat;
    Data1 is the format, Data2 is this config. HDA adds Auro layouts (0x30+).

    See: SH289E "Request incoming audio format (0x43)".
    """

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

# --- CC 0x44: INCOMING_AUDIO_SAMPLE_RATE ---

#: Wire byte -> sample rate in Hz (or None for unknown/undetected).
#: Used by INCOMING_AUDIO_SAMPLE_RATE (0x44).
#: See: SH289E "Request incoming audio sample rate (0x44)".
SAMPLE_RATE_MAP: dict[int, int | None] = {
    0x00: 32000,
    0x01: 44100,
    0x02: 48000,
    0x03: 88200,
    0x04: 96000,
    0x05: 176400,
    0x06: 192000,
    0x07: None,  # Unknown
    0x08: None,  # Undetected
}

class SampleRateCodec(Codec[int]):
    """1 byte → sample rate in Hz via SAMPLE_RATE_MAP (read-only)."""

    def decode(self, data: bytes) -> int | None:
        return SAMPLE_RATE_MAP.get(data[0], 0)

# --- CC 0x49: VIDEO_FILM_MODE ---

class VideoFilmMode(IntOrTypeEnum):
    """Video film-mode detection setting.

    Used by VIDEO_FILM_MODE (0x49).

    See: SH256E "Set/Request Film Mode (0x49)".
    """

    AUTO = 0x00
    OFF = 0x01

# --- CC 0x4C/0x4D: VIDEO_NOISE_REDUCTION / VIDEO_MPEG_NOISE_REDUCTION ---

class VideoNoiseReduction(IntOrTypeEnum):
    """Video noise reduction level.

    Shared by VIDEO_NOISE_REDUCTION (0x4C) and VIDEO_MPEG_NOISE_REDUCTION (0x4D).

    See: SH256E "Set/Request Noise Reduction (0x4C)",
         "Set/Request MPEG Noise Reduction (0x4D)".
    """

    OFF = 0x00
    LOW = 0x01
    MEDIUM = 0x02
    HIGH = 0x03

# --- CC 0x4E: ZONE_1_OSD_ON_OFF ---

class ZoneOsd(IntOrTypeEnum):
    """Zone 1 on-screen display state.

    Used by ZONE_1_OSD_ON_OFF (0x4E). Response uses 0x00/0x01; Set uses
    0xF1/0xF2 (via set_map on the ByteEnum schema).

    See: SH256E "Set/Request Zone 1 OSD on/off (0x4E)".
    """

    ON = 0x00
    OFF = 0x01

#: Asymmetric set codes for ZONE_1_OSD_ON_OFF — the set form uses 0xF1/0xF2.
ZONE_OSD_SET_MAP = {ZoneOsd.ON: 0xF1, ZoneOsd.OFF: 0xF2}

# --- CC 0x4F: VIDEO_OUTPUT_SWITCHING ---

class HdmiOutput(IntOrTypeEnum):
    """Active HDMI output(s).

    Used by VIDEO_OUTPUT_SWITCHING (0x4F).

    See: SH289E "Set/Request Video Output Switching (0x4F)".
    """

    OUT_1 = 0x02
    OUT_2 = 0x03
    OUT_1_2 = 0x04

# --- CC 0x50: BLUETOOTH_STATUS ---

# --- CC 0x58: AUTO_SHUTDOWN_CONTROL ---

class AutoShutdown(IntOrTypeEnum):
    """Auto-shutdown timer setting.

    Used by AUTO_SHUTDOWN_CONTROL (0x58).

    See: SH277E "Auto shutdown control (0x58)".
    """

    DISABLED = 0x00
    MINUTES_30 = 0x01
    HOUR_1 = 0x02
    HOURS_2 = 0x03
    HOURS_4 = 0x04

# --- CC 0x5B: PROCESSOR_MODE_INPUT ---

class SaProcessorModeCodec(Codec["SourceCodes | None"]):
    """1 byte ↔ SourceCodes | None; 0x00 → None (disabled), other bytes via the
    SA-series source encoding (zone 1).

    See: SH306E / SH320E "Processor mode input (0x5B)".
    """

    def decode(self, data: bytes) -> SourceCodes | None:
        if int.from_bytes(data, "big") == 0x00:
            return None
        try:
            return SourceCodes.from_bytes(data, ApiModel.APISA_SERIES, 1)
        except ValueError:
            return None

    def encode(self, value: SourceCodes | None) -> bytes:
        if value is None:
            return bytes([0x00])
        return value.to_bytes(ApiModel.APISA_SERIES, 1)

# --- CC 0x61: DAC_FILTER ---

class DacFilter(IntOrTypeEnum):
    """DAC digital filter type.

    Used by DAC_FILTER (0x61). SA20 supports all seven; SA10 supports
    only the first three.

    See: SH277E "DAC Filter (0x61)".
    """

    LINEAR_FAST = 0x00
    LINEAR_SLOW = 0x01
    MINIMUM_FAST = 0x02
    MINIMUM_SLOW = 0x03
    BRICK_WALL = 0x04
    CORRECTED_FAST = 0x05
    APODIZING = 0x06


class BluetoothAudioStatus(IntOrTypeEnum):
    """Bluetooth connection and codec status.

    Used by BLUETOOTH_STATUS (0x50). This command code was "Output Frame Rate"
    on the 450 series (SH256E).

    See: SH289E "Bluetooth status (0x50)".
    """

    NO_CONNECTION = 0x00
    PAUSED = 0x01
    PLAYING_SBC = 0x02
    PLAYING_AAC = 0x03
    PLAYING_APTX = 0x04
    PLAYING_APTX_HD = 0x05

# --- CC 0x64: NOW_PLAYING_INFO ---

class NowPlayingEncoder(IntOrTypeEnum):
    """Audio encoder/codec of the currently playing track.

    Returned by NOW_PLAYING_INFO (0x64) when sub-request is ENCODER (0xF5).

    See: SH289E "Now Playing Information (0x64)".
    """

    MP3 = 0x00
    WAV = 0x01
    WMA = 0x02
    FLAC = 0x03
    ALAC = 0x04
    MQA = 0x05
    UNKNOWN = 0x0A

class NowPlayingRequest(IntOrTypeEnum):
    """Sub-request codes sent as Data1 of NOW_PLAYING_INFO (0x64).

    Each code requests a different field of the currently playing track.

    See: SH289E "Now Playing Information (0x64)".
    """

    TRACK = 0xF0
    ARTIST = 0xF1
    ALBUM = 0xF2
    APPLICATION = 0xF3
    SAMPLE_RATE = 0xF4
    ENCODER = 0xF5

def _decode_string(data: bytes) -> str:
    """Decode a UTF-8 payload, stripping trailing NUL bytes."""
    return data.decode("utf8", errors="replace").rstrip("\x00")

@attr.s
class NowPlayingInfo:
    """Aggregated now-playing metadata from NOW_PLAYING_INFO (0x64).

    Each field corresponds to one NowPlayingRequest sub-code. The ``metadata``
    on each attr carries the sub-request code and a converter for the raw
    response bytes.

    See: SH289E "Now Playing Information (0x64)".
    """

    track = attr.ib(type=str | None, default=None, metadata={"request": NowPlayingRequest.TRACK, "converter": _decode_string})
    artist = attr.ib(type=str | None, default=None, metadata={"request": NowPlayingRequest.ARTIST, "converter": _decode_string})
    album = attr.ib(type=str | None, default=None, metadata={"request": NowPlayingRequest.ALBUM, "converter": _decode_string})
    application = attr.ib(type=str | None, default=None, metadata={"request": NowPlayingRequest.APPLICATION, "converter": _decode_string})
    sample_rate = attr.ib(type=int | None, default=None, metadata={"request": NowPlayingRequest.SAMPLE_RATE, "converter": lambda x: SAMPLE_RATE_MAP.get(x[0], 0)})
    encoder = attr.ib(type=NowPlayingEncoder | None, default=None, metadata={"request": NowPlayingRequest.ENCODER, "converter": lambda x: NowPlayingEncoder.from_int(x[0])})
