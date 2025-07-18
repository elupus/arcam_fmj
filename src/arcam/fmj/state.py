"""Zone state"""

import asyncio
import logging
from typing import Any, TypeVar

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
    CommandCodes,
    CommandInvalidAtThisTime,
    CommandNotRecognised,
    DecodeMode2CH,
    DecodeModeMCH,
    IncomingAudioConfig,
    IncomingAudioFormat,
    MenuCodes,
    NotConnectedException,
    PresetDetail,
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
    UnsupportedZone,
)
from .client import Client

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


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
            "MENU": self.get_menu(),
            "INCOMING_VIDEO_PARAMETERS": self.get_incoming_video_parameters(),
            "INCOMING_AUDIO_FORMAT": self.get_incoming_audio_format(),
            "INCOMING_AUDIO_SAMPLE_RATE": self.get_incoming_audio_sample_rate(),
            "DECODE_MODE_2CH": self.get_decode_mode_2ch(),
            "DECODE_MODE_MCH": self.get_decode_mode_mch(),
            "DAB_STATION": self.get_dab_station(),
            "DLS_PDT": self.get_dls_pdt(),
            "RDS_INFORMATION": self.get_rds_information(),
            "TUNER_PRESET": self.get_tuner_preset(),
            "PRESET_DETAIL": self.get_preset_details(),
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

    def get_incoming_audio_sample_rate(self) -> int:
        value = self._state.get(CommandCodes.INCOMING_AUDIO_SAMPLE_RATE)
        if value is None:
            return 0
        map = {
            0x00: 32000,
            0x01: 44100,
            0x02: 48000,
            0x03: 88200,
            0x04: 96000,
            0x05: 176400,
            0x06: 192000,
        }
        return map.get(value[0], 0)

    def get_decode_mode_2ch(self) -> DecodeMode2CH | None:
        value = self._state.get(CommandCodes.DECODE_MODE_STATUS_2CH)
        if value is None:
            return None
        return DecodeMode2CH.from_bytes(value)

    async def set_decode_mode_2ch(self, mode: DecodeMode2CH) -> None:
        command = self.get_rc5code(RC5CODE_DECODE_MODE_2CH, mode)
        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
        )

    def get_decode_mode_mch(self) -> DecodeModeMCH | None:
        value = self._state.get(CommandCodes.DECODE_MODE_STATUS_MCH)
        if value is None:
            return None
        return DecodeModeMCH.from_bytes(value)

    async def set_decode_mode_mch(self, mode: DecodeModeMCH) -> None:
        command = self.get_rc5code(RC5CODE_DECODE_MODE_MCH, mode)
        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
        )

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
            return list(RC5CODE_DECODE_MODE_2CH[(self._api_model, self._zn)])
        else:
            return list(RC5CODE_DECODE_MODE_MCH[(self._api_model, self._zn)])

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
            command = self.get_rc5code(RC5CODE_POWER, power)
            if power:
                await self._client.request(
                    self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
                )
            else:
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
            command = self.get_rc5code(RC5CODE_MUTE, mute)
            await self._client.request(
                self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
            )

    def get_source(self) -> SourceCodes | None:
        value = self._state.get(CommandCodes.CURRENT_SOURCE)
        if value is None:
            return None
        try:
            return SourceCodes.from_bytes(value, self._api_model, self._zn)
        except ValueError:
            return None

    def get_source_list(self) -> list[SourceCodes]:
        return list(RC5CODE_SOURCE[(self._api_model, self._zn)].keys())

    async def set_source(self, src: SourceCodes) -> None:
        if self._api_model in SOURCE_WRITE_SUPPORTED:
            value = src.to_bytes(self._api_model, self._zn)
            await self._client.request(self._zn, CommandCodes.CURRENT_SOURCE, value)
        else:
            command = self.get_rc5code(RC5CODE_SOURCE, src)
            await self._client.request(
                self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
            )

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
            command = self.get_rc5code(RC5CODE_VOLUME, True)
            await self._client.request(
                self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
            )

    async def dec_volume(self) -> None:
        if self._api_model in VOLUME_STEP_SUPPORTED:
            await self._client.request(self._zn, CommandCodes.VOLUME, bytes([0xF2]))
        else:
            command = self.get_rc5code(RC5CODE_VOLUME, False)
            await self._client.request(
                self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
            )

    def get_dab_station(self) -> str | None:
        value = self._state.get(CommandCodes.DAB_STATION)
        if value is None:
            return None
        return value.decode("utf8").rstrip()

    def get_dls_pdt(self) -> str | None:
        value = self._state.get(CommandCodes.DLS_PDT_INFO)
        if value is None:
            return None
        return value.decode("utf8").rstrip()

    def get_rds_information(self) -> str | None:
        value = self._state.get(CommandCodes.RDS_INFORMATION)
        if value is None:
            return None
        return value.decode("utf8").rstrip()

    async def set_tuner_preset(self, preset: int) -> None:
        await self._client.request(self._zn, CommandCodes.TUNER_PRESET, bytes([preset]))

    def get_tuner_preset(self) -> int | None:
        value = self._state.get(CommandCodes.TUNER_PRESET)
        if value is None or value == b"\xff":
            return None
        return int.from_bytes(value, "big")

    def get_preset_details(self) -> dict[int, PresetDetail]:
        return self._presets

    async def update(self) -> None:
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

        if self._client.connected:
            if self._amxduet is None:
                await _update_amxduet()

            await asyncio.gather(
                *[
                    _update(CommandCodes.POWER),
                    _update(CommandCodes.VOLUME),
                    _update(CommandCodes.MUTE),
                    _update(CommandCodes.CURRENT_SOURCE),
                    _update(CommandCodes.MENU),
                    _update(CommandCodes.DECODE_MODE_STATUS_2CH),
                    _update(CommandCodes.DECODE_MODE_STATUS_MCH),
                    _update(CommandCodes.INCOMING_VIDEO_PARAMETERS),
                    _update(CommandCodes.INCOMING_AUDIO_FORMAT),
                    _update(CommandCodes.INCOMING_AUDIO_SAMPLE_RATE),
                    _update(CommandCodes.DAB_STATION),
                    _update(CommandCodes.DLS_PDT_INFO),
                    _update(CommandCodes.RDS_INFORMATION),
                    _update(CommandCodes.TUNER_PRESET),
                    _update_presets(),
                ]
            )
        else:
            if self._state:
                self._state = dict()
