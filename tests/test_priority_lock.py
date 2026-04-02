import asyncio

import pytest

from arcam.fmj.priority_lock import PriorityLock


async def test_basic_acquire_release():
    lock = PriorityLock()
    async with lock(0):
        pass


async def test_mutual_exclusion():
    lock = PriorityLock()
    counter = 0

    async def bump():
        nonlocal counter
        async with lock(0):
            tmp = counter
            await asyncio.sleep(0)
            counter = tmp + 1

    await asyncio.gather(bump(), bump(), bump())
    assert counter == 3


async def test_higher_priority_wins():
    """When multiple waiters queue up, lower numeric priority acquires first."""
    lock = PriorityLock()
    order = []

    async def worker(name, priority, ready: asyncio.Event):
        ready.set()
        async with lock(priority):
            order.append(name)

    # Hold the lock so workers queue up.
    async with lock(0):
        events = []
        for name, pri in [("low", 10), ("high", 1), ("mid", 5)]:
            ev = asyncio.Event()
            events.append(ev)
            asyncio.create_task(worker(name, pri, ev))
        # Wait until all workers are queued.
        for ev in events:
            await ev.wait()
        # One more yield to ensure they're all blocked on acquire.
        await asyncio.sleep(0)

    # Let all queued tasks finish.
    await asyncio.sleep(0.01)
    assert order == ["high", "mid", "low"]


async def test_fifo_within_same_priority():
    """Equal-priority waiters are served in FIFO order."""
    lock = PriorityLock()
    order = []

    async def worker(name, ready: asyncio.Event):
        ready.set()
        async with lock(5):
            order.append(name)

    async with lock(0):
        events = []
        for name in ["first", "second", "third"]:
            ev = asyncio.Event()
            events.append(ev)
            asyncio.create_task(worker(name, ev))
        for ev in events:
            await ev.wait()
        await asyncio.sleep(0)

    await asyncio.sleep(0.01)
    assert order == ["first", "second", "third"]


async def test_default_priority():
    """Priority defaults to 0."""
    lock = PriorityLock()
    async with lock():
        pass


async def test_reentrant_deadlock():
    """Re-entering the lock from the same task should deadlock (not silently succeed)."""
    lock = PriorityLock()

    async def reenter():
        async with lock(0):
            async with lock(0):
                pass  # pragma: no cover

    with pytest.raises(asyncio.TimeoutError):
        async with asyncio.timeout(0.05):
            await reenter()


async def test_exception_in_body_releases_lock():
    lock = PriorityLock()

    with pytest.raises(RuntimeError):
        async with lock(0):
            raise RuntimeError("boom")

    # Lock should be available again.
    async with lock(0):
        pass


async def test_cancel_waiter():
    """Cancelling a waiting task doesn't break the lock for others."""
    lock = PriorityLock()
    acquired = False

    async def cancelled_worker():
        async with lock(5):
            pass  # pragma: no cover

    async def good_worker():
        nonlocal acquired
        async with lock(5):
            acquired = True

    async with lock(0):
        task_cancel = asyncio.create_task(cancelled_worker())
        task_good = asyncio.create_task(good_worker())
        await asyncio.sleep(0)
        task_cancel.cancel()

    # The good worker should still get through.
    await asyncio.sleep(0.01)
    assert acquired
    assert task_good.done()


async def test_many_priorities():
    """Larger spread of priorities all sort correctly."""
    lock = PriorityLock()
    order = []
    n = 20

    async def worker(i, ready: asyncio.Event):
        ready.set()
        async with lock(i):
            order.append(i)

    # Queue up workers with priorities 19, 18, ..., 0 (reverse order).
    async with lock(-1):
        events = []
        for i in reversed(range(n)):
            ev = asyncio.Event()
            events.append(ev)
            asyncio.create_task(worker(i, ev))
        for ev in events:
            await ev.wait()
        await asyncio.sleep(0)

    await asyncio.sleep(0.05)
    assert order == list(range(n))


async def test_negative_priorities():
    lock = PriorityLock()
    order = []

    async def worker(name, priority, ready: asyncio.Event):
        ready.set()
        async with lock(priority):
            order.append(name)

    async with lock(0):
        events = []
        for name, pri in [("normal", 0), ("urgent", -10), ("low", 10)]:
            ev = asyncio.Event()
            events.append(ev)
            asyncio.create_task(worker(name, pri, ev))
        for ev in events:
            await ev.wait()
        await asyncio.sleep(0)

    await asyncio.sleep(0.01)
    assert order == ["urgent", "normal", "low"]


async def test_stress_concurrent():
    """Many tasks contending on the lock; verify mutual exclusion holds."""
    lock = PriorityLock()
    n_tasks = 200
    inside = 0
    max_inside = 0
    completed = 0

    async def worker(priority):
        nonlocal inside, max_inside, completed
        async with lock(priority):
            inside += 1
            max_inside = max(max_inside, inside)
            # Yield to give other tasks a chance to violate exclusion.
            await asyncio.sleep(0)
            inside -= 1
            completed += 1

    tasks = [
        asyncio.create_task(worker(i % 10)) for i in range(n_tasks)
    ]
    await asyncio.gather(*tasks)
    assert max_inside == 1
    assert completed == n_tasks


async def test_stress_priority_ordering():
    """Under contention, verify priority ordering is respected across waves."""
    lock = PriorityLock()
    order = []
    n_waves = 5
    per_wave = 10

    async def worker(wave, priority, ready: asyncio.Event):
        ready.set()
        async with lock(priority):
            order.append((wave, priority))
            # Simulate work so next wave queues up.
            await asyncio.sleep(0.001)

    for wave in range(n_waves):
        async with lock(-1):
            events = []
            for pri in reversed(range(per_wave)):
                ev = asyncio.Event()
                events.append(ev)
                asyncio.create_task(worker(wave, pri, ev))
            for ev in events:
                await ev.wait()
            await asyncio.sleep(0)

        # Let wave drain.
        await asyncio.sleep(0.05)

        wave_order = [pri for w, pri in order if w == wave]
        assert wave_order == list(range(per_wave)), f"Wave {wave}: {wave_order}"

    assert len(order) == n_waves * per_wave
