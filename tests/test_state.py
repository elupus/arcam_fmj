import pytest
from unittest.mock import MagicMock
from arcam.fmj.client import Client
from arcam.fmj.state import State
from arcam.fmj import AnswerCodes, CommandCodes, RC5Codes, ResponsePacket


@pytest.mark.parametrize("zn", [0, 1])
async def test_power_on(zn):
    client = MagicMock(spec=Client)
    state = State(client, zn)
    response = ResponsePacket(
        zn,
        CommandCodes.SIMULATE_RC5_IR_COMMAND,
        AnswerCodes.STATUS_UPDATE,
        bytes([0x01]),
    )
    client.request.return_value = response

    await state.set_power(True)
    if zn == 1:
        code = RC5Codes.POWER_ON
    else:
        code = RC5Codes.POWER_ON_ZONE2

    client.request.assert_called_with(
        zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, code.value
    )


@pytest.mark.parametrize("zn", [0, 1])
async def test_power_off(zn):
    client = MagicMock(spec=Client)
    state = State(client, zn)

    assert state.get_power() is None
    await state.set_power(False)
    if zn == 1:
        code = RC5Codes.POWER_OFF
    else:
        code = RC5Codes.POWER_OFF_ZONE2

    client.send.assert_called_with(
        zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, code.value
    )
    assert state.get_power() == False
