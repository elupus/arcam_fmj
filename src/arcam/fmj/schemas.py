"""Schema types attached to CommandCodes members.

Each CommandCode carries a `schema` attribute holding one of these
dataclasses. The decorator that drives auto-generated getters/setters
(see state.py) inspects `cc.schema` directly — there is no separate
registry. CommandCodes is the single source of truth.

Schema types are pure data; this module deliberately has no imports from
the rest of arcam.fmj so __init__.py can import these dataclasses while
defining CommandCodes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = [
    "AsciiString",
    "BoolByte",
    "ByteEnum",
    "IncDecRc5",
    "IntByte",
    "Rc5Fallback",
    "ScaledSigned",
    "Schema",
    "StructFromBytes",
]


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


@dataclass(frozen=True)
class IncDecRc5:
    """Generates `inc_<name>` and `dec_<name>` methods that use RC5 unless
    the device is in `step_via_cc_supported`, in which case the CC is sent
    directly with `inc_data` / `dec_data` bytes."""
    rc5_table: dict
    step_via_cc_supported: frozenset = field(default_factory=frozenset)
    inc_data: bytes = b"\xF1"
    dec_data: bytes = b"\xF2"


@dataclass(frozen=True, kw_only=True)
class Schema:
    """Common base for command schemas; carries optional inc/dec form."""
    inc_dec: IncDecRc5 | None = None


@dataclass(frozen=True)
class BoolByte(Schema):
    """1 byte → bool. inverted=True flips the truthy/falsy mapping (MUTE)."""
    inverted: bool = False

    @property
    def type_name(self) -> str:
        return "bool"

    def decode(self, data: bytes) -> bool:
        v = int.from_bytes(data, "big")
        return v == 0x00 if self.inverted else v == 0x01

    def encode(self, value: bool) -> bytes:
        if self.inverted:
            return bytes([0x00 if value else 0x01])
        return bytes([0x01 if value else 0x00])


@dataclass(frozen=True)
class IntByte(Schema):
    """1 byte → int."""

    @property
    def type_name(self) -> str:
        return "int"

    def decode(self, data: bytes) -> int:
        return int.from_bytes(data, "big")

    def encode(self, value: int) -> bytes:
        return bytes([value])


@dataclass(frozen=True)
class ByteEnum(Schema):
    """1 byte ↔ VersionedEnum.from_bytes / encode via set_map or .value."""
    enum_cls: type
    set_map: dict | None = None  # asymmetric Set codes (IMAX_ENHANCED, ZONE_1_OSD_ON_OFF)

    @property
    def type_name(self) -> str:
        return self.enum_cls.__name__

    def decode(self, data: bytes) -> Any:
        return self.enum_cls.from_bytes(data)

    def encode(self, value: Any) -> bytes:
        if self.set_map is not None:
            return bytes([self.set_map[value]])
        return bytes([int(value)])


@dataclass(frozen=True)
class ScaledSigned(Schema):
    """Negative-biased scaled float; reuses _get_scaled_negative / _set_scaled."""
    min_value: float
    max_value: float
    scale: float

    @property
    def type_name(self) -> str:
        return "float"

    def decode(self, data: bytes) -> float | None:
        return _get_scaled_negative(data, self.min_value, self.max_value, self.scale)

    def encode(self, value: float) -> bytes:
        return bytes([_set_scaled(value, self.min_value, self.max_value, self.scale)])


@dataclass(frozen=True)
class AsciiString(Schema):
    """N-byte string, decoded with errors='replace' and rstrip()."""
    encoding: str = "utf-8"

    @property
    def type_name(self) -> str:
        return "str"

    def decode(self, data: bytes) -> str:
        return data.decode(self.encoding, errors="replace").rstrip()

    def encode(self, value: str) -> bytes:
        return value.encode(self.encoding)


@dataclass(frozen=True)
class StructFromBytes(Schema):
    """Multi-byte struct with a .from_bytes() classmethod (read-only)."""
    cls: type

    @property
    def type_name(self) -> str:
        return self.cls.__name__

    def decode(self, data: bytes) -> Any:
        return self.cls.from_bytes(data)


@dataclass(frozen=True)
class Rc5Fallback(Schema):
    """Setter that prefers direct CC write but falls back to RC5 when the
    device is outside `direct_set_supported`. Get is delegated to `inner`."""
    inner: Any
    rc5_table: dict
    direct_set_supported: frozenset = field(default_factory=frozenset)

    @property
    def type_name(self) -> str:
        return self.inner.type_name

    def decode(self, data: bytes) -> Any:
        return self.inner.decode(data)
