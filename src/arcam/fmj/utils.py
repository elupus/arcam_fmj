import asyncio
import functools
import logging
from datetime import datetime, timedelta
from typing import List, Optional

import aiohttp
from async_upnp_client.aiohttp import AiohttpSessionRequester
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.search import async_search
from async_upnp_client.ssdp import SSDP_PORT
from async_upnp_client.utils import CaseInsensitiveDict

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

async def get_upnp_headers(host: str) -> Optional[CaseInsensitiveDict]:
    """Get search response headers from a host based on ssdp/upnp."""
    search_target = "upnp:rootdevice"

    responses : List[CaseInsensitiveDict] = []

    async def _handle_response(headers: CaseInsensitiveDict) -> None:
        responses.append(headers)

    await async_search(
        search_target=search_target,
        target=(host, SSDP_PORT),
        async_callback=_handle_response,
    )

    if len(responses) == 0:
        _LOGGER.warning(f"No UPNP response from {host}")
        return None
    elif len(responses) > 1:
        _LOGGER.warning(f"More than one UPNP response from {host}")
        return None

    return responses[0]

async def get_upnp_field(host: str, field_name: str) -> Optional[str]:
    """Get a search response header from a host based on ssdp/upnp."""
    headers = await get_upnp_headers(host)
    if headers is None:
        return None
    return headers.get(field_name, None)


async def get_upnp_udn(host: str) -> Optional[str]:
    """Get the UDN from a host based on ssdp/upnp."""
    return await get_upnp_field(host, "_udn")


async def get_uniqueid(host: str) -> Optional[str]:
    """Try to deduce a unique id from a host based on ssdp/upnp."""
    udn = await get_upnp_udn(host)
    if udn is None:
        return None
    return get_uniqueid_from_udn(udn)


async def get_uniqueid_from_host(session: aiohttp.ClientSession, host: str):
    """
    Try to deduce a unique id from a host based on ssdp/upnp.
    
    Back compatible argument list for HA integration
    """
    return await get_uniqueid(host)


async def get_serial_number_from_host(session: aiohttp.ClientSession, host: str):
    """Get the serial number from a host based on ssdp/upnp."""
    location = await get_upnp_field(host, "location")
    if location is None:
        return None

    requester = AiohttpSessionRequester(session, with_sleep=True)
    factory = UpnpFactory(requester)
    device = await factory.async_create_device(location)

    return device.serial_number # More immutable than device.udn
