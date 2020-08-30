import argparse
import asyncio
import logging
import sys

from . import CommandCodes, CommandInvalidAtThisTime, SourceCodes, IncomingAudioFormat, IncomingAudioConfig, DecodeMode2CH, DecodeModeMCH, RC5Codes, CommandNotRecognised, _LOGGER, ResponsePacket, AnswerCodes
from .client import Client, ClientContext
from .server import Server, ServerContext
from .state import State

# pylint: disable=invalid-name

def auto_int(x):
    return int(x, 0)

def auto_bytes(x):
    print(x)
    return bytes.decode(x)

parser = argparse.ArgumentParser(description='Communicate with arcam receivers.')
parser.add_argument('--verbose', action='store_true')

subparsers = parser.add_subparsers(dest="subcommand")

parser_state = subparsers.add_parser('state')
parser_state.add_argument('--host', required=True)
parser_state.add_argument('--port', default=50000)
parser_state.add_argument('--zone', default=1, type=int)
parser_state.add_argument('--volume', type=int)
parser_state.add_argument('--source', type=auto_int)
parser_state.add_argument('--monitor', action='store_true')

parser_client = subparsers.add_parser('client')
parser_client.add_argument('--host', required=True)
parser_client.add_argument('--port', default=50000)
parser_client.add_argument('--zone', default=1, type=int)
parser_client.add_argument('--command', type=auto_int)
parser_client.add_argument('--data', nargs='+', default=[0xF0], type=auto_int)

parser_server = subparsers.add_parser('server')
parser_server.add_argument('--host', default='localhost')
parser_server.add_argument('--port', default=50000)


async def run_client(args):
    client = Client(args.host, args.port)
    async with ClientContext(client):
        result = await client.request(args.zone, args.command, bytes(args.data))
        print(result)

async def run_state(args):
    client = Client(args.host, args.port)
    async with ClientContext(client):
        state = State(client, args.zone)

        if args.volume is not None:
            await state.set_volume(args.volume)

        if args.source is not None:
            await state.set_source(args.source)

        if args.monitor:
            async with state:
                prev = repr(state)
                await state.update()
                while client.connected:
                    curr = repr(state)
                    if prev != curr:
                        print(curr)
                        prev = curr
                    await asyncio.sleep(delay=1)
        else:
            await state.update()
            print(state)


async def run_server(args):
    class DummyServer(Server):

        def __init__(self, host, port):
            super().__init__(host, port)

            self._volume = bytes([10])
            self._source = bytes([SourceCodes.PVR])
            self._audio_format = bytes([IncomingAudioFormat.PCM, IncomingAudioConfig.STEREO_ONLY])
            self._decode_mode_2ch = bytes([DecodeMode2CH.DOLBY_PLII_IIx_MUSIC])
            self._decode_mode_mch = bytes([DecodeModeMCH.DOLBY_PLII_IIx_MUSIC])
            self._tuner_preset = b'\0xff'
            self._presets = {
                b'\x01': b'\x03SR P1   ',
                b'\x02': b'\x03SR Klass',
                b'\x03' : b'\x03P3 Star ',
                b'\x04': b'\x02SR P4   ',
                b'\x05': b'\x02SR P4   ',
                b'\x06': b'\x01jP',
            }


            self.register_handler(0x01, CommandCodes.POWER, bytes([0xF0]), self.get_power)
            self.register_handler(0x01, CommandCodes.VOLUME, bytes([0xF0]), self.get_volume)
            self.register_handler(0x01, CommandCodes.VOLUME, None, self.set_volume)
            self.register_handler(0x01, CommandCodes.CURRENT_SOURCE, bytes([0xF0]), self.get_source)
            self.register_handler(0x01, CommandCodes.INCOMING_AUDIO_FORMAT, bytes([0xF0]), self.get_incoming_audio_format)
            self.register_handler(0x01, CommandCodes.DECODE_MODE_STATUS_2CH, bytes([0xF0]), self.get_decode_mode_2ch)
            self.register_handler(0x01, CommandCodes.DECODE_MODE_STATUS_MCH, bytes([0xF0]), self.get_decode_mode_mch)
            self.register_handler(0x01, CommandCodes.SIMULATE_RC5_IR_COMMAND, None, self.ir_command)
            self.register_handler(0x01, CommandCodes.PRESET_DETAIL, None, self.get_preset_detail)
            self.register_handler(0x01, CommandCodes.TUNER_PRESET, bytes([0xF0]), self.get_tuner_preset)
            self.register_handler(0x01, CommandCodes.TUNER_PRESET, None, self.set_tuner_preset)

        def get_power(self, **kwargs):
            return bytes([1])

        def set_volume(self, data, **kwargs):
            self._volume = data
            return self._volume

        def get_volume(self, **kwargs):
            return self._volume

        def get_source(self, **kwargs):
            return self._source

        def set_source(self, data, **kwargs):
            self._source = data
            return self._source

        def ir_command(self, data, **kwargs):
            source_commands = {
                RC5Codes.SELECT_AUX.value: SourceCodes.AUX,
                RC5Codes.SELECT_AV.value: SourceCodes.AV,
                RC5Codes.SELECT_PVR.value: SourceCodes.PVR,
                RC5Codes.SELECT_DISPLAY.value: SourceCodes.DISPLAY,
            }
            source = source_commands.get(data)
            if source:
                self.set_source(bytes([source]))
                return [
                    ResponsePacket(
                        zn=0x01,
                        cc=CommandCodes.SIMULATE_RC5_IR_COMMAND,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=data
                    ),
                    ResponsePacket(
                        zn=0x01,
                        cc=CommandCodes.CURRENT_SOURCE,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=bytes([source])
                    )
                ]

            raise CommandNotRecognised()

        def get_decode_mode_2ch(self, **kwargs):
            return self._decode_mode_2ch

        def get_decode_mode_mch(self, **kwargs):
            return self._decode_mode_mch

        def get_incoming_audio_format(self, **kwargs):
            return self._audio_format

        def get_tuner_preset(self, **kwargs):
            return self._tuner_preset

        def set_tuner_preset(self, data, **kwargs):
            self._tuner_preset = data
            return self._tuner_preset

        def get_preset_detail(self, data, **kwargs):
            preset = self._presets.get(data)
            if preset:
                return data + preset
            else:
                raise CommandInvalidAtThisTime()

    server = DummyServer(args.host, args.port)
    async with ServerContext(server):
        while True:
            await asyncio.sleep(delay=1)

def main():

    args = parser.parse_args()

    if args.verbose:
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        channel = logging.StreamHandler(sys.stdout)
        channel.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        channel.setFormatter(formatter)
        root.addHandler(channel)


    loop = asyncio.get_event_loop()

    if args.subcommand == 'client':
        loop.run_until_complete(run_client(args))
    elif args.subcommand == 'state':
        loop.run_until_complete(run_state(args))
    elif args.subcommand == 'server':
        loop.run_until_complete(run_server(args))

if __name__ == "__main__":
    main()
