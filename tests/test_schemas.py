"""Tests for the schemas module and its integration with State.

Covers:
- Per-schema round-trip behavior (decode/encode)
- Registry coverage meta-test: every CommandCodes entry is either
  schema-driven, a manual override, or excluded by flag rules
- Stub completeness: every schema-driven method is declared in state.pyi
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest

from arcam.fmj.codecs import (
    DecodeMode2CH,
    DolbyAudioMode,
    IMAX_ENHANCED_SET_MAP,
    ImaxEnhancedMode,
)
from arcam.fmj.commands import CommandCodes
from arcam.fmj.schemas import (
    AsciiString,
    BoolByte,
    ByteEnum,
    IncDecRc5,
    IntByte,
    Rc5Fallback,
    ScaledSigned,
    StructFromBytes,
)
from arcam.fmj.state import State


# --- Per-schema round-trip ---


def test_boolbyte_default():
    s = BoolByte()
    assert s.decode(bytes([0x01])) is True
    assert s.decode(bytes([0x00])) is False
    assert s.encode(True) == bytes([0x01])
    assert s.encode(False) == bytes([0x00])


def test_boolbyte_inverted():
    s = BoolByte(inverted=True)
    assert s.decode(bytes([0x00])) is True
    assert s.decode(bytes([0x01])) is False
    assert s.encode(True) == bytes([0x00])
    assert s.encode(False) == bytes([0x01])


def test_intbyte_roundtrip():
    s = IntByte()
    for v in (0, 1, 127, 255):
        assert s.decode(s.encode(v)) == v


def test_byteenum_symmetric():
    s = ByteEnum(DolbyAudioMode)
    encoded = s.encode(DolbyAudioMode.MOVIE)
    assert s.decode(encoded) == DolbyAudioMode.MOVIE


def test_byteenum_asymmetric_set_map():
    s = ByteEnum(ImaxEnhancedMode, set_map=IMAX_ENHANCED_SET_MAP)
    # Decode uses the wire response codes
    assert s.decode(bytes([ImaxEnhancedMode.AUTO.value])) == ImaxEnhancedMode.AUTO
    # Encode uses the set_map
    assert s.encode(ImaxEnhancedMode.AUTO) == bytes([IMAX_ENHANCED_SET_MAP[ImaxEnhancedMode.AUTO]])


@pytest.mark.parametrize(
    "scale, in_db, expected_byte",
    [
        (1.0, 0.0, 0x00),
        (1.0, 6.0, 0x06),
        (1.0, -6.0, 0x86),
        (0.5, 5.0, 0x0A),
        (0.5, -5.0, 0x8A),
    ],
)
def test_scaledsigned_encode(scale, in_db, expected_byte):
    s = ScaledSigned(-12.0, 12.0, scale)
    assert s.encode(in_db) == bytes([expected_byte])


@pytest.mark.parametrize(
    "scale, byte, expected",
    [
        (1.0, 0x00, 0.0),
        (1.0, 0x06, 6.0),
        (1.0, 0x86, -6.0),
        (0.5, 0x0A, 5.0),
    ],
)
def test_scaledsigned_decode(scale, byte, expected):
    s = ScaledSigned(-12.0, 12.0, scale)
    assert s.decode(bytes([byte])) == expected


def test_asciistring():
    s = AsciiString()
    assert s.decode(b"hello   ") == "hello"
    assert s.decode(b"\xff\xfe") == "\ufffd\ufffd"  # replace on invalid


def test_structfrombytes():
    s = StructFromBytes(DolbyAudioMode)  # any VersionedEnum has from_bytes
    assert s.decode(bytes([DolbyAudioMode.MOVIE.value])) == DolbyAudioMode.MOVIE


# --- Registry & State integration ---


def test_state_has_schema_driven_methods():
    """Smoke test: the decorator installed methods from COMMAND_SCHEMAS."""
    assert "get_volume" in State.__dict__
    assert "set_volume" in State.__dict__
    assert "inc_volume" in State.__dict__
    assert "dec_volume" in State.__dict__
    assert "get_mute" in State.__dict__
    assert "set_mute" in State.__dict__
    assert "get_decode_mode_2ch" in State.__dict__
    # Decode-mode set is RC5, kept manual: decorator must NOT have replaced it.
    assert "set_decode_mode_2ch" in State.__dict__


# --- Coverage: every CommandCode is accounted for ---


# Commands that have a *manual* method on State (or no read/write surface).
# Listing them here makes "I forgot to add a schema" loud.
_KNOWN_MANUAL: set[CommandCodes] = {
    CommandCodes.SOFTWARE_VERSION,         # composite "major.minor"
    CommandCodes.RESTORE_FACTORY_DEFAULT,  # bare action; no schema
    CommandCodes.SAVE_RESTORE_COPY_OF_SETTINGS,  # save_settings / restore_settings
    CommandCodes.SIMULATE_RC5_IR_COMMAND,  # plumbed through _send_rc5 / send_*
    CommandCodes.SELECT_ANALOG_DIGITAL,    # no high-level wrapper today
    CommandCodes.CURRENT_SOURCE,           # get_source/set_source — model+zone aware
    CommandCodes.TUNER_PRESET,             # special "0xff = None" handling
    CommandCodes.TUNE,                     # 2-byte freq + inc/dec
    CommandCodes.DAB_PROGRAM_TYPE_CATEGORY,
    CommandCodes.PRESET_DETAIL,            # composite buffered in self._presets
    CommandCodes.INPUT_NAME,               # get_input_name(slot) — uncached, parameterized
    CommandCodes.NETWORK_MENU_INFO,
    CommandCodes.BLUETOOTH_MENU_INFO,
    CommandCodes.ENGINEERING_MENU_INFO,
    CommandCodes.FM_SCAN,                  # fm_scan(up: bool) — direction byte
    CommandCodes.DAB_SCAN,                 # dab_scan() — no params
    CommandCodes.HEARTBEAT,                # keep-alive; not a user API
    CommandCodes.REBOOT,                   # bare action
    CommandCodes.SPEAKER_TYPES,            # no wrapper; multi-byte
    CommandCodes.SPEAKER_DISTANCES,
    CommandCodes.SPEAKER_LEVELS,
    CommandCodes.VIDEO_INPUTS,
    CommandCodes.HDMI_SETTINGS,
    CommandCodes.ZONE_SETTINGS,
    CommandCodes.INPUT_CONFIG,
    CommandCodes.GENERAL_SETUP,
    CommandCodes.SETUP,
    CommandCodes.VIDEO_OUTPUT_RESOLUTION,
    CommandCodes.INCOMING_AUDIO_FORMAT,    # 2-byte tuple of two enums
    CommandCodes.INCOMING_AUDIO_SAMPLE_RATE,  # 1-byte → Hz lookup
    CommandCodes.ROOM_EQ_NAMES,            # 20-byte chunked array
    CommandCodes.BLUETOOTH_STATUS,         # enum + ASCII track name
    CommandCodes.NOW_PLAYING_INFO,         # composite buffered in _now_playing
    CommandCodes.UNKNOWN_F0,                # reserved range — read-only by tag
    CommandCodes.SERIAL_NUMBER,
    CommandCodes.MAC_ADDRESS,
    CommandCodes.UNKNOWN_F3,
    # Commands without high-level wrappers (yet)
    CommandCodes.IP_ADDRESS,
    CommandCodes.PHONO_INPUT_TYPE,
    CommandCodes.SYSTEM_STATUS,
    CommandCodes.TIMEOUT_COUNTER,
}


def test_every_command_is_schema_or_manual():
    """Every CommandCode either has a schema attached or is listed as manual."""
    schemed = {cc for cc in CommandCodes if cc.schema is not None}
    missing = set(CommandCodes) - schemed - _KNOWN_MANUAL
    assert not missing, (
        f"CommandCodes lacking a schema or _KNOWN_MANUAL entry: "
        f"{sorted(m.name for m in missing)}"
    )


# --- state.pyi consistency ---


def _pyi_signatures() -> dict[str, tuple[bool, str]]:
    """Parse state.pyi and return {name: (is_async, signature_str)}.

    Each stub def is exec'd in a namespace with all arcam types available,
    then inspect.signature produces a canonical signature string.
    """
    from arcam.fmj import codecs, commands, models, rc5, schemas
    from arcam.fmj.client import Client, UpdateTask

    pyi = Path(__file__).resolve().parent.parent / "src" / "arcam" / "fmj" / "state.pyi"
    tree = ast.parse(pyi.read_text())

    ns: dict = {}
    for mod in (codecs, commands, models, rc5, schemas):
        ns.update(vars(mod))
    ns["Any"] = Any
    ns["Client"] = Client
    ns["UpdateTask"] = UpdateTask

    result: dict[str, tuple[bool, str]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "State"):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.decorator_list:
                continue  # skip @property etc.
            mod = ast.Module(body=[item], type_ignores=[])
            ast.fix_missing_locations(mod)
            local: dict = {}
            exec(compile(mod, "<pyi>", "exec"), ns, local)
            func = local[item.name]
            is_async = isinstance(item, ast.AsyncFunctionDef)
            result[item.name] = (is_async, str(inspect.signature(func, eval_str=True)))
    return result


def _normalize_sig(sig: str) -> str:
    """Normalize a signature for comparison by stripping defaults and paths.

    Handles pyi ``...`` defaults, runtime tuple defaults like ``(1, 2, 3, 4)``,
    module-qualified type names, and TypeVar repr differences.
    """
    import re
    # Strip all default values — work right-to-left to handle nested parens
    # Match ` = <anything>` up to the next top-level `,` or `)`
    result = []
    depth = 0
    i = 0
    while i < len(sig):
        ch = sig[i]
        if ch in "([":
            depth += 1
            result.append(ch)
        elif ch in ")]":
            depth -= 1
            result.append(ch)
        elif ch == "=" and depth == 1:
            # Skip everything until next `,` or `)` at depth 1
            i += 1
            inner_depth = 0
            while i < len(sig):
                c = sig[i]
                if c in "([":
                    inner_depth += 1
                elif c in ")]":
                    if inner_depth == 0:
                        break
                    inner_depth -= 1
                elif c == "," and inner_depth == 0:
                    break
                i += 1
            continue  # re-process the delimiter
        else:
            result.append(ch)
        i += 1
    sig = "".join(result)
    # Clean up whitespace around commas/parens
    sig = re.sub(r"\s*,\s*", ", ", sig)
    sig = re.sub(r"\(\s+", "(", sig)
    sig = re.sub(r"\s+\)", ")", sig)
    # Strip module prefixes: `arcam.fmj.codecs.Foo` → `Foo`
    sig = re.sub(r"[a-zA-Z_][a-zA-Z0-9_.]*\.([A-Z]\w*)", r"\1", sig)
    # Normalize TypeVar repr: `~_T` → `Any`, bare `_T` → `Any`
    sig = re.sub(r"~_\w+", "Any", sig)
    sig = re.sub(r"\b_T\b", "Any", sig)
    # Normalize `typing.Any` → `Any`
    sig = re.sub(r"typing\.Any", "Any", sig)
    return sig


def _fmt_sig(name: str, is_async: bool, sig: str) -> str:
    prefix = "async def" if is_async else "def"
    return f"{prefix} {name}{sig}"


def test_state_pyi_matches_runtime():
    """Every public method on State must have a matching stub in state.pyi,
    with the same async/sync kind and the same signature."""
    pyi = _pyi_signatures()
    wrong = []

    for name in sorted(State.__dict__):
        if name.startswith("_"):
            continue
        method = State.__dict__[name]
        if isinstance(method, property) or not callable(method):
            continue

        runtime_is_async = inspect.iscoroutinefunction(method)
        try:
            runtime_sig = str(inspect.signature(method, eval_str=True))
        except (ValueError, TypeError):
            continue

        if name not in pyi:
            wrong.append(f"missing from pyi: {_fmt_sig(name, runtime_is_async, runtime_sig)}")
            continue

        stub_is_async, stub_sig = pyi[name]
        if runtime_is_async != stub_is_async:
            wrong.append(
                f"  runtime: {_fmt_sig(name, runtime_is_async, runtime_sig)}\n"
                f"     stub: {_fmt_sig(name, stub_is_async, stub_sig)}"
            )
        elif method.__annotations__ and _normalize_sig(runtime_sig) != _normalize_sig(stub_sig):
            # Only compare signatures when the runtime has annotations;
            # unannotated manual methods are checked for existence and
            # async/sync only — the pyi is authoritative for their types.
            wrong.append(
                f"  runtime: {_fmt_sig(name, runtime_is_async, runtime_sig)}\n"
                f"     stub: {_fmt_sig(name, stub_is_async, stub_sig)}"
            )

    for name in sorted(pyi):
        if not hasattr(State, name):
            wrong.append(f"stub {name} has no runtime counterpart")

    assert not wrong, "state.pyi mismatches:\n" + "\n".join(wrong)
