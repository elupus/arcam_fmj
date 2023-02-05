import logging

import pytest
from unittest.mock import MagicMock

from src.arcam.fmj.client import Client
from src.arcam.fmj.state import State
from src.arcam.fmj import (
  SourceCodes,
  ApiModel,
  AnswerCodes,
  CommandCodes,
  ResponsePacket,
  SOURCE_CODES,
  SOURCE_WRITE_SUPPORTED,
  RC5CODE_SOURCE,
)

NO_SOURCE = {ApiModel.APIPA_SERIES}

TEST_PARAMS = [
    (1, ApiModel.API450_SERIES),
    (1, ApiModel.API860_SERIES),
    (1, ApiModel.APIHDA_SERIES),
    (1, ApiModel.APISA_SERIES),
    (1, ApiModel.APIPA_SERIES),
    (2, ApiModel.API450_SERIES),
    (2, ApiModel.API860_SERIES),
    (2, ApiModel.APIHDA_SERIES),
    (2, ApiModel.APISA_SERIES),
    (2, ApiModel.APIPA_SERIES),
]

@pytest.mark.parametrize("zn, api_model", TEST_PARAMS)
async def test_get_source(zn, api_model):
  client = MagicMock(spec=Client)
  state = State(client, zn, api_model)
  source = SourceCodes.AUX
  state._state[CommandCodes.CURRENT_SOURCE] = source

  source_not_supported = api_model in NO_SOURCE
  if source_not_supported:
    result = state.get_source()
    assert result == None
  else:
    expected_source = SOURCE_CODES.get((api_model, zn))[source]
    expected_source_as_int = int.from_bytes(expected_source, 'big')
    result = state.get_source()
    assert result == expected_source_as_int
  

@pytest.mark.parametrize("zn, api_model", TEST_PARAMS)
async def test_set_source(zn, api_model):
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)
    state._api_model = api_model
    source = SourceCodes.AUX

    command_code = CommandCodes.SIMULATE_RC5_IR_COMMAND

    raises_exception = api_model in NO_SOURCE
    if raises_exception:
      with pytest.raises(ValueError):
        code = state.get_rc5code(RC5CODE_SOURCE, source)
        return
    else:
      if api_model in SOURCE_WRITE_SUPPORTED:
        command_code = CommandCodes.CURRENT_SOURCE 
        code = SOURCE_CODES.get((api_model, zn))[source]
      else:
        code = state.get_rc5code(RC5CODE_SOURCE, source)

      response = ResponsePacket(
          zn,
          command_code,
          AnswerCodes.STATUS_UPDATE,
          bytes([0x01]),
      )
      client.request.return_value = response

      await state.set_source(source)
      client.request.assert_called_with(
              zn, command_code, code
          )
