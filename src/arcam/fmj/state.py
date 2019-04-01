"""Zone state"""
import asyncio
import logging

from . import (
    AnswerCodes,
    CommandCodes,
    DecodeMode2CH,
    DecodeModeMCH,
    MenuCodes,
    ResponseException,
    ResponsePacket,
    SourceCodes
)
from .client import Client

_LOGGER = logging.getLogger(__name__)

class State():
    def __init__(self, client: Client, zn: int):
        self._zn = zn
        self._client = client
        self._state = dict()

    async def start(self):
        self._client._listen.add(self._listen)
        await self.update()

    async def stop(self):
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
            'DECODE_MODE_2CH': self.get_decode_mode_2ch(),
            'DECODE_MODE_MCH': self.get_decode_mode_mch(),
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

    def get(self, cc):
        return self._state[cc]

    def get_decode_mode_2ch(self):
        value = self._state.get(CommandCodes.DECODE_MODE_STATUS_2CH)
        if value:
            return DecodeMode2CH.from_bytes(value)
        else:
            return None

    def get_decode_mode_mch(self):
        value = self._state.get(CommandCodes.DECODE_MODE_STATUS_MCH)
        if value:
            return DecodeModeMCH.from_bytes(value)
        else:
            return None

    def get_power(self):
        value = self._state.get(CommandCodes.POWER)
        if value:
            return int.from_bytes(value, 'big')
        else:
            return None

    def get_menu(self) -> MenuCodes:
        value = self._state.get(CommandCodes.MENU)
        if value:
            return MenuCodes.from_bytes(value)

    def get_mute(self) -> bool:
        value = self._state.get(CommandCodes.MUTE)
        if value:
            return int.from_bytes(value, 'big') == 0
        else:
            return None

    async def set_mute(self, mute: bool) -> None:
        if mute:
            command = 119
        else:
            command = 120

        await self._client.request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND,
            bytes([16, command]))

    def get_source(self) -> SourceCodes:
        value = self._state.get(CommandCodes.CURRENT_SOURCE)
        if value:
            return SourceCodes.from_int(
                int.from_bytes(value, 'big'))
        else:
            return None

    async def set_source(self, src: SourceCodes) -> None:
        await self._client.request(
            self._zn, CommandCodes.CURRENT_SOURCE, bytes([src]))

    def get_volume(self) -> int:
        value = self._state.get(CommandCodes.VOLUME)
        if value:
            return int.from_bytes(value, 'big')
        else:
            return None

    async def set_volume(self, volume: int) -> None:
        await self._client.request(
            self._zn, CommandCodes.VOLUME, bytes([volume]))

    async def update(self):
        async def _update(cc):
            try:
                data = await self._client.request(self._zn, cc, bytes([0xF0]))
                self._state[cc] = data
            except ResponseException as e:
                _LOGGER.debug("Response error skipping %s - %s", cc, e.ac)
                self._state[cc] = None
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout requesting %s", cc)

        await asyncio.wait([
            _update(CommandCodes.POWER),
            _update(CommandCodes.VOLUME),
            _update(CommandCodes.MUTE),
            _update(CommandCodes.CURRENT_SOURCE),
            _update(CommandCodes.MENU),
            _update(CommandCodes.DECODE_MODE_STATUS_2CH),
            _update(CommandCodes.DECODE_MODE_STATUS_MCH),
        ])
