"""CommandCodes: per-command protocol metadata + optional schemas.

Each entry carries ``(value, version, flags, sources, schema)``. The
optional ``schema`` drives auto-generated get_X / set_X / inc_X / dec_X
methods on ``State``; see ``state.add_accessors`` for gating rules.

This module is the single source of truth for the command catalogue. To add
a new command:
- Append an entry below.
- If the command has a get/set form, supply a schema (BoolByte, ByteEnum,
  ScaledSigned, etc.) so the methods are auto-generated. Attach an
  ``inc_dec=IncDecRc5(...)`` on the schema to add inc/dec steppers.
- If the schema needs a new codec type or RC5 table, define it in ``_codecs``
  or ``_rc5`` first.
"""
from __future__ import annotations

import enum

from .codecs import *  # noqa: F401,F403
from .models import *  # noqa: F401,F403
from .rc5 import *  # noqa: F401,F403
from .schemas import *  # noqa: F401,F403


__all__ = [
    "CommandCodes",
    "CommandFlags",
    "MUTE_WRITE_SUPPORTED",
    "POWER_WRITE_SUPPORTED",
    "SOURCE_WRITE_SUPPORTED",
    "VOLUME_STEP_SUPPORTED",
]


class CommandFlags(enum.IntFlag):
    """Behavioral protocol traits of a command."""
    ZONE_SUPPORT = enum.auto()
    READ_ONLY = enum.auto()     # Request (read) works; Set (write) is unsupported or unsafe.
    WRITE_ONLY = enum.auto()    # Set (write) works; no Request (read) form defined.
    UPDATE = enum.auto()        # Fetched by the State update loop.
    NOT_PUSHED = enum.auto()    # Device does not send unsolicited updates

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
_Z = CommandFlags.ZONE_SUPPORT
_RO = CommandFlags.READ_ONLY
_WO = CommandFlags.WRITE_ONLY
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

class CommandCodes(IntOrTypeEnum):
    """Per-command protocol metadata.

    Each member is ``(cc_byte, version, flags, sources, schema)``. The
    optional ``schema`` drives auto-generated get_X / set_X / inc_X / dec_X
    methods on ``State`` (method names are derived from ``cc.name.lower()``).
    See state.add_accessors for gating rules.
    """

    flags: CommandFlags
    sources: frozenset[SourceCodes] | None
    schema: Schema | None

    @classmethod
    def _create_member(cls, value):
        pseudo_member = cls._value2member_map_.get(value, None)
        if pseudo_member is None:
            obj = int.__new__(cls, value)
            obj._name_ = f"CODE_{value}"
            obj._value_ = value
            obj.version = None
            obj.flags = CommandFlags(0)
            obj.sources = None
            obj.schema = None
            pseudo_member = cls._value2member_map_.setdefault(value, obj)
        return pseudo_member

    def __new__(
        cls,
        value: int,
        version: set[str] | None = None,
        flags: CommandFlags | None = None,
        sources: frozenset[SourceCodes] | None = None,
        schema: Schema | None = None,
    ):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.version = version
        obj.flags = flags if flags is not None else CommandFlags(0)
        obj.sources = sources
        obj.schema = schema
        return obj

    # fmt: off
    # Name                            CC    Version     Flags             Sources  Schema
    # ----                            --    -------     -----             -------  ------

    # --- System ---
    POWER                           = 0x00, None,       _Z | _U,          None,    BoolByte()
    DISPLAY_BRIGHTNESS              = 0x01, _AVR_SA_ST, _U,               None,    Rc5Fallback(inner=ByteEnum(DisplayBrightness), rc5_table=RC5CODE_DISPLAY_BRIGHTNESS)
    HEADPHONES                      = 0x02, _AVR_SA,    _RO | _U,         None,    BoolByte()
    FM_GENRE                        = 0x03, _AVR,       _Z | _RO | _U,    _FM,     AsciiString()
    SOFTWARE_VERSION                = 0x04, None,       _RO | _U
    RESTORE_FACTORY_DEFAULT         = 0x05, None,       _WO
    SAVE_RESTORE_COPY_OF_SETTINGS   = 0x06, _AVR,       _WO
    SIMULATE_RC5_IR_COMMAND         = 0x08, _AVR_SA_ST, _Z | _WO
    DISPLAY_INFO_TYPE               = 0x09, _AVR,       _Z | _RO | _U,    _FM,     IntByte()  # per probe — AV41 only responds in FM source
    CURRENT_SOURCE                  = 0x1D, _AVR_SA_ST, _Z | _RO | _U
    HEADPHONES_OVERRIDE             = 0x1F, _AVR_SA,    _Z | _WO,         None,    BoolByte()

    # --- Input ---
    VIDEO_SELECTION                 = 0x0A, _PRE_HDA,   _U,               None,    ByteEnum(VideoSelection)
    SELECT_ANALOG_DIGITAL           = 0x0B, _AVR,       _Z
    IMAX_ENHANCED                   = 0x0C, _IMAX,      _U,               None,    ByteEnum(ImaxEnhancedMode, set_map=IMAX_ENHANCED_SET_MAP)  # was "Video input type" in 450 (SH256E); not AVR5 (SH289E)

    # --- Output ---
    VOLUME                          = 0x0D, _AVR_SA_ST, _Z | _U,          None,    IntByte(inc_dec=IncDecRc5(rc5_table=RC5CODE_VOLUME, step_via_cc_supported=frozenset(VOLUME_STEP_SUPPORTED)))
    MUTE                            = 0x0E, None,       _Z | _RO | _U,    None,    Rc5Fallback(inner=BoolByte(inverted=True), rc5_table=RC5CODE_MUTE, direct_set_supported=frozenset(MUTE_WRITE_SUPPORTED))
    DIRECT_MODE                     = 0x0F, _DIRECT,    _RO | _U,         None,    Rc5Fallback(inner=BoolByte(), rc5_table=RC5CODE_DIRECT_MODE)
    DECODE_MODE_2CH                 = 0x10, _AVR,       _RO | _U,         None,    Rc5Fallback(inner=ByteEnum(DecodeMode2CH), rc5_table=RC5CODE_DECODE_MODE_2CH)
    DECODE_MODE_MCH                 = 0x11, _AVR,       _RO | _U,         None,    Rc5Fallback(inner=ByteEnum(DecodeModeMCH), rc5_table=RC5CODE_DECODE_MODE_MCH)
    RDS_INFORMATION                 = 0x12, _AVR,       _Z | _RO | _U,    _FM,     AsciiString()
    VIDEO_OUTPUT_RESOLUTION         = 0x13, _AVR,       _RO

    # --- Menu / Tuner / Source ---
    MENU                            = 0x14, _AVR,       _RO | _U,         None,    ByteEnum(MenuCodes)
    TUNER_PRESET                    = 0x15, _AVR,       _Z | _U,          _FM
    TUNE                            = 0x16, _AVR,       _Z
    DAB_STATION                     = 0x18, _AVR,       _Z | _RO | _U,    _DAB,    AsciiString()
    DAB_PROGRAM_TYPE_CATEGORY       = 0x19, _AVR,       _Z | _RO | _U,    _DAB
    DLS_PDT                         = 0x1A, _AVR,       _Z | _RO | _U,    _DAB,    AsciiString()
    PRESET_DETAIL                   = 0x1B, _AVR,       _Z | _RO | _U,    _TUN  # request data is the preset number to query
    NETWORK_PLAYBACK_STATUS         = 0x1C, _NET_PLAY,  _RO | _U | _NP,   _NET,    StructFromBytes(NetworkPlaybackStatus)

    # --- Extended (2.0) ---
    INPUT_NAME                      = 0x20, _AVR,       _RO
    FM_SCAN                         = 0x23, _AVR,       _WO
    DAB_SCAN                        = 0x24, _AVR,       _WO | _U,         _DAB
    HEARTBEAT                       = 0x25, None,       _RO
    REBOOT                          = 0x26, None
    SETUP                           = 0x27, _HDA
    INPUT_CONFIG                    = 0x28, _HDA,       _RO
    GENERAL_SETUP                   = 0x29, _HDA,       _RO
    SPEAKER_TYPES                   = 0x2A, _HDA
    SPEAKER_DISTANCES               = 0x2B, _HDA,       _RO
    SPEAKER_LEVELS                  = 0x2C, _HDA,       _RO
    VIDEO_INPUTS                    = 0x2D, _HDA,       _RO
    HDMI_SETTINGS                   = 0x2E, _HDA,       _RO
    ZONE_SETTINGS                   = 0x2F, _HDA_MZ,    _RO
    NETWORK_MENU_INFO               = 0x30, _NET_MENU,  _RO
    BLUETOOTH_MENU_INFO             = 0x32, _HDA,       _RO
    ENGINEERING_MENU_INFO           = 0x33, _HDA,       _RO
    ROOM_EQ_NAMES                   = 0x34, _ROOM_NAM,  _U

    # --- Setup / EQ ---
    TREBLE_EQUALIZATION             = 0x35, _AVR,       _Z | _U,          None,    ScaledSigned(-12.0, 12.0, 1.0, inc_dec=IncDecRc5(rc5_table=RC5CODE_TREBLE))
    BASS_EQUALIZATION               = 0x36, _AVR,       _Z | _U,          None,    ScaledSigned(-12.0, 12.0, 1.0, inc_dec=IncDecRc5(rc5_table=RC5CODE_BASS))
    ROOM_EQUALIZATION               = 0x37, _ROOM_EQ,   _Z | _U,          None,    ByteEnum(RoomEqMode)
    DOLBY_AUDIO                     = 0x38, _AVR,       _Z | _U,          None,    ByteEnum(DolbyAudioMode)  # was "Dolby Volume" in 450/860 (SH256E/SH274E)
    DOLBY_LEVELER                   = 0x39, _AVR,       _Z | _U,          None,    IntByte()  # per probe: AV41 still responds despite spec removal at SH289E issue C.0; 0xFF = off
    DOLBY_VOLUME_CALIBRATION_OFFSET = 0x3A, _AVR,       _Z | _U,          None,    ScaledSigned(-15.0, 15.0, 1.0)  # per probe: AV41 still responds despite spec removal at SH289E issue C.0
    BALANCE                         = 0x3B, _AVR_SA,    _Z | _U,          None,    ScaledSigned(-6.0, 6.0, 1.0, inc_dec=IncDecRc5(rc5_table=RC5CODE_BALANCE))
    DOLBY_PLIIX_DIMENSION           = 0x3C, _450,       _U,               None,    IntByte(inc_dec=IncDecRc5(rc5_table=RC5CODE_DOLBY_PLIIX_DIMENSION))
    DOLBY_PLIIX_CENTRE_WIDTH        = 0x3D, _450,       _U,               None,    IntByte(inc_dec=IncDecRc5(rc5_table=RC5CODE_DOLBY_PLIIX_CENTRE_WIDTH))
    DOLBY_PLIIX_PANORAMA            = 0x3E, _450,       _U,               None,    Rc5Fallback(inner=BoolByte(), rc5_table=RC5CODE_DOLBY_PLIIX_PANORAMA)
    SUBWOOFER_TRIM                  = 0x3F, _AVR,       _Z | _U,          None,    ScaledSigned(-10.0, 10.0, 0.5, inc_dec=IncDecRc5(rc5_table=RC5CODE_SUB_TRIM))
    LIPSYNC_DELAY                   = 0x40, _AVR,       _Z | _U,          None,    ScaledSigned(0.0, 250.0, 5.0, inc_dec=IncDecRc5(rc5_table=RC5CODE_LIPSYNC))
    COMPRESSION                     = 0x41, _AVR,       _Z | _U,          None,    ByteEnum(CompressionMode)

    # --- Incoming Signal / Video ---
    INCOMING_VIDEO_PARAMETERS       = 0x42, _AVR,       _RO | _U,         None,    StructFromBytes(VideoParameters)
    INCOMING_AUDIO_FORMAT           = 0x43, _AVR,       _RO | _U
    INCOMING_AUDIO_SAMPLE_RATE      = 0x44, _AVR_SA_ST, _RO | _U
    SUB_STEREO_TRIM                 = 0x45, _AVR,       _U,               None,    ScaledSigned(-10.0, 0.0, 0.5)
    VIDEO_BRIGHTNESS                = 0x46, _450,       _U,               None,    ScaledSigned(-50.0, 50.0, 1.0)
    VIDEO_CONTRAST                  = 0x47, _450,       _U,               None,    ScaledSigned(-50.0, 50.0, 1.0)
    VIDEO_COLOUR                    = 0x48, _450,       _U,               None,    ScaledSigned(-50.0, 50.0, 1.0)
    VIDEO_FILM_MODE                 = 0x49, _450,       _U,               None,    ByteEnum(VideoFilmMode)
    VIDEO_EDGE_ENHANCEMENT          = 0x4A, _450,       _U,               None,    IntByte()  # 0–50
    VIDEO_NOISE_REDUCTION           = 0x4C, _450,       _U,               None,    ByteEnum(VideoNoiseReduction)
    VIDEO_MPEG_NOISE_REDUCTION      = 0x4D, _450,       _U,               None,    ByteEnum(VideoNoiseReduction)
    ZONE_1_OSD_ON_OFF               = 0x4E, _AVR,       _U,               None,    ByteEnum(ZoneOsd, set_map=ZONE_OSD_SET_MAP)
    VIDEO_OUTPUT_SWITCHING          = 0x4F, _AVR,       _U,               None,    ByteEnum(HdmiOutput)
    BLUETOOTH_STATUS                = 0x50, _HDA,       _RO | _U | _NP,   _BT  # was "Output Frame Rate" in 450 (SH256E)

    # --- Diagnostics / Amp Control ---
    DC_OFFSET                       = 0x51, _THERM,     _RO | _U | _NP,   None,    BoolByte()  # True = DC offset detected
    SHORT_CIRCUIT_STATUS            = 0x52, _CLASS_G,   _RO | _U | _NP,   None,    BoolByte()  # True = short circuit fault
    TIMEOUT_COUNTER                 = 0x55, _AMP_DIAG,  _RO
    # bug in PA720 1.8 firmware — does not return sensor id
    LIFTER_TEMPERATURE              = 0x56, _CLASS_G,   _RO | _U | _NP,   None,    IntByte()
    OUTPUT_TEMPERATURE              = 0x57, _THERM,     _RO | _U | _NP,   None,    IntByte()
    AUTO_SHUTDOWN_CONTROL           = 0x58, _AMP_DIAG,  _U,               None,    ByteEnum(AutoShutdown)

    # --- Status / Diagnostics ---
    FRIENDLY_NAME                   = 0x53, _SIMPLE_IP, _U,               None,    AsciiString()
    IP_ADDRESS                      = 0x54, _SIMPLE_IP  # 4-byte IP
    PHONO_INPUT_TYPE                = 0x59, _PHONO
    INPUT_DETECT                    = 0x5A, _AMP_DIAG,  _RO | _U,         None,    BoolByte()
    PROCESSOR_MODE_INPUT            = 0x5B, _SA,        _U,               None,    SaProcessorModeInput()
    PROCESSOR_MODE_VOLUME           = 0x5C, _SA,        _U,               None,    IntByte()  # 0–99; ST60 reuses 0x5C for Fixed Volume
    SYSTEM_STATUS                   = 0x5D, _AMP_DIAG,  _RO  # 0xF0 triggers bulk status dump
    SYSTEM_MODEL                    = 0x5E, _AMP_DIAG,  _RO | _U,         None,    AsciiString()
    DAC_FILTER                      = 0x61, _DAC_FILT,  _U,               None,    ByteEnum(DacFilter)  # clashes with AMPLIFIER_MODE on PA240
    NOW_PLAYING_INFO                = 0x64, _NOW_PLAY,  _Z | _U | _NP,    _NET
    MAX_TURN_ON_VOLUME              = 0x65, _APP_SAFE,  _U,               None,    IntByte()
    MAX_VOLUME                      = 0x66, _APP_SAFE,  _U,               None,    IntByte()
    MAX_STREAMING_VOLUME            = 0x67, _APP_SAFE,  _U,               None,    IntByte()

    # Undocumented (per probe of AV41 firmware 2.0.0); not in any published spec.
    # READ_ONLY because we're curious, not crazy
    UNKNOWN_F0                      = 0xF0, _HDA,       _RO  # Returns single byte 0x01
    SERIAL_NUMBER                   = 0xF1, _HDA,       _RO  # 16-byte ASCII device serial
    MAC_ADDRESS                     = 0xF2, _HDA,       _RO  # 6-byte MAC address
    UNKNOWN_F3                      = 0xF3, _HDA,       _RO  # Returns single byte 0x01
    # fmt: on
