"""Zone state"""
import asyncio
import logging
from typing import Dict, List

from . import (
    AnswerCodes,
    CommandCodes,
    CommandInvalidAtThisTime,
    DecodeMode2CH,
    DecodeModeMCH,
    IncomingAudioConfig,
    IncomingAudioFormat,
    MenuCodes,
    NotConnectedException,
    PresetDetail,
    RC5Codes,
    ResponseException,
    ResponsePacket,
    SourceCodes,
    SOURCECODE_TO_RC5CODE_ZONE1,
    SOURCECODE_TO_RC5CODE_ZONE2,
)
from .client import Client

_LOGGER = logging.getLogger(__name__)

class State():
    _state: Dict[int, bytes]
    _presets: Dict[int, PresetDetail]

    def __init__(self, client: Client, zn: int):
        self._zn = zn
        self._client = client
        self._state = dict()
        self._presets = dict()

    async def start(self):
        # pylint: disable=protected-access
        self._client._listen.add(self._listen)

    async def stop(self):
        # pylint: disable=protected-access
        self._client._listen.remove(self._listen)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def to_dict(self):
        return {
            'POWER': self.get_power(),
            'VOLUME': self.get_volume(),
            'SOURCE': self.get_source(),
            'MUTE': self.get_mute(),
            'MENU': self.get_menu(),
            'INCOMING_AUDIO_FORMAT': self.get_incoming_audio_format(),
            'DECODE_MODE_2CH': self.get_decode_mode_2ch(),
            'DECODE_MODE_MCH': self.get_decode_mode_mch(),
            'DAB_STATION': self.get_dab_station(),
            'DLS_PDT': self.get_dls_pdt(),
            'RDS_INFORMATION': self.get_rds_information(),
            'TUNER_PRESET': self.get_tuner_preset(),
            'PRESET_DETAIL': self.get_preset_details(),
        }

    def __repr__(self):
        return "State ({})".format(self.to_dict())

    def _listen(self, packet: ResponsePacket):
        if packet.zn != self._zn:
            return

        if packet.ac == AnswerCodes.STATUS_UPDATE:
            self._state[packet.cc] = packet.data
        else:
            self._state[packet.cc] = None

    @property
    def zn(self):
        return self._zn

    @property
    def client(self):
        return self._client

    def get(self, cc):
        return self._state[cc]

    def get_incoming_audio_format(self):
        value = self._state.get(CommandCodes.INCOMING_AUDIO_FORMAT)
        if value is None:
            return None, None
        return (IncomingAudioFormat.from_int(value[0]),
                IncomingAudioConfig.from_int(value[1]))

    def get_decode_mode_2ch(self) -> DecodeMode2CH:
        value = self._state.get(CommandCodes.DECODE_MODE_STATUS_2CH)
        if value is None:
            return None
        return DecodeMode2CH.from_bytes(value)

    async def set_decode_mode_2ch(self, mode: DecodeMode2CH):
        if mode == DecodeMode2CH.STEREO:
            command = RC5Codes.STEREO
        elif mode == DecodeMode2CH.DOLBY_PLII_IIx_MOVIE:
            command = RC5Codes.DOLBY_PLII_IIx_MOVIE
        elif mode == DecodeMode2CH.DOLBY_PLII_IIx_MUSIC:
            command = RC5Codes.DOLBY_PLII_IIx_MUSIC
        elif mode == DecodeMode2CH.DOLBY_PLII_IIx_GAME:
            command = RC5Codes.DOLBY_PLII_IIx_GAME
        elif mode == DecodeMode2CH.DOLBY_PL:
            command = RC5Codes.DOLBY_PL
        elif mode == DecodeMode2CH.DTS_NEO_6_CINEMA:
            command = RC5Codes.DTS_NEO_6_CINEMA
        elif mode == DecodeMode2CH.DTS_NEO_6_MUSIC:
            command = RC5Codes.DTS_NEO_6_MUSIC
        elif mode == DecodeMode2CH.MCH_STEREO:
            command = RC5Codes.MCH_STEREO
        else:
            raise ValueError("Unkown mapping for mode {}".format(mode))

        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command.value)

    def get_decode_mode_mch(self) -> DecodeModeMCH:
        value = self._state.get(CommandCodes.DECODE_MODE_STATUS_MCH)
        if value is None:
            return None
        return DecodeModeMCH.from_bytes(value)

    async def set_decode_mode_mch(self, mode: DecodeModeMCH):
        if mode == DecodeModeMCH.STEREO_DOWNMIX:
            command = RC5Codes.STEREO
        elif mode == DecodeModeMCH.MULTI_CHANNEL:
            command = RC5Codes.MULTI_CHANNEL
        elif mode == DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES:
            command = RC5Codes.DOLBY_D_EX
        elif mode == DecodeModeMCH.DOLBY_PLII_IIx_MOVIE:
            command = RC5Codes.DOLBY_PLII_IIx_MOVIE
        elif mode == DecodeModeMCH.DOLBY_PLII_IIx_MUSIC:
            command = RC5Codes.DOLBY_PLII_IIx_MUSIC
        else:
            raise ValueError("Unkown mapping for mode {}".format(mode))

        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command.value)

    def get_power(self):
        value = self._state.get(CommandCodes.POWER)
        if value is None:
            return None
        return int.from_bytes(value, 'big')

    async def set_power(self, power: bool) -> None:
        if power:
            if self._zn == 1:
                command = RC5Codes.POWER_ON
            else:
                command = RC5Codes.POWER_ON_ZONE2
        else:
            if self._zn == 1:
                command = RC5Codes.POWER_OFF
            else:
                command = RC5Codes.POWER_OFF_ZONE2

        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command.value)

    def get_menu(self) -> MenuCodes:
        value = self._state.get(CommandCodes.MENU)
        if value is None:
            return None
        return MenuCodes.from_bytes(value)

    def get_mute(self) -> bool:
        value = self._state.get(CommandCodes.MUTE)
        if value is None:
            return None
        return int.from_bytes(value, 'big') == 0

    async def set_mute(self, mute: bool) -> None:
        if mute:
            if self._zn == 1:
                command = RC5Codes.MUTE_ON
            else:
                command = RC5Codes.MUTE_ON_ZONE2
        else:
            if self._zn == 1:
                command = RC5Codes.MUTE_OFF
            else:
                command = RC5Codes.MUTE_OFF_ZONE2

        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command.value)

    def get_source(self) -> SourceCodes:
        value = self._state.get(CommandCodes.CURRENT_SOURCE)
        if value is None:
            return None
        return SourceCodes.from_int(
            int.from_bytes(value, 'big'))

    def get_source_list(self) -> List[SourceCodes]:
        if self._zn == 1:
            return list(SOURCECODE_TO_RC5CODE_ZONE1.keys())
        else:
            return list(SOURCECODE_TO_RC5CODE_ZONE2.keys())

    async def set_source(self, src: SourceCodes) -> None:

        if self._zn == 1:
            command = SOURCECODE_TO_RC5CODE_ZONE1[src]
        else:
            command = SOURCECODE_TO_RC5CODE_ZONE2[src]

        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command.value)

    def get_volume(self) -> int:
        value = self._state.get(CommandCodes.VOLUME)
        if value is None:
            return None
        return int.from_bytes(value, 'big')

    async def set_volume(self, volume: int) -> None:
        await self._client.request(
            self._zn, CommandCodes.VOLUME, bytes([volume]))

    async def inc_volume(self) -> None:
        if self._zn == 1:
            command = RC5Codes.INC_VOLUME
        else:
            command = RC5Codes.INC_VOLUME_ZONE2

        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command.value)

    async def dec_volume(self) -> None:
        if self._zn == 1:
            command = RC5Codes.DEC_VOLUME
        else:
            command = RC5Codes.DEC_VOLUME_ZONE2

        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command.value)

    def get_dab_station(self):
        value = self._state.get(CommandCodes.DAB_STATION)
        if value is None:
            return None
        return value.decode('utf8').rstrip()

    def get_dls_pdt(self):
        value = self._state.get(CommandCodes.DLS_PDT_INFO)
        if value is None:
            return None
        return value.decode('utf8').rstrip()

    def get_rds_information(self):
        value = self._state.get(CommandCodes.RDS_INFORMATION)
        if value is None:
            return None
        return value.decode('utf8').rstrip()

    async def set_tuner_preset(self, preset):
        await self._client.request(self._zn, CommandCodes.TUNER_PRESET, bytes([preset]))

    def get_tuner_preset(self):
        value = self._state.get(CommandCodes.TUNER_PRESET)
        if value is None or value == b'\xff':
            return None
        return int.from_bytes(value, 'big')

    def get_preset_details(self):
        return self._presets

    async def update(self):
        async def _update(cc):
            try:
                data = await self._client.request(self._zn, cc, bytes([0xF0]))
                self._state[cc] = data
            except ResponseException as e:
                _LOGGER.debug("Response error skipping %s - %s", cc, e.ac)
                self._state[cc] = None
            except NotConnectedException as e:
                _LOGGER.debug("Not connected skipping %s", cc)
                self._state[cc] = None
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout requesting %s", cc)

        async def _update_presets():
            presets = {}
            for preset in range(1, 51):
                try:
                    data = await self._client.request(self._zn, CommandCodes.PRESET_DETAIL, bytes([preset]))
                    presets[preset] = PresetDetail.from_bytes(data)
                except CommandInvalidAtThisTime:
                    break
                except NotConnectedException as e:
                    _LOGGER.debug("Not connected skipping %s", cc)
                    return
                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout requesting %s", cc)
                    return
            self._presets = presets

        if self._client.connected:
            await asyncio.wait([
                _update(CommandCodes.POWER),
                _update(CommandCodes.VOLUME),
                _update(CommandCodes.MUTE),
                _update(CommandCodes.CURRENT_SOURCE),
                _update(CommandCodes.MENU),
                _update(CommandCodes.DECODE_MODE_STATUS_2CH),
                _update(CommandCodes.DECODE_MODE_STATUS_MCH),
                _update(CommandCodes.INCOMING_AUDIO_FORMAT),
                _update(CommandCodes.DAB_STATION),
                _update(CommandCodes.DLS_PDT_INFO),
                _update(CommandCodes.RDS_INFORMATION),
                _update(CommandCodes.TUNER_PRESET),
                _update_presets(),
            ])
        else:
            if self._state:
                self._state = dict()

