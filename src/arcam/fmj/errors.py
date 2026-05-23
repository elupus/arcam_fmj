"""Exception classes for the arcam_fmj library."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .codecs import AnswerCodes

if TYPE_CHECKING:
    from .packets import ResponsePacket

class ArcamException(Exception):
    pass

class ConnectionFailed(ArcamException):
    pass

class NotConnectedException(ArcamException):
    pass

class UnsupportedZone(ArcamException):
    pass

class UnsupportedCommand(ArcamException):
    def __init__(self, cc=None, model=None):
        self.cc = cc
        self.model = model
        super().__init__(f"Command {cc} not supported on {model}")

class ResponseException(ArcamException):
    def __init__(self, ac=None, zn=None, cc=None, data=None):
        self.ac = ac
        self.zn = zn
        self.cc = cc
        self.data = data
        super().__init__(f"'ac':{ac}, 'zn':{zn}, 'cc':{cc}, 'data':{data}")

    @staticmethod
    def from_response(response: "ResponsePacket"):
        kwargs = {"zn": response.zn, "cc": response.cc, "data": response.data}
        if response.ac == AnswerCodes.ZONE_INVALID:
            return InvalidZoneException(**kwargs)
        elif response.ac == AnswerCodes.COMMAND_NOT_RECOGNISED:
            return CommandNotRecognised(**kwargs)
        elif response.ac == AnswerCodes.PARAMETER_NOT_RECOGNISED:
            return ParameterNotRecognised(**kwargs)
        elif response.ac == AnswerCodes.COMMAND_INVALID_AT_THIS_TIME:
            return CommandInvalidAtThisTime(**kwargs)
        elif response.ac == AnswerCodes.INVALID_DATA_LENGTH:
            return InvalidDataLength(**kwargs)
        else:
            return ResponseException(ac=response.ac, **kwargs)

class InvalidZoneException(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.ZONE_INVALID, zn=zn, cc=cc, data=data)

class CommandNotRecognised(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.COMMAND_NOT_RECOGNISED, zn=zn, cc=cc, data=data)

class ParameterNotRecognised(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(
            ac=AnswerCodes.PARAMETER_NOT_RECOGNISED, zn=zn, cc=cc, data=data
        )

class CommandInvalidAtThisTime(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(
            ac=AnswerCodes.COMMAND_INVALID_AT_THIS_TIME, zn=zn, cc=cc, data=data
        )

class InvalidDataLength(ResponseException):
    def __init__(self, zn=None, cc=None, data=None):
        super().__init__(ac=AnswerCodes.INVALID_DATA_LENGTH, zn=zn, cc=cc, data=data)

class InvalidPacket(ArcamException):
    pass

class NullPacket(ArcamException):
    pass
