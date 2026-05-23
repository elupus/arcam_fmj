"""RC5 control-code tables and parameter enums.

Each ``RC5CODE_*`` dict maps ``(ApiModel, zone) -> {value: bytes}`` where
the two-byte value is an RC5 system address + command code, sent via
SIMULATE_RC5_IR_COMMAND (0x08).

Tables that affect a specific CC are ordered by that CC.  Tables for
fire-and-forget actions (navigation, playback, toggles, etc.) follow at the
end.

See: SH289E "Simulate RC5 IR Command (0x08)" and "AV RC5 command codes";
     SH256E "Simulate RC5 IR Command (0x08)" and "AVR380/450/750 RC5 command codes".
"""
from __future__ import annotations

import enum

from .codecs import (
    DecodeMode2CH,
    DecodeModeMCH,
    DisplayBrightness,
    HdmiOutput,
    SourceCodes,
)
from .models import ApiModel

# --- Parameter enums ---
# Keys for the RC5CODE_* lookup tables below.  Used by State's send_*
# methods to let callers specify an action by name rather than raw bytes.

class RC5CodeNavigation(enum.Enum):
    """OSD / menu navigation actions."""
    UP = enum.auto()
    DOWN = enum.auto()
    LEFT = enum.auto()
    RIGHT = enum.auto()
    OK = enum.auto()
    MENU = enum.auto()
    HOME = enum.auto()
    RETURN = enum.auto()

class RC5CodePlayback(enum.Enum):
    """Transport / playback controls."""
    PLAY = enum.auto()
    PAUSE = enum.auto()
    STOP = enum.auto()
    SKIP_FORWARD = enum.auto()
    SKIP_BACK = enum.auto()
    FAST_FORWARD = enum.auto()
    REWIND = enum.auto()
    RANDOM = enum.auto()
    REPEAT = enum.auto()
    EJECT = enum.auto()

class RC5CodeToggle(enum.Enum):
    """Stateless toggle actions (no on/off parameter)."""
    STANDBY = enum.auto()
    MUTE = enum.auto()
    MODE = enum.auto()
    INFO = enum.auto()
    DISPLAY_BRIGHTNESS = enum.auto()
    DIRECT_MODE = enum.auto()
    DOLBY_AUDIO = enum.auto()
    ROOM_EQ = enum.auto()
    RADIO = enum.auto()
    DTS_DIALOG_CONTROL = enum.auto()
    FOLLOW_ZONE_1 = enum.auto()
    NEXT_ZONE = enum.auto()
    CYCLE_OUTPUT_RESOLUTION = enum.auto()

class RC5CodeMenuAccess(enum.Enum):
    """Direct-access keys that open a specific setup menu."""
    BASS = enum.auto()
    TREBLE = enum.auto()
    LIPSYNC = enum.auto()
    SUB_TRIM = enum.auto()
    SPEAKER_TRIM = enum.auto()

class RC5CodeColor(enum.Enum):
    """Teletext-style colour buttons used for on-screen menu actions."""
    RED = enum.auto()
    GREEN = enum.auto()
    YELLOW = enum.auto()
    BLUE = enum.auto()

# --- Tables ordered by affected CC ---
# Bool-keyed tables use True = up/increase/on, False = down/decrease/off.

#: Power on/off -> RC5 code.  True = on, False = off.
#: Used to set POWER (0x00) on models not in POWER_WRITE_SUPPORTED.
RC5CODE_POWER = {
    (ApiModel.API450_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.API450_SERIES, 2): {True: bytes([23, 123]), False: bytes([23, 124])},
    (ApiModel.API860_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.API860_SERIES, 2): {True: bytes([23, 123]), False: bytes([23, 124])},
    (ApiModel.APIHDA_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.APIHDA_SERIES, 2): {True: bytes([23, 123]), False: bytes([23, 124])},
    (ApiModel.APISA_SERIES, 1): {True: bytes([16, 123]), False: bytes([16, 124])},
    (ApiModel.APISA_SERIES, 2): {True: bytes([16, 123]), False: bytes([16, 124])},
}

#: Display brightness level -> RC5 code.  Used to set DISPLAY_BRIGHTNESS (0x01).
RC5CODE_DISPLAY_BRIGHTNESS: dict[tuple[ApiModel, int], dict[DisplayBrightness, bytes]] = {
    (ApiModel.API450_SERIES, 1): {
        DisplayBrightness.OFF: bytes([0x10, 0x1F]),
        DisplayBrightness.L1: bytes([0x10, 0x21]),
        DisplayBrightness.L2: bytes([0x10, 0x23]),
    },
    (ApiModel.API860_SERIES, 1): {
        DisplayBrightness.OFF: bytes([0x10, 0x1F]),
        DisplayBrightness.L1: bytes([0x10, 0x22]),
        DisplayBrightness.L2: bytes([0x10, 0x23]),
    },
    (ApiModel.APIHDA_SERIES, 1): {
        DisplayBrightness.OFF: bytes([0x10, 0x1F]),
        DisplayBrightness.L1: bytes([0x10, 0x22]),
        DisplayBrightness.L2: bytes([0x10, 0x23]),
    },
    (ApiModel.APISA_SERIES, 1): {
        DisplayBrightness.OFF: bytes([0x10, 0x1F]),
        DisplayBrightness.L1: bytes([0x10, 0x22]),
        DisplayBrightness.L2: bytes([0x10, 0x23]),
    },
}

#: Volume up/down -> RC5 code.  True = up, False = down.
#: Used to step VOLUME (0x0D) on models not in VOLUME_STEP_SUPPORTED.
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

#: Mute on/off -> RC5 code.  True = mute, False = unmute.
#: Used to set MUTE (0x0E) on models not in MUTE_WRITE_SUPPORTED.
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

#: Direct mode on/off -> RC5 code.  Used to set DIRECT_MODE_STATUS (0x0F).
RC5CODE_DIRECT_MODE: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x4E]), False: bytes([0x10, 0x4F])},
    (ApiModel.API860_SERIES, 1): {True: bytes([0x10, 0x4E]), False: bytes([0x10, 0x4F])},
    (ApiModel.APIHDA_SERIES, 1): {True: bytes([0x10, 0x4E]), False: bytes([0x10, 0x4F])},
}

#: 2CH decode mode -> RC5 code.  Used to set DECODE_MODE_STATUS_2CH (0x10)
#: on models that lack a direct CC write.
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
    (ApiModel.API860_SERIES, 1): {
        DecodeMode2CH.STEREO: bytes([16, 107]),
        DecodeMode2CH.DTS_NEURAL_X: bytes([16, 113]),
        DecodeMode2CH.DTS_VIRTUAL_X: bytes([16, 115]),
        DecodeMode2CH.DOLBY_PL: bytes([16, 110]),
        DecodeMode2CH.DTS_NEO_6_CINEMA: bytes([16, 111]),
        DecodeMode2CH.DTS_NEO_6_MUSIC: bytes([16, 112]),
        DecodeMode2CH.MCH_STEREO: bytes([16, 69]),
    },
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
}

#: MCH decode mode -> RC5 code.  Used to set DECODE_MODE_STATUS_MCH (0x11)
#: on models that lack a direct CC write.
RC5CODE_DECODE_MODE_MCH: dict[tuple[ApiModel, int], dict[DecodeModeMCH, bytes]] = {
    (ApiModel.API450_SERIES, 1): {
        DecodeModeMCH.STEREO_DOWNMIX: bytes([16, 107]),
        DecodeModeMCH.MULTI_CHANNEL: bytes([16, 106]),
        DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES: bytes([16, 118]),
        DecodeModeMCH.DOLBY_PLII_IIx_MOVIE: bytes([16, 103]),
        DecodeModeMCH.DOLBY_PLII_IIx_MUSIC: bytes([16, 104]),
    },
    (ApiModel.API860_SERIES, 1): {
        DecodeModeMCH.STEREO_DOWNMIX: bytes([16, 107]),
        DecodeModeMCH.MULTI_CHANNEL: bytes([16, 106]),
        DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES: bytes([16, 113]),  # maps to DTS_NEURAL_X
        DecodeModeMCH.DOLBY_SURROUND: bytes([16, 110]),
        DecodeModeMCH.DTS_VIRTUAL_X: bytes([16, 115]),
    },
    (ApiModel.APIHDA_SERIES, 1): {
        DecodeModeMCH.STEREO_DOWNMIX: bytes([16, 107]),
        DecodeModeMCH.MULTI_CHANNEL: bytes([16, 106]),
        DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES: bytes([16, 113]),  # maps to DTS_NEURAL_X
        DecodeModeMCH.DOLBY_SURROUND: bytes([16, 110]),
        DecodeModeMCH.DOLBY_VIRTUAL_HEIGHT: bytes([16, 115]),
        DecodeModeMCH.AURO_NATIVE: bytes([16, 103]),
        DecodeModeMCH.AURO_MATIC_3D: bytes([16, 71]),
        DecodeModeMCH.AURO_2D: bytes([16, 104]),
    },
}

#: Source selection -> RC5 code.  Used to set CURRENT_SOURCE (0x1D)
#: on models that lack a direct CC write.
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
}

#: Treble inc/dec -> RC5 code.  Used to step TREBLE_EQUALIZATION (0x35).
RC5CODE_TREBLE: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x2E]), False: bytes([0x10, 0x62])},
    (ApiModel.API860_SERIES, 1): {True: bytes([0x10, 0x2E]), False: bytes([0x10, 0x66])},
    (ApiModel.APIHDA_SERIES, 1): {True: bytes([0x10, 0x2E]), False: bytes([0x10, 0x66])},
}

#: Bass inc/dec -> RC5 code.  Used to step BASS_EQUALIZATION (0x36).
RC5CODE_BASS: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x2C]), False: bytes([0x10, 0x2D])},
    (ApiModel.API860_SERIES, 1): {True: bytes([0x10, 0x2C]), False: bytes([0x10, 0x38])},
    (ApiModel.APIHDA_SERIES, 1): {True: bytes([0x10, 0x2C]), False: bytes([0x10, 0x38])},
}

#: Balance left/right -> RC5 code.  Used to step BALANCE (0x3B).
RC5CODE_BALANCE: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x28]), False: bytes([0x10, 0x26])},
    (ApiModel.API860_SERIES, 1): {True: bytes([0x10, 0x28]), False: bytes([0x10, 0x26])},
    (ApiModel.APIHDA_SERIES, 1): {True: bytes([0x10, 0x28]), False: bytes([0x10, 0x26])},
    (ApiModel.APISA_SERIES, 1): {True: bytes([0x10, 0x28]), False: bytes([0x10, 0x26])},
}

#: Dolby PLIIx dimension inc/dec -> RC5 code.  450 only.
#: Used to step DOLBY_PLII_X_MUSIC_DIMENSION (0x3C).
RC5CODE_DOLBY_PLIIX_DIMENSION: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x72]), False: bytes([0x10, 0x73])},
}

#: Dolby PLIIx centre width inc/dec -> RC5 code.  450 only.
#: Used to step DOLBY_PLII_X_MUSIC_CENTRE_WIDTH (0x3D).
RC5CODE_DOLBY_PLIIX_CENTRE_WIDTH: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x6D]), False: bytes([0x10, 0x71])},
}

#: Dolby PLIIx panorama on/off -> RC5 code.  450 only.
#: Used to set DOLBY_PLII_X_MUSIC_PANORAMA (0x3E).
RC5CODE_DOLBY_PLIIX_PANORAMA: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x74]), False: bytes([0x10, 0x75])},
}

#: Subwoofer trim inc/dec -> RC5 code.  Used to step SUBWOOFER_TRIM (0x3F).
RC5CODE_SUB_TRIM: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x69]), False: bytes([0x10, 0x6C])},
    (ApiModel.API860_SERIES, 1): {True: bytes([0x10, 0x69]), False: bytes([0x10, 0x6C])},
    (ApiModel.APIHDA_SERIES, 1): {True: bytes([0x10, 0x69]), False: bytes([0x10, 0x6C])},
}

#: Lip-sync delay inc/dec -> RC5 code.  Used to step LIPSYNC_DELAY (0x40).
RC5CODE_LIPSYNC: dict[tuple[ApiModel, int], dict[bool, bytes]] = {
    (ApiModel.API450_SERIES, 1): {True: bytes([0x10, 0x29]), False: bytes([0x10, 0x65])},
    (ApiModel.API860_SERIES, 1): {True: bytes([0x10, 0x0F]), False: bytes([0x10, 0x65])},
    (ApiModel.APIHDA_SERIES, 1): {True: bytes([0x10, 0x0F]), False: bytes([0x10, 0x65])},
}

#: HDMI output selection -> RC5 code.  Used to set VIDEO_OUTPUT_SWITCHING (0x4F).
#: 860/HDA only.
RC5CODE_HDMI_OUTPUT: dict[tuple[ApiModel, int], dict[HdmiOutput, bytes]] = {
    (ApiModel.API860_SERIES, 1): {
        HdmiOutput.OUT_1: bytes([0x10, 0x49]),
        HdmiOutput.OUT_2: bytes([0x10, 0x4A]),
        HdmiOutput.OUT_1_2: bytes([0x10, 0x4B]),
    },
    (ApiModel.APIHDA_SERIES, 1): {
        HdmiOutput.OUT_1: bytes([0x10, 0x49]),
        HdmiOutput.OUT_2: bytes([0x10, 0x4A]),
        HdmiOutput.OUT_1_2: bytes([0x10, 0x4B]),
    },
}

# --- Fire-and-forget tables (no corresponding readable CC) ---

_AVR_NAVIGATION: dict[RC5CodeNavigation, bytes] = {
    RC5CodeNavigation.UP: bytes([0x10, 0x56]),
    RC5CodeNavigation.DOWN: bytes([0x10, 0x55]),
    RC5CodeNavigation.LEFT: bytes([0x10, 0x51]),
    RC5CodeNavigation.RIGHT: bytes([0x10, 0x50]),
    RC5CodeNavigation.OK: bytes([0x10, 0x57]),
    RC5CodeNavigation.MENU: bytes([0x10, 0x52]),
    RC5CodeNavigation.HOME: bytes([0x10, 0x2B]),
}

#: OSD navigation -> RC5 code.  860/HDA/SA add RETURN.
RC5CODE_NAVIGATION: dict[tuple[ApiModel, int], dict[RC5CodeNavigation, bytes]] = {
    (ApiModel.API450_SERIES, 1): {**_AVR_NAVIGATION},
    (ApiModel.API860_SERIES, 1): {**_AVR_NAVIGATION, RC5CodeNavigation.RETURN: bytes([0x10, 0x33])},
    (ApiModel.APIHDA_SERIES, 1): {**_AVR_NAVIGATION, RC5CodeNavigation.RETURN: bytes([0x10, 0x33])},
    (ApiModel.APISA_SERIES, 1): {**_AVR_NAVIGATION, RC5CodeNavigation.RETURN: bytes([0x10, 0x33])},
}

_860_HDA_PLAYBACK: dict[RC5CodePlayback, bytes] = {
    RC5CodePlayback.PLAY: bytes([0x10, 0x35]),
    RC5CodePlayback.PAUSE: bytes([0x10, 0x30]),
    RC5CodePlayback.STOP: bytes([0x10, 0x36]),
    RC5CodePlayback.SKIP_FORWARD: bytes([0x10, 0x0B]),
    RC5CodePlayback.SKIP_BACK: bytes([0x10, 0x21]),
    RC5CodePlayback.FAST_FORWARD: bytes([0x10, 0x34]),
    RC5CodePlayback.REWIND: bytes([0x10, 0x79]),
    RC5CodePlayback.RANDOM: bytes([0x10, 0x4C]),
    RC5CodePlayback.REPEAT: bytes([0x10, 0x31]),
}

#: Transport controls -> RC5 code.  450 has a limited subset.
RC5CODE_PLAYBACK: dict[tuple[ApiModel, int], dict[RC5CodePlayback, bytes]] = {
    (ApiModel.API450_SERIES, 1): {
        RC5CodePlayback.PAUSE: bytes([0x10, 0x30]),
        RC5CodePlayback.RANDOM: bytes([0x10, 0x31]),
        RC5CodePlayback.EJECT: bytes([0x10, 0x2D]),
    },
    (ApiModel.API860_SERIES, 1): {**_860_HDA_PLAYBACK, RC5CodePlayback.EJECT: bytes([0x10, 0x2D])},
    (ApiModel.APIHDA_SERIES, 1): {**_860_HDA_PLAYBACK, RC5CodePlayback.EJECT: bytes([0x10, 0x2D])},
}

_AVR_TOGGLES: dict[RC5CodeToggle, bytes] = {
    RC5CodeToggle.STANDBY: bytes([0x10, 0x0C]),
    RC5CodeToggle.MUTE: bytes([0x10, 0x0D]),
    RC5CodeToggle.MODE: bytes([0x10, 0x20]),
    RC5CodeToggle.INFO: bytes([0x10, 0x37]),
    RC5CodeToggle.DISPLAY_BRIGHTNESS: bytes([0x10, 0x3B]),
    RC5CodeToggle.DIRECT_MODE: bytes([0x10, 0x0A]),
    RC5CodeToggle.DOLBY_AUDIO: bytes([0x10, 0x46]),
    RC5CodeToggle.ROOM_EQ: bytes([0x10, 0x1E]),
    RC5CodeToggle.FOLLOW_ZONE_1: bytes([0x10, 0x14]),
    RC5CodeToggle.NEXT_ZONE: bytes([0x10, 0x5F]),
}

#: Stateless toggles -> RC5 code.  860/HDA add RADIO and DTS_DIALOG_CONTROL.
RC5CODE_TOGGLE: dict[tuple[ApiModel, int], dict[RC5CodeToggle, bytes]] = {
    (ApiModel.API450_SERIES, 1): {
        **_AVR_TOGGLES,
        RC5CodeToggle.CYCLE_OUTPUT_RESOLUTION: bytes([0x10, 0x2F]),
    },
    (ApiModel.API450_SERIES, 2): {
        RC5CodeToggle.MUTE: bytes([0x17, 0x03]),
        RC5CodeToggle.NEXT_ZONE: bytes([0x10, 0x5F]),
    },
    (ApiModel.API860_SERIES, 1): {
        **_AVR_TOGGLES,
        RC5CodeToggle.RADIO: bytes([0x10, 0x5B]),
        RC5CodeToggle.DTS_DIALOG_CONTROL: bytes([0x10, 0x5A]),
    },
    (ApiModel.API860_SERIES, 2): {
        RC5CodeToggle.MUTE: bytes([0x17, 0x03]),
        RC5CodeToggle.NEXT_ZONE: bytes([0x10, 0x5F]),
    },
    (ApiModel.APIHDA_SERIES, 1): {
        **_AVR_TOGGLES,
        RC5CodeToggle.RADIO: bytes([0x10, 0x5B]),
        RC5CodeToggle.DTS_DIALOG_CONTROL: bytes([0x10, 0x5A]),
    },
    (ApiModel.APIHDA_SERIES, 2): {
        RC5CodeToggle.MUTE: bytes([0x17, 0x03]),
        RC5CodeToggle.NEXT_ZONE: bytes([0x10, 0x5F]),
    },
    (ApiModel.APISA_SERIES, 1): {
        RC5CodeToggle.STANDBY: bytes([0x10, 0x0C]),
        RC5CodeToggle.MUTE: bytes([0x10, 0x0D]),
        RC5CodeToggle.DISPLAY_BRIGHTNESS: bytes([0x10, 0x3B]),
    },
}

_AVR_MENU_ACCESS: dict[RC5CodeMenuAccess, bytes] = {
    RC5CodeMenuAccess.BASS: bytes([0x10, 0x27]),
    RC5CodeMenuAccess.TREBLE: bytes([0x10, 0x0E]),
    RC5CodeMenuAccess.LIPSYNC: bytes([0x10, 0x32]),
    RC5CodeMenuAccess.SUB_TRIM: bytes([0x10, 0x33]),
    RC5CodeMenuAccess.SPEAKER_TRIM: bytes([0x10, 0x25]),
}

#: Direct menu-access keys -> RC5 code.  AVR models only.
RC5CODE_MENU_ACCESS: dict[tuple[ApiModel, int], dict[RC5CodeMenuAccess, bytes]] = {
    (ApiModel.API450_SERIES, 1): {**_AVR_MENU_ACCESS},
    (ApiModel.API860_SERIES, 1): {**_AVR_MENU_ACCESS},
    (ApiModel.APIHDA_SERIES, 1): {**_AVR_MENU_ACCESS},
}

_AVR_COLORS: dict[RC5CodeColor, bytes] = {
    RC5CodeColor.RED: bytes([0x10, 0x29]),
    RC5CodeColor.GREEN: bytes([0x10, 0x2A]),
    RC5CodeColor.YELLOW: bytes([0x10, 0x2B]),
    RC5CodeColor.BLUE: bytes([0x10, 0x37]),
}

#: Colour buttons -> RC5 code.  AVR models only.
RC5CODE_COLOR: dict[tuple[ApiModel, int], dict[RC5CodeColor, bytes]] = {
    (ApiModel.API450_SERIES, 1): {**_AVR_COLORS},
    (ApiModel.API860_SERIES, 1): {**_AVR_COLORS},
    (ApiModel.APIHDA_SERIES, 1): {**_AVR_COLORS},
}
