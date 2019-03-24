"""Zone state"""
import asyncio
import logging

from . import CommandCodes, ResponsePacket, SourceCodes, ResponseException
from .client import Client

_LOGGER = logging.getLogger(__name__)

class State():
    def __init__(self, client: Client, zn: int):
        self._zn = zn
        self._client = client
        self._state = dict()

        self.monitor(CommandCodes.POWER)
        self.monitor(CommandCodes.VOLUME)
        self.monitor(CommandCodes.MUTE)

    def monitor(self, cc):
        self._state[cc] = None

    def _listen(self, packet: ResponsePacket):
        if packet.zn != self._zn:
            return

        if packet.cc in self._state:
            self._state[packet.cc] = packet.data

    def get(self, cc):
        return self._state[cc]

    def get_power(self):
        return int.from_bytes(self._state[CommandCodes.POWER], 'big')

    async def set_power(self, power: int) -> None:
        await self._client.request(
            self._zn, CommandCodes.POWER, bytes([power]))

    def get_mute(self):
        if self._state[CommandCodes.MUTE]:
            return int.from_bytes(self._state[CommandCodes.MUTE], 'big')
        else:
            return None

    async def set_mute(self, mute: int) -> None:
        await self._client.request(
            self._zn, CommandCodes.MUTE, bytes([mute]))

    def get_source(self) -> SourceCodes:
        if self._state[CommandCodes.CURRENT_SOURCE]:
            return SourceCodes.from_int(
                int.from_bytes(self._state[CommandCodes.CURRENT_SOURCE], 'big'))
        else:
            return None

    async def set_source(self, mute: SourceCodes) -> None:
        await self._client.request(
            self._zn, CommandCodes.CURRENT_SOURCE, bytes([mute]))

    def get_volume(self) -> int:
        if self._state[CommandCodes.VOLUME]:
            return int.from_bytes(self._state[CommandCodes.VOLUME], 'big')
        else:
            return None

    async def set_volume(self, volume: int) -> None:
        await self._client.request(
            self._zn, CommandCodes.VOLUME, bytes([volume]))

    async def update(self):
        async def _update(cc):
            _LOGGER.debug("Updating %s", cc)
            try:
                data = await self._client.request(self._zn, cc, bytes([0xF0]))
                self._state[cc] = data
            except ResponseException:
                _LOGGER.error("Response error skipping %s", cc, exc_info=1)
                self._state[cc] = None
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout requesting %s", cc)
                
    
        await asyncio.wait(
            [_update(cc) for cc in self._state.keys()]
        )
