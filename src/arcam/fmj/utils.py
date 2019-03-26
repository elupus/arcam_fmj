import asyncio
import functools
import logging
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)

def async_retry(attempts=2, allowed_exceptions=()):
    def decorator(f):
        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            attempt = attempts
            while True:
                attempt -= 1

                try:
                    return await f(*args, **kwargs)
                except allowed_exceptions:
                    if attempt == 0:
                        raise
                    _LOGGER.warning("Retrying: %s %s", f, args)

        return wrapper
    return decorator


class Throttle:
    def __init__(self, delay):
        self._timestamp = datetime.now()
        self._lock = asyncio.Lock()
        self._delay = timedelta(seconds=delay)

    async def get(self):
        async with self._lock:
            timestamp = datetime.now()
            delay = (self._timestamp - timestamp).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            self._timestamp = datetime.now() + self._delay
