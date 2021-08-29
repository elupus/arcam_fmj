import pytest
from unittest.mock import MagicMock
from arcam.fmj.client import Client
from arcam.fmj.state import State
from arcam.fmj import AnswerCodes, ApiModel, CommandCodes, ResponsePacket

TEST_PARAMS = [
    (1, ApiModel.API450_SERIES, True),
    (1, ApiModel.API450_SERIES, False),
    (1, ApiModel.API860_SERIES, True),
    (1, ApiModel.API860_SERIES, False),
    (1, ApiModel.APISA_SERIES, True),
    (1, ApiModel.APISA_SERIES, False),
    (2, ApiModel.API450_SERIES, True),
    (2, ApiModel.API450_SERIES, False),
    (2, ApiModel.API860_SERIES, True),
    (2, ApiModel.API860_SERIES, False),
    (2, ApiModel.APISA_SERIES, True),
    (2, ApiModel.APISA_SERIES, False)
]

# zn, api_model, power
PARAMS_TO_RC5COMMAND = {
    (1, ApiModel.API450_SERIES, True): bytes([16, 123]),
    (1, ApiModel.API450_SERIES, False): bytes([16, 124]),
    (1, ApiModel.API860_SERIES, True): bytes([16, 123]),
    (1, ApiModel.API860_SERIES, False): bytes([16, 124]),
    (1, ApiModel.APISA_SERIES, True): bytes([16, 123]),
    (1, ApiModel.APISA_SERIES, False): bytes([16, 124]),
    (2, ApiModel.API450_SERIES, True): bytes([23, 123]),
    (2, ApiModel.API450_SERIES, False): bytes([23, 124]),
    (2, ApiModel.API860_SERIES, True): bytes([23, 123]),
    (2, ApiModel.API860_SERIES, False): bytes([23, 124]),
    (2, ApiModel.APISA_SERIES, True): bytes([16, 123]),
    (2, ApiModel.APISA_SERIES, False): bytes([16, 124])
}

@pytest.mark.parametrize("zn, api_model, use_rc5", TEST_PARAMS)
async def test_power_on(zn, api_model, use_rc5):
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)
    response = ResponsePacket(
        zn,
        CommandCodes.SIMULATE_RC5_IR_COMMAND,
        AnswerCodes.STATUS_UPDATE,
        bytes([0x01]),
    )
    client.request.return_value = response
    if not use_rc5:
        if api_model != ApiModel.APISA_SERIES:
            with pytest.raises(ValueError):
                await state.set_power(True, use_rc5)
        else:
            await state.set_power(True, use_rc5)
            client.request.assert_called_with(
                zn, CommandCodes.POWER, bytes([0x01])
            )
    else:
        await state.set_power(True, use_rc5)
        # zn, api_model, power
        code = PARAMS_TO_RC5COMMAND[zn, api_model, True]
        client.request.assert_called_with(
            zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, code
        )


@pytest.mark.parametrize("zn, api_model, use_rc5", TEST_PARAMS)
async def test_power_off(zn, api_model, use_rc5):
    client = MagicMock(spec=Client)
    state = State(client, zn, api_model)

    assert state.get_power() is None
    if not use_rc5:
        if api_model != ApiModel.APISA_SERIES:
            with pytest.raises(ValueError):
                await state.set_power(False, use_rc5)
        else:
            await state.set_power(False, use_rc5)
            client.send.assert_called_with(
                zn, CommandCodes.POWER, bytes([0x00])
            )
            assert state.get_power() == False
    else:
        await state.set_power(False, use_rc5)
        # zn, api_model, power
        code = PARAMS_TO_RC5COMMAND[zn, api_model, False]
        client.send.assert_called_with(
            zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, code
        )
        assert state.get_power() == False
