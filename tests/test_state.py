import pytest
from unittest.mock import MagicMock
from arcam.fmj.client import Client
from arcam.fmj.state import State, _get_scaled_negative, _set_scaled
from arcam.fmj import (
    AmxDuetResponse,
    AnswerCodes,
    ApiModel,
    CommandCodes,
    CompressionMode,
    DolbyAudioMode,
    ImaxEnhancedMode,
    IncomingAudioFormat,
    ResponsePacket,
    RoomEqMode,
    POWER_WRITE_SUPPORTED,
    SAVE_RESTORE_CONFIRMATION,
    SaveRestoreSubCommand,
)

TEST_PARAMS = [
    (1, ApiModel.API450_SERIES),
    (1, ApiModel.API860_SERIES),
    (1, ApiModel.APIHDA_SERIES),
    (1, ApiModel.APISA_SERIES),
    (1, ApiModel.APIPA_SERIES),
    (1, ApiModel.APIST_SERIES),
    (2, ApiModel.API450_SERIES),
    (2, ApiModel.API860_SERIES),
    (2, ApiModel.APIHDA_SERIES),
    (2, ApiModel.APISA_SERIES),
    (2, ApiModel.APIPA_SERIES),
]

# zn, api_model, power
PARAMS_TO_RC5COMMAND = {
    (1, ApiModel.API450_SERIES, True): bytes([16, 123]),
    (1, ApiModel.API450_SERIES, False): bytes([16, 124]),
    (1, ApiModel.API860_SERIES, True): bytes([16, 123]),
    (1, ApiModel.API860_SERIES, False): bytes([16, 124]),
    (1, ApiModel.APIHDA_SERIES, True): bytes([16, 123]),
    (1, ApiModel.APIHDA_SERIES, False): bytes([16, 124]),
    (1, ApiModel.APISA_SERIES, True): bytes([16, 123]),
    (1, ApiModel.APISA_SERIES, False): bytes([16, 124]),
    (2, ApiModel.API450_SERIES, True): bytes([23, 123]),
    (2, ApiModel.API450_SERIES, False): bytes([23, 124]),
    (2, ApiModel.API860_SERIES, True): bytes([23, 123]),
    (2, ApiModel.API860_SERIES, False): bytes([23, 124]),
    (2, ApiModel.APIHDA_SERIES, True): bytes([23, 123]),
    (2, ApiModel.APIHDA_SERIES, False): bytes([23, 124]),
    (2, ApiModel.APISA_SERIES, True): bytes([16, 123]),
    (2, ApiModel.APISA_SERIES, False): bytes([16, 124]),
}


@pytest.mark.parametrize("zn, api_model", TEST_PARAMS)
async def test_power_on(zn, api_model):
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)
    response = ResponsePacket(
        zn,
        CommandCodes.SIMULATE_RC5_IR_COMMAND,
        AnswerCodes.STATUS_UPDATE,
        bytes([0x01]),
    )
    client.request.return_value = response
    await state.set_power(True)
    if api_model in POWER_WRITE_SUPPORTED:
        client.request.assert_called_with(zn, CommandCodes.POWER, bytes([0x01]))
    else:
        # zn, api_model, power
        code = PARAMS_TO_RC5COMMAND[zn, api_model, True]
        client.request.assert_called_with(
            zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, code
        )


@pytest.mark.parametrize("zn, api_model", TEST_PARAMS)
async def test_power_off(zn, api_model):
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)

    assert state.get_power() is None
    await state.set_power(False)
    if api_model in POWER_WRITE_SUPPORTED:
        client.request.assert_called_with(zn, CommandCodes.POWER, bytes([0x00]))
    else:
        # zn, api_model, power
        code = PARAMS_TO_RC5COMMAND[zn, api_model, False]
        client.send.assert_called_with(zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, code)
    assert state.get_power() is False


# --- Scaled value encoding ---


def test_get_scaled_negative_none_input():
    assert _get_scaled_negative(None, -12.0, 12.0, 1.0) is None


def test_get_scaled_negative_zero():
    assert _get_scaled_negative(bytes([0x00]), -12.0, 12.0, 1.0) == 0.0


@pytest.mark.parametrize("byte_val, expected", [
    (1, 1.0),
    (6, 6.0),
    (12, 12.0),
])
def test_get_scaled_negative_positive(byte_val, expected):
    assert _get_scaled_negative(bytes([byte_val]), -12.0, 12.0, 1.0) == expected


@pytest.mark.parametrize("byte_val, expected", [
    (0x81, -1.0),
    (0x86, -6.0),
    (0x8C, -12.0),
])
def test_get_scaled_negative_negative(byte_val, expected):
    assert _get_scaled_negative(bytes([byte_val]), -12.0, 12.0, 1.0) == expected


def test_get_scaled_negative_out_of_range():
    assert _get_scaled_negative(bytes([13]), -12.0, 12.0, 1.0) is None
    assert _get_scaled_negative(bytes([0x80]), -12.0, 12.0, 1.0) is None
    assert _get_scaled_negative(bytes([0x8D]), -12.0, 12.0, 1.0) is None


def test_get_scaled_negative_fractional_scale():
    """With subwoofer trim params (scale=0.5), byte_val=1 should mean 0.5 dB."""
    assert _get_scaled_negative(bytes([1]), -10.0, 10.0, 0.5) == 0.5


def test_set_scaled():
    assert _set_scaled(6.0, -12.0, 12.0, 1.0) == 6


# --- Volume ---


def test_get_volume_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_volume() is None


def test_get_volume():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.VOLUME] = bytes([50])
    assert state.get_volume() == 50


# --- Mute ---


def test_get_mute_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_mute() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, True),   # 0 = muted
    (0x01, False),  # 1 = unmuted
])
def test_get_mute(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.MUTE] = bytes([byte_val])
    assert state.get_mute() == expected


async def test_set_mute_write_supported():
    """SA/PA/ST series use direct MUTE command."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APISA_SERIES)
    await state.set_mute(True)
    client.request.assert_called_with(1, CommandCodes.MUTE, bytes([0x00]))


async def test_set_mute_rc5():
    """450/860/HDA series use RC5 IR command for mute."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.API450_SERIES)
    await state.set_mute(True)
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([16, 119])
    )


# --- Decode mode ---


@pytest.mark.parametrize("fmt, expected", [
    (IncomingAudioFormat.PCM, True),
    (IncomingAudioFormat.ANALOGUE_DIRECT, True),
    (IncomingAudioFormat.UNDETECTED, True),
    (IncomingAudioFormat.DOLBY_DIGITAL, False),
    (IncomingAudioFormat.DTS, False),
])
def test_get_2ch(fmt, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._state[CommandCodes.INCOMING_AUDIO_FORMAT] = bytes([fmt, 0x02])
    assert state.get_2ch() == expected


def test_get_2ch_no_audio():
    """No audio format data defaults to 2ch."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    assert state.get_2ch() is True


# --- Listener routing ---


def test_listen_status_update():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._listen(ResponsePacket(1, CommandCodes.VOLUME, AnswerCodes.STATUS_UPDATE, bytes([42])))
    assert state.get_volume() == 42


def test_listen_ignores_other_zone():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._listen(ResponsePacket(2, CommandCodes.VOLUME, AnswerCodes.STATUS_UPDATE, bytes([42])))
    assert state.get_volume() is None


def test_listen_clears_on_error():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.VOLUME] = bytes([42])
    state._listen(ResponsePacket(1, CommandCodes.VOLUME, AnswerCodes.COMMAND_NOT_RECOGNISED, b""))
    assert state.get_volume() is None


def test_listen_amxduet():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    amx = AmxDuetResponse({"Device-Model": "AV860", "Device-Revision": "1.2.3"})
    state._listen(amx)
    assert state.model == "AV860"
    assert state.revision == "1.2.3"


# --- Save/Restore Settings (0x06) ---


async def test_save_settings_default_pin():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.save_settings()
    client.request.assert_called_with(
        1, CommandCodes.SAVE_RESTORE_COPY_OF_SETTINGS,
        bytes([SaveRestoreSubCommand.SAVE, *SAVE_RESTORE_CONFIRMATION, 0x01, 0x02, 0x03, 0x04]),
    )


async def test_restore_settings_default_pin():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.restore_settings()
    client.request.assert_called_with(
        1, CommandCodes.SAVE_RESTORE_COPY_OF_SETTINGS,
        bytes([SaveRestoreSubCommand.RESTORE, *SAVE_RESTORE_CONFIRMATION, 0x01, 0x02, 0x03, 0x04]),
    )


async def test_save_settings_custom_pin():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.save_settings(pin=(9, 8, 7, 6))
    client.request.assert_called_with(
        1, CommandCodes.SAVE_RESTORE_COPY_OF_SETTINGS,
        bytes([SaveRestoreSubCommand.SAVE, *SAVE_RESTORE_CONFIRMATION, 0x09, 0x08, 0x07, 0x06]),
    )


# --- Headphones (0x02) ---


def test_get_headphones_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_headphones() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, False),
    (0x01, True),
])
def test_get_headphones(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.HEADPHONES] = bytes([byte_val])
    assert state.get_headphones() == expected


# --- Display Information Type (0x09) ---


def test_get_display_info_type_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_display_info_type() is None


def test_get_display_info_type():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.DISPLAY_INFORMATION_TYPE] = bytes([0x02])
    assert state.get_display_info_type() == 2


async def test_set_display_info_type():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_display_info_type(0x03)
    client.request.assert_called_with(
        1, CommandCodes.DISPLAY_INFORMATION_TYPE, bytes([0x03])
    )


async def test_set_display_info_type_cycle():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_display_info_type(0xE0)
    client.request.assert_called_with(
        1, CommandCodes.DISPLAY_INFORMATION_TYPE, bytes([0xE0])
    )


# --- Lipsync Delay (0x40) ---


def test_get_lipsync_delay_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_lipsync_delay() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, 0.0),
    (0x0A, 50.0),
    (0x32, 250.0),
])
def test_get_lipsync_delay(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.LIPSYNC_DELAY] = bytes([byte_val])
    assert state.get_lipsync_delay() == expected


@pytest.mark.parametrize("value, expected_byte", [
    (0, 0),
    (50, 0x0A),
    (250, 0x32),
])
async def test_set_lipsync_delay(value, expected_byte):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_lipsync_delay(value)
    client.request.assert_called_with(1, CommandCodes.LIPSYNC_DELAY, bytes([expected_byte]))


# --- Subwoofer Trim (0x3F) ---


def test_get_subwoofer_trim_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_subwoofer_trim() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, 0.0),
    (0x02, 1.0),
    (0x14, 10.0),
    (0x81, -0.5),
    (0x82, -1.0),
    (0x94, -10.0),
])
def test_get_subwoofer_trim(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.SUBWOOFER_TRIM] = bytes([byte_val])
    assert state.get_subwoofer_trim() == expected


@pytest.mark.parametrize("value, expected_byte", [
    (0.0, 0),
    (1.0, 2),
    (10.0, 0x14),
    (-1.0, 0x82),
    (-10.0, 0x94),
])
async def test_set_subwoofer_trim(value, expected_byte):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_subwoofer_trim(value)
    client.request.assert_called_with(1, CommandCodes.SUBWOOFER_TRIM, bytes([expected_byte]))


# --- Sub Stereo Trim (0x45) ---


def test_get_sub_stereo_trim_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_sub_stereo_trim() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, 0.0),
    (0x81, -0.5),
    (0x84, -2.0),
    (0x94, -10.0),
])
def test_get_sub_stereo_trim(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.SUB_STEREO_TRIM] = bytes([byte_val])
    assert state.get_sub_stereo_trim() == expected


@pytest.mark.parametrize("value, expected_byte", [
    (0.0, 0),
    (-0.5, 0x81),
    (-2.0, 0x84),
    (-10.0, 0x94),
])
async def test_set_sub_stereo_trim(value, expected_byte):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_sub_stereo_trim(value)
    client.request.assert_called_with(1, CommandCodes.SUB_STEREO_TRIM, bytes([expected_byte]))


# --- Treble Equalization (0x35) ---


def test_get_treble_equalization_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_treble_equalization() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, 0.0),
    (0x06, 6.0),
    (0x0C, 12.0),
    (0x81, -1.0),
    (0x8C, -12.0),
])
def test_get_treble_equalization(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.TREBLE_EQUALIZATION] = bytes([byte_val])
    assert state.get_treble_equalization() == expected


@pytest.mark.parametrize("value, expected_byte", [
    (0.0, 0),
    (6.0, 6),
    (-6.0, 0x86),
])
async def test_set_treble_equalization(value, expected_byte):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_treble_equalization(value)
    client.request.assert_called_with(1, CommandCodes.TREBLE_EQUALIZATION, bytes([expected_byte]))


# --- Bass Equalization (0x36) ---


def test_get_bass_equalization_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_bass_equalization() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, 0.0),
    (0x06, 6.0),
    (0x0C, 12.0),
    (0x81, -1.0),
    (0x8C, -12.0),
])
def test_get_bass_equalization(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.BASS_EQUALIZATION] = bytes([byte_val])
    assert state.get_bass_equalization() == expected


@pytest.mark.parametrize("value, expected_byte", [
    (0.0, 0),
    (6.0, 6),
    (-6.0, 0x86),
    (12.0, 12),
    (-12.0, 0x8C),
])
async def test_set_bass_equalization(value, expected_byte):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_bass_equalization(value)
    client.request.assert_called_with(1, CommandCodes.BASS_EQUALIZATION, bytes([expected_byte]))


# --- Room EQ (0x37) ---


def test_get_room_equalization_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_room_equalization() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, RoomEqMode.OFF),
    (0x01, RoomEqMode.EQ1),
    (0x02, RoomEqMode.EQ2),
    (0x03, RoomEqMode.EQ3),
])
def test_get_room_equalization(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.ROOM_EQUALIZATION] = bytes([byte_val])
    assert state.get_room_equalization() == expected


@pytest.mark.parametrize("mode, expected_byte", [
    (RoomEqMode.OFF, 0x00),
    (RoomEqMode.EQ1, 0x01),
    (RoomEqMode.EQ2, 0x02),
    (RoomEqMode.EQ3, 0x03),
])
async def test_set_room_equalization(mode, expected_byte):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_room_equalization(mode)
    client.request.assert_called_with(1, CommandCodes.ROOM_EQUALIZATION, bytes([expected_byte]))


# --- Room EQ Names (0x34) ---


def test_get_room_eq_names_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_room_eq_names() is None


def test_get_room_eq_names():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    name1 = b"Living Room\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    name2 = b"Flat\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    state._state[CommandCodes.ROOM_EQ_NAMES] = name1 + name2
    names = state.get_room_eq_names()
    assert names == ["Living Room", "Flat"]


# --- Dolby Audio (0x38) ---


def test_get_dolby_audio_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_dolby_audio() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, DolbyAudioMode.OFF),
    (0x01, DolbyAudioMode.MOVIE),
    (0x02, DolbyAudioMode.MUSIC),
    (0x03, DolbyAudioMode.NIGHT),
])
def test_get_dolby_audio(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.DOLBY_AUDIO] = bytes([byte_val])
    assert state.get_dolby_audio() == expected


async def test_set_dolby_audio():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_dolby_audio(DolbyAudioMode.NIGHT)
    client.request.assert_called_with(1, CommandCodes.DOLBY_AUDIO, bytes([0x03]))


# --- Balance (0x3B) ---


def test_get_balance_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_balance() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, 0.0),
    (0x03, 3.0),
    (0x06, 6.0),
    (0x81, -1.0),
    (0x83, -3.0),
    (0x86, -6.0),
])
def test_get_balance(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.BALANCE] = bytes([byte_val])
    assert state.get_balance() == expected


@pytest.mark.parametrize("value, expected_byte", [
    (0.0, 0),
    (3.0, 3),
    (-3.0, 0x83),
    (6.0, 6),
    (-6.0, 0x86),
])
async def test_set_balance(value, expected_byte):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_balance(value)
    client.request.assert_called_with(1, CommandCodes.BALANCE, bytes([expected_byte]))


# --- Compression (0x41) ---


def test_get_compression_none():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.get_compression() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, CompressionMode.OFF),
    (0x01, CompressionMode.MEDIUM),
    (0x02, CompressionMode.HIGH),
])
def test_get_compression(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._state[CommandCodes.COMPRESSION] = bytes([byte_val])
    assert state.get_compression() == expected


async def test_set_compression():
    client = MagicMock(spec=Client)
    state = State(client, 1)
    await state.set_compression(CompressionMode.HIGH)
    client.request.assert_called_with(1, CommandCodes.COMPRESSION, bytes([0x02]))


# --- IMAX Enhanced (0x0C) ---


def test_get_imax_enhanced_none():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    assert state.get_imax_enhanced() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, ImaxEnhancedMode.OFF),
    (0x01, ImaxEnhancedMode.ON),
    (0x02, ImaxEnhancedMode.AUTO),
])
def test_get_imax_enhanced(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._state[CommandCodes.IMAX_ENHANCED] = bytes([byte_val])
    assert state.get_imax_enhanced() == expected


@pytest.mark.parametrize("mode, expected_byte", [
    (ImaxEnhancedMode.OFF, 0xF3),
    (ImaxEnhancedMode.ON, 0xF2),
    (ImaxEnhancedMode.AUTO, 0xF1),
])
async def test_set_imax_enhanced(mode, expected_byte):
    """Set values are asymmetric: OFF->0xF3, ON->0xF2, AUTO->0xF1."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.set_imax_enhanced(mode)
    client.request.assert_called_with(
        1, CommandCodes.IMAX_ENHANCED, bytes([expected_byte])
    )
