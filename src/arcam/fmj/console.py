import argparse
import asyncio
import logging
import sys
from pprint import pprint

from .codecs import (
    AnswerCodes,
    CompressionMode,
    DecodeMode2CH,
    DecodeModeMCH,
    DolbyAudioMode,
    ImaxEnhancedMode,
    IncomingAudioConfig,
    IncomingAudioFormat,
    IncomingVideoAspectRatio,
    IncomingVideoColorspace,
    RoomEqMode,
    SourceCodes,
    VideoParameters,
)
from .commands import CommandCodes, CommandFlags
from .errors import CommandInvalidAtThisTime, CommandNotRecognised
from .models import (
    APIVERSION_AVR_SERIES,
    api_model_for,
)
from .packets import ResponsePacket
from .rc5 import RC5CODE_SOURCE
from .schemas import (
    AsciiString,
    BoolByte,
    ByteEnum,
    IntByte,
    Rc5Fallback,
    ScaledSigned,
    StructFromBytes,
)
from .client import Client, ClientSerial, ClientContext
from .server import Server, ServerContext
from .state import State

# pylint: disable=invalid-name


def auto_int(x):
    return int(x, 0)


def auto_source(x):
    return SourceCodes[x]


def _inner_schema(schema):
    """Unwrap Rc5Fallback to get the inner schema."""
    return schema.inner if isinstance(schema, Rc5Fallback) else schema


def _schema_argparse_kwargs(schema):
    """Map a schema to argparse add_argument kwargs, or None if not CLI-settable."""
    inner = _inner_schema(schema)
    if isinstance(inner, BoolByte):
        return {"action": argparse.BooleanOptionalAction}
    if isinstance(inner, IntByte):
        return {"type": int}
    if isinstance(inner, ByteEnum):
        cls = inner.enum_cls
        return {
            "type": lambda x, c=cls: c[x.upper()],
            "choices": list(cls),
            "metavar": "MODE",
        }
    if isinstance(inner, ScaledSigned):
        return {
            "type": float,
            "help": f"({inner.min_value} to {inner.max_value})",
        }
    if isinstance(inner, AsciiString):
        return {}
    return None


def _schema_default_bytes(schema):
    """Provide a sensible default encoded value for a schema type."""
    if isinstance(schema, Rc5Fallback):
        return _schema_default_bytes(schema.inner)
    if isinstance(schema, BoolByte):
        return bytes([0x00])
    if isinstance(schema, IntByte):
        return bytes([0x00])
    if isinstance(schema, ByteEnum):
        members = list(schema.enum_cls)
        return bytes([int(members[0])]) if members else bytes([0x00])
    if isinstance(schema, ScaledSigned):
        return bytes([0x00])
    if isinstance(schema, AsciiString):
        return b"Default"
    return bytes([0x00])


def _register_schema_args(parser):
    """Auto-register CLI arguments for all schema-driven setters on State."""
    stems = []
    for cc in CommandCodes:
        if cc.schema is None:
            continue
        stem = cc.name.lower()
        if not hasattr(State, f"set_{stem}"):
            continue
        kwargs = _schema_argparse_kwargs(cc.schema)
        if kwargs is None:
            continue
        flag = f"--{stem.replace('_', '-')}"
        parser.add_argument(flag, **kwargs)
        stems.append(stem)
    return stems


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

_SETTABLE_COMMANDS = _register_schema_args(parser_state)

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
            args.zone, CommandCodes(args.command), bytes(args.data)
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

        for stem in _SETTABLE_COMMANDS:
            value = getattr(args, stem, None)
            if value is not None:
                await getattr(state, f"set_{stem}")(value)

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

            for cc in CommandCodes:
                schema = cc.schema
                if schema is None:
                    continue
                inner = _inner_schema(schema)
                if isinstance(inner, StructFromBytes):
                    continue

                self._store[cc] = _schema_default_bytes(schema)

                if not (cc.flags & CommandFlags.WRITE_ONLY):
                    self.register_handler(
                        0x01, cc, bytes([0xF0]),
                        lambda cc=cc, **kw: self._store[cc],
                    )

                if hasattr(inner, "encode"):
                    if not (cc.flags & CommandFlags.READ_ONLY) or isinstance(
                        schema, Rc5Fallback
                    ):
                        self.register_handler(
                            0x01, cc, None,
                            lambda data, cc=cc, **kw: self._set(cc, data),
                        )

                if isinstance(schema, Rc5Fallback):
                    table = schema.rc5_table.get(rc5_key, {})
                    for value, code in table.items():
                        if isinstance(inner, ByteEnum):
                            encoded = bytes([int(value)])
                        elif isinstance(inner, BoolByte):
                            encoded = inner.encode(value)
                        else:
                            encoded = bytes([int(value)])
                        self._rc5_reverse[code] = (cc, encoded)

            # Overrides for realistic defaults
            self._store[CommandCodes.POWER] = bytes([0x01])
            self._store[CommandCodes.VOLUME] = bytes([10])

            # CURRENT_SOURCE — no schema, manual handlers
            self._store[CommandCodes.CURRENT_SOURCE] = SourceCodes.PVR.to_bytes(
                self._api_version, 1
            )
            self.register_handler(
                0x01, CommandCodes.CURRENT_SOURCE, bytes([0xF0]),
                lambda **kw: self._store[CommandCodes.CURRENT_SOURCE],
            )
            source_table = RC5CODE_SOURCE.get(rc5_key, {})
            for src, code in source_table.items():
                self._rc5_reverse[code] = (
                    CommandCodes.CURRENT_SOURCE,
                    src.to_bytes(self._api_version, 1),
                )

            # INCOMING_VIDEO_PARAMETERS — StructFromBytes needs real data
            self._store[CommandCodes.INCOMING_VIDEO_PARAMETERS] = VideoParameters(
                horizontal_resolution=1920,
                vertical_resolution=1080,
                refresh_rate=60,
                interlaced=False,
                aspect_ratio=IncomingVideoAspectRatio.ASPECT_16_9,
                colorspace=IncomingVideoColorspace.NORMAL,
            ).to_bytes()
            self.register_handler(
                0x01, CommandCodes.INCOMING_VIDEO_PARAMETERS, bytes([0xF0]),
                lambda **kw: self._store[CommandCodes.INCOMING_VIDEO_PARAMETERS],
            )

            # INCOMING_AUDIO_FORMAT — no schema
            self._store[CommandCodes.INCOMING_AUDIO_FORMAT] = bytes(
                [IncomingAudioFormat.PCM, IncomingAudioConfig.STEREO_ONLY]
            )
            self.register_handler(
                0x01, CommandCodes.INCOMING_AUDIO_FORMAT, bytes([0xF0]),
                lambda **kw: self._store[CommandCodes.INCOMING_AUDIO_FORMAT],
            )

            # INCOMING_AUDIO_SAMPLE_RATE — no schema
            self._store[CommandCodes.INCOMING_AUDIO_SAMPLE_RATE] = bytes([0x02])
            self.register_handler(
                0x01, CommandCodes.INCOMING_AUDIO_SAMPLE_RATE, bytes([0xF0]),
                lambda **kw: self._store[CommandCodes.INCOMING_AUDIO_SAMPLE_RATE],
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
                0x01, CommandCodes.PRESET_DETAIL, None, self._get_preset_detail,
            )

            # TUNER_PRESET — no schema
            self._store[CommandCodes.TUNER_PRESET] = b"\xff"
            self.register_handler(
                0x01, CommandCodes.TUNER_PRESET, bytes([0xF0]),
                lambda **kw: self._store[CommandCodes.TUNER_PRESET],
            )
            self.register_handler(
                0x01, CommandCodes.TUNER_PRESET, None,
                lambda data, **kw: self._set(CommandCodes.TUNER_PRESET, data),
            )

            # RC5 IR command handler (uses auto-built reverse table)
            self.register_handler(
                0x01, CommandCodes.SIMULATE_RC5_IR_COMMAND, None, self._ir_command,
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
                        cc=CommandCodes.SIMULATE_RC5_IR_COMMAND,
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
