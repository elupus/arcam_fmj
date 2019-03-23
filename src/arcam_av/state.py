"""Zone state"""
import asyncio
import logging

from . import CommandCodes
from .client import Client

_LOGGER = logging.getLogger(__name__)

class State():
    def __init__(self, client: Client, zn: int):
        self._zn = zn
        self._client = client
        self._state = dict()

        self.monitor(CommandCodes.POWER)
        self.monitor(CommandCodes.VOLUME)

    def monitor(self, cc):
        self._state[cc] = None

    def get(self, cc):
        return self._state[cc]

    async def update(self):
        async def _update(cc):
            _LOGGER.debug("Updating %s", cc)
            data = await self._client.request(self._zn, cc, bytes([0xF0]))
            self._state[cc] = data
    
        await asyncio.wait(
            [_update(cc) for cc in self._state.keys()]
        )
