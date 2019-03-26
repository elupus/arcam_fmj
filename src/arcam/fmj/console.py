import argparse
import asyncio
import logging
import sys

from .client import Client
from .state import State

parser = argparse.ArgumentParser(description='Communicate with arcam receivers.')
parser.add_argument('--host', required=True)
parser.add_argument('--port', default=50000)
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--zone', default=1, type=int)
parser.add_argument('--volume', type=int)
parser.add_argument('--source', type=int)
parser.add_argument('--state', action='store_true')
parser.add_argument('--monitor', action='store_true')

async def run(args):
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
    loop.run_until_complete (run(args))
