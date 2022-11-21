import asyncio
import aiohttp
import functools
import logging
import re
from datetime import datetime, timedelta
from defusedxml import ElementTree
from typing import Optional, Any

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
    def __init__(self, delay: float) -> None:
        self._timestamp = datetime.now()
        self._lock = asyncio.Lock()
        self._delay = timedelta(seconds=delay)

    async def get(self) -> None:
        async with self._lock:
            timestamp = datetime.now()
            delay = (self._timestamp - timestamp).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            self._timestamp = datetime.now() + self._delay


def _log_exception(msg, *args):
    """Log an error and turn on traceback if debug is on."""
    _LOGGER.error(msg, *args, exc_info=_LOGGER.getEffectiveLevel() == logging.DEBUG)


def get_uniqueid_from_udn(data) -> Optional[str]:
    """Extract a unique id from udn."""
    try:
        return data[5:].split("-")[4]
    except IndexError:
        _log_exception("Unable to get unique id from %s", data)
        return None


def get_possibly_invalid_xml(data) -> Any:
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError:
        _LOGGER.info("Device provide corrupt xml, trying with ampersand replacement")
        data = re.sub(r'&(?![A-Za-z]+[0-9]*;|#[0-9]+;|#x[0-9a-fA-F]+;)', r'&amp;', data)
        return ElementTree.fromstring(data)

def get_udn_from_xml(xml: Any) -> Optional[str]:
    return xml.findtext("d:device/d:UDN", None, {"d": "urn:schemas-upnp-org:device-1-0"})

async def get_uniqueid_from_device_description(session: aiohttp.ClientSession, url: str):
    """Retrieve and extract unique id from url."""
    try:
        async with session.get(url) as req:
            req.raise_for_status()
            data = await req.text()
            xml = get_possibly_invalid_xml(data)
            udn = get_udn_from_xml(xml)
            return get_uniqueid_from_udn(udn)
    except (aiohttp.ClientError, asyncio.TimeoutError, ElementTree.ParseError):
        _log_exception("Unable to get device description from %s", url)
        return None


async def get_uniqueid_from_host(session: aiohttp.ClientSession, host: str):
    """Try to deduce a unique id from a host based on ssdp/upnp."""
    return await get_uniqueid_from_device_description(
        session, f"http://{host}:8080/dd.xml"
    )
