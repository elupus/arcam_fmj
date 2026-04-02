"""Async priority lock: when multiple coroutines are waiting, the highest-priority (lowest number) waiter wins."""

import asyncio
import heapq
from contextlib import asynccontextmanager


class PriorityLock:
    def __init__(self):
        self._locked = False
        self._heap: list[tuple[int, int, asyncio.Future]] = []
        self._counter = 0  # tiebreaker for equal priorities (FIFO)

    @asynccontextmanager
    async def __call__(self, priority: int = 0):
        await self._acquire(priority)
        try:
            yield
        finally:
            self._release()

    async def _acquire(self, priority: int) -> None:
        if not self._locked and not self._heap:
            self._locked = True
            return

        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        entry = (priority, self._counter, future)
        self._counter += 1
        heapq.heappush(self._heap, entry)
        await future

    def _release(self) -> None:
        while self._heap:
            _, _, future = heapq.heappop(self._heap)
            if not future.cancelled():
                future.set_result(None)
                return
        self._locked = False
