import argparse
import asyncio
import logging
import sys

import arcam_av

parser = argparse.ArgumentParser(description='Communicate with arcam receivers.')
parser.add_argument('--host', required=True)
parser.add_argument('--port', default=50000)
parser.add_argument('--verbose', action='store_true')

async def run(args):
    async with await arcam_av.Client.connect(args.host, args.port) as client:
        pass

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
