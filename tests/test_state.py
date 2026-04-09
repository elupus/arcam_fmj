import pytest
from unittest.mock import MagicMock
from arcam.fmj.client import Client
from arcam.fmj.state import State, _get_scaled_negative, _set_scaled
from arcam.fmj import (
    AmxDuetResponse,
    AnswerCodes,
    ApiModel,
    BluetoothAudioStatus,
    CommandCodes,
    CommandInvalidAtThisTime,
    CommandNotRecognised,
    CompressionMode,
    DolbyAudioMode,
    ImaxEnhancedMode,
    IncomingAudioFormat,
    NetworkPlaybackStatus,
    NotConnectedException,
    NowPlayingEncoder,
    NowPlayingInfo,
    DisplayBrightness,
    HdmiOutput,
    RC5CodeNavigation,
    RC5CodePlayback,
    RC5CodeToggle,
    RC5CODE_NAVIGATION,
    RC5CODE_PLAYBACK,
    RC5CODE_TOGGLE,
    RC5CODE_BASS,
    RC5CODE_DISPLAY_BRIGHTNESS,
    RC5CODE_HDMI_OUTPUT,
    ResponseException,
    ResponsePacket,
    RoomEqMode,
    UnsupportedCommand,
    VideoSelection,
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


# --- Network Playback Status (0x1C) ---


def test_get_network_playback_status_none():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    assert state.get_network_playback_status() is None


@pytest.mark.parametrize("byte_val, expected", [
    (0x00, NetworkPlaybackStatus.STOPPED),
    (0x01, NetworkPlaybackStatus.TRANSITIONING),
    (0x02, NetworkPlaybackStatus.PLAYING),
    (0x03, NetworkPlaybackStatus.PAUSED),
])
def test_get_network_playback_status(byte_val, expected):
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._state[CommandCodes.NETWORK_PLAYBACK_STATUS] = bytes([byte_val])
    assert state.get_network_playback_status() == expected


# --- Now Playing Info (0x64) ---


def test_get_now_playing_none():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    assert state.get_now_playing() is None


def test_get_now_playing():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._now_playing = NowPlayingInfo(
        track="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        encoder=NowPlayingEncoder.FLAC,
        sample_rate=44100,
    )
    info = state.get_now_playing()
    assert info.track == "Bohemian Rhapsody"
    assert info.artist == "Queen"
    assert info.album == "A Night at the Opera"
    assert info.encoder == NowPlayingEncoder.FLAC
    assert info.sample_rate == 44100


# --- Bluetooth Status (0x50) ---


def test_get_bluetooth_status_none():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    status, track = state.get_bluetooth_status()
    assert status is None
    assert track is None


def test_get_bluetooth_status_no_connection():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._state[CommandCodes.BLUETOOTH_STATUS] = bytes([0x00])
    status, track = state.get_bluetooth_status()
    assert status == BluetoothAudioStatus.NO_CONNECTION
    assert track == ""


def test_get_bluetooth_status_playing_with_track():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._state[CommandCodes.BLUETOOTH_STATUS] = bytes([0x03]) + b"My Song"
    status, track = state.get_bluetooth_status()
    assert status == BluetoothAudioStatus.PLAYING_AAC
    assert track == "My Song"


# --- RC5 typed tables ---


async def test_send_playback():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.send_playback(RC5CodePlayback.PLAY)
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x35])
    )


async def test_send_navigation():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.send_navigation(RC5CodeNavigation.UP)
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x56])
    )


async def test_send_toggle():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.send_toggle(RC5CodeToggle.RADIO)
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x5B])
    )


async def test_send_playback_unsupported_model():
    """PA series has no playback."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIPA_SERIES)
    with pytest.raises(ValueError):
        await state.send_playback(RC5CodePlayback.PLAY)
    client.request.assert_not_called()


async def test_send_playback_unsupported_code():
    """SA series lacks playback codes."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APISA_SERIES)
    with pytest.raises(ValueError):
        await state.send_playback(RC5CodePlayback.PLAY)
    client.request.assert_not_called()


@pytest.mark.parametrize("table", [
    RC5CODE_NAVIGATION, RC5CODE_PLAYBACK, RC5CODE_TOGGLE,
])
def test_rc5_table_entries_are_valid(table):
    """All table entries should map to 2-byte RC5 commands."""
    for key, codes in table.items():
        for code, data in codes.items():
            assert len(data) == 2, f"Bad data for {key} {code}: {data!r}"


@pytest.mark.parametrize("model", [
    ApiModel.API450_SERIES,
    ApiModel.API860_SERIES,
    ApiModel.APIHDA_SERIES,
])
def test_rc5_avr_has_navigation(model):
    """AVR series should all have navigation codes."""
    table = RC5CODE_NAVIGATION[(model, 1)]
    for code in [RC5CodeNavigation.UP, RC5CodeNavigation.DOWN,
                 RC5CodeNavigation.LEFT, RC5CodeNavigation.RIGHT,
                 RC5CodeNavigation.OK, RC5CodeNavigation.MENU]:
        assert code in table


# --- Bool-keyed RC5 tables ---


async def test_inc_bass_equalization():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.inc_bass_equalization()
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x2C])
    )


async def test_dec_bass_equalization():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.dec_bass_equalization()
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x38])
    )


async def test_inc_bass_equalization_unsupported():
    """SA series has no bass RC5 codes."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APISA_SERIES)
    with pytest.raises(ValueError):
        await state.inc_bass_equalization()


def test_rc5_bass_table_entries_are_valid():
    for key, codes in RC5CODE_BASS.items():
        for direction, data in codes.items():
            assert isinstance(direction, bool)
            assert len(data) == 2


# --- Enum-keyed RC5 tables ---


async def test_set_display_brightness():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.set_display_brightness(DisplayBrightness.L2)
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x23])
    )


async def test_set_hdmi_output():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.set_hdmi_output(HdmiOutput.OUT_1_2)
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x4B])
    )


async def test_set_hdmi_output_unsupported():
    """450 series has no HDMI output codes."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.API450_SERIES)
    with pytest.raises(ValueError):
        await state.set_hdmi_output(HdmiOutput.OUT_1)


def test_rc5_display_brightness_table_entries_are_valid():
    for key, codes in RC5CODE_DISPLAY_BRIGHTNESS.items():
        for level, data in codes.items():
            assert isinstance(level, DisplayBrightness)
            assert len(data) == 2


def test_rc5_hdmi_output_table_entries_are_valid():
    for key, codes in RC5CODE_HDMI_OUTPUT.items():
        for output, data in codes.items():
            assert isinstance(output, HdmiOutput)
            assert len(data) == 2


async def test_set_direct_mode():
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    await state.set_direct_mode(True)
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x4E])
    )
    await state.set_direct_mode(False)
    client.request.assert_called_with(
        1, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, 0x4F])
    )


# --- Command support checking ---


def test_is_command_supported_universal():
    """Commands with version=None are always supported."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APISA_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "SA30"})
    assert state._is_command_supported(CommandCodes.POWER) is True
    assert state._is_command_supported(CommandCodes.VOLUME) is True


def test_is_command_supported_matching_model():
    """Commands with version set are supported when model is in the set."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "AVR30"})
    # IMAX_ENHANCED has version=APIVERSION_IMAX_SERIES which includes AVR30
    assert state._is_command_supported(CommandCodes.IMAX_ENHANCED) is True
    # BLUETOOTH_STATUS has version=APIVERSION_HDA_SERIES which includes AVR30
    assert state._is_command_supported(CommandCodes.BLUETOOTH_STATUS) is True


def test_is_command_supported_non_matching_model():
    """Commands with version set are NOT supported when model is not in the set."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APISA_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "SA30"})
    # IMAX_ENHANCED is not supported on SA series
    assert state._is_command_supported(CommandCodes.IMAX_ENHANCED) is False
    # BLUETOOTH_STATUS is HDA-only
    assert state._is_command_supported(CommandCodes.BLUETOOTH_STATUS) is False
    # VIDEO_SELECTION is PRE_HDA_AVR only
    assert state._is_command_supported(CommandCodes.VIDEO_SELECTION) is False


def test_is_command_supported_no_model_is_permissive():
    """When model is unknown, version-restricted commands are allowed."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    # No AMX discovery yet, model is None
    assert state.model is None
    assert state._is_command_supported(CommandCodes.IMAX_ENHANCED) is True


def test_is_command_supported_runtime_blocklist():
    """Commands in the runtime blocklist are not supported regardless of version."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "AVR30"})
    assert state._is_command_supported(CommandCodes.VOLUME) is True
    state._unsupported_commands.add(CommandCodes.VOLUME)
    assert state._is_command_supported(CommandCodes.VOLUME) is False


def test_require_command_raises_for_unsupported():
    """_require_command raises UnsupportedCommand for unsupported commands."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APISA_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "SA30"})
    with pytest.raises(UnsupportedCommand) as exc_info:
        state._require_command(CommandCodes.IMAX_ENHANCED)
    assert exc_info.value.cc == CommandCodes.IMAX_ENHANCED
    assert exc_info.value.model == "SA30"


def test_require_command_passes_for_supported():
    """_require_command does not raise for supported commands."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "AVR30"})
    state._require_command(CommandCodes.POWER)  # should not raise
    state._require_command(CommandCodes.IMAX_ENHANCED)  # should not raise


def test_require_command_raises_for_runtime_blocked():
    """_require_command raises for commands blocked at runtime."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._unsupported_commands.add(CommandCodes.VOLUME)
    with pytest.raises(UnsupportedCommand):
        state._require_command(CommandCodes.VOLUME)


async def test_setter_raises_for_unsupported_command():
    """Setter methods raise UnsupportedCommand when the command is not supported."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APISA_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "SA30"})
    with pytest.raises(UnsupportedCommand):
        await state.set_imax_enhanced(ImaxEnhancedMode.AUTO)
    client.request.assert_not_called()


async def test_setter_raises_for_runtime_blocked_command():
    """Setter methods raise UnsupportedCommand for runtime-blocked commands."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.APIHDA_SERIES)
    state._unsupported_commands.add(CommandCodes.VOLUME)
    with pytest.raises(UnsupportedCommand):
        await state.set_volume(50)
    client.request.assert_not_called()


async def test_update_skips_unsupported_commands():
    """update() should not request commands that are not supported by the device."""
    from arcam.fmj import CommandInvalidAtThisTime

    client = MagicMock(spec=Client)
    client.connected = True
    # Make all requests raise so we purely test which commands are attempted
    client.request.side_effect = CommandInvalidAtThisTime()
    state = State(client, 1, ApiModel.APISA_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "SA30"})

    await state.update()
    requested_commands = [call.args[1] for call in client.request.call_args_list]
    # These commands have version restrictions that exclude SA30
    assert CommandCodes.IMAX_ENHANCED not in requested_commands
    assert CommandCodes.BLUETOOTH_STATUS not in requested_commands
    assert CommandCodes.VIDEO_SELECTION not in requested_commands
    # But universal commands like POWER should still be requested
    assert CommandCodes.POWER in requested_commands


async def test_update_records_command_not_recognised():
    """update() should record COMMAND_NOT_RECOGNISED in the runtime blocklist."""
    from arcam.fmj import CommandNotRecognised

    client = MagicMock(spec=Client)
    client.connected = True
    client.request.side_effect = CommandNotRecognised(cc=CommandCodes.MENU)
    state = State(client, 1, ApiModel.API450_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "AVR450"})

    assert CommandCodes.MENU not in state._unsupported_commands
    await state.update()
    assert CommandCodes.MENU in state._unsupported_commands


# --- _set_scaled return type ---


def test_set_scaled_returns_int():
    """_set_scaled returns an int (callers wrap in bytes([...]))."""
    result = _set_scaled(5.0, 0.0, 10.0, 1.0)
    assert isinstance(result, int)
    assert result == 5


def test_set_scaled_negative_returns_int():
    result = _set_scaled(-3.0, -10.0, 10.0, 1.0)
    assert isinstance(result, int)
    assert result == 0x80 + 3  # 131


# --- Video Selection (0x0A) ---


@pytest.mark.parametrize("zn, api_model", [
    (1, ApiModel.API450_SERIES),
    (1, ApiModel.API860_SERIES),
])
async def test_set_video_selection(zn, api_model):
    """set_video_selection must use CommandCodes.VIDEO_SELECTION, not VideoSelection."""
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)
    client.request.return_value = bytes([0x00])
    await state.set_video_selection(VideoSelection.BD)
    client.request.assert_called_once_with(
        zn, CommandCodes.VIDEO_SELECTION, bytes([VideoSelection.BD])
    )


# --- Model auto-detection API ---


async def test_api_model_property_default():
    """Default api_model should be API450_SERIES."""
    client = MagicMock(spec=Client)
    state = State(client, 1)
    assert state.api_model == ApiModel.API450_SERIES


async def test_api_model_property_setter():
    """api_model can be set manually for devices with unreliable AMX."""
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state.api_model = ApiModel.APIHDA_SERIES
    assert state.api_model == ApiModel.APIHDA_SERIES


async def test_detect_model_from_cached_beacon():
    """detect_model() should use a cached AMX beacon if available."""
    client = MagicMock(spec=Client)
    state = State(client, 1)

    # Simulate a cached AMX response (as if _listen received a beacon)
    state._amxduet = AmxDuetResponse({
        "Device-SDKClass": "Receiver",
        "Device-Make": "ARCAM",
        "Device-Model": "AVR30",
        "Device-Revision": "1.0",
    })

    result = await state.detect_model()
    assert result == ApiModel.APIHDA_SERIES
    assert state.api_model == ApiModel.APIHDA_SERIES
    # Should not have sent any AMX query since beacon was cached
    client.request_raw.assert_not_called()


async def test_detect_model_from_amx_query():
    """detect_model() sends AMX query if no beacon is cached."""
    client = MagicMock(spec=Client)
    state = State(client, 1)

    amx_response = AmxDuetResponse({
        "Device-SDKClass": "Receiver",
        "Device-Make": "ARCAM",
        "Device-Model": "SA30",
        "Device-Revision": "2.0",
    })
    client.request_raw.return_value = amx_response

    result = await state.detect_model()
    assert result == ApiModel.APISA_SERIES
    assert state.api_model == ApiModel.APISA_SERIES
    assert state.model == "SA30"


@pytest.mark.parametrize("model_str, expected_api", [
    ("AVR30", ApiModel.APIHDA_SERIES),
    ("SDP-58", ApiModel.APIHDA_SERIES),
    ("AVR850", ApiModel.API860_SERIES),
    ("AVR450", ApiModel.API450_SERIES),
    ("SA30", ApiModel.APISA_SERIES),
    ("PA720", ApiModel.APIPA_SERIES),
    ("ST60", ApiModel.APIST_SERIES),
])
async def test_detect_model_all_series(model_str, expected_api):
    """detect_model() maps all known model strings correctly."""
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._amxduet = AmxDuetResponse({"Device-Model": model_str})

    result = await state.detect_model()
    assert result == expected_api


async def test_detect_model_unknown_falls_back_to_setup_probe():
    """Unknown model strings should fall back to SETUP probe."""
    client = MagicMock(spec=Client)
    state = State(client, 1, ApiModel.API860_SERIES)
    state._amxduet = AmxDuetResponse({"Device-Model": "UNKNOWN-9000"})

    # SETUP probe raises CommandNotRecognised -> not HDA, keep current
    client.request.side_effect = CommandNotRecognised(cc=CommandCodes.SETUP)

    result = await state.detect_model()
    assert result == ApiModel.API860_SERIES  # unchanged
    client.request.assert_called_once_with(1, CommandCodes.SETUP, bytes([0xF0]))


# --- SETUP probe fallback ---


async def test_detect_model_amx_fails_setup_probe_succeeds():
    """AMX query fails, SETUP probe succeeds -> HDA series."""
    client = MagicMock(spec=Client)
    state = State(client, 1)

    client.request_raw.side_effect = TimeoutError()
    client.request.return_value = bytes([0x01])  # SETUP probe succeeds

    result = await state.detect_model()
    assert result == ApiModel.APIHDA_SERIES
    assert state.api_model == ApiModel.APIHDA_SERIES
    client.request.assert_called_once_with(1, CommandCodes.SETUP, bytes([0xF0]))


async def test_detect_model_amx_fails_setup_probe_invalid_at_this_time():
    """AMX fails, SETUP raises CommandInvalidAtThisTime -> HDA."""
    client = MagicMock(spec=Client)
    state = State(client, 1)

    client.request_raw.side_effect = TimeoutError()
    client.request.side_effect = CommandInvalidAtThisTime(cc=CommandCodes.SETUP)

    result = await state.detect_model()
    assert result == ApiModel.APIHDA_SERIES


async def test_detect_model_amx_fails_setup_probe_not_recognised():
    """AMX fails, SETUP raises CommandNotRecognised -> keep default."""
    client = MagicMock(spec=Client)
    state = State(client, 1)  # default API450_SERIES

    client.request_raw.side_effect = TimeoutError()
    client.request.side_effect = CommandNotRecognised(cc=CommandCodes.SETUP)

    result = await state.detect_model()
    assert result == ApiModel.API450_SERIES  # default unchanged


async def test_detect_model_amx_fails_setup_probe_timeout():
    """AMX fails, SETUP probe times out -> keep default."""
    client = MagicMock(spec=Client)
    state = State(client, 1)

    client.request_raw.side_effect = TimeoutError()
    client.request.side_effect = TimeoutError()

    result = await state.detect_model()
    assert result == ApiModel.API450_SERIES


async def test_detect_model_unknown_model_setup_probe_succeeds():
    """AMX returns unknown model, SETUP probe succeeds -> HDA."""
    client = MagicMock(spec=Client)
    state = State(client, 1)
    state._amxduet = AmxDuetResponse({"Device-Model": "FUTURE-9000"})

    client.request.return_value = bytes([0x01])

    result = await state.detect_model()
    assert result == ApiModel.APIHDA_SERIES
    client.request.assert_called_once_with(1, CommandCodes.SETUP, bytes([0xF0]))


async def test_detect_model_amx_no_model_name_falls_back_to_setup():
    """AMX beacon has no device_model -> falls back to SETUP probe."""
    client = MagicMock(spec=Client)
    state = State(client, 1)
    # Beacon with no Device-Model key
    state._amxduet = AmxDuetResponse({"Device-Make": "ARCAM"})
    assert state._amxduet.device_model is None

    client.request.return_value = bytes([0x01])  # SETUP succeeds

    result = await state.detect_model()
    assert result == ApiModel.APIHDA_SERIES
    client.request.assert_called_once_with(1, CommandCodes.SETUP, bytes([0xF0]))


async def test_detect_model_setup_probe_not_connected():
    """SETUP probe raises NotConnectedException -> inconclusive, keep default."""
    client = MagicMock(spec=Client)
    state = State(client, 1)

    client.request_raw.side_effect = TimeoutError()
    client.request.side_effect = NotConnectedException()

    result = await state.detect_model()
    assert result == ApiModel.API450_SERIES


async def test_detect_model_setup_probe_uses_zone_1():
    """SETUP probe must use zone 1 regardless of State's zone."""
    client = MagicMock(spec=Client)
    state = State(client, 2)  # zone 2

    client.request_raw.side_effect = TimeoutError()
    client.request.return_value = bytes([0x01])

    await state.detect_model()
    client.request.assert_called_once_with(1, CommandCodes.SETUP, bytes([0xF0]))


async def test_detection_attempted_prevents_repeated_probing():
    """detect_model() should only run once via update()."""
    client = MagicMock(spec=Client)
    state = State(client, 1)
    client.connected = True

    client.request_raw.side_effect = TimeoutError()
    client.request.side_effect = CommandNotRecognised(cc=CommandCodes.SETUP)

    # First detect_model sets _detection_attempted
    await state.detect_model()
    assert state._detection_attempted is True

    # Reset mock call counts
    client.request_raw.reset_mock()
    client.request.reset_mock()

    # Second call via update() should skip detection
    await state.update()
    client.request_raw.assert_not_called()  # no AMX query
