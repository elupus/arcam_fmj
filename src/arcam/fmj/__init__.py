"""Arcam AV Control.

Submodule layout:
- ``_models``   — API version sets, ApiModel, IntOrTypeEnum base
- ``_errors``   — Exception classes
- ``_codecs``   — Codec enums and dataclasses (SourceCodes, DecodeMode*, etc.)
- ``_rc5``      — RC5 control-code tables and parameter enums
- ``_commands`` — CommandCodes enum (the command catalogue)
- ``_packets``  — Wire-protocol packet types and async serialization helpers

This module re-exports the public API for backward compatibility — callers
can keep importing from ``arcam.fmj`` directly.
"""

import logging

from ._models import *  # noqa: F401,F403
from ._codecs import *  # noqa: F401,F403
from ._errors import *  # noqa: F401,F403
from ._rc5 import *  # noqa: F401,F403
from ._commands import *  # noqa: F401,F403
from ._packets import *  # noqa: F401,F403

# Private packet-reader helpers used by tests.
from ._packets import _read_command, _read_delimited, _read_response  # noqa: F401

_LOGGER = logging.getLogger(__name__)
