"""Tests for utils."""
import pytest

from arcam.fmj.utils import async_retry


async def test_retry_fails():

    calls = 0

    @async_retry(2, Exception)
    async def tester():
        nonlocal calls
        calls += 1
        raise Exception()

    with pytest.raises(Exception):
        await tester()

    assert calls == 2


async def test_retry_succeeds():

    calls = 0

    @async_retry(2, Exception)
    async def tester():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise Exception()
        return True

    assert await tester() == True


async def test_retry_unexpected():


    calls = 0

    @async_retry(2, TimeoutError)
    async def tester():
        nonlocal calls
        calls += 1
        raise ValueError()

    with pytest.raises(ValueError):
        await tester()
    assert calls == 1
