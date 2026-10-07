import argparse
import asyncio
import logging
import sys
from pprint import pprint

from .codecs import (
    AnswerCodes,
    BoolCodec,
    EnumCodec,
    IncomingAudioConfig,
    IncomingAudioFormat,
    IncomingVideoAspectRatio,
    IncomingVideoColorspace,
    IntCodec,
    ScaledCodec,
    SourceCodes,
    StringCodec,
    StructCodec,
    VideoParameters,
)
from .commands import (
    COMMANDS,
    CURRENT_SOURCE,
    INCOMING_AUDIO_FORMAT,
    INCOMING_VIDEO_PARAMETERS,
    POWER,
    PRESET_DETAIL,
    ReadCommand,
    SIMULATE_RC5_IR_COMMAND,
    TUNER_PRESET,
    VOLUME,
    WriteCommand,
)
from .errors import CommandInvalidAtThisTime, CommandNotRecognised
from .models import (
    APIVERSION_AVR_SERIES,
    api_model_for,
)
from .packets import ResponsePacket
from .rc5 import RC5CODE_SOURCE
from .client import Client, ClientSerial, ClientContext
from .server import Server, ServerContext
from .state import State

# pylint: disable=invalid-name


def auto_int(x):
    return int(x, 0)


def auto_source(x):
    return SourceCodes[x]


def _codec_argparse_kwargs(codec):
    """Map a codec to argparse add_argument kwargs, or None if not CLI-settable."""
    if isinstance(codec, BoolCodec):
        return {"action": argparse.BooleanOptionalAction}
    if isinstance(codec, IntCodec):
        return {"type": int}
    if isinstance(codec, EnumCodec):
        cls = codec.enum_cls
        by_name = {name.lower(): member for name, member in cls.__members__.items()}
        return {
            "type": lambda x, m=by_name: m[x.lower()],
            "choices": list(cls),
            "metavar": "MODE",
        }
    if isinstance(codec, ScaledCodec):
        return {
            "type": float,
            "help": f"({codec.min_value} to {codec.max_value})",
        }
    if isinstance(codec, StringCodec):
        return {}
    return None


def _codec_default_bytes(codec):
    """A plausible default encoded value for a codec, for the dummy server store."""
    if isinstance(codec, EnumCodec):
        members = list(codec.enum_cls)
        return bytes([int(members[0])]) if members else bytes([0x00])
    if isinstance(codec, StringCodec):
        return b"Default"
    return bytes([0x00])


def _register_settable_args(parser):
    """Auto-register CLI arguments for the writable commands. Returns (stem, command) pairs."""
    settable = []
    for command in COMMANDS:
        if not isinstance(command, WriteCommand):
            continue
        kwargs = _codec_argparse_kwargs(command.codec)
        if kwargs is None:
            continue
        stem = command.name.lower()
        parser.add_argument(f"--{stem.replace('_', '-')}", **kwargs)
        settable.append((stem, command))
    return settable


parser = argparse.ArgumentParser(description="Communicate with arcam receivers.")
parser.add_argument("--verbose", action="store_true")

subparsers = parser.add_subparsers(dest="subcommand")

parser_state = subparsers.add_parser("state")
target = parser_state.add_mutually_exclusive_group(required=True)
target.add_argument("--host")
target.add_argument("--serial")
parser_state.add_argument("--port", default=50000)
parser_state.add_argument("--zone", default=1, type=int)
parser_state.add_argument("--source", type=auto_source)
parser_state.add_argument("--monitor", action="store_true")
parser_state.add_argument(
    "--save-settings",
    action="store_true",
    help="Save a secure backup of device settings",
)
parser_state.add_argument(
    "--restore-settings",
    action="store_true",
    help="Restore device settings from secure backup",
)
parser_state.add_argument(
    "--pin",
    nargs=4,
    type=int,
    default=[1, 2, 3, 4],
    metavar=("D1", "D2", "D3", "D4"),
    help="Installer PIN for save/restore (default: 1 2 3 4)",
)

_SETTABLE_COMMANDS = _register_settable_args(parser_state)

parser_client = subparsers.add_parser("client")
target = parser_client.add_mutually_exclusive_group(required=True)
target.add_argument("--host", default=None)
target.add_argument("--serial", default=None)
parser_client.add_argument("--port", default=50000)
parser_client.add_argument("--zone", default=1, type=int)
parser_client.add_argument("--command", type=auto_int, required=True)
parser_client.add_argument("--data", nargs="+", default=[0xF0], type=auto_int)

parser_server = subparsers.add_parser("server")
parser_server.add_argument("--host", default="localhost")
parser_server.add_argument("--port", default=50000)
parser_server.add_argument("--model", default="AVR450")


async def run_client(args):
    if args.host:
        client = Client(args.host, args.port)
    else:
        client = ClientSerial(args.serial)

    async with ClientContext(client):
        result = await client.request(
            args.zone, args.command, bytes(args.data)
        )
        print(result)


async def run_state(args):
    if args.host:
        client = Client(args.host, args.port)
    else:
        client = ClientSerial(args.serial)
    async with ClientContext(client), State(client, args.zone) as state:
        await state.update()

        pin = tuple(args.pin)

        if args.save_settings:
            await state.save_settings(pin)
            print("Settings saved.")

        if args.restore_settings:
            await state.restore_settings(pin)
            print("Settings restored.")

        if args.source is not None:
            await state.set_source(args.source)

        for stem, command in _SETTABLE_COMMANDS:
            value = getattr(args, stem, None)
            if value is not None:
                await state.set(command, value)

        if args.monitor:
            updated = asyncio.Event()
            prev = state.to_dict()
            with client.listen(lambda _: updated.set()):
                while client.connected:
                    await updated.wait()
                    updated.clear()
                    curr = state.to_dict()
                    if prev != curr:
                        pprint(curr)
                        prev = curr
        else:
            pprint(state.to_dict())


async def run_server(args):
    class DummyServer(Server):
        def __init__(self, host, port, model):
            super().__init__(host, port, model)

            if model not in APIVERSION_AVR_SERIES:
                raise ValueError("Unexpected model")
            self._api_version = api_model_for(model)

            rc5_key = (self._api_version, 1)
            self._store = {}
            self._rc5_reverse = {}

            for command in COMMANDS:
                cc = command.cc
                if isinstance(command.codec, StructCodec):
                    continue

                self._store[cc] = _codec_default_bytes(command.codec)

                if isinstance(command, ReadCommand):
                    self.register_handler(
                        0x01, cc, bytes([0xF0]),
                        lambda cc=cc, **kw: self._store[cc],
                    )

                if isinstance(command, WriteCommand):
                    self.register_handler(
                        0x01, cc, None,
                        lambda data, cc=cc, **kw: self._set(cc, data),
                    )

                if command.rc5_write is not None:
                    for value, code in command.rc5_write.table.get(rc5_key, {}).items():
                        self._rc5_reverse[code] = (cc, command.codec.encode(value))

            # Overrides for realistic defaults
            self._store[POWER.cc] = bytes([0x01])
            self._store[VOLUME.cc] = bytes([10])
            self._store[TUNER_PRESET.cc] = b"\xff"

            # CURRENT_SOURCE — no codec, manual handlers
            self._store[CURRENT_SOURCE.cc] = SourceCodes.PVR.to_bytes(
                self._api_version, 1
            )
            self.register_handler(
                0x01, CURRENT_SOURCE.cc, bytes([0xF0]),
                lambda **kw: self._store[CURRENT_SOURCE.cc],
            )
            source_table = RC5CODE_SOURCE.get(rc5_key, {})
            for src, code in source_table.items():
                self._rc5_reverse[code] = (
                    CURRENT_SOURCE.cc,
                    src.to_bytes(self._api_version, 1),
                )

            # INCOMING_VIDEO_PARAMETERS — StructCodec needs real data
            self._store[INCOMING_VIDEO_PARAMETERS.cc] = VideoParameters(
                horizontal_resolution=1920,
                vertical_resolution=1080,
                refresh_rate=60,
                interlaced=False,
                aspect_ratio=IncomingVideoAspectRatio.ASPECT_16_9,
                colorspace=IncomingVideoColorspace.NORMAL,
            ).to_bytes()
            self.register_handler(
                0x01, INCOMING_VIDEO_PARAMETERS.cc, bytes([0xF0]),
                lambda **kw: self._store[INCOMING_VIDEO_PARAMETERS.cc],
            )

            # INCOMING_AUDIO_FORMAT — no codec, manual handler
            self._store[INCOMING_AUDIO_FORMAT.cc] = bytes(
                [IncomingAudioFormat.PCM, IncomingAudioConfig.STEREO_ONLY]
            )
            self.register_handler(
                0x01, INCOMING_AUDIO_FORMAT.cc, bytes([0xF0]),
                lambda **kw: self._store[INCOMING_AUDIO_FORMAT.cc],
            )

            # PRESET_DETAIL — custom lookup logic
            self._presets = {
                b"\x01": b"\x03SR P1   ",
                b"\x02": b"\x03SR Klass",
                b"\x03": b"\x03P3 Star ",
                b"\x04": b"\x02SR P4   ",
                b"\x05": b"\x02SR P4   ",
                b"\x06": b"\x01jP",
            }
            self.register_handler(
                0x01, PRESET_DETAIL.cc, None, self._get_preset_detail,
            )

            # TUNER_PRESET — write handler is auto-registered; seed read handler too
            self.register_handler(
                0x01, TUNER_PRESET.cc, bytes([0xF0]),
                lambda **kw: self._store[TUNER_PRESET.cc],
            )

            # RC5 IR command handler (uses auto-built reverse table)
            self.register_handler(
                0x01, SIMULATE_RC5_IR_COMMAND.cc, None, self._ir_command,
            )

        def _set(self, cc, data):
            self._store[cc] = data
            return data

        def _ir_command(self, data, **kwargs):
            result = self._rc5_reverse.get(data)
            if result:
                cc, encoded = result
                self._store[cc] = encoded
                return [
                    ResponsePacket(
                        zn=0x01,
                        cc=SIMULATE_RC5_IR_COMMAND.cc,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=data,
                    ),
                    ResponsePacket(
                        zn=0x01,
                        cc=cc,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=encoded,
                    ),
                ]
            raise CommandNotRecognised()

        def _get_preset_detail(self, data, **kwargs):
            preset = self._presets.get(data)
            if preset:
                return data + preset
            raise CommandInvalidAtThisTime()

    server = DummyServer(args.host, args.port, args.model)
    async with ServerContext(server):
        while True:
            await asyncio.sleep(delay=1)


def main_real():
    args = parser.parse_args()

    if args.verbose:
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        channel = logging.StreamHandler(sys.stdout)
        channel.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        channel.setFormatter(formatter)
        root.addHandler(channel)

    if args.subcommand == "client":
        asyncio.run(run_client(args))
    elif args.subcommand == "state":
        asyncio.run(run_state(args))
    elif args.subcommand == "server":
        asyncio.run(run_server(args))

def main():
    try:
        main_real()
    except KeyboardInterrupt as exc:
        raise SystemExit(1) from exc

if __name__ == "__main__":
    main()
