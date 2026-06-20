"""API version constants, ApiModel, base enum infrastructure."""
from __future__ import annotations

import enum
from collections.abc import Iterable
from typing import Literal, SupportsBytes, SupportsIndex, TypeVar

APIVERSION_450_SERIES = {
    "AVR380",
    "AVR450",
    "AVR750",
}
APIVERSION_860_SERIES = {
    "AV860",
    "AVR850",
    "AVR550",
    "AVR390",
    "SR250",
    "RV-6",
    "RV-9",
    "MC-10",
}
APIVERSION_SA_SERIES = {
    "SA10",
    "SA20",
    "SA30",
    "SA750",
}
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
APIVERSION_PA_SERIES = {
    "PA720",
    "PA240",
    "PA410",
}
APIVERSION_ST_SERIES = {
    "ST60",
}

APIVERSION_DAB_SERIES = {
    "AVR450",
    "AVR750",
    "AV860",
    "AVR850",
    "AVR550",
    "AVR390",
    "RV-6",
    "RV-9",
    "MC-10",
    *APIVERSION_HDA_SERIES,
}

APIVERSION_ZONE2_SERIES = {
    *APIVERSION_450_SERIES,
    *APIVERSION_860_SERIES,
    *APIVERSION_HDA_MULTI_ZONE_SERIES,
}

APIVERSION_DOLBY_PL_SERIES = APIVERSION_450_SERIES

APIVERSION_AURO_SERIES = APIVERSION_HDA_PREMIUM_SERIES

APIVERSION_IMAX_SERIES = {
    *APIVERSION_860_SERIES,
    *APIVERSION_HDA_PREMIUM_SERIES,
}

### General AVR Groups
APIVERSION_AVR_SERIES = {
    *APIVERSION_450_SERIES,
    *APIVERSION_860_SERIES,
    *APIVERSION_HDA_SERIES,
}

APIVERSION_AVR_860_ONWARD_SERIES = {
    *APIVERSION_860_SERIES,
    *APIVERSION_HDA_SERIES,
}

APIVERSION_AVR_PRE_HDA_SERIES = {
    *APIVERSION_450_SERIES,
    *APIVERSION_860_SERIES,
}

# AVR + SA integrated amps (headphones, balance, source selection, etc.)
APIVERSION_AVR_AND_SA_SERIES = {
    *APIVERSION_AVR_SERIES,
    *APIVERSION_SA_SERIES,
}

# AVR + SA + ST (everything except PA power amps)
APIVERSION_AVR_SA_AND_ST_SERIES = {
    *APIVERSION_AVR_AND_SA_SERIES,
    *APIVERSION_ST_SERIES,
}

### Feature-specific Groups

# AVR + SA30/SA750 (direct mode, room EQ — not SA10/SA20)
APIVERSION_DIRECT_MODE_SERIES = {
    *APIVERSION_AVR_SERIES,
    "SA30",
    "SA750",
}

APIVERSION_ROOM_EQ_SERIES = APIVERSION_DIRECT_MODE_SERIES

# HDA + SA30 + SA750
APIVERSION_ROOM_EQ_NAMES_SERIES = {
    *APIVERSION_HDA_SERIES,
    "SA30",
    "SA750",
}

# Diagnostics: SA + PA + ST
APIVERSION_AMP_DIAGNOSTICS_SERIES = {
    *APIVERSION_SA_SERIES,
    *APIVERSION_PA_SERIES,
    *APIVERSION_ST_SERIES,
}

# Thermal/electrical diagnostics: SA + PA only (not ST)
APIVERSION_THERMAL_DIAGNOSTICS_SERIES = {
    *APIVERSION_SA_SERIES,
    *APIVERSION_PA_SERIES,
}

APIVERSION_CLASS_G_SERIES = {
    "PA720",
    "PA240",
    "SA20",
    "SA30",
    "SA750",
}

APIVERSION_PHONO_SERIES = {
    "SA30",
    "SA750",
}

APIVERSION_SIMPLE_IP_SERIES = {
    "PA720",
    "PA240",
    "SA10",
    "SA20",
}

APIVERSION_APP_SAFETY_SERIES = {
    "SA30",
    "SA750",
    "ST60",
}

APIVERSION_NETWORK_PLAYBACK_SERIES = {
    *APIVERSION_AVR_SERIES,
    *APIVERSION_APP_SAFETY_SERIES,
}

# Semantic alias, used in State
APIVERSION_RC5_NUMERIC_SERIES = APIVERSION_AVR_SERIES

# HDA + SA30/SA750 + ST60
APIVERSION_NETWORK_MENU_SERIES = {
    *APIVERSION_HDA_SERIES,
    *APIVERSION_APP_SAFETY_SERIES,
}

APIVERSION_NOW_PLAYING_SERIES = {
    *APIVERSION_HDA_SERIES,
    *APIVERSION_APP_SAFETY_SERIES,
}

# SA + ST60 (DAC_FILTER); clashes with AMPLIFIER_MODE on PA240
APIVERSION_DAC_FILTER_SERIES = {
    *APIVERSION_SA_SERIES,
    *APIVERSION_ST_SERIES,
}

class ApiModel(enum.Enum):
    """Product-family identifier used to select model-specific behaviour.

    Maps to the APIVERSION_*_SERIES sets above and drives source-code
    mapping tables, RC5 code lookups, and write-support gating.
    """

    API450_SERIES = 1
    API860_SERIES = 2
    APISA_SERIES = 3
    APIHDA_SERIES = 4
    APIPA_SERIES = 5
    APIST_SERIES = 6

_API_MODEL_BY_MODEL = {
    model: api
    for series, api in (
        (APIVERSION_450_SERIES, ApiModel.API450_SERIES),
        (APIVERSION_860_SERIES, ApiModel.API860_SERIES),
        (APIVERSION_HDA_SERIES, ApiModel.APIHDA_SERIES),
        (APIVERSION_SA_SERIES, ApiModel.APISA_SERIES),
        (APIVERSION_PA_SERIES, ApiModel.APIPA_SERIES),
        (APIVERSION_ST_SERIES, ApiModel.APIST_SERIES),
    )
    for model in series
}

def api_model_for(model: str | None) -> ApiModel:
    """Map an AMX device-model string to its product family; API450 for unknown/None."""
    return _API_MODEL_BY_MODEL.get(model, ApiModel.API450_SERIES)

_T = TypeVar("_T", bound="IntOrTypeEnum")

class IntOrTypeEnum(enum.IntEnum):
    """Base enum for protocol byte values with optional model-version gating.

    Subclasses (AnswerCodes, DecodeMode2CH, etc.) use the ``version`` field
    to record which device families support a given value.
    """

    version: set[str] | None

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
            pseudo_member = cls._value2member_map_.setdefault(value, obj)
        return pseudo_member

    def __new__(cls, value: int, version: set[str] | None = None):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.version = version
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
