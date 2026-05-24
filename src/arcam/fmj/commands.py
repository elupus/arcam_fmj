"""CommandCodes enum — the command catalogue.

Each entry carries ``(value, version, flags)`` where *version* gates model
support and *flags* describe protocol behaviour. Definitions are ordered
by command-code hex value within each section.
"""
from __future__ import annotations

import enum

from .models import (
    APIVERSION_450_SERIES,
    APIVERSION_AMP_DIAGNOSTICS_SERIES,
    APIVERSION_APP_SAFETY_SERIES,
    APIVERSION_AVR_AND_SA_SERIES,
    APIVERSION_AVR_PRE_HDA_SERIES,
    APIVERSION_AVR_SA_AND_ST_SERIES,
    APIVERSION_AVR_SERIES,
    APIVERSION_CLASS_G_SERIES,
    APIVERSION_DAC_FILTER_SERIES,
    APIVERSION_DIRECT_MODE_SERIES,
    APIVERSION_HDA_MULTI_ZONE_SERIES,
    APIVERSION_HDA_SERIES,
    APIVERSION_IMAX_SERIES,
    APIVERSION_NETWORK_MENU_SERIES,
    APIVERSION_NETWORK_PLAYBACK_SERIES,
    APIVERSION_NOW_PLAYING_SERIES,
    APIVERSION_PHONO_SERIES,
    APIVERSION_ROOM_EQ_NAMES_SERIES,
    APIVERSION_ROOM_EQ_SERIES,
    APIVERSION_SA_SERIES,
    APIVERSION_SIMPLE_IP_SERIES,
    APIVERSION_THERMAL_DIAGNOSTICS_SERIES,
    ApiModel,
    IntOrTypeEnum,
)

class CommandFlags(enum.IntFlag):
    """Behavioural protocol traits of a command code.

    ``priority`` controls update-loop ordering: higher-priority commands
    are fetched first.
    """

    def __new__(cls, value, priority=0):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.priority = priority
        return obj

    ZONE_SUPPORT = enum.auto()
    POLL_REQUIRED = (enum.auto(), 20)
    FULL_UPDATE = (enum.auto(), 10)

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
_P = CommandFlags.POLL_REQUIRED
_F = CommandFlags.FULL_UPDATE

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

class CommandCodes(IntOrTypeEnum):
    """Per-command protocol metadata.

    Each member is ``(cc_byte, version_set | None, flags)``. The ``version``
    field gates which device families support the command; ``flags`` describe
    zone support, polling requirements, and update behaviour.
    """

    flags: CommandFlags

    @classmethod
    def _create_member(cls, value):
        pseudo_member = cls._value2member_map_.get(value, None)
        if pseudo_member is None:
            obj = int.__new__(cls, value)
            obj._name_ = f"CODE_{value}"
            obj._value_ = value
            obj.version = None
            obj.flags = CommandFlags(0)
            pseudo_member = cls._value2member_map_.setdefault(value, obj)
        return pseudo_member

    def __new__(cls, value: int, version: set[str] | None = None, flags=CommandFlags(0)):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.version = version
        obj.flags = flags
        return obj

    # fmt: off
    # Name                            CC    Version     Flags
    # ====                            ==    =======     =====

    # --- System ---
    POWER                           = 0x00, None,       _Z | _F
    DISPLAY_BRIGHTNESS              = 0x01, _AVR_SA_ST
    HEADPHONES                      = 0x02, _AVR_SA,    _F
    FMGENRE                         = 0x03, _AVR,       _Z
    SOFTWARE_VERSION                = 0x04, None
    RESTORE_FACTORY_DEFAULT         = 0x05, None
    SAVE_RESTORE_COPY_OF_SETTINGS   = 0x06, _AVR
    SIMULATE_RC5_IR_COMMAND         = 0x08, _AVR_SA_ST, _Z
    DISPLAY_INFORMATION_TYPE        = 0x09, _AVR,       _Z | _F

    # --- Input ---
    VIDEO_SELECTION                 = 0x0A, _PRE_HDA,   _F
    SELECT_ANALOG_DIGITAL           = 0x0B, _AVR,       _Z
    IMAX_ENHANCED                   = 0x0C, _IMAX,      _F          # was "Video input type" in 450 (SH256E); not AVR5 (SH289E)

    # --- Output ---
    VOLUME                          = 0x0D, _AVR_SA_ST, _Z | _F
    MUTE                            = 0x0E, None,       _Z | _F
    DIRECT_MODE_STATUS              = 0x0F, _DIRECT
    DECODE_MODE_STATUS_2CH          = 0x10, _AVR,       _F
    DECODE_MODE_STATUS_MCH          = 0x11, _AVR,       _F
    RDS_INFORMATION                 = 0x12, _AVR,       _Z | _F
    VIDEO_OUTPUT_RESOLUTION         = 0x13, _AVR

    # --- Menu / Tuner / Source ---
    MENU                            = 0x14, _AVR,       _F
    TUNER_PRESET                    = 0x15, _AVR,       _Z | _F
    TUNE                            = 0x16, _AVR,       _Z
    DAB_STATION                     = 0x18, _AVR,       _Z | _F
    DAB_PROGRAM_TYPE_CATEGORY       = 0x19, _AVR,       _Z
    DLS_PDT_INFO                    = 0x1A, _AVR,       _Z | _F
    PRESET_DETAIL                   = 0x1B, _AVR,       _Z | _F
    NETWORK_PLAYBACK_STATUS         = 0x1C, _NET_PLAY,  _P | _F
    CURRENT_SOURCE                  = 0x1D, _AVR_SA_ST, _Z | _F
    HEADPHONES_OVERRIDE             = 0x1F, _AVR_SA,    _Z

    # --- Extended (2.0) ---
    INPUT_NAME                      = 0x20, _AVR
    FM_SCAN                         = 0x23, _AVR
    DAB_SCAN                        = 0x24, _AVR
    HEARTBEAT                       = 0x25, None
    REBOOT                          = 0x26, None
    SETUP                           = 0x27, _HDA
    INPUT_CONFIG                    = 0x28, _HDA
    GENERAL_SETUP                   = 0x29, _HDA
    SPEAKER_TYPES                   = 0x2A, _HDA
    SPEAKER_DISTANCES               = 0x2B, _HDA
    SPEAKER_LEVELS                  = 0x2C, _HDA
    VIDEO_INPUTS                    = 0x2D, _HDA
    HDMI_SETTINGS                   = 0x2E, _HDA
    ZONE_SETTINGS                   = 0x2F, _HDA_MZ
    NETWORK_MENU_INFO               = 0x30, _NET_MENU
    BLUETOOTH_MENU_INFO             = 0x32, _HDA
    ENGINEERING_MENU_INFO           = 0x33, _HDA
    ROOM_EQ_NAMES                   = 0x34, _ROOM_NAM,  _F

    # --- Setup / EQ ---
    TREBLE_EQUALIZATION             = 0x35, _AVR,       _Z | _F
    BASS_EQUALIZATION               = 0x36, _AVR,       _Z | _F
    ROOM_EQUALIZATION               = 0x37, _ROOM_EQ,   _Z | _F
    DOLBY_AUDIO                     = 0x38, _AVR,       _Z | _F     # was "Dolby Volume" in 450/860 (SH256E/SH274E)
    DOLBY_LEVELER                   = 0x39, _PRE_HDA,   _Z          # removed from HDA (SH289E issue C.0)
    DOLBY_VOLUME_CALIBRATION_OFFSET = 0x3A, _PRE_HDA,   _Z          # removed from HDA (SH289E issue C.0)
    BALANCE                         = 0x3B, _AVR_SA,    _Z | _F
    DOLBY_PLII_X_MUSIC_DIMENSION    = 0x3C, _450
    DOLBY_PLII_X_MUSIC_CENTRE_WIDTH = 0x3D, _450
    DOLBY_PLII_X_MUSIC_PANORAMA     = 0x3E, _450
    SUBWOOFER_TRIM                  = 0x3F, _AVR,       _Z | _F
    LIPSYNC_DELAY                   = 0x40, _AVR,       _Z | _F
    COMPRESSION                     = 0x41, _AVR,       _Z | _F

    # --- Incoming Signal / Video ---
    INCOMING_VIDEO_PARAMETERS       = 0x42, _AVR,       _F
    INCOMING_AUDIO_FORMAT           = 0x43, _AVR,       _F
    INCOMING_AUDIO_SAMPLE_RATE      = 0x44, _AVR_SA_ST, _F
    SUB_STEREO_TRIM                 = 0x45, _AVR,       _F
    VIDEO_BRIGHTNESS                = 0x46, _450
    VIDEO_CONTRAST                  = 0x47, _450
    VIDEO_COLOUR                    = 0x48, _450
    VIDEO_FILM_MODE                 = 0x49, _450
    VIDEO_EDGE_ENHANCEMENT          = 0x4A, _450
    VIDEO_NOISE_REDUCTION           = 0x4C, _450
    VIDEO_MPEG_NOISE_REDUCTION      = 0x4D, _450
    ZONE_1_OSD_ON_OFF               = 0x4E, _AVR
    VIDEO_OUTPUT_SWITCHING          = 0x4F, _AVR
    BLUETOOTH_STATUS                = 0x50, _HDA,       _P | _F     # was "Output Frame Rate" in 450 (SH256E)

    # --- Diagnostics / Amp Control ---
    DC_OFFSET                       = 0x51, _THERM
    SHORT_CIRCUIT_STATUS            = 0x52, _CLASS_G
    FRIENDLY_NAME                   = 0x53, _SIMPLE_IP
    IP_ADDRESS                      = 0x54, _SIMPLE_IP
    TIMEOUT_COUNTER                 = 0x55, _AMP_DIAG
    LIFTER_TEMPERATURE              = 0x56, _CLASS_G                 # bug in PA720 1.8: no sensor id in response
    OUTPUT_TEMPERATURE              = 0x57, _THERM                   # bug in PA720 1.8: no sensor id in response
    AUTO_SHUTDOWN_CONTROL           = 0x58, _AMP_DIAG
    PHONO_INPUT_TYPE                = 0x59, _PHONO
    INPUT_DETECT                    = 0x5A, _AMP_DIAG
    PROCESSOR_MODE_INPUT            = 0x5B, _SA
    PROCESSOR_MODE_VOLUME           = 0x5C, _SA                      # ST60 reuses 0x5C for Fixed Volume
    SYSTEM_STATUS                   = 0x5D, _AMP_DIAG
    SYSTEM_MODEL                    = 0x5E, _AMP_DIAG
    DAC_FILTER                      = 0x61, _DAC_FILT                # clashes with AMPLIFIER_MODE on PA240
    NOW_PLAYING_INFO                = 0x64, _NOW_PLAY,  _Z | _P | _F
    MAXIMUM_TURN_ON_VOLUME          = 0x65, _APP_SAFE
    MAXIMUM_VOLUME                  = 0x66, _APP_SAFE
    MAXIMUM_STREAMING_VOLUME        = 0x67, _APP_SAFE
    # fmt: on
