"""Zone state"""

import asyncio
import logging
from typing import Any, TypeVar

import attr

from . import (
    APIVERSION_450_SERIES,
    APIVERSION_860_SERIES,
    APIVERSION_HDA_SERIES,
    APIVERSION_SA_SERIES,
    APIVERSION_PA_SERIES,
    APIVERSION_ST_SERIES,
    AmxDuetRequest,
    AmxDuetResponse,
    AnswerCodes,
    ApiModel,
    BluetoothAudioStatus,
    CommandCodes,
    CommandInvalidAtThisTime,
    EnumFlags,
    CommandNotRecognised,
    CompressionMode,
    ParameterNotRecognised,
    DisplayBrightness,
    HdmiOutput,
    RC5CodeNavigation,
    RC5CodePlayback,
    RC5CodeToggle,
    RC5CodeMenuAccess,
    RC5CodeColor,
    APIVERSION_RC5_NUMERIC_SERIES,
    RC5CODE_NAVIGATION,
    RC5CODE_PLAYBACK,
    RC5CODE_TOGGLE,
    RC5CODE_MENU_ACCESS,
    RC5CODE_BASS,
    RC5CODE_TREBLE,
    RC5CODE_BALANCE,
    RC5CODE_SUB_TRIM,
    RC5CODE_LIPSYNC,
    RC5CODE_DIRECT_MODE,
    RC5CODE_DISPLAY_BRIGHTNESS,
    RC5CODE_HDMI_OUTPUT,
    RC5CODE_COLOR,
    RC5CODE_DOLBY_PLIIX_CENTRE_WIDTH,
    RC5CODE_DOLBY_PLIIX_DIMENSION,
    RC5CODE_DOLBY_PLIIX_PANORAMA,
    DecodeMode2CH,
    DecodeModeMCH,
    DolbyAudioMode,
    IMAX_ENHANCED_SET_MAP,
    ImaxEnhancedMode,
    IncomingAudioConfig,
    IncomingAudioFormat,
    MenuCodes,
    NetworkPlaybackStatus,
    NotConnectedException,
    NowPlayingInfo,
    PresetDetail,
    RoomEqMode,
    SAMPLE_RATE_MAP,
    VideoParameters,
    ResponseException,
    ResponsePacket,
    SourceCodes,
    POWER_WRITE_SUPPORTED,
    MUTE_WRITE_SUPPORTED,
    SOURCE_WRITE_SUPPORTED,
    VOLUME_STEP_SUPPORTED,
    RC5CODE_SOURCE,
    RC5CODE_POWER,
    RC5CODE_MUTE,
    RC5CODE_VOLUME,
    RC5CODE_DECODE_MODE_2CH,
    RC5CODE_DECODE_MODE_MCH,
    SAVE_RESTORE_CONFIRMATION,
    SaveRestoreSubCommand,
    UnsupportedZone,
    VideoSelection,
)
from .client import Client

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")



def _get_scaled_negative(data: bytes | None, min_value: float, max_value: float, scale: float) -> float | None:
    if data is None:
        return None

    neg_limit = round(-min_value / scale) + 0x80
    pos_limit = round(max_value / scale)

    byte_val = int.from_bytes(data, "big")
    if byte_val >= 0x81 and byte_val <= neg_limit:
        return - (byte_val - 0x80) * scale
    if byte_val >= 0x00 and byte_val <= pos_limit:
        return  byte_val * scale
    return None

def _set_scaled(value: float, min_value: float, max_value: float, scale: float) -> bytes:
    value = max(min_value, min(max_value, value))
    value = round(value / scale)
    if value >= 0:
        return value
    else:
        return 0x80 - value

class State:
    _state: dict[int, bytes | None]
    _presets: dict[int, PresetDetail]

    def __init__(
        self, client: Client, zn: int, api_model: ApiModel = ApiModel.API450_SERIES
    ) -> None:
        self._zn = zn
        self._client = client
        self._state = dict()
        self._presets = dict()
        self._now_playing: NowPlayingInfo | None = None
        self._amxduet: AmxDuetResponse | None = None
        self._api_model = api_model

    async def start(self) -> None:
        # pylint: disable=protected-access
        self._client._listen.add(self._listen)

    async def stop(self) -> None:
        # pylint: disable=protected-access
        self._client._listen.remove(self._listen)

    async def __aenter__(self) -> "State":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def to_dict(self) -> dict[str, Any]:
        return {
            "POWER": self.get_power(),
            "VOLUME": self.get_volume(),
            "SOURCE": self.get_source(),
            "MUTE": self.get_mute(),
            "HEADPHONES": self.get_headphones(),
            "MENU": self.get_menu(),
            "DISPLAY_INFO_TYPE": self.get_display_info_type(),
            "IMAX_ENHANCED": self.get_imax_enhanced(),
            "INCOMING_VIDEO_PARAMETERS": self.get_incoming_video_parameters(),
            "INCOMING_AUDIO_FORMAT": self.get_incoming_audio_format(),
            "INCOMING_AUDIO_SAMPLE_RATE": self.get_incoming_audio_sample_rate(),
            "DECODE_MODE_2CH": self.get_decode_mode_2ch(),
            "DECODE_MODE_MCH": self.get_decode_mode_mch(),
            "ROOM_EQUALIZATION": self.get_room_equalization(),
            "ROOM_EQ_NAMES": self.get_room_eq_names(),
            "DOLBY_AUDIO": self.get_dolby_audio(),
            "BASS_EQUALIZATION": self.get_bass_equalization(),
            "TREBLE_EQUALIZATION": self.get_treble_equalization(),
            "BALANCE": self.get_balance(),
            "LIPSYNC_DELAY": self.get_lipsync_delay(),
            "SUBWOOFER_TRIM": self.get_subwoofer_trim(),
            "SUB_STEREO_TRIM": self.get_sub_stereo_trim(),
            "COMPRESSION": self.get_compression(),
            "DAB_STATION": self.get_dab_station(),
            "DLS_PDT": self.get_dls_pdt(),
            "RDS_INFORMATION": self.get_rds_information(),
            "TUNER_PRESET": self.get_tuner_preset(),
            "PRESET_DETAIL": self.get_preset_details(),
            "NETWORK_PLAYBACK_STATUS": self.get_network_playback_status(),
            "NOW_PLAYING": self.get_now_playing(),
            "BLUETOOTH_STATUS": self.get_bluetooth_status(),
        }

    def __repr__(self) -> str:
        return "State ({}) Amx ({})".format(
            self.to_dict(), self._amxduet.values if self._amxduet else {}
        )

    def _listen(self, packet: ResponsePacket | AmxDuetResponse) -> None:
        if isinstance(packet, AmxDuetResponse):
            self._amxduet = packet
            return

        if packet.zn != self._zn:
            return

        if packet.ac == AnswerCodes.STATUS_UPDATE:
            self._state[packet.cc] = packet.data
        else:
            self._state[packet.cc] = None

    @property
    def zn(self) -> int:
        return self._zn

    @property
    def client(self) -> Client:
        return self._client

    @property
    def model(self) -> str | None:
        if self._amxduet:
            return self._amxduet.device_model
        return None

    @property
    def revision(self) -> str | None:
        if self._amxduet:
            return self._amxduet.device_revision
        return None

    def get_rc5code(
        self, table: dict[tuple[ApiModel, int], dict[_T, bytes]], value: _T
    ) -> bytes:
        lookup = table.get((self._api_model, self._zn))
        if not lookup:
            raise ValueError(
                "Unkown mapping for model {} and zone {}".format(
                    self._api_model, self._zn
                )
            )

        command = lookup.get(value)
        if not command:
            raise ValueError(
                "Unkown command for model {} and zone {} and value {}".format(
                    self._api_model, self._zn, value
                )
            )
        return command

    async def _send_rc5(self, table: dict, value) -> None:
        command = self.get_rc5code(table, value)
        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
        )

    def get(self, cc):
        return self._state[cc]

    def get_incoming_video_parameters(self) -> VideoParameters | None:
        value = self._state.get(CommandCodes.INCOMING_VIDEO_PARAMETERS)
        if value is None:
            return None
        return VideoParameters.from_bytes(value)

    def get_incoming_audio_format(
        self,
    ) -> tuple[IncomingAudioFormat, IncomingAudioConfig] | tuple[None, None]:
        value = self._state.get(CommandCodes.INCOMING_AUDIO_FORMAT)
        if value is None:
            return None, None
        return (
            IncomingAudioFormat.from_int(value[0]),
            IncomingAudioConfig.from_int(value[1]),
        )

    def get_incoming_audio_sample_rate(self) -> int | None:
        value = self._state.get(CommandCodes.INCOMING_AUDIO_SAMPLE_RATE)
        if value is None:
            return None
        return SAMPLE_RATE_MAP.get(value[0], 0)

    def get_decode_mode_2ch(self) -> DecodeMode2CH | None:
        value = self._state.get(CommandCodes.DECODE_MODE_STATUS_2CH)
        if value is None:
            return None
        return DecodeMode2CH.from_bytes(value)

    async def set_decode_mode_2ch(self, mode: DecodeMode2CH) -> None:
        await self._send_rc5(RC5CODE_DECODE_MODE_2CH, mode)

    def get_decode_mode_mch(self) -> DecodeModeMCH | None:
        value = self._state.get(CommandCodes.DECODE_MODE_STATUS_MCH)
        if value is None:
            return None
        return DecodeModeMCH.from_bytes(value)

    async def set_decode_mode_mch(self, mode: DecodeModeMCH) -> None:
        await self._send_rc5(RC5CODE_DECODE_MODE_MCH, mode)

    def get_2ch(self) -> bool:
        """Return if source is 2 channel or not."""
        audio_format, _ = self.get_incoming_audio_format()
        return bool(
            audio_format
            in (
                IncomingAudioFormat.PCM,
                IncomingAudioFormat.ANALOGUE_DIRECT,
                IncomingAudioFormat.UNDETECTED,
                None,
            )
        )

    def get_decode_mode(self) -> DecodeModeMCH | DecodeMode2CH | None:
        if self.get_2ch():
            return self.get_decode_mode_2ch()
        else:
            return self.get_decode_mode_mch()

    def get_decode_modes(
        self,
    ) -> list[DecodeModeMCH] | list[DecodeMode2CH] | None:
        if self.get_2ch():
            return list(RC5CODE_DECODE_MODE_2CH.get((self._api_model, self._zn), {}))
        else:
            return list(RC5CODE_DECODE_MODE_MCH.get((self._api_model, self._zn), {}))

    async def set_decode_mode(self, mode: str | DecodeModeMCH | DecodeMode2CH) -> None:
        if self.get_2ch():
            if isinstance(mode, str):
                mode = DecodeMode2CH[mode]
            elif not isinstance(mode, DecodeMode2CH):
                raise ValueError("Decode mode not supported at this time")
            await self.set_decode_mode_2ch(mode)
        else:
            if isinstance(mode, str):
                mode = DecodeModeMCH[mode]
            elif not isinstance(mode, DecodeModeMCH):
                raise ValueError("Decode mode not supported at this time")
            await self.set_decode_mode_mch(mode)

    async def set_direct_mode(self, on: bool) -> None:
        await self._send_rc5(RC5CODE_DIRECT_MODE, on)

    def get_power(self) -> bool | None:
        value = self._state.get(CommandCodes.POWER)
        if value is None:
            return None
        return int.from_bytes(value, "big") == 0x01

    async def set_power(self, power: bool) -> None:
        if self._api_model in POWER_WRITE_SUPPORTED:
            bool_to_hex = 0x01 if power else 0x00
            if not power:
                self._state[CommandCodes.POWER] = bytes([0])
            await self._client.request(
                self._zn, CommandCodes.POWER, bytes([bool_to_hex])
            )
        else:
            if power:
                await self._send_rc5(RC5CODE_POWER, power)
            else:
                command = self.get_rc5code(RC5CODE_POWER, power)
                # seed with a response, since device might not
                # respond in timely fashion, so let's just
                # assume we succeded until response come
                # back.
                self._state[CommandCodes.POWER] = bytes([0])
                await self._client.send(
                    self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
                )

    def get_menu(self) -> MenuCodes | None:
        value = self._state.get(CommandCodes.MENU)
        if value is None:
            return None
        return MenuCodes.from_bytes(value)

    def get_mute(self) -> bool | None:
        value = self._state.get(CommandCodes.MUTE)
        if value is None:
            return None
        return int.from_bytes(value, "big") == 0

    async def set_mute(self, mute: bool) -> None:
        if self._api_model in MUTE_WRITE_SUPPORTED:
            bool_to_hex = 0x00 if mute else 0x01
            await self._client.request(
                self._zn, CommandCodes.MUTE, bytes([bool_to_hex])
            )
        else:
            await self._send_rc5(RC5CODE_MUTE, mute)

    def get_headphones(self) -> bool | None:
        """Return whether headphones are connected."""
        value = self._state.get(CommandCodes.HEADPHONES)
        if value is None:
            return None
        return int.from_bytes(value, "big") == 0x01

    def get_display_info_type(self) -> int | None:
        """Return the current display information type."""
        value = self._state.get(CommandCodes.DISPLAY_INFORMATION_TYPE)
        if value is None:
            return None
        return int.from_bytes(value, "big")

    async def set_display_info_type(self, info_type: int) -> None:
        """Set the display information type. Use 0xE0 to cycle."""
        await self._client.request(
            self._zn, CommandCodes.DISPLAY_INFORMATION_TYPE, bytes([info_type])
        )

    async def set_display_brightness(self, level: DisplayBrightness) -> None:
        await self._send_rc5(RC5CODE_DISPLAY_BRIGHTNESS, level)

    def get_lipsync_delay(self) -> int | None:
        """Return lip sync delay in milliseconds (0-250ms in 5ms steps)."""
        data = self._state.get(CommandCodes.LIPSYNC_DELAY)
        return _get_scaled_negative(data, 0.0, 250.0, 5.0)

    async def set_lipsync_delay(self, delay_ms: int) -> None:
        """Set lip sync delay in milliseconds (0-250ms in 5ms steps)."""
        byte_val = _set_scaled(delay_ms, 0.0, 250.0, 5.0)
        await self._client.request(
            self._zn, CommandCodes.LIPSYNC_DELAY, bytes([byte_val])
        )

    async def inc_lipsync_delay(self) -> None:
        await self._send_rc5(RC5CODE_LIPSYNC, True)

    async def dec_lipsync_delay(self) -> None:
        await self._send_rc5(RC5CODE_LIPSYNC, False)

    def get_subwoofer_trim(self) -> float | None:
        """Return subwoofer trim level in dB (-10 to +10 dB in 0.5dB steps)."""
        data = self._state.get(CommandCodes.SUBWOOFER_TRIM)
        return _get_scaled_negative(data, -10.0, 10.0, 0.5)

    async def set_subwoofer_trim(self, trim_db: float) -> None:
        """Set subwoofer trim level in dB (-10 to +10 dB in 0.5dB steps)."""
        byte_val = _set_scaled(trim_db, -10.0, 10.0, 0.5)
        await self._client.request(
            self._zn, CommandCodes.SUBWOOFER_TRIM, bytes([byte_val])
        )

    async def inc_subwoofer_trim(self) -> None:
        await self._send_rc5(RC5CODE_SUB_TRIM, True)

    async def dec_subwoofer_trim(self) -> None:
        await self._send_rc5(RC5CODE_SUB_TRIM, False)

    def get_sub_stereo_trim(self) -> float | None:
        """Return sub stereo trim level in dB (0 to -10 dB in 0.5dB steps)."""
        data = self._state.get(CommandCodes.SUB_STEREO_TRIM)
        return _get_scaled_negative(data, -10.0, 0.0, 0.5)

    async def set_sub_stereo_trim(self, trim_db: float) -> None:
        """Set sub stereo trim level in dB (0 to -10 dB in 0.5dB steps)."""
        byte_val = _set_scaled(trim_db, -10.0, 0.0, 0.5)
        await self._client.request(
            self._zn, CommandCodes.SUB_STEREO_TRIM, bytes([byte_val])
        )

    def get_treble_equalization(self) -> float | None:
        """Return treble equalization level in dB (-12 to +12 dB in 1dB steps)."""
        data = self._state.get(CommandCodes.TREBLE_EQUALIZATION)
        return _get_scaled_negative(data, -12.0, 12.0, 1.0)

    async def set_treble_equalization(self, trim_db: float) -> None:
        """Set treble equalization level in dB (-12 to +12 dB in 1dB steps)."""
        byte_val = _set_scaled(trim_db, -12.0, 12.0, 1.0)
        await self._client.request(
            self._zn, CommandCodes.TREBLE_EQUALIZATION, bytes([byte_val])
        )

    async def inc_treble_equalization(self) -> None:
        await self._send_rc5(RC5CODE_TREBLE, True)

    async def dec_treble_equalization(self) -> None:
        await self._send_rc5(RC5CODE_TREBLE, False)

    def get_bass_equalization(self) -> float | None:
        """Return bass equalization level in dB (-12 to +12 dB in 1dB steps)."""
        data = self._state.get(CommandCodes.BASS_EQUALIZATION)
        return _get_scaled_negative(data, -12.0, 12.0, 1.0)

    async def set_bass_equalization(self, trim_db: float) -> None:
        """Set bass equalization level in dB (-12 to +12 dB in 1dB steps)."""
        byte_val = _set_scaled(trim_db, -12.0, 12.0, 1.0)
        await self._client.request(
            self._zn, CommandCodes.BASS_EQUALIZATION, bytes([byte_val])
        )

    async def inc_bass_equalization(self) -> None:
        await self._send_rc5(RC5CODE_BASS, True)

    async def dec_bass_equalization(self) -> None:
        await self._send_rc5(RC5CODE_BASS, False)

    def get_room_equalization(self) -> RoomEqMode | None:
        """Return room equalization (DIRAC) mode."""
        value = self._state.get(CommandCodes.ROOM_EQUALIZATION)
        if value is None:
            return None
        return RoomEqMode.from_bytes(value)

    async def set_room_equalization(self, mode: RoomEqMode) -> None:
        """Set room equalization (DIRAC) mode."""
        await self._client.request(
            self._zn, CommandCodes.ROOM_EQUALIZATION, bytes([mode])
        )

    def get_room_eq_names(self) -> list[str] | None:
        """Return user-defined names for the room EQ profiles."""
        value = self._state.get(CommandCodes.ROOM_EQ_NAMES)
        if value is None:
            return None
        names = []
        for i in range(0, len(value), 20):
            name = value[i:i + 20].decode("ascii", errors="replace").rstrip("\x00").strip()
            names.append(name)
        return names

    def get_dolby_audio(self) -> DolbyAudioMode | None:
        """Return the current Dolby Audio mode."""
        value = self._state.get(CommandCodes.DOLBY_AUDIO)
        if value is None:
            return None
        return DolbyAudioMode.from_bytes(value)

    async def set_dolby_audio(self, mode: DolbyAudioMode) -> None:
        """Set the Dolby Audio mode."""
        await self._client.request(
            self._zn, CommandCodes.DOLBY_AUDIO, bytes([mode])
        )

    async def inc_dolby_pliix_centre_width(self) -> None:
        await self._send_rc5(RC5CODE_DOLBY_PLIIX_CENTRE_WIDTH, True)

    async def dec_dolby_pliix_centre_width(self) -> None:
        await self._send_rc5(RC5CODE_DOLBY_PLIIX_CENTRE_WIDTH, False)

    async def inc_dolby_pliix_dimension(self) -> None:
        await self._send_rc5(RC5CODE_DOLBY_PLIIX_DIMENSION, True)

    async def dec_dolby_pliix_dimension(self) -> None:
        await self._send_rc5(RC5CODE_DOLBY_PLIIX_DIMENSION, False)

    async def set_dolby_pliix_panorama(self, on: bool) -> None:
        await self._send_rc5(RC5CODE_DOLBY_PLIIX_PANORAMA, on)

    def get_balance(self) -> float | None:
        """Return balance level (-6 to +6 in 1dB steps)."""
        data = self._state.get(CommandCodes.BALANCE)
        return _get_scaled_negative(data, -6.0, 6.0, 1.0)

    async def set_balance(self, value: float) -> None:
        """Set balance level (-6 to +6 in 1dB steps)."""
        byte_val = _set_scaled(value, -6.0, 6.0, 1.0)
        await self._client.request(
            self._zn, CommandCodes.BALANCE, bytes([byte_val])
        )

    async def inc_balance(self) -> None:
        """Shift balance right."""
        await self._send_rc5(RC5CODE_BALANCE, True)

    async def dec_balance(self) -> None:
        """Shift balance left."""
        await self._send_rc5(RC5CODE_BALANCE, False)

    def get_compression(self) -> CompressionMode | None:
        """Return the dynamic range compression setting."""
        value = self._state.get(CommandCodes.COMPRESSION)
        if value is None:
            return None
        return CompressionMode.from_bytes(value)

    async def set_compression(self, mode: CompressionMode) -> None:
        """Set the dynamic range compression setting."""
        await self._client.request(
            self._zn, CommandCodes.COMPRESSION, bytes([mode])
        )

    def get_imax_enhanced(self) -> ImaxEnhancedMode | None:
        """Return the IMAX Enhanced mode (HDA premium series)."""
        value = self._state.get(CommandCodes.IMAX_ENHANCED)
        if value is None:
            return None
        return ImaxEnhancedMode.from_bytes(value)

    async def set_imax_enhanced(self, mode: ImaxEnhancedMode) -> None:
        """Set the IMAX Enhanced mode (HDA premium series)."""
        command_byte = IMAX_ENHANCED_SET_MAP[mode]
        await self._client.request(
            self._zn, CommandCodes.IMAX_ENHANCED, bytes([command_byte])
        )

    def get_video_selection(self) -> VideoSelection | None:
        """Return the video input selection (pre-HDA AVR series)."""
        value = self._state.get(CommandCodes.VIDEO_SELECTION)
        if value is None:
            return None
        return VideoSelection.from_bytes(value)

    async def set_video_selection(self, mode: VideoSelection) -> None:
        """Set the video input selection (pre-HDA AVR series)."""
        await self._client.request(
            self._zn, VideoSelection.VIDEO_SELECTION, bytes([mode])
        )

    async def set_hdmi_output(self, output: HdmiOutput) -> None:
        await self._send_rc5(RC5CODE_HDMI_OUTPUT, output)

    def get_source(self) -> SourceCodes | None:
        value = self._state.get(CommandCodes.CURRENT_SOURCE)
        if value is None:
            return None
        try:
            return SourceCodes.from_bytes(value, self._api_model, self._zn)
        except ValueError:
            return None

    def get_source_list(self) -> list[SourceCodes]:
        return list(RC5CODE_SOURCE.get((self._api_model, self._zn), {}).keys())

    async def get_input_name(self) -> str | None:
        """Query the user-configured input name for the current source."""
        try:
            data = await self._client.request(
                self._zn, CommandCodes.INPUT_NAME, bytes([0xF0])
            )
            return data.decode('utf-8', errors='replace').rstrip('\x00').strip()
        except Exception as e:
            _LOGGER.warning("Failed to get input name: %s", e)
            return None

    async def set_source(self, src: SourceCodes) -> None:
        if self._api_model in SOURCE_WRITE_SUPPORTED:
            value = src.to_bytes(self._api_model, self._zn)
            await self._client.request(self._zn, CommandCodes.CURRENT_SOURCE, value)
        else:
            await self._send_rc5(RC5CODE_SOURCE, src)

    def get_volume(self) -> int | None:
        value = self._state.get(CommandCodes.VOLUME)
        if value is None:
            return None
        return int.from_bytes(value, "big")

    async def set_volume(self, volume: int) -> None:
        await self._client.request(self._zn, CommandCodes.VOLUME, bytes([volume]))

    async def inc_volume(self) -> None:
        if self._api_model in VOLUME_STEP_SUPPORTED:
            await self._client.request(self._zn, CommandCodes.VOLUME, bytes([0xF1]))
        else:
            await self._send_rc5(RC5CODE_VOLUME, True)

    async def dec_volume(self) -> None:
        if self._api_model in VOLUME_STEP_SUPPORTED:
            await self._client.request(self._zn, CommandCodes.VOLUME, bytes([0xF2]))
        else:
            await self._send_rc5(RC5CODE_VOLUME, False)

    def get_dab_station(self) -> str | None:
        value = self._state.get(CommandCodes.DAB_STATION)
        if value is None:
            return None
        return value.decode("utf8", errors="replace").rstrip()

    def get_dls_pdt(self) -> str | None:
        value = self._state.get(CommandCodes.DLS_PDT_INFO)
        if value is None:
            return None
        return value.decode("utf8", errors="replace").rstrip()

    def get_rds_information(self) -> str | None:
        value = self._state.get(CommandCodes.RDS_INFORMATION)
        if value is None:
            return None
        return value.decode("utf8", errors="replace").rstrip()

    async def set_tuner_preset(self, preset: int) -> None:
        await self._client.request(self._zn, CommandCodes.TUNER_PRESET, bytes([preset]))

    def get_tuner_preset(self) -> int | None:
        value = self._state.get(CommandCodes.TUNER_PRESET)
        if value is None or value == b"\xff":
            return None
        return int.from_bytes(value, "big")

    def get_preset_details(self) -> dict[int, PresetDetail]:
        return self._presets

    async def send_navigation(self, code: RC5CodeNavigation) -> None:
        await self._send_rc5(RC5CODE_NAVIGATION, code)

    async def send_playback(self, code: RC5CodePlayback) -> None:
        await self._send_rc5(RC5CODE_PLAYBACK, code)

    async def send_toggle(self, code: RC5CodeToggle) -> None:
        await self._send_rc5(RC5CODE_TOGGLE, code)

    async def send_menu_access(self, code: RC5CodeMenuAccess) -> None:
        await self._send_rc5(RC5CODE_MENU_ACCESS, code)

    async def send_numeric(self, digit: int) -> None:
        if not 0 <= digit <= 9:
            raise ValueError(f"Digit must be 0-9, got {digit}")
        if self.model and self.model not in APIVERSION_RC5_NUMERIC_SERIES:
            raise ValueError(
                f"Numeric RC5 not supported on {self.model}"
            )
        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, digit])
        )

    async def send_color(self, color: RC5CodeColor) -> None:
        await self._send_rc5(RC5CODE_COLOR, color)

    async def save_settings(self, pin: tuple[int, int, int, int] = (1, 2, 3, 4)) -> None:
        """Save a secure backup of device settings.

        The PIN defaults to (1, 2, 3, 4), the factory default installer PIN.
        """
        await self._client.request(
            1, CommandCodes.SAVE_RESTORE_COPY_OF_SETTINGS,
            bytes([SaveRestoreSubCommand.SAVE, *SAVE_RESTORE_CONFIRMATION, *pin]),
        )

    async def restore_settings(self, pin: tuple[int, int, int, int] = (1, 2, 3, 4)) -> None:
        """Restore settings from the secure backup.

        The PIN defaults to (1, 2, 3, 4), the factory default installer PIN.
        Raises CommandInvalidAtThisTime if no backup exists.
        """
        await self._client.request(
            1, CommandCodes.SAVE_RESTORE_COPY_OF_SETTINGS,
            bytes([SaveRestoreSubCommand.RESTORE, *SAVE_RESTORE_CONFIRMATION, *pin]),
        )

    def get_network_playback_status(self) -> NetworkPlaybackStatus | None:
        """Return the network playback status (stopped/transitioning/playing/paused)."""
        value = self._state.get(CommandCodes.NETWORK_PLAYBACK_STATUS)
        if value is None:
            return None
        return NetworkPlaybackStatus.from_bytes(value)

    def get_now_playing(self) -> NowPlayingInfo | None:
        """Return now-playing metadata (HDA series, NET/BT sources)."""
        return self._now_playing

    def get_bluetooth_status(
        self,
    ) -> tuple[BluetoothAudioStatus, str] | tuple[None, None]:
        """Return Bluetooth audio status and track name (HDA series)."""
        value = self._state.get(CommandCodes.BLUETOOTH_STATUS)
        if value is None:
            return None, None
        status = BluetoothAudioStatus.from_int(value[0])
        if len(value) > 1:
            track = value[1:].decode("ascii", errors="replace").rstrip("\x00").strip()
        else:
            track = ""
        return status, track

    async def update(self, flags: EnumFlags = EnumFlags.FULL_UPDATE) -> None:
        async def _update(cc: CommandCodes):
            try:
                data = await self._client.request(self._zn, cc, bytes([0xF0]))
                self._state[cc] = data
            except UnsupportedZone:
                _LOGGER.debug("Unsupported zone %s for %s", self._zn, cc)
            except ResponseException as e:
                _LOGGER.debug("Response error skipping %s - %s", cc, e.ac)
                self._state[cc] = None
            except NotConnectedException as e:
                _LOGGER.debug("Not connected skipping %s", cc)
                self._state[cc] = None
            except TimeoutError:
                _LOGGER.error("Timeout requesting %s", cc)

        async def _update_presets() -> None:
            presets = {}
            for preset in range(1, 51):
                try:
                    data = await self._client.request(
                        self._zn, CommandCodes.PRESET_DETAIL, bytes([preset])
                    )
                    if data != b"\x00":
                        presets[preset] = PresetDetail.from_bytes(data)
                except CommandInvalidAtThisTime:
                    break
                except CommandNotRecognised:
                    _LOGGER.debug("Presets not supported skipping %s", preset)
                    break
                except NotConnectedException as e:
                    _LOGGER.debug("Not connected skipping preset %s", preset)
                    return
                except TimeoutError:
                    _LOGGER.error("Timeout requesting preset %s", preset)
                    return
            self._presets = presets

        async def _update_now_playing() -> None:
            kwargs = {}
            for field in attr.fields(NowPlayingInfo):
                if "request" not in field.metadata:
                    continue
                try:
                    data = await self._client.request(
                        self._zn, CommandCodes.NOW_PLAYING_INFO, bytes([field.metadata["request"]])
                    )
                    kwargs[field.name] = field.metadata["converter"](data)
                except CommandNotRecognised:
                    _LOGGER.debug("Now playing not supported")
                    self._now_playing = None
                    return
                except ParameterNotRecognised:
                    _LOGGER.debug("Now playing %s not supported", field.name)
                except NotConnectedException:
                    _LOGGER.debug("Not connected skipping now playing")
                    self._now_playing = None
                    return
                except ResponseException as e:
                    _LOGGER.debug("Now playing %s error: %s", field.name, e.ac)
                except TimeoutError:
                    _LOGGER.error("Timeout requesting now playing %s", field.name)

            if kwargs:
                self._now_playing = NowPlayingInfo(**kwargs)
            else:
                self._now_playing = None

        async def _update_amxduet() -> None:
            try:
                data = await self._client.request_raw(AmxDuetRequest())
                self._amxduet = data

                if data.device_model in APIVERSION_450_SERIES:
                    self._api_model = ApiModel.API450_SERIES

                if data.device_model in APIVERSION_860_SERIES:
                    self._api_model = ApiModel.API860_SERIES

                if data.device_model in APIVERSION_HDA_SERIES:
                    self._api_model = ApiModel.APIHDA_SERIES

                if data.device_model in APIVERSION_SA_SERIES:
                    self._api_model = ApiModel.APISA_SERIES

                if data.device_model in APIVERSION_PA_SERIES:
                    self._api_model = ApiModel.APIPA_SERIES

                if data.device_model in APIVERSION_ST_SERIES:
                    self._api_model = ApiModel.APIST_SERIES

            except ResponseException as e:
                _LOGGER.debug("Response error skipping %s", e.ac)
            except NotConnectedException as e:
                _LOGGER.debug("Not connected skipping amx")
            except TimeoutError:
                _LOGGER.error("Timeout requesting amx")

        if not self._client.connected:
            if self._state:
                self._state = dict()
                self._now_playing = None
            return

        if self._amxduet is None:
            await _update_amxduet()

        tasks: list = []
        for cc in CommandCodes:
            if not (cc.flags & flags):
                continue
            if cc == CommandCodes.NOW_PLAYING_INFO:
                tasks.append(_update_now_playing())
            elif cc == CommandCodes.PRESET_DETAIL:
                tasks.append(_update_presets())
            else:
                tasks.append(_update(cc))
        if tasks:
            await asyncio.gather(*tasks)
