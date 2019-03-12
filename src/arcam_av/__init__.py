"""Arcam AV Control"""
import asyncio
import attr
import logging

PROTOCOL_STR = b'\x21'
PROTOCOL_ETR = b'\x0D'

_LOGGER = logging.getLogger(__name__)

class InvalidPacket(Exception):
    pass

@attr.s
class ResponsePacket(object):
    zn = attr.ib(type=int)
    cc = attr.ib(type=int)
    ac = attr.ib(type=int)
    data = attr.ib(type=bytes)

@attr.s
class CommandPacket(object):
    zn   = attr.ib(type=int)
    cc   = attr.ib(type=int)
    data = attr.ib(type=bytes)

async def _read_packet(reader: asyncio.StreamReader) -> ResponsePacket:
    while await reader.read(1) != PROTOCOL_STR:
        pass

    data = await reader.readuntil(PROTOCOL_ETR)

    if len(data) < 5:
        raise InvalidPacket("Packet to short {}".format(data))

    if data[3] != len(data)-5:
        raise InvalidPacket("Invalid length in data {}".format(data))

    return ResponsePacket(
        data[0],
        data[1],
        data[2],
        data[4:4+data[3]])


async def _write_packet(writer: asyncio.StreamWriter, packet: CommandPacket) -> None:
    writer.write(PROTOCOL_STR)
    writer.write(packet.zn.to_bytes(1, 'big'))
    writer.write(packet.cc.to_bytes(1, 'big'))
    writer.write(len(packet.data).to_bytes(1, 'big'))
    writer.write(packet.data)
    writer.write(PROTOCOL_ETR)
    await writer.drain()
