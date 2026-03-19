********************************
Arcam IP Control
********************************
This module supports controlling an Arcam FMJ receiver (as well as JBL and AudioControl processors) over the network.
It's built mainly for use with the Home Assistant project, but should work for other projects as well.

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


Protocol Specifications
=======================

- `AVR5/AVR10/AVR20/AVR30/AV40/AVR11/AVR21/AVR31/AV41 <https://www.arcam.co.uk/ugc/tor/AVR11/Custom%20Installation%20Notes/RS232_5_10_20_30_40_11_21_31_41__SH289E_F_07Oct21.pdf>`_
- `AV860/AVR850/AVR550/AVR390/SR250 <https://www.arcam.co.uk/ugc/tor/avr390/RS232/RS232_860_850_550_390_250_SH274E_D_181018.pdf>`_
- `SA10/SA20 <https://www.arcam.co.uk/ugc/tor/SA20/Custom%20Installation%20Notes/SH277E_RS232_SA10_SA20_B.pdf>`_
- `PA720/PA240/PA410 <https://www.arcam.co.uk/ugc/tor/PA240/Custom%20Installation%20Notes/RS232_PA720_PA240_PA410_SH305E_3.pdf>`_
