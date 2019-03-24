import functools
import logging

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
                    _LOGGER.warning("Retrying")

        return wrapper
    return decorator
