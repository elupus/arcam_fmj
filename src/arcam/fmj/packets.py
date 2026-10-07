"""Wire-protocol packet types and async serialization helpers.

The Arcam protocol frames every command and response with STR (0x21) and
ETR (0x0D) delimiters. AMX discovery uses a separate ``AMX\\r`` / ``AMXB``
framing that shares the same TCP connection.
"""
from __future__ import annotations

import asyncio
import logging
import re
from asyncio.exceptions import IncompleteReadError
from typing import Union

import attr

from .errors import (
    ConnectionFailed,
    InvalidPacket,
    NullPacket,
)
from .codecs import AnswerCodes

_LOGGER = logging.getLogger(__name__)
_WRITE_TIMEOUT = 3
_READ_TIMEOUT = 3

#: Start-of-packet delimiter (``!``).
PROTOCOL_STR = b"\x21"
#: End-of-packet delimiter (carriage return).
PROTOCOL_ETR = b"\x0d"
#: Sentinel for a clean stream close.
PROTOCOL_EOF = b""

@attr.s
class ResponsePacket:
    """A parsed response frame from the device.

    Wire format: ``STR Zn Cc Ac Dl Data… ETR``.
    """

    zn = attr.ib(type=int)
    cc = attr.ib(type=int)
    ac = attr.ib(type=int)
    data = attr.ib(type=bytes)

    def response_to(self, request: Union["AmxDuetRequest", "CommandPacket"]):
        if not isinstance(request, CommandPacket):
            return False
        return self.zn == request.zn and self.cc == request.cc

    @staticmethod
    def from_bytes(data: bytes) -> "ResponsePacket":
        if len(data) < 6:
            raise InvalidPacket(f"Packet to short {data!r}")

        if data[4] != len(data) - 6:
            raise InvalidPacket(f"Invalid length in data {data!r}")

        return ResponsePacket(
            data[1],
            data[2],
            AnswerCodes.from_int(data[3]),
            data[5 : 5 + data[4]],
        )

    def to_bytes(self):
        return bytes(
            [
                *PROTOCOL_STR,
                self.zn,
                self.cc,
                self.ac,
                len(self.data),
                *self.data,
                *PROTOCOL_ETR,
            ]
        )

@attr.s
class CommandPacket:
    """A parsed command frame sent to the device.

    Wire format: ``STR Zn Cc Dl Data… ETR``.
    """

    zn = attr.ib(type=int)
    cc = attr.ib(type=int)
    data = attr.ib(type=bytes)

    def to_bytes(self):
        return bytes(
            [*PROTOCOL_STR, self.zn, self.cc, len(self.data), *self.data, *PROTOCOL_ETR]
        )

    @staticmethod
    def from_bytes(data: bytes) -> "CommandPacket":
        if len(data) < 5:
            raise InvalidPacket(f"Packet to short {data!r}")

        if data[3] != len(data) - 5:
            raise InvalidPacket(f"Invalid length in data {data!r}")

        return CommandPacket(
            data[1], data[2], data[4 : 4 + data[3]]
        )

@attr.s
class AmxDuetRequest:
    """An AMX discovery request (``AMX\\r``).

    Sent by AMX-compatible controllers to discover Arcam devices on the
    network.
    """

    @staticmethod
    def from_bytes(data: bytes) -> "AmxDuetRequest":
        if not data == b"AMX\r":
            raise InvalidPacket(f"Packet is not a amx request {data!r}")
        return AmxDuetRequest()

    def to_bytes(self):
        return b"AMX\r"

@attr.s
class AmxDuetResponse:
    """An AMX discovery response (``AMXB<Key=Value>…\\r``).

    Returned by the device in response to an AmxDuetRequest. Contains
    device metadata as key-value tags (model, make, revision, etc.).
    """

    values = attr.ib(type=dict)

    @property
    def device_class(self) -> str | None:
        return self.values.get("Device-SDKClass")

    @property
    def device_make(self) -> str | None:
        return self.values.get("Device-Make")

    @property
    def device_model(self) -> str | None:
        return self.values.get("Device-Model")

    @property
    def device_revision(self) -> str | None:
        return self.values.get("Device-Revision")

    def response_to(self, packet: AmxDuetRequest | CommandPacket):
        if not isinstance(packet, AmxDuetRequest):
            return False
        return True

    @staticmethod
    def from_bytes(data: bytes) -> "AmxDuetResponse":
        if not data.startswith(b"AMXB"):
            raise InvalidPacket(f"Packet is not a amx response {data!r}")

        tags = re.findall(r"<(.+?)=(.+?)>", data[4:].decode("ASCII"))
        return AmxDuetResponse(dict(tags))

    def to_bytes(self):
        res = (
            "AMXB"
            + "".join([f"<{key}={value}>" for key, value in self.values.items()])
            + "\r"
        )
        return res.encode("ASCII")

async def _read_delimited(reader: asyncio.StreamReader, header_len) -> bytes | None:
    """Read one delimited frame (Arcam or AMX) from the stream.

    Returns the raw frame bytes, or None on EOF.  Handles three framing
    variants: standard STR-delimited Arcam packets, ``AMX\\r`` requests,
    and the ``\\x01^AMX`` variant seen from some devices.
    """
    try:
        start = await reader.readexactly(1)
        if start == PROTOCOL_EOF:
            _LOGGER.debug("eof")
            return None

        if start == PROTOCOL_STR:
            header = await reader.readexactly(header_len - 1)
            data_len = await reader.readexactly(1)
            data = await reader.readexactly(int.from_bytes(data_len, "big"))
            etr = await reader.readexactly(1)

            if etr != PROTOCOL_ETR:
                raise InvalidPacket(f"unexpected etr byte {etr!r}")

            packet = bytes([*start, *header, *data_len, *data, *etr])
        elif start == b"\x01":
            # Some devices send the AMX header as \x01^AMX
            header = await reader.readexactly(4)
            if header != b"^AMX":
                raise InvalidPacket(f"Unexpected AMX header: {header!r}")

            data = await reader.readuntil(PROTOCOL_ETR)
            packet = bytes([*b"AMX", *data])
        elif start == b"A":
            header = await reader.readexactly(2)
            if header != b"MX":
                raise InvalidPacket("Unexpected AMX header")

            data = await reader.readuntil(PROTOCOL_ETR)
            packet = bytes([*start, *header, *data])
        elif start == b"\x00":
            raise NullPacket()
        else:
            raise InvalidPacket(f"unexpected str byte {start!r}")

        return packet

    except TimeoutError as exception:
        raise ConnectionFailed() from exception
    except ConnectionError as exception:
        raise ConnectionFailed() from exception
    except OSError as exception:
        raise ConnectionFailed() from exception
    except IncompleteReadError as exception:
        raise ConnectionFailed() from exception

async def _read_response(
    reader: asyncio.StreamReader,
) -> ResponsePacket | AmxDuetResponse | None:
    """Read and parse a single response or AMX discovery frame."""
    data = await _read_delimited(reader, 4)
    if not data:
        return None

    if data.startswith(b"AMX"):
        return AmxDuetResponse.from_bytes(data)
    else:
        return ResponsePacket.from_bytes(data)

async def read_response(
    reader: asyncio.StreamReader,
) -> ResponsePacket | AmxDuetResponse | None:
    """Read the next valid response, skipping malformed and null packets."""
    while True:
        try:
            data = await _read_response(reader)
        except InvalidPacket as e:
            _LOGGER.warning(str(e))
            continue
        except NullPacket:
            _LOGGER.debug("Ignoring 0x00 start byte sent from some devices")
            continue
        return data

async def _read_command(
    reader: asyncio.StreamReader,
) -> CommandPacket | AmxDuetRequest | None:
    """Read and parse a single command or AMX discovery frame."""
    data = await _read_delimited(reader, 3)
    if not data:
        return None
    if data.startswith(b"AMX"):
        return AmxDuetRequest.from_bytes(data)
    else:
        return CommandPacket.from_bytes(data)

async def read_command(
    reader: asyncio.StreamReader,
) -> CommandPacket | AmxDuetRequest | None:
    """Read the next valid command, skipping malformed packets."""
    while True:
        try:
            data = await _read_command(reader)
        except InvalidPacket as e:
            _LOGGER.warning(str(e))
            continue
        return data

async def write_packet(
    writer: asyncio.StreamWriter,
    packet: CommandPacket | ResponsePacket | AmxDuetRequest | AmxDuetResponse,
) -> None:
    """Serialize and write a packet to the stream."""
    try:
        data = packet.to_bytes()
        writer.write(data)
        async with asyncio.timeout(_WRITE_TIMEOUT):
            await writer.drain()
    except TimeoutError as exception:
        raise ConnectionFailed() from exception
    except ConnectionError as exception:
        raise ConnectionFailed() from exception
    except OSError as exception:
        raise ConnectionFailed() from exception
