"""Tests for utils."""
import pytest
from aiohttp import web
from typing import Awaitable, Callable, Optional

from async_upnp_client.utils import CaseInsensitiveDict
from async_upnp_client.ssdp import AddressTupleVXType

from arcam.fmj.utils import async_retry
from arcam.fmj.utils import (
    get_uniqueid_from_udn,
    get_uniqueid,
    get_upnp_headers,
    get_uniqueid_from_host,
    get_serial_number_from_host,
)

TEST_HOST = "dummy host"
TEST_LOCATION = "/dd.xml"
MOCK_UNIQUE_ID = "0011044feeef"
MOCK_UDN = f"uuid:aa331113-fa23-3333-2222-{MOCK_UNIQUE_ID}"
MOCK_SERIAL_NO = "01a0132032f01103100400010010ff00"

def _get_dd(unique_id, serial_no, udn):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0" xmlns:pnpx="http://schemas.microsoft.com/windows/pnpx/2005/11" xmlns:microsoft="urn:schemas-microsoft-com:WMPNSS-1-0" xmlns:df="http://schemas.microsoft.com/windows/2008/09/devicefoundation">
   <specVersion>
      <major>1</major>
      <minor>0</minor>
   </specVersion>
   <device>
      <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
      
      
      <friendlyName>Arcam media client {unique_id}</friendlyName>
      <manufacturer>ARCAM</manufacturer>
      <manufacturerURL>http://www.arcam.co.uk</manufacturerURL>
      <modelDescription>ir-ser-FS2026-0500-0001_V2.5.14.36554-15</modelDescription>
      <modelName> </modelName>
      <modelNumber>AVR450, AVR750</modelNumber>
      <modelURL>http://www.arcamradio.co.uk</modelURL>
      <serialNumber>{serial_no}</serialNumber>
      <UDN>{udn}</UDN>
      <iconList>
         <icon>
            <mimetype>image/png</mimetype>
            <width>48</width>
            <height>48</height>
            <depth>32</depth>
            <url>/icon.png</url>
         </icon>
         <icon>
            <mimetype>image/jpeg</mimetype>
            <width>48</width>
            <height>48</height>
            <depth>32</depth>
            <url>/icon.jpg</url>
         </icon>
         <icon>
            <mimetype>image/png</mimetype>
            <width>120</width>
            <height>120</height>
            <depth>32</depth>
            <url>/icon2.png</url>
         </icon>
         <icon>
            <mimetype>image/jpeg</mimetype>
            <width>120</width>
            <height>120</height>
            <depth>32</depth>
            <url>/icon2.jpg</url>
         </icon>
      </iconList>
      <serviceList></serviceList>
      <dlna:X_DLNADOC xmlns:dlna="urn:schemas-dlna-org:device-1-0">DMR-1.50</dlna:X_DLNADOC>
      <pnpx:X_hardwareId>VEN_2A2D&amp;DEV_0001&amp;SUBSYS_0001&amp;REV_01 VEN_0033&amp;DEV_0006&amp;REV_01</pnpx:X_hardwareId>
      <pnpx:X_compatibleId>MS_DigitalMediaDeviceClass_DMR_V001</pnpx:X_compatibleId>
      <pnpx:X_deviceCategory>MediaDevices</pnpx:X_deviceCategory>
      <df:X_deviceCategory>Multimedia.DMR</df:X_deviceCategory>
      <microsoft:magicPacketWakeSupported>0</microsoft:magicPacketWakeSupported>
      <microsoft:magicPacketSendSupported>1</microsoft:magicPacketSendSupported>
   </device>
</root>
"""


async def test_retry_fails(event_loop):

    calls = 0

    @async_retry(2, Exception)
    async def tester():
        nonlocal calls
        calls += 1
        raise Exception()

    with pytest.raises(Exception):
        await tester()

    assert calls == 2


async def test_retry_succeeds(event_loop):

    calls = 0

    @async_retry(2, Exception)
    async def tester():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise Exception()
        return True

    assert await tester()


async def test_retry_unexpected(event_loop):


    calls = 0

    @async_retry(2, TimeoutError)
    async def tester():
        nonlocal calls
        calls += 1
        raise ValueError()

    with pytest.raises(ValueError):
        await tester()
    assert calls == 1


@pytest.fixture
async def mock_search(mocker):
    responses = []
    async def mock_async_search(
        async_callback: Callable[[CaseInsensitiveDict], Awaitable],
        search_target: str,
        target: Optional[AddressTupleVXType],
    ) -> None:
        for response in responses:
            await async_callback(CaseInsensitiveDict(response))

    mocker.patch('arcam.fmj.utils.async_search', new = mock_async_search)

    return responses


async def test_get_upnp_headers(mock_search):
    mock_search.append({"_udn": MOCK_UDN})
    headers = await get_upnp_headers(TEST_HOST)
    assert headers["_udn"] == MOCK_UDN


async def test_get_upnp_headers_no_response(mock_search):
    headers = await get_upnp_headers(TEST_HOST)
    assert headers == None


async def test_get_upnp_headers_multiple_response(mock_search):
    mock_search.append({"_udn": MOCK_UDN})
    mock_search.append({"_udn": MOCK_UDN})
    headers = await get_upnp_headers(TEST_HOST)
    assert headers == None


@pytest.mark.parametrize("data, expected", [
    (MOCK_UDN, MOCK_UNIQUE_ID),
    ("", None),
    ("malformed udn", None),
    ("uuid:", None),
    ('uuid:aa331113-fa23-3333-2222', None),
    ])
def test_unique_id_from_udn(data, expected):
    assert get_uniqueid_from_udn(data) == expected


@pytest.fixture
async def mock_headers(mocker):
    mocker.patch('arcam.fmj.utils.get_upnp_headers', return_value = CaseInsensitiveDict({"location": TEST_LOCATION, "_udn": MOCK_UDN}))


@pytest.fixture
async def mock_no_headers(mocker):
    mocker.patch('arcam.fmj.utils.get_upnp_headers', return_value = None)


async def test_get_uniqueid(event_loop, mock_headers):
    assert await get_uniqueid(TEST_HOST) == MOCK_UNIQUE_ID


async def test_get_uniqueid_no_headers(event_loop, mock_no_headers):
    assert await get_uniqueid(TEST_HOST) == None


async def test_get_uniqueid_from_host(event_loop, mock_headers, aiohttp_client):
    app = web.Application()
    dummy_client = await aiohttp_client(app)
    assert await get_uniqueid_from_host(dummy_client, TEST_HOST) == MOCK_UNIQUE_ID


@pytest.fixture
def response_text():
    return 

@pytest.fixture
async def mock_client_session(aiohttp_client):
    response_text = _get_dd(MOCK_UNIQUE_ID, MOCK_SERIAL_NO, MOCK_UDN)
    async def device_description(request):
        return web.Response(text=response_text)
    app = web.Application()
    app.router.add_get(TEST_LOCATION, device_description)
    return await aiohttp_client(app)


async def test_get_serial_number_from_host(event_loop, mock_headers, mock_client_session):
    assert await get_serial_number_from_host(mock_client_session, TEST_HOST) == MOCK_SERIAL_NO


async def test_get_serial_number_from_host_no_headers(event_loop, mock_no_headers, mock_client_session):
    assert await get_serial_number_from_host(mock_client_session, TEST_HOST) == None
