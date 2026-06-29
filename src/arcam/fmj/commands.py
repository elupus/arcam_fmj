"""The command catalogue — one table, one row per command.

Each constant is a command: its CC byte (``cc``), protocol metadata (``version``,
``flags``, ``sources``) and — where the command has a get/set form — a ``Codec``
and a read/write/step capability via the ``ReadCommand`` / ``WriteCommand`` /
``StepCommand`` classes. ``ro`` / ``rw`` / ``rw_step`` / ``wo`` build typed commands;
``proto`` builds protocol-only ones (no accessor). ``State.get`` / ``set`` /
``inc`` / ``dec`` operate on these; the wire layer keys off ``command.cc``.

To add a command, add one row. Define any new codec in ``codecs`` and any RC5
table in ``rc5`` first.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from .codecs import *  # noqa: F401,F403
from .models import *  # noqa: F401,F403
from .rc5 import *  # noqa: F401,F403


__all__ = [
    "CommandFlags",
    "MUTE_WRITE_SUPPORTED",
    "POWER_WRITE_SUPPORTED",
    "SOURCE_WRITE_SUPPORTED",
    "VOLUME_STEP_SUPPORTED",
    "Command",
    "CommandContext",
    "Rc5Step",
    "Rc5Write",
    "ReadCommand",
    "WriteCommand",
    "StepCommand",
    "ReadWriteCommand",
    "ReadWriteStepCommand",
    "ro",
    "rw",
    "rw_step",
    "wo",
    "proto",
    "COMMANDS",
    "command_for",
]


class CommandFlags(enum.IntFlag):
    """Behavioral protocol traits consulted by the update loop and zone gating."""
    ZONE_SUPPORT = enum.auto()
    UPDATE = enum.auto()        # Fetched by the State update loop.
    NOT_PUSHED = enum.auto()    # Device does not send unsolicited updates.

#: Models that accept a direct CC write for power on/off.
POWER_WRITE_SUPPORTED = {
    ApiModel.APISA_SERIES,
    ApiModel.APIPA_SERIES,
    ApiModel.APIST_SERIES,
}

#: Models that accept a direct CC write for mute on/off.
MUTE_WRITE_SUPPORTED = POWER_WRITE_SUPPORTED

#: Models that accept a direct CC write for source selection.
SOURCE_WRITE_SUPPORTED = {
    ApiModel.APISA_SERIES,
}

#: Models that accept a direct CC write for volume step (inc/dec).
VOLUME_STEP_SUPPORTED = {
    ApiModel.APIST_SERIES,
}

# Short aliases for the table below.
_0 = CommandFlags(0)
_Z = CommandFlags.ZONE_SUPPORT
_U = CommandFlags.UPDATE
_NP = CommandFlags.NOT_PUSHED

_AVR = APIVERSION_AVR_SERIES
_AVR_SA = APIVERSION_AVR_AND_SA_SERIES
_AVR_SA_ST = APIVERSION_AVR_SA_AND_ST_SERIES
_PRE_HDA = APIVERSION_AVR_PRE_HDA_SERIES
_HDA = APIVERSION_HDA_SERIES
_HDA_MZ = APIVERSION_HDA_MULTI_ZONE_SERIES
_SA = APIVERSION_SA_SERIES
_450 = APIVERSION_450_SERIES
_IMAX = APIVERSION_IMAX_SERIES
_DIRECT = APIVERSION_DIRECT_MODE_SERIES
_ROOM_EQ = APIVERSION_ROOM_EQ_SERIES
_ROOM_NAM = APIVERSION_ROOM_EQ_NAMES_SERIES
_NET_PLAY = APIVERSION_NETWORK_PLAYBACK_SERIES
_NET_MENU = APIVERSION_NETWORK_MENU_SERIES
_NOW_PLAY = APIVERSION_NOW_PLAYING_SERIES
_APP_SAFE = APIVERSION_APP_SAFETY_SERIES
_AMP_DIAG = APIVERSION_AMP_DIAGNOSTICS_SERIES
_THERM = APIVERSION_THERMAL_DIAGNOSTICS_SERIES
_CLASS_G = APIVERSION_CLASS_G_SERIES
_SIMPLE_IP = APIVERSION_SIMPLE_IP_SERIES
_PHONO = APIVERSION_PHONO_SERIES
_DAC_FILT = APIVERSION_DAC_FILTER_SERIES

_FM = frozenset({SourceCodes.FM})
_DAB = frozenset({SourceCodes.DAB})
_TUN = frozenset({SourceCodes.FM, SourceCodes.DAB})
_NET = frozenset({SourceCodes.NET, SourceCodes.USB, SourceCodes.NET_USB})
_BT = frozenset({SourceCodes.BT})


# === Command machinery ===

T = TypeVar("T")


@dataclass(frozen=True)
class Rc5Write:
    """RC5 fallback for a Set: direct CC write when the model is in
    ``direct_supported``, otherwise the RC5 code for the value."""
    table: dict
    direct_supported: frozenset = field(default_factory=frozenset)


@dataclass(frozen=True)
class Rc5Step:
    """Inc/dec policy: step via direct CC (``inc_data`` / ``dec_data``) when the
    model is in ``via_cc_supported``, otherwise the up/down RC5 code."""
    table: dict
    via_cc_supported: frozenset = field(default_factory=frozenset)
    inc_data: bytes = b"\xF1"
    dec_data: bytes = b"\xF2"


class CommandContext(Protocol):
    """The slice of ``State`` that command write/step delegate into."""
    @property
    def api_model(self) -> ApiModel: ...
    def set_cached(self, cc: int, data: bytes | None) -> None: ...
    def supported_on_source(self, command: Command[Any]) -> bool: ...
    def get_rc5code(self, table: dict, value: Any) -> bytes: ...
    async def request(self, command: Command[Any], data: bytes) -> bytes: ...
    async def send_rc5(self, table: dict, value: Any) -> None: ...


@dataclass(frozen=True, eq=False, repr=False)
class Command(Generic[T]):
    cc: int
    version: set[str] | None = None
    flags: CommandFlags = CommandFlags(0)
    sources: frozenset[SourceCodes] | None = None
    codec: Codec[T] | None = None
    rc5_write: Rc5Write | None = None
    rc5_step: Rc5Step | None = None
    name: str = ""

    def __repr__(self) -> str:
        return self.name or f"CODE_0x{self.cc:02X}"


class ReadCommand(Command[T]):
    """Read capability: ``State.get`` accepts it. Decodes the cached payload."""
    def read(self, raw: bytes) -> T | None:
        assert self.codec is not None
        return self.codec.decode(raw)


class WriteCommand(Command[T]):
    """Write capability: ``State.set`` accepts it; direct CC or RC5 fallback."""
    async def write(self, context: CommandContext, value: T) -> None:
        if not context.supported_on_source(self) or self.codec is None:
            return
        write = self.rc5_write
        if write is not None and context.api_model not in write.direct_supported:
            await context.send_rc5(write.table, value)
        else:
            await context.request(self, self.codec.encode(value))


class StepCommand(Command[T]):
    """Step capability: ``State.inc`` / ``dec`` accept it."""
    async def step(self, context: CommandContext, increment: bool) -> None:
        if not context.supported_on_source(self):
            return
        step = self.rc5_step
        assert step is not None
        if context.api_model in step.via_cc_supported:
            await context.request(self, step.inc_data if increment else step.dec_data)
        else:
            await context.send_rc5(step.table, increment)


@dataclass(frozen=True, eq=False, repr=False)
class ReadWriteCommand(ReadCommand[T], WriteCommand[T]): ...

@dataclass(frozen=True, eq=False, repr=False)
class ReadWriteStepCommand(ReadCommand[T], WriteCommand[T], StepCommand[T]): ...


def ro(cc: int, version: set[str] | None, flags: CommandFlags, codec: Codec[T],
       sources: frozenset[SourceCodes] | None = None) -> ReadCommand[T]:
    return ReadCommand(cc, version, flags, sources, codec)


def wo(cc: int, version: set[str] | None, flags: CommandFlags, codec: Codec[T],
       sources: frozenset[SourceCodes] | None = None, *, rc5: Rc5Write | None = None) -> WriteCommand[T]:
    return WriteCommand(cc, version, flags, sources, codec, rc5_write=rc5)


def rw(cc: int, version: set[str] | None, flags: CommandFlags, codec: Codec[T],
       sources: frozenset[SourceCodes] | None = None, *, rc5: Rc5Write | None = None) -> ReadWriteCommand[T]:
    return ReadWriteCommand(cc, version, flags, sources, codec, rc5_write=rc5)


def rw_step(cc: int, version: set[str] | None, flags: CommandFlags, codec: Codec[T],
            sources: frozenset[SourceCodes] | None = None, *, step: Rc5Step,
            rc5: Rc5Write | None = None) -> ReadWriteStepCommand[T]:
    return ReadWriteStepCommand(cc, version, flags, sources, codec, rc5_write=rc5, rc5_step=step)


def proto(cc: int, version: set[str] | None = None, flags: CommandFlags = _0,
          sources: frozenset[SourceCodes] | None = None) -> Command[Any]:
    return Command(cc, version, flags, sources)


@dataclass(frozen=True, eq=False, repr=False)
class _PowerCommand(ReadWriteCommand[bool]):
    """POWER: direct CC where supported, else RC5. Power-off seeds the cache
    first, since the device may not answer promptly while shutting down."""
    async def write(self, context: CommandContext, value: bool) -> None:
        assert self.codec is not None and self.rc5_write is not None
        if not value:
            context.set_cached(self.cc, bytes([0]))
        if context.api_model in POWER_WRITE_SUPPORTED:
            await context.request(self, self.codec.encode(value))
        else:
            await context.send_rc5(self.rc5_write.table, value)


def power(cc: int, version: set[str] | None, flags: CommandFlags, codec: Codec[bool],
          *, rc5: Rc5Write) -> _PowerCommand:
    return _PowerCommand(cc, version, flags, None, codec, rc5_write=rc5)


# === The table ===
# Name                            Type    CC    API         Flags          Codec / policy [, sources]

# --- System ---
POWER                           = power  (0x00, None,       _Z | _U,       BoolCodec(), rc5=Rc5Write(RC5CODE_POWER))
DISPLAY_BRIGHTNESS              = rw     (0x01, _AVR_SA_ST, _U,            EnumCodec(DisplayBrightness), rc5=Rc5Write(RC5CODE_DISPLAY_BRIGHTNESS))
HEADPHONES                      = ro     (0x02, _AVR_SA,    _U,            BoolCodec())
FM_GENRE                        = ro     (0x03, _AVR,       _Z | _U,       StringCodec(), _FM)
SOFTWARE_VERSION                = proto  (0x04, None,       _U)
RESTORE_FACTORY_DEFAULT         = proto  (0x05)
SAVE_RESTORE_COPY_OF_SETTINGS   = proto  (0x06, _AVR)
SIMULATE_RC5_IR_COMMAND         = proto  (0x08, _AVR_SA_ST, _Z)
DISPLAY_INFO_TYPE               = ro     (0x09, _AVR,       _Z | _U,       IntCodec(), _FM)  # per probe — AV41 only responds in FM source
CURRENT_SOURCE                  = proto  (0x1D, _AVR_SA_ST, _Z | _U)
HEADPHONES_OVERRIDE             = wo     (0x1F, _AVR_SA,    _Z,            BoolCodec())

# --- Input ---
VIDEO_SELECTION                 = rw     (0x0A, _PRE_HDA,   _U,            EnumCodec(VideoSelection))
SELECT_ANALOG_DIGITAL           = proto  (0x0B, _AVR,       _Z)
IMAX_ENHANCED                   = rw     (0x0C, _IMAX,      _U,            EnumCodec(ImaxEnhancedMode, set_map=IMAX_ENHANCED_SET_MAP))  # was "Video input type" in 450 (SH256E)

# --- Output ---
VOLUME                          = rw_step(0x0D, _AVR_SA_ST, _Z | _U,       IntCodec(), step=Rc5Step(RC5CODE_VOLUME, frozenset(VOLUME_STEP_SUPPORTED)))
MUTE                            = rw     (0x0E, None,       _Z | _U,       BoolCodec(inverted=True), rc5=Rc5Write(RC5CODE_MUTE, frozenset(MUTE_WRITE_SUPPORTED)))
DIRECT_MODE                     = rw     (0x0F, _DIRECT,    _U,            BoolCodec(), rc5=Rc5Write(RC5CODE_DIRECT_MODE))
DECODE_MODE_2CH                 = rw     (0x10, _AVR,       _U,            EnumCodec(DecodeMode2CH), rc5=Rc5Write(RC5CODE_DECODE_MODE_2CH))
DECODE_MODE_MCH                 = rw     (0x11, _AVR,       _U,            EnumCodec(DecodeModeMCH), rc5=Rc5Write(RC5CODE_DECODE_MODE_MCH))
RDS_INFORMATION                 = ro     (0x12, _AVR,       _Z | _U,       StringCodec(), _FM)
VIDEO_OUTPUT_RESOLUTION         = proto  (0x13, _AVR)

# --- Menu / Tuner ---
MENU                            = ro     (0x14, _AVR,       _U,            EnumCodec(MenuCodes))
TUNER_PRESET                    = rw     (0x15, _AVR,       _Z | _U,       TunerPresetCodec(), _FM)
TUNE                            = proto  (0x16, _AVR,       _Z)
DAB_STATION                     = ro     (0x18, _AVR,       _Z | _U,       StringCodec(), _DAB)
DAB_PROGRAM_TYPE_CATEGORY       = proto  (0x19, _AVR,       _Z | _U,       _DAB)
DLS_PDT                         = ro     (0x1A, _AVR,       _Z | _U,       StringCodec(), _DAB)
PRESET_DETAIL                   = proto  (0x1B, _AVR,       _Z | _U,       _TUN)
NETWORK_PLAYBACK_STATUS         = ro     (0x1C, _NET_PLAY,  _U | _NP,      EnumCodec(NetworkPlaybackStatus), _NET)
ROOM_EQ_NAMES                   = ro     (0x34, _ROOM_NAM,  _U,            RoomEqNamesCodec())

# --- Extended (2.0) ---
INPUT_NAME                      = proto  (0x20, _AVR)
FM_SCAN                         = proto  (0x23, _AVR)
DAB_SCAN                        = proto  (0x24, _AVR,       _0,            _DAB)
HEARTBEAT                       = proto  (0x25)
REBOOT                          = proto  (0x26)
SETUP                           = proto  (0x27, _HDA)
INPUT_CONFIG                    = proto  (0x28, _HDA)
GENERAL_SETUP                   = proto  (0x29, _HDA)
SPEAKER_TYPES                   = proto  (0x2A, _HDA)
SPEAKER_DISTANCES               = proto  (0x2B, _HDA)
SPEAKER_LEVELS                  = proto  (0x2C, _HDA)
VIDEO_INPUTS                    = proto  (0x2D, _HDA)
HDMI_SETTINGS                   = proto  (0x2E, _HDA)
ZONE_SETTINGS                   = proto  (0x2F, _HDA_MZ)
NETWORK_MENU_INFO               = proto  (0x30, _NET_MENU)
BLUETOOTH_MENU_INFO             = proto  (0x32, _HDA)
ENGINEERING_MENU_INFO           = proto  (0x33, _HDA)

# --- Setup / EQ ---
TREBLE_EQUALIZATION             = rw_step(0x35, _AVR,       _Z | _U,       ScaledCodec(-12.0, 12.0, 1.0), step=Rc5Step(RC5CODE_TREBLE))
BASS_EQUALIZATION               = rw_step(0x36, _AVR,       _Z | _U,       ScaledCodec(-12.0, 12.0, 1.0), step=Rc5Step(RC5CODE_BASS))
ROOM_EQUALIZATION               = rw     (0x37, _ROOM_EQ,   _Z | _U,       EnumCodec(RoomEqMode))
DOLBY_AUDIO                     = rw     (0x38, _AVR,       _Z | _U,       EnumCodec(DolbyAudioMode))  # was "Dolby Volume" in 450/860 (SH256E/SH274E)
DOLBY_LEVELER                   = rw     (0x39, _AVR,       _Z | _U,       IntCodec())  # per probe: AV41 still responds despite spec removal at SH289E issue C.0; 0xFF = off
DOLBY_VOLUME_CALIBRATION_OFFSET = rw     (0x3A, _AVR,       _Z | _U,       ScaledCodec(-15.0, 15.0, 1.0))  # per probe: AV41 still responds despite spec removal
BALANCE                         = rw_step(0x3B, _AVR_SA,    _Z | _U,       ScaledCodec(-6.0, 6.0, 1.0), step=Rc5Step(RC5CODE_BALANCE))
DOLBY_PLIIX_DIMENSION           = rw_step(0x3C, _450,       _U,            IntCodec(), step=Rc5Step(RC5CODE_DOLBY_PLIIX_DIMENSION))
DOLBY_PLIIX_CENTRE_WIDTH        = rw_step(0x3D, _450,       _U,            IntCodec(), step=Rc5Step(RC5CODE_DOLBY_PLIIX_CENTRE_WIDTH))
DOLBY_PLIIX_PANORAMA            = rw     (0x3E, _450,       _U,            BoolCodec(), rc5=Rc5Write(RC5CODE_DOLBY_PLIIX_PANORAMA))
SUBWOOFER_TRIM                  = rw_step(0x3F, _AVR,       _Z | _U,       ScaledCodec(-10.0, 10.0, 0.5), step=Rc5Step(RC5CODE_SUB_TRIM))
LIPSYNC_DELAY                   = rw_step(0x40, _AVR,       _Z | _U,       ScaledCodec(0.0, 250.0, 5.0), step=Rc5Step(RC5CODE_LIPSYNC))
COMPRESSION                     = rw     (0x41, _AVR,       _Z | _U,       EnumCodec(CompressionMode))

# --- Incoming Signal / Video ---
INCOMING_VIDEO_PARAMETERS       = ro     (0x42, _AVR,       _U,            StructCodec(VideoParameters.from_bytes))
INCOMING_AUDIO_FORMAT           = proto  (0x43, _AVR,       _U)
INCOMING_AUDIO_SAMPLE_RATE      = ro     (0x44, _AVR_SA_ST, _U,            SampleRateCodec())
SUB_STEREO_TRIM                 = rw     (0x45, _AVR,       _U,            ScaledCodec(-10.0, 0.0, 0.5))
VIDEO_BRIGHTNESS                = rw     (0x46, _450,       _U,            ScaledCodec(-50.0, 50.0, 1.0))
VIDEO_CONTRAST                  = rw     (0x47, _450,       _U,            ScaledCodec(-50.0, 50.0, 1.0))
VIDEO_COLOUR                    = rw     (0x48, _450,       _U,            ScaledCodec(-50.0, 50.0, 1.0))
VIDEO_FILM_MODE                 = rw     (0x49, _450,       _U,            EnumCodec(VideoFilmMode))
VIDEO_EDGE_ENHANCEMENT          = rw     (0x4A, _450,       _U,            IntCodec())  # 0–50
VIDEO_NOISE_REDUCTION           = rw     (0x4C, _450,       _U,            EnumCodec(VideoNoiseReduction))
VIDEO_MPEG_NOISE_REDUCTION      = rw     (0x4D, _450,       _U,            EnumCodec(VideoNoiseReduction))
ZONE_1_OSD_ON_OFF               = rw     (0x4E, _AVR,       _U,            EnumCodec(ZoneOsd, set_map=ZONE_OSD_SET_MAP))
VIDEO_OUTPUT_SWITCHING          = rw     (0x4F, _AVR,       _U,            EnumCodec(HdmiOutput))
BLUETOOTH_STATUS                = proto  (0x50, _HDA,       _U | _NP,      _BT)  # was "Output Frame Rate" in 450 (SH256E)

# --- Diagnostics / Amp Control ---
DC_OFFSET                       = ro     (0x51, _THERM,     _U | _NP,      BoolCodec())  # True = DC offset detected
SHORT_CIRCUIT_STATUS            = ro     (0x52, _CLASS_G,   _U | _NP,      BoolCodec())  # True = short circuit fault
TIMEOUT_COUNTER                 = proto  (0x55, _AMP_DIAG)
# bug in PA720 1.8 firmware — does not return sensor id
LIFTER_TEMPERATURE              = ro     (0x56, _CLASS_G,   _U | _NP,      IntCodec())
OUTPUT_TEMPERATURE              = ro     (0x57, _THERM,     _U | _NP,      IntCodec())
AUTO_SHUTDOWN_CONTROL           = rw     (0x58, _AMP_DIAG,  _U,            EnumCodec(AutoShutdown))

# --- Status / Diagnostics ---
FRIENDLY_NAME                   = rw     (0x53, _SIMPLE_IP, _U,            StringCodec())
IP_ADDRESS                      = proto  (0x54, _SIMPLE_IP)  # 4-byte IP
PHONO_INPUT_TYPE                = proto  (0x59, _PHONO)
INPUT_DETECT                    = ro     (0x5A, _AMP_DIAG,  _U,            BoolCodec())
PROCESSOR_MODE_INPUT            = rw     (0x5B, _SA,        _U,            SaProcessorModeCodec())
PROCESSOR_MODE_VOLUME           = rw     (0x5C, _SA,        _U,            IntCodec())  # 0–99; ST60 reuses 0x5C for Fixed Volume
SYSTEM_STATUS                   = proto  (0x5D, _AMP_DIAG)  # 0xF0 triggers bulk status dump
SYSTEM_MODEL                    = ro     (0x5E, _AMP_DIAG,  _U,            StringCodec())
DAC_FILTER                      = rw     (0x61, _DAC_FILT,  _U,            EnumCodec(DacFilter))  # clashes with AMPLIFIER_MODE on PA240
NOW_PLAYING_INFO                = proto  (0x64, _NOW_PLAY,  _Z | _U | _NP, _NET)
MAX_TURN_ON_VOLUME              = rw     (0x65, _APP_SAFE,  _U,            IntCodec())
MAX_VOLUME                      = rw     (0x66, _APP_SAFE,  _U,            IntCodec())
MAX_STREAMING_VOLUME            = rw     (0x67, _APP_SAFE,  _U,            IntCodec())
# Undocumented (per probe of AV41 firmware 2.0.0); not in any published spec.
UNKNOWN_F0                      = proto  (0xF0, _HDA)  # Returns single byte 0x01
SERIAL_NUMBER                   = proto  (0xF1, _HDA)  # 16-byte ASCII device serial
MAC_ADDRESS                     = proto  (0xF2, _HDA)  # 6-byte MAC address
UNKNOWN_F3                      = proto  (0xF3, _HDA)  # Returns single byte 0x01


# Name each command from its module global, then index by CC.
_ALL: dict[str, Command[Any]] = {
    _n: _v for _n, _v in list(globals().items()) if isinstance(_v, Command)
}
for _n, _v in _ALL.items():
    object.__setattr__(_v, "name", _n)

#: Every command, ordered by CC.
COMMANDS: tuple[Command[Any], ...] = tuple(sorted(_ALL.values(), key=lambda c: c.cc))

_BY_CODE: dict[int, Command[Any]] = {c.cc: c for c in COMMANDS}


def command_for(cc: int) -> Command[Any] | None:
    """The command with this CC byte, or None for an unknown code."""
    return _BY_CODE.get(cc)
