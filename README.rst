********************************
Arcam IP Control
********************************
This module support controlling an arcam fmj received over it's network.
It's built mainly for use with home-assistant project, but should work
for other projects as well.

Status
______
.. image:: https://github.com/elupus/arcam_fmj/actions/workflows/python-package.yml/badge.svg
    :target: https://github.com/elupus/arcam_fmj/actions

Module
======

Code to set volume and source using library.

.. code-block:: python


    async def run():

        host = '192.168.0.2'
        port = '50000'
        zone = 1

        volume = 50
        source = SourceCodes.PVR

        client = Client(host, port)
        async with ClientContext(client):
            state = State(client, zone)

            await state.set_volume(volume)
            await state.set_source(source)

    loop = asyncio.get_event_loop()
    loop.run_until_complete (run())


Console
=======

The module contains a commandline utility to test and request data from
called ``arcam-fmj``.

Code to set volume and source using console.

.. code-block:: bash


    arcam-fmj state --host 192.168.0.2 --port 50000 --source 5 --volume 50
