"""Tests for the codecs and the typed command catalogue.

Covers:
- Per-codec round-trip behavior (decode/encode), including sentinels
- Catalogue coverage: every CommandCodes is either a typed Command or listed
  as manual / protocol-only
- Capability composition: read/write/step are derivable via isinstance
"""
from __future__ import annotations

import pytest

from arcam.fmj.codecs import (
    BoolCodec,
    DolbyAudioMode,
    EnumCodec,
    IMAX_ENHANCED_SET_MAP,
    ImaxEnhancedMode,
    IntCodec,
    RoomEqNamesCodec,
    SaProcessorModeCodec,
    SampleRateCodec,
    ScaledCodec,
    SourceCodes,
    StringCodec,
    StructCodec,
    TunerPresetCodec,
)
from arcam.fmj.commands import (
    COMMANDS,
    Command,
    OUTPUT_TEMPERATURE,
    ReadCommand,
    StepCommand,
    VOLUME,
    WriteCommand,
)


# --- Per-codec round-trip ---


def test_boolcodec_default():
    s = BoolCodec()
    assert s.decode(bytes([0x01])) is True
    assert s.decode(bytes([0x00])) is False
    assert s.encode(True) == bytes([0x01])
    assert s.encode(False) == bytes([0x00])


def test_boolcodec_inverted():
    s = BoolCodec(inverted=True)
    assert s.decode(bytes([0x00])) is True
    assert s.decode(bytes([0x01])) is False
    assert s.encode(True) == bytes([0x00])
    assert s.encode(False) == bytes([0x01])


def test_intcodec_roundtrip():
    s = IntCodec()
    for v in (0, 1, 127, 255):
        assert s.decode(s.encode(v)) == v


def test_enumcodec_symmetric():
    s = EnumCodec(DolbyAudioMode)
    assert s.decode(s.encode(DolbyAudioMode.MOVIE)) == DolbyAudioMode.MOVIE


def test_enumcodec_asymmetric_set_map():
    s = EnumCodec(ImaxEnhancedMode, set_map=IMAX_ENHANCED_SET_MAP)
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
def test_scaledcodec_encode(scale, in_db, expected_byte):
    s = ScaledCodec(-12.0, 12.0, scale)
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
def test_scaledcodec_decode(scale, byte, expected):
    s = ScaledCodec(-12.0, 12.0, scale)
    assert s.decode(bytes([byte])) == expected


def test_scaledcodec_out_of_range_is_none():
    s = ScaledCodec(-6.0, 6.0, 1.0)
    assert s.decode(bytes([0x40])) is None


def test_stringcodec():
    s = StringCodec()
    assert s.decode(b"hello   ") == "hello"
    assert s.decode(b"\xff\xfe") == "��"  # replace on invalid


def test_structcodec():
    s = StructCodec(DolbyAudioMode.from_bytes)  # any from_bytes callable
    assert s.decode(bytes([DolbyAudioMode.MOVIE.value])) == DolbyAudioMode.MOVIE


def test_tunerpresetcodec_sentinel():
    s = TunerPresetCodec()
    assert s.decode(b"\xff") is None
    assert s.decode(bytes([5])) == 5
    assert s.encode(5) == bytes([5])


def test_samplerate_codec():
    s = SampleRateCodec()
    assert s.decode(bytes([0x02])) == 48000
    assert s.decode(bytes([0x07])) is None  # unknown
    assert s.decode(bytes([0x42])) == 0  # not in map


def test_roomeqnames_codec():
    s = RoomEqNamesCodec()
    data = b"Profile 1".ljust(20, b"\x00") + b"Profile 2".ljust(20, b"\x00")
    assert s.decode(data) == ["Profile 1", "Profile 2"]


def test_saprocessormode_codec():
    s = SaProcessorModeCodec()
    assert s.decode(bytes([0x00])) is None
    assert s.encode(None) == bytes([0x00])
    assert s.decode(bytes([0x01])) == SourceCodes.PHONO  # SA encoding, zone 1
    assert s.encode(SourceCodes.PHONO) == bytes([0x01])
    assert s.decode(bytes([0x0A])) is None  # gap in SA source map — must not raise
    assert s.decode(bytes([0x0C])) is None


# --- Capability composition ---


def test_capabilities_derived_via_isinstance():
    assert isinstance(VOLUME, ReadCommand)
    assert isinstance(VOLUME, WriteCommand)
    assert isinstance(VOLUME, StepCommand)
    assert isinstance(OUTPUT_TEMPERATURE, ReadCommand)
    assert not isinstance(OUTPUT_TEMPERATURE, WriteCommand)
    assert not isinstance(OUTPUT_TEMPERATURE, StepCommand)


# --- Catalogue integrity ---


def test_no_duplicate_codes():
    codes = [command.cc for command in COMMANDS]
    assert len(codes) == len(set(codes)), "duplicate CC bytes in the catalogue"


def test_every_command_typed_or_proto():
    """Each command is exactly one of: a typed accessor (ReadCommand/WriteCommand) or
    a protocol-only command (a bare Command instance)."""
    for command in COMMANDS:
        typed = isinstance(command, (ReadCommand, WriteCommand))
        is_proto = type(command) is Command
        assert typed != is_proto, f"{command.name} must be exactly one of typed / proto"


def test_every_command_named():
    for command in COMMANDS:
        assert command.name, f"command 0x{command.cc:02X} has no name"
