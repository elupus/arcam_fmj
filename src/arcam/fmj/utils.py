import asyncio
import aiohttp
from collections.abc import Coroutine
from copy import copy
import functools
import logging
import re
from defusedxml import ElementTree
from typing import Optional, Any

_LOGGER = logging.getLogger(__name__)


async def run_tasks(*tasks: Coroutine) -> None:
    """Run coroutines in a TaskGroup, unwrapping BaseExceptionGroup on failure."""
    try:
        async with asyncio.TaskGroup() as group:
            for task in tasks:
                group.create_task(task)
    except BaseExceptionGroup as exc:
        raise copy(exc.exceptions[0]).with_traceback(exc.exceptions[0].__traceback__)


async def cancel_and_wait(task: asyncio.Task[Any]) -> None:
    """Cancel a task and await it, re-raising only a cancellation of the calling task.
    """
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling() > 0:
            raise
    except Exception:
        _LOGGER.exception("Error from task %r", task)


async def wait_any(*events: asyncio.Event) -> None:
    """Wait until at least one of the events is set."""
    if any(event.is_set() for event in events):
        return
    waits = [asyncio.create_task(event.wait()) for event in events]
    try:
        await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for wait in waits:
            wait.cancel()
        await asyncio.wait(waits)


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


def _log_exception(msg, *args):
    """Log an error and turn on traceback if debug is on."""
    _LOGGER.error(msg, *args, exc_info=_LOGGER.getEffectiveLevel() == logging.DEBUG)


def get_uniqueid_from_udn(data) -> str | None:
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
        data = re.sub(r"&(?![A-Za-z]+[0-9]*;|#[0-9]+;|#x[0-9a-fA-F]+;)", r"&amp;", data)
        return ElementTree.fromstring(data)


def get_udn_from_xml(xml: Any) -> str | None:
    return xml.findtext(
        "d:device/d:UDN", None, {"d": "urn:schemas-upnp-org:device-1-0"}
    )


async def get_uniqueid_from_device_description(
    session: aiohttp.ClientSession, url: str
):
    """Retrieve and extract unique id from url."""
    try:
        async with session.get(url) as req:
            req.raise_for_status()
            data = await req.text()
            xml = get_possibly_invalid_xml(data)
            udn = get_udn_from_xml(xml)
            return get_uniqueid_from_udn(udn)
    except (aiohttp.ClientError, TimeoutError, ElementTree.ParseError):
        _log_exception("Unable to get device description from %s", url)
        return None


async def get_uniqueid_from_host(session: aiohttp.ClientSession, host: str):
    """Try to deduce a unique id from a host based on ssdp/upnp."""
    return await get_uniqueid_from_device_description(
        session, f"http://{host}:8080/dd.xml"
    )
