import argparse
import asyncio
import logging
import sys

from . import (
    APIVERSION_450_SERIES,
    APIVERSION_860_SERIES,
    APIVERSION_LEXICON_SERIES,
    APIVERSION_HDA_SERIES,
    ApiModel,
    CommandCodes,
    CommandInvalidAtThisTime,
    SourceCodes,
    IncomingVideoAspectRatio,
    IncomingVideoColorspace,
    IncomingAudioFormat,
    IncomingAudioConfig,
    DecodeMode2CH,
    DecodeModeMCH,
    CommandNotRecognised,
    _LOGGER,
    VideoParameters,
    ResponsePacket,
    AnswerCodes,
    RC5CODE_SOURCE,
    RC5CODE_DECODE_MODE_2CH,
    RC5CODE_DECODE_MODE_MCH,
)
from .client import Client, ClientContext
from .server import Server, ServerContext
from .state import State

# pylint: disable=invalid-name


def auto_int(x):
    return int(x, 0)


def auto_bytes(x):
    print(x)
    return bytes.decode(x)


def auto_source(x):
    return SourceCodes[x]


parser = argparse.ArgumentParser(description="Communicate with arcam receivers.")
parser.add_argument("--verbose", action="store_true")

subparsers = parser.add_subparsers(dest="subcommand")

parser_state = subparsers.add_parser("state")
parser_state.add_argument("--host", required=True)
parser_state.add_argument("--port", default=50000)
parser_state.add_argument("--zone", default=1, type=int)
parser_state.add_argument("--volume", type=int)
parser_state.add_argument("--source", type=auto_source)
parser_state.add_argument("--monitor", action="store_true")
parser_state.add_argument("--power-on", action=argparse.BooleanOptionalAction)
parser_state.add_argument("--power-off", action=argparse.BooleanOptionalAction)
parser_state.add_argument("--dirac-on", action=argparse.BooleanOptionalAction)
parser_state.add_argument("--dirac-off", action=argparse.BooleanOptionalAction)
parser_state.add_argument("--lipsync", type=int, help="Set lip sync delay in ms")
parser_state.add_argument(
    "--subwoofer-trim",
    type=float,
    help="Set subwoofer trim in dB (-12 to +12)",
)
parser_state.add_argument(
    "--show-audio",
    action="store_true",
    help="Show audio-related fields (format, sample rate, decode, Dirac, lipsync, subwoofer)",
)
parser_state.add_argument(
    "--input-name",
    action="store_true",
    help="Query the user-configured input name",
)

parser_client = subparsers.add_parser("client")
parser_client.add_argument("--host", required=True)
parser_client.add_argument("--port", default=50000)
parser_client.add_argument("--zone", default=1, type=int)
parser_client.add_argument("--command", type=auto_int, required=True)
parser_client.add_argument("--data", nargs="+", default=[0xF0], type=auto_int)

parser_server = subparsers.add_parser("server")
parser_server.add_argument("--host", default="localhost")
parser_server.add_argument("--port", default=50000)
parser_server.add_argument("--model", default="AVR450")


async def run_client(args):
    client = Client(args.host, args.port)
    async with ClientContext(client):
        result = await client.request(
            args.zone, CommandCodes(args.command), bytes(args.data)
        )
        print(result)


async def run_state(args):
    client = Client(args.host, args.port)
    async with ClientContext(client):
        state = State(client, args.zone)
        await state.update()

        if args.volume is not None:
            await state.set_volume(args.volume)

        if args.source is not None:
            await state.set_source(args.source)

        if args.power_on is not None:
            await state.set_power(True)

        if args.power_off is not None:
            await state.set_power(False)

        if args.dirac_on is not None:
            await state.set_room_equalization(True)

        if args.dirac_off is not None:
            await state.set_room_equalization(False)

        if args.lipsync is not None:
            await state.set_lipsync_delay(args.lipsync)

        if args.subwoofer_trim is not None:
            await state.set_subwoofer_trim(args.subwoofer_trim)

        if args.monitor:
            async with state:
                prev = repr(state)
                while client.connected:
                    curr = repr(state)
                    if prev != curr:
                        print(curr)
                        prev = curr
                    await asyncio.sleep(delay=1)
        else:
            # Avoid printing full state if actions already printed output
            did_action = any(
                [
                    args.volume is not None,
                    args.source is not None,
                    args.power_on is not None,
                    args.power_off is not None,
                    args.dirac_on is not None,
                    args.dirac_off is not None,
                    args.lipsync is not None,
                    args.subwoofer_trim is not None,
                    args.show_audio,
                    args.input_name,
                ]
            )
            if args.show_audio or args.input_name:
                info = {}
                if args.show_audio:
                    fmt, cfg = state.get_incoming_audio_format()
                    dec = state.get_decode_mode()
                    src = state.get_source()
                    info.update({
                        "audio_format": fmt.name if fmt is not None else None,
                        "audio_config": cfg.name if cfg is not None else None,
                        "sample_rate": state.get_incoming_audio_sample_rate(),
                        "decode_mode": dec.name if dec is not None else None,
                        "source": src.name if src is not None else None,
                        "dirac_enabled": state.get_room_equalization(),
                        "lipsync_ms": state.get_lipsync_delay(),
                        "subwoofer_trim_db": state.get_subwoofer_trim(),
                    })
                if args.input_name:
                    input_name = await state.get_input_name()
                    info["input_name"] = input_name
                print(info)
            elif not did_action:
                print(state)


async def run_server(args):
    class DummyServer(Server):
        def __init__(self, host, port, model):
            super().__init__(host, port, model)

            if model in APIVERSION_450_SERIES:
                self._api_version = ApiModel.API450_SERIES
            elif model in APIVERSION_LEXICON_SERIES:
                self._api_version = ApiModel.APILEXICON_SERIES
            elif model in APIVERSION_860_SERIES:
                self._api_version = ApiModel.API860_SERIES
            elif model in APIVERSION_HDA_SERIES:
                self._api_version = ApiModel.APIHDA_SERIES
            else:
                raise ValueError("Unexpected model")

            rc5_key = (self._api_version, 1)

            self._volume = bytes([10])
            self._source = SourceCodes.PVR.to_bytes(self._api_version, 1)
            self._video_parameters = VideoParameters(
                horizontal_resolution=1920,
                vertical_resolution=1080,
                refresh_rate=60,
                interlaced=False,
                aspect_ratio=IncomingVideoAspectRatio.ASPECT_16_9,
                colorspace=IncomingVideoColorspace.NORMAL,
            )
            self._audio_format = bytes(
                [IncomingAudioFormat.PCM, IncomingAudioConfig.STEREO_ONLY]
            )
            self._audio_sample_rate = 48000
            self._decode_mode_2ch = next(
                iter(RC5CODE_DECODE_MODE_2CH[rc5_key].values())
            )
            self._decode_mode_mch = next(
                iter(RC5CODE_DECODE_MODE_MCH[rc5_key].values())
            )
            self._tuner_preset = b"\0xff"
            self._presets = {
                b"\x01": b"\x03SR P1   ",
                b"\x02": b"\x03SR Klass",
                b"\x03": b"\x03P3 Star ",
                b"\x04": b"\x02SR P4   ",
                b"\x05": b"\x02SR P4   ",
                b"\x06": b"\x01jP",
            }

            def invert_rc5(data):
                return {value: key for key, value in data[rc5_key].items()}

            self._source_rc5 = invert_rc5(RC5CODE_SOURCE)
            self._decode_mode_2ch_rc5 = invert_rc5(RC5CODE_DECODE_MODE_2CH)
            self._decode_mode_mch_rc5 = invert_rc5(RC5CODE_DECODE_MODE_MCH)

            self.register_handler(
                0x01, CommandCodes.POWER, bytes([0xF0]), self.get_power
            )
            self.register_handler(
                0x01, CommandCodes.VOLUME, bytes([0xF0]), self.get_volume
            )
            self.register_handler(0x01, CommandCodes.VOLUME, None, self.set_volume)
            self.register_handler(
                0x01, CommandCodes.CURRENT_SOURCE, bytes([0xF0]), self.get_source
            )
            self.register_handler(
                0x01,
                CommandCodes.INCOMING_VIDEO_PARAMETERS,
                bytes([0xF0]),
                self.get_incoming_video_parameters,
            )
            self.register_handler(
                0x01,
                CommandCodes.INCOMING_AUDIO_FORMAT,
                bytes([0xF0]),
                self.get_incoming_audio_format,
            )
            self.register_handler(
                0x01,
                CommandCodes.INCOMING_AUDIO_SAMPLE_RATE,
                bytes([0xF0]),
                self.get_incoming_audio_sample_rate,
            )
            self.register_handler(
                0x01,
                CommandCodes.DECODE_MODE_STATUS_2CH,
                bytes([0xF0]),
                self.get_decode_mode_2ch,
            )
            self.register_handler(
                0x01,
                CommandCodes.DECODE_MODE_STATUS_MCH,
                bytes([0xF0]),
                self.get_decode_mode_mch,
            )
            self.register_handler(
                0x01, CommandCodes.SIMULATE_RC5_IR_COMMAND, None, self.ir_command
            )
            self.register_handler(
                0x01, CommandCodes.PRESET_DETAIL, None, self.get_preset_detail
            )
            self.register_handler(
                0x01, CommandCodes.TUNER_PRESET, bytes([0xF0]), self.get_tuner_preset
            )
            self.register_handler(
                0x01, CommandCodes.TUNER_PRESET, None, self.set_tuner_preset
            )

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
            status = None

            source = self._source_rc5.get(data)
            if source:
                self.set_source(bytes([source]))
                return [
                    ResponsePacket(
                        zn=0x01,
                        cc=CommandCodes.SIMULATE_RC5_IR_COMMAND,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=data,
                    ),
                    ResponsePacket(
                        zn=0x01,
                        cc=CommandCodes.CURRENT_SOURCE,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=bytes([source]),
                    ),
                ]
            decode_mode_2ch = self._decode_mode_2ch_rc5.get(data)
            if decode_mode_2ch:
                self._decode_mode_2ch = bytes([decode_mode_2ch])
                return [
                    ResponsePacket(
                        zn=0x01,
                        cc=CommandCodes.SIMULATE_RC5_IR_COMMAND,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=data,
                    ),
                    ResponsePacket(
                        zn=0x01,
                        cc=CommandCodes.DECODE_MODE_STATUS_2CH,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=self._decode_mode_2ch,
                    ),
                ]

            decode_mode_mch = self._decode_mode_mch_rc5.get(data)
            if decode_mode_mch:
                self._decode_mode_mch = bytes([decode_mode_mch])
                return [
                    ResponsePacket(
                        zn=0x01,
                        cc=CommandCodes.SIMULATE_RC5_IR_COMMAND,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=data,
                    ),
                    ResponsePacket(
                        zn=0x01,
                        cc=CommandCodes.DECODE_MODE_STATUS_MCH,
                        ac=AnswerCodes.STATUS_UPDATE,
                        data=self._decode_mode_mch,
                    ),
                ]

            raise CommandNotRecognised()

        def get_decode_mode_2ch(self, **kwargs):
            return self._decode_mode_2ch

        def get_decode_mode_mch(self, **kwargs):
            return self._decode_mode_mch

        def get_incoming_video_parameters(self, **kwargs):
            return self._video_parameters

        def get_incoming_audio_format(self, **kwargs):
            return self._audio_format

        def get_incoming_audio_sample_rate(self, **kwargs):
            return self._audio_sample_rate

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

    server = DummyServer(args.host, args.port, args.model)
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


if __name__ == "__main__":
    main()
