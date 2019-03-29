import argparse
import asyncio
import logging
import sys

from .server import Server
from .client import Client
from .state import State
from . import CommandCodes, AnswerCodes

parser = argparse.ArgumentParser(description='Communicate with arcam receivers.')
parser.add_argument('--verbose', action='store_true')

subparsers = parser.add_subparsers(dest="command")

parser_client = subparsers.add_parser('client')
parser_client.add_argument('--host', required=True)
parser_client.add_argument('--port', default=50000)
parser_client.add_argument('--zone', default=1, type=int)
parser_client.add_argument('--volume', type=int)
parser_client.add_argument('--source', type=int)
parser_client.add_argument('--state', action='store_true')
parser_client.add_argument('--monitor', action='store_true')

parser_server = subparsers.add_parser('server')
parser_server.add_argument('--host', default='localhost')
parser_server.add_argument('--port', default=50000)


async def run_client(args):
    async with Client(args.host, args.port) as client:
        state = State(client, args.zone)

        if args.volume is not None:
            await state.set_volume(args.volume)

        if args.source is not None:
            await state.set_source(args.source)

        if args.state:
            await state.update()
            print(state)
 
        if args.monitor:
            async with state:
                prev = repr(state)
                await state.update()
                while True:
                    curr = repr(state)
                    if prev != curr:
                        print(curr)
                        prev = curr
                    await asyncio.sleep(delay=1)

async def run_server(args):
    async with Server(args.host, args.port) as server:
        server.register_handler(0x01, CommandCodes.POWER, bytes([0xF0]),
            lambda **kwargs: (AnswerCodes.STATUS_UPDATE, bytes([0x00]))
        )
        server.register_handler(0x01, CommandCodes.VOLUME, bytes([0xF0]),
            lambda **kwargs: (AnswerCodes.STATUS_UPDATE, bytes([0x10]))
        )

        while True:
            await asyncio.sleep(delay=1)

def main():

    args = parser.parse_args()

    if args.verbose:
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        root.addHandler(ch)


    loop = asyncio.get_event_loop()

    if args.command == 'client':
        loop.run_until_complete (run_client(args))
    elif args.command == 'server':
        loop.run_until_complete (run_server(args))
