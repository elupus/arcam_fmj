import logging

import pytest
from unittest.mock import MagicMock

from arcam.fmj.client import Client
from arcam.fmj.state import State
from arcam.fmj import (
  SourceCodes,
  ApiModel,
  AnswerCodes,
  CommandCodes,
  ResponsePacket,
)

@pytest.mark.parametrize("zn, api_model, source, data", [
    (1, ApiModel.API450_SERIES, SourceCodes.AUX, bytes([0x08])),
    (1, ApiModel.API860_SERIES, SourceCodes.AUX, bytes([0x08])),
    (1, ApiModel.APIHDA_SERIES, SourceCodes.AUX, bytes([0x08])),
    (1, ApiModel.APIHDA_SERIES, SourceCodes.UHD, bytes([0x06])),
    (1, ApiModel.APISA_SERIES, SourceCodes.AUX, bytes([0x02])),
    (1, ApiModel.APIST_SERIES, SourceCodes.DIG1, bytes([0x01])),
    (1, ApiModel.APIPA_SERIES, None, bytes([0x02])),
    (2, ApiModel.API450_SERIES, SourceCodes.AUX, bytes([0x08])),
    (2, ApiModel.API860_SERIES, SourceCodes.AUX, bytes([0x08])),
    (2, ApiModel.APIHDA_SERIES, SourceCodes.AUX, bytes([0x08])),
    (2, ApiModel.APIHDA_SERIES, SourceCodes.UHD, bytes([0x06])),
    (2, ApiModel.APISA_SERIES, SourceCodes.AUX, bytes([0x02])),
    (2, ApiModel.APIPA_SERIES, None, bytes([0x02])),
    (2, ApiModel.APIST_SERIES, None, bytes([0x01])),
])
async def test_get_source(zn, api_model, source, data):
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)
    state._state[CommandCodes.CURRENT_SOURCE] = data

    assert state.get_source() == source

@pytest.mark.parametrize("zn, api_model, source, ir, data", [
    (1, ApiModel.API450_SERIES, SourceCodes.AUX, True, bytes([16, 8])),
    (1, ApiModel.API860_SERIES, SourceCodes.AUX, True, bytes([16, 99])),
    (1, ApiModel.APIHDA_SERIES, SourceCodes.AUX, True, bytes([16, 99])),
    (1, ApiModel.APIHDA_SERIES, SourceCodes.UHD, True, bytes([16, 125])),
    (1, ApiModel.APISA_SERIES, SourceCodes.AUX, False, bytes([0x02])),
    (2, ApiModel.API450_SERIES, SourceCodes.AUX, True, bytes([23, 13])),
    (2, ApiModel.API860_SERIES, SourceCodes.AUX, True, bytes([23, 13])),
    (2, ApiModel.APIHDA_SERIES, SourceCodes.AUX, True, bytes([23, 13])),
    (2, ApiModel.APIHDA_SERIES, SourceCodes.UHD, True, bytes([23, 23])),
    (2, ApiModel.APISA_SERIES, SourceCodes.AUX, False, bytes([0x02])),
])
async def test_set_source(zn, api_model, source, ir, data):
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)

    if ir:
        command_code = CommandCodes.SIMULATE_RC5_IR_COMMAND
    else:
        command_code = CommandCodes.CURRENT_SOURCE

    client.request.return_value = ResponsePacket(
        zn,
        command_code,
        AnswerCodes.STATUS_UPDATE,
        bytes([0x01]),
    )

    await state.set_source(source)

    client.request.assert_called_with(
            zn, command_code, data
        )


@pytest.mark.parametrize("zn, api_model, source", [
    (1, ApiModel.APIPA_SERIES, SourceCodes.AUX),
    (2, ApiModel.APIPA_SERIES, SourceCodes.AUX),
])
async def test_set_source_invalid(zn, api_model, source):
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)

    with pytest.raises(ValueError):
        await state.set_source(source)
