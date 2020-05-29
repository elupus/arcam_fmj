import asyncio
import aiohttp
import functools
import logging
from datetime import datetime, timedelta
from defusedxml import ElementTree

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


def _log_exception(msg, *args):
    """Log an error and turn on traceback if debug is on."""
    _LOGGER.error(msg, *args, exc_info=_LOGGER.getEffectiveLevel() == logging.DEBUG)


def get_uniqueid_from_udn(data):
    """Extract a unique id from udn."""
    try:
        return data[5:].split("-")[4]
    except IndexError:
        _log_exception("Unable to get unique id from %s", data)
        return None


async def get_uniqueid_from_device_description(session, url):
    """Retrieve and extract unique id from url."""
    try:
        async with session.get(url) as req:
            req.raise_for_status()
            data = await req.text()
            xml = ElementTree.fromstring(data)
            udn = xml.findtext("d:device/d:UDN", None, {"d": "urn:schemas-upnp-org:device-1-0"})
            return get_uniqueid_from_udn(udn)
    except (aiohttp.ClientError, asyncio.TimeoutError, ElementTree.ParseError):
        _log_exception("Unable to get device description from %s", url)
        return None


async def get_uniqueid_from_host(session, host):
    """Try to deduce a unique id from a host based on ssdp/upnp."""
    return await get_uniqueid_from_device_description(
        session, f"http://{host}:8080/dd.xml"
    )
