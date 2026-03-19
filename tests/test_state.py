import pytest
from unittest.mock import MagicMock
from arcam.fmj.client import Client
from arcam.fmj.state import State, _get_scaled_negative, _set_scaled
from arcam.fmj import (
    AmxDuetResponse,
    AnswerCodes,
    ApiModel,
    CommandCodes,
    IncomingAudioFormat,
    NetworkPlaybackStatus,
    NowPlayingEncoder,
    NowPlayingInfo,
    ResponsePacket,
    POWER_WRITE_SUPPORTED,
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
