"""Manages cached zone state and translates high-level operations into protocol requests."""

import asyncio
import logging
from typing import Any, TypeVar

import attr

from .codecs import (
    AnswerCodes,
    AutoShutdown,
    BluetoothAudioStatus,
    CompressionMode,
    DacFilter,
    DecodeMode2CH,
    DecodeModeMCH,
    DisplayBrightness,
    DolbyAudioMode,
    HdmiOutput,
    IMAX_ENHANCED_SET_MAP,
    ImaxEnhancedMode,
    IncomingAudioConfig,
    IncomingAudioFormat,
    MenuCodes,
    NetworkPlaybackStatus,
    NowPlayingInfo,
    PresetDetail,
    RoomEqMode,
    SAMPLE_RATE_MAP,
    SAVE_RESTORE_CONFIRMATION,
    SaveRestoreSubCommand,
    SourceCodes,
    VideoFilmMode,
    VideoNoiseReduction,
    VideoParameters,
    VideoSelection,
    ZoneOsd,
)
from .commands import (
    CommandCodes,
    CommandFlags,
    MUTE_WRITE_SUPPORTED,
    POWER_WRITE_SUPPORTED,
    SOURCE_WRITE_SUPPORTED,
    VOLUME_STEP_SUPPORTED,
)
from .errors import (
    CommandInvalidAtThisTime,
    CommandNotRecognised,
    NotConnectedException,
    ParameterNotRecognised,
    ResponseException,
    UnsupportedCommand,
    UnsupportedZone,
)
from .models import (
    APIVERSION_RC5_NUMERIC_SERIES,
    ApiModel,
    api_model_for,
)
from .packets import (
    AmxDuetRequest,
    AmxDuetResponse,
    ResponsePacket,
)
from .rc5 import (
    RC5CODE_BALANCE,
    RC5CODE_BASS,
    RC5CODE_COLOR,
    RC5CODE_DECODE_MODE_2CH,
    RC5CODE_DECODE_MODE_MCH,
    RC5CODE_DIRECT_MODE,
    RC5CODE_DISPLAY_BRIGHTNESS,
    RC5CODE_DOLBY_PLIIX_CENTRE_WIDTH,
    RC5CODE_DOLBY_PLIIX_DIMENSION,
    RC5CODE_DOLBY_PLIIX_PANORAMA,
    RC5CODE_HDMI_OUTPUT,
    RC5CODE_LIPSYNC,
    RC5CODE_MENU_ACCESS,
    RC5CODE_MUTE,
    RC5CODE_NAVIGATION,
    RC5CODE_PLAYBACK,
    RC5CODE_POWER,
    RC5CODE_SOURCE,
    RC5CODE_SUB_TRIM,
    RC5CODE_TOGGLE,
    RC5CODE_TREBLE,
    RC5CODE_VOLUME,
    RC5CodeColor,
    RC5CodeMenuAccess,
    RC5CodeNavigation,
    RC5CodePlayback,
    RC5CodeToggle,
)
from .schemas import IncDecRc5, Rc5Fallback
from .schemas import _get_scaled_negative, _set_scaled  # re-exported for tests
from .client import Client, UpdateTask, _UPDATE_PRIORITY
from .utils import run_tasks, wait_any


def _schema_types(schema) -> tuple[str | None, str | None]:
    """Return ``(value_type_name, return_type_name)`` for a schema."""
    ret_name = getattr(schema, "type_name", None)
    inner = schema.inner if isinstance(schema, Rc5Fallback) else schema
    val_name = ret_name if hasattr(inner, "encode") else None
    return val_name, ret_name


def add_accessors(cls: type) -> type:
    """Install auto-generated get/set/inc/dec methods from ``CommandCodes`` metadata.

    Method names are derived from ``cc.name.lower()``.  Manual methods
    already on the class win -- the decorator never replaces an existing
    attribute.  After installing methods, it collects the list of sync,
    no-arg getters into ``_to_dict_getters`` for :meth:`State.to_dict`.
    """
    for cc in CommandCodes:
        schema = cc.schema
        if schema is None:
            continue
        stem = cc.name.lower()

        getter_name = f"get_{stem}"
        if (
            getter_name not in cls.__dict__
            and not (cc.flags & CommandFlags.WRITE_ONLY)
            and hasattr(schema, "decode")
        ):
            setattr(cls, getter_name, _make_getter(cc, schema))

        setter_name = f"set_{stem}"
        if setter_name not in cls.__dict__:
            if isinstance(schema, Rc5Fallback):
                setattr(cls, setter_name, _make_rc5_fallback_setter(cc, schema))
            elif hasattr(schema, "encode") and not (cc.flags & CommandFlags.READ_ONLY):
                setattr(cls, setter_name, _make_setter(cc, schema))

        if schema.inc_dec is not None:
            inc_name = f"inc_{stem}"
            if inc_name not in cls.__dict__:
                setattr(cls, inc_name, _make_inc_dec(cc, schema.inc_dec, increment=True))
            dec_name = f"dec_{stem}"
            if dec_name not in cls.__dict__:
                setattr(cls, dec_name, _make_inc_dec(cc, schema.inc_dec, increment=False))

    getters = []
    for name in sorted(cls.__dict__):
        if not name.startswith("get_"):
            continue
        method = cls.__dict__[name]
        if isinstance(method, property) or not callable(method):
            continue
        if asyncio.iscoroutinefunction(method):
            continue
        if method.__code__.co_argcount != 1:
            continue
        getters.append(name)
    cls._to_dict_getters = tuple(getters)

    return cls


def _make_getter(cc, schema):
    """Create a sync getter that decodes ``_state[cc]``."""
    _, ret_name = _schema_types(schema)

    def getter(self):
        if not self._is_command_supported_on_source(cc):
            return None
        data = self._state.get(cc)
        if data is None:
            return None
        return schema.decode(data)

    getter.__name__ = f"get_{cc.name.lower()}"
    getter.__qualname__ = f"State.{getter.__name__}"
    if ret_name:
        getter.__annotations__ = {"return": f"{ret_name} | None"}
    return getter


def _make_setter(cc, schema):
    """Create an async setter that encodes and sends a direct CC write."""
    val_name, _ = _schema_types(schema)

    async def setter(self, value):
        if not self._is_command_supported_on_source(cc):
            return
        await self._request(self._zn, cc, schema.encode(value))

    setter.__name__ = f"set_{cc.name.lower()}"
    setter.__qualname__ = f"State.{setter.__name__}"
    if val_name:
        setter.__annotations__ = {"value": val_name, "return": None}
    return setter


def _make_rc5_fallback_setter(cc, schema: Rc5Fallback):
    """Create an async setter that uses direct CC write when supported, RC5 otherwise."""
    val_name, _ = _schema_types(schema)

    async def setter(self, value):
        if not self._is_command_supported_on_source(cc):
            return
        if self._api_model in schema.direct_set_supported:
            await self._request(self._zn, cc, schema.inner.encode(value))
        else:
            await self._send_rc5(schema.rc5_table, value)

    setter.__name__ = f"set_{cc.name.lower()}"
    setter.__qualname__ = f"State.{setter.__name__}"
    if val_name:
        setter.__annotations__ = {"value": val_name, "return": None}
    return setter


def _make_inc_dec(cc, schema: IncDecRc5, increment: bool):
    """Create an async increment or decrement stepper."""
    direct_data = schema.inc_data if increment else schema.dec_data

    async def stepper(self):
        if not self._is_command_supported_on_source(cc):
            return
        if self._api_model in schema.step_via_cc_supported:
            await self._request(self._zn, cc, direct_data)
        else:
            await self._send_rc5(schema.rc5_table, increment)

    prefix = "inc" if increment else "dec"
    stepper.__name__ = f"{prefix}_{cc.name.lower()}"
    stepper.__qualname__ = f"State.{stepper.__name__}"
    stepper.__annotations__ = {"return": None}
    return stepper


_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


@add_accessors
class State:
    """Cached view of a single zone's state, kept in sync via status-update listener.

    Most getters and setters are auto-generated by :func:`add_accessors`
    from schemas on :class:`CommandCodes`.  Methods that require special
    logic (multi-byte parsing, RC5 fallback with model gating, etc.) are
    hand-written in the *Manual accessors* section at the bottom.
    """

    _state: dict[int, bytes | None]
    _presets: dict[int, PresetDetail]

    def __init__(self, client: Client, zn: int) -> None:
        self._zn = zn
        self._client = client
        self._state = dict()
        self._presets = dict()
        self._now_playing: NowPlayingInfo | None = None
        self._amxduet: AmxDuetResponse | None = None
        self._unsupported_commands: set[CommandCodes] = set()
        self._updated = asyncio.Event()

    async def start(self) -> None:
        """Register the status-update listener and update provider."""
        # pylint: disable=protected-access
        self._client._listen.add(self._listen)
        self._client.register_update_provider(self.get_update_tasks)

    async def stop(self) -> None:
        """Unregister the status-update listener and update provider."""
        # pylint: disable=protected-access
        self._client._listen.remove(self._listen)
        self._client.unregister_update_provider(self.get_update_tasks)

    async def __aenter__(self) -> "State":
        """Start listening and return self."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop listening."""
        await self.stop()

    def to_dict(self) -> dict[str, Any]:
        """Return all readable state as a flat dict keyed by command stem."""
        return {name[4:].upper(): getattr(self, name)() for name in self._to_dict_getters}

    def __repr__(self) -> str:
        """Show cached state and AMX discovery info."""
        return "State ({}) Amx ({})".format(
            self.to_dict(), self._amxduet.values if self._amxduet else {}
        )

    @property
    def zn(self) -> int:
        """Zone number (1-based)."""
        return self._zn

    @property
    def client(self) -> Client:
        """Underlying protocol client."""
        return self._client

    @property
    def model(self) -> str | None:
        """Device model string from AMX discovery, or None."""
        if self._amxduet:
            return self._amxduet.device_model
        return None

    @property
    def revision(self) -> str | None:
        """Device revision string from AMX discovery, or None."""
        if self._amxduet:
            return self._amxduet.device_revision
        return None

    # --- Internal helpers ---

    def _listen(self, packet: ResponsePacket | AmxDuetResponse) -> None:
        """Handle incoming packets: cache status updates."""
        if isinstance(packet, AmxDuetResponse):
            self._amxduet = packet
            return

        if packet.zn != self._zn:
            return

        if packet.ac == AnswerCodes.STATUS_UPDATE:
            self._state[packet.cc] = packet.data
        else:
            self._state[packet.cc] = None

    @property
    def _api_model(self) -> ApiModel:
        return api_model_for(self.model)

    def _is_command_supported(self, cc: CommandCodes) -> bool:
        """Check if a command is supported by the current device."""
        if cc in self._unsupported_commands:
            return False
        if cc.version is not None and self.model is not None:
            return self.model in cc.version
        return True

    def _is_command_supported_on_source(self, cc: CommandCodes) -> bool:
        """True iff `cc` has no source gate, the gate is satisfied, or the current source is unknown."""
        if cc.sources is None:
            return True
        src = self.get_source()
        return src is None or src in cc.sources

    def _should_update(self, cc: CommandCodes) -> bool:
        """Whether the update loop should fetch this command right now."""
        if not self._is_command_supported(cc):
            return False
        if not (cc.flags & CommandFlags.ZONE_SUPPORT) and self._zn != 1:
            return False
        if not (cc.flags & CommandFlags.UPDATE):
            return False
        # Pushed commands are fetched only during the initial pass.
        if not (cc.flags & CommandFlags.NOT_PUSHED) and self._updated.is_set():
            return False
        if not self._is_command_supported_on_source(cc):
            return False
        return True

    def _require_command(self, cc: CommandCodes) -> None:
        """Raise UnsupportedCommand if the command is not supported."""
        if not self._is_command_supported(cc):
            raise UnsupportedCommand(cc=cc, model=self.model)

    async def _request(self, zn: int, cc: CommandCodes, data: bytes, priority: int = 0) -> bytes:
        """Check command support, then send a request."""
        self._require_command(cc)
        try:
            return await self._client.request(zn, cc, data, priority)
        except CommandNotRecognised:
            _LOGGER.debug("Command not recognised, marking %s as unsupported", cc)
            self._unsupported_commands.add(cc)
            raise

    async def _send_rc5(self, table: dict, value) -> None:
        """Send an RC5 IR command via the SIMULATE_RC5_IR_COMMAND CC."""
        command = self.get_rc5code(table, value)
        await self._request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
        )

    def get(self, cc):
        """Return raw cached bytes for a command code."""
        return self._state[cc]

    def get_rc5code(
        self, table: dict[tuple[ApiModel, int], dict[_T, bytes]], value: _T
    ) -> bytes:
        """Look up an RC5 IR code from a model+zone keyed table."""
        lookup = table.get((self._api_model, self._zn))
        if not lookup:
            raise ValueError(
                "Unkown mapping for model {} and zone {}".format(
                    self._api_model, self._zn
                )
            )

        command = lookup.get(value)
        if not command:
            raise ValueError(
                "Unkown command for model {} and zone {} and value {}".format(
                    self._api_model, self._zn, value
                )
            )
        return command

    # --- Update provider ---

    async def get_update_tasks(self) -> list[UpdateTask]:
        """Return a list of update coroutines for the current device state.
        """
        priority = _UPDATE_PRIORITY

        async def _update(cc: CommandCodes):
            try:
                data = await self._request(self._zn, cc, bytes([0xF0]), priority)
                self._state[cc] = data
            except UnsupportedZone:
                _LOGGER.debug("Unsupported zone %s for %s", self._zn, cc)
            except CommandNotRecognised:
                self._state[cc] = None
            except ResponseException as e:
                _LOGGER.debug("Response error skipping %s - %s", cc, e.ac)
                self._state[cc] = None
            except NotConnectedException as e:
                _LOGGER.debug("Not connected skipping %s", cc)
                self._state[cc] = None
            except TimeoutError:
                _LOGGER.error("Timeout requesting %s", cc)

        async def _update_presets() -> None:
            presets = {}
            for preset in range(1, 51):
                try:
                    data = await self._request(
                        self._zn, CommandCodes.PRESET_DETAIL, bytes([preset]), priority
                    )
                    if data != b"\x00":
                        presets[preset] = PresetDetail.from_bytes(data)
                except CommandInvalidAtThisTime:
                    break
                except CommandNotRecognised:
                    _LOGGER.debug("Presets not supported skipping %s", preset)
                    break
                except NotConnectedException as e:
                    _LOGGER.debug("Not connected skipping preset %s", preset)
                    return
                except TimeoutError:
                    _LOGGER.error("Timeout requesting preset %s", preset)
                    return
            self._presets = presets

        async def _update_now_playing() -> None:
            kwargs = {}
            for field in attr.fields(NowPlayingInfo):
                if "request" not in field.metadata:
                    continue
                try:
                    data = await self._request(
                        self._zn, CommandCodes.NOW_PLAYING_INFO, bytes([field.metadata["request"]]), priority
                    )
                    kwargs[field.name] = field.metadata["converter"](data)
                except CommandNotRecognised:
                    _LOGGER.debug("Now playing not supported")
                    self._now_playing = None
                    return
                except ParameterNotRecognised:
                    _LOGGER.debug("Now playing %s not supported", field.name)
                except NotConnectedException:
                    _LOGGER.debug("Not connected skipping now playing")
                    self._now_playing = None
                    return
                except ResponseException as e:
                    _LOGGER.debug("Now playing %s error: %s", field.name, e.ac)
                except TimeoutError:
                    _LOGGER.error("Timeout requesting now playing %s", field.name)

            if kwargs:
                self._now_playing = NowPlayingInfo(**kwargs)
            else:
                self._now_playing = None

        async def _update_amxduet() -> None:
            try:
                data = await self._client.request_raw(AmxDuetRequest(), priority)
                self._amxduet = data
            except ResponseException as e:
                _LOGGER.debug("Response error skipping %s", e.ac)
            except NotConnectedException as e:
                _LOGGER.debug("Not connected skipping amx")
            except TimeoutError:
                _LOGGER.error("Timeout requesting amx")

        if not self._client.connected:
            if self._state:
                self._state = dict()
                self._now_playing = None
            self._updated.clear()
            return []

        if self._amxduet is None:
            await _update_amxduet()

        tasks: list[UpdateTask] = []
        for cc in CommandCodes:
            if not self._should_update(cc):
                continue
            if cc == CommandCodes.NOW_PLAYING_INFO:
                tasks.append(_update_now_playing())
            elif cc == CommandCodes.PRESET_DETAIL:
                tasks.append(_update_presets())
            else:
                tasks.append(_update(cc))

        if not self._updated.is_set():
            if not tasks:
                self._updated.set()
                return []

            async def _run_and_signal():
                try:
                    await run_tasks(*tasks)
                finally:
                    self._updated.set()

            return [_run_and_signal()]

        return tasks

    async def update(self) -> None:
        """Block until the provider-driven update loop completes one pass."""
        # pylint: disable=protected-access
        await wait_any(self._updated, self._client._disconnected)
        if self._client._disconnected.is_set():
            raise NotConnectedException()

    # --- Manual accessors (ordered by CommandCodes value) ---

    # POWER (0x00)
    async def set_power(self, power: bool) -> None:
        """Turn the zone on or off, using direct CC or RC5 per model support."""
        if self._api_model in POWER_WRITE_SUPPORTED:
            bool_to_hex = 0x01 if power else 0x00
            if not power:
                self._state[CommandCodes.POWER] = bytes([0])
            await self._request(self._zn, CommandCodes.POWER, bytes([bool_to_hex]))
        else:
            if power:
                await self._send_rc5(RC5CODE_POWER, power)
            else:
                command = self.get_rc5code(RC5CODE_POWER, power)
                # Seed with a response since the device might not respond
                # in a timely fashion on power-off.
                self._state[CommandCodes.POWER] = bytes([0])
                await self._client.request(
                    self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, command
                )

    # SAVE_RESTORE_COPY_OF_SETTINGS (0x06)
    async def save_settings(self, pin: tuple[int, int, int, int] = (1, 2, 3, 4)) -> None:
        """Save a secure backup of device settings.

        The PIN defaults to (1, 2, 3, 4), the factory default installer PIN.
        """
        await self._request(
            1, CommandCodes.SAVE_RESTORE_COPY_OF_SETTINGS,
            bytes([SaveRestoreSubCommand.SAVE, *SAVE_RESTORE_CONFIRMATION, *pin]),
        )

    async def restore_settings(self, pin: tuple[int, int, int, int] = (1, 2, 3, 4)) -> None:
        """Restore settings from the secure backup.

        The PIN defaults to (1, 2, 3, 4), the factory default installer PIN.
        Raises CommandInvalidAtThisTime if no backup exists.
        """
        await self._request(
            1, CommandCodes.SAVE_RESTORE_COPY_OF_SETTINGS,
            bytes([SaveRestoreSubCommand.RESTORE, *SAVE_RESTORE_CONFIRMATION, *pin]),
        )

    # SIMULATE_RC5_IR_COMMAND (0x08) — RC5 command senders
    async def set_hdmi_output(self, output: HdmiOutput) -> None:
        """Switch the HDMI output via RC5."""
        await self._send_rc5(RC5CODE_HDMI_OUTPUT, output)

    async def send_navigation(self, code: RC5CodeNavigation) -> None:
        """Send a navigation RC5 command."""
        await self._send_rc5(RC5CODE_NAVIGATION, code)

    async def send_playback(self, code: RC5CodePlayback) -> None:
        """Send a playback RC5 command."""
        await self._send_rc5(RC5CODE_PLAYBACK, code)

    async def send_toggle(self, code: RC5CodeToggle) -> None:
        """Send a toggle RC5 command."""
        await self._send_rc5(RC5CODE_TOGGLE, code)

    async def send_menu_access(self, code: RC5CodeMenuAccess) -> None:
        """Send a menu-access RC5 command."""
        await self._send_rc5(RC5CODE_MENU_ACCESS, code)

    async def send_numeric(self, digit: int) -> None:
        """Send a numeric digit (0-9) via RC5."""
        if not 0 <= digit <= 9:
            raise ValueError(f"Digit must be 0-9, got {digit}")
        if self.model and self.model not in APIVERSION_RC5_NUMERIC_SERIES:
            raise ValueError(
                f"Numeric RC5 not supported on {self.model}"
            )
        await self._request(
            self._zn, CommandCodes.SIMULATE_RC5_IR_COMMAND, bytes([0x10, digit])
        )

    async def send_color(self, color: RC5CodeColor) -> None:
        """Send a color-button RC5 command."""
        await self._send_rc5(RC5CODE_COLOR, color)

    # DECODE_MODE_2CH (0x10) / DECODE_MODE_MCH (0x11) — composite helpers
    def get_2ch(self) -> bool:
        """Return whether the incoming audio is 2-channel."""
        audio_format, _ = self.get_incoming_audio_format()
        return bool(
            audio_format
            in (
                IncomingAudioFormat.PCM,
                IncomingAudioFormat.ANALOGUE_DIRECT,
                IncomingAudioFormat.UNDETECTED,
                None,
            )
        )

    def get_decode_mode(self) -> DecodeModeMCH | DecodeMode2CH | None:
        """Return the active decode mode for the current channel count."""
        if self.get_2ch():
            return self.get_decode_mode_2ch()
        else:
            return self.get_decode_mode_mch()

    def get_decode_modes(
        self,
    ) -> list[DecodeModeMCH] | list[DecodeMode2CH] | None:
        """Return available decode modes for the current channel count."""
        if self.get_2ch():
            return list(RC5CODE_DECODE_MODE_2CH.get((self._api_model, self._zn), {}))
        else:
            return list(RC5CODE_DECODE_MODE_MCH.get((self._api_model, self._zn), {}))

    async def set_decode_mode(self, mode: str | DecodeModeMCH | DecodeMode2CH) -> None:
        """Set the decode mode, dispatching to 2CH or MCH by current channel count."""
        if self.get_2ch():
            if isinstance(mode, str):
                mode = DecodeMode2CH[mode]
            elif not isinstance(mode, DecodeMode2CH):
                raise ValueError("Decode mode not supported at this time")
            await self.set_decode_mode_2ch(mode)
        else:
            if isinstance(mode, str):
                mode = DecodeModeMCH[mode]
            elif not isinstance(mode, DecodeModeMCH):
                raise ValueError("Decode mode not supported at this time")
            await self.set_decode_mode_mch(mode)

    # TUNER_PRESET (0x15)
    def get_tuner_preset(self) -> int | None:
        """Return the active tuner preset number, or None if no preset is selected."""
        if not self._is_command_supported_on_source(CommandCodes.TUNER_PRESET):
            return None
        value = self._state.get(CommandCodes.TUNER_PRESET)
        if value is None or value == b"\xff":
            return None
        return int.from_bytes(value, "big")

    async def set_tuner_preset(self, preset: int) -> None:
        """Select a tuner preset by number."""
        if not self._is_command_supported_on_source(CommandCodes.TUNER_PRESET):
            return
        await self._request(self._zn, CommandCodes.TUNER_PRESET, bytes([preset]))

    # PRESET_DETAIL (0x1B)
    def get_preset_details(self) -> dict[int, PresetDetail] | None:
        """Return the buffered preset detail map, or None when the current source isn't a tuner."""
        if not self._is_command_supported_on_source(CommandCodes.PRESET_DETAIL):
            return None
        return self._presets

    # CURRENT_SOURCE (0x1D)
    def get_source(self) -> SourceCodes | None:
        """Return the currently selected source."""
        value = self._state.get(CommandCodes.CURRENT_SOURCE)
        if value is None:
            return None
        try:
            return SourceCodes.from_bytes(value, self._api_model, self._zn)
        except ValueError:
            return None

    def get_source_list(self) -> list[SourceCodes]:
        """Return the list of sources available for this model and zone."""
        return list(RC5CODE_SOURCE.get((self._api_model, self._zn), {}).keys())

    async def set_source(self, src: SourceCodes) -> None:
        """Select a source, using direct CC or RC5 per model support."""
        if self._api_model in SOURCE_WRITE_SUPPORTED:
            value = src.to_bytes(self._api_model, self._zn)
            await self._request(self._zn, CommandCodes.CURRENT_SOURCE, value)
        else:
            await self._send_rc5(RC5CODE_SOURCE, src)

    # INPUT_NAME (0x20)
    async def get_input_name(self) -> str | None:
        """Fetch the name of the currently selected input (uncached)."""
        if not self._is_command_supported_on_source(CommandCodes.INPUT_NAME):
            return None
        data = await self._request(self._zn, CommandCodes.INPUT_NAME, bytes([0xF0]))
        return data.decode("utf-8", errors="replace").rstrip("\x00").strip()

    # ROOM_EQ_NAMES (0x34)
    def get_room_eq_names(self) -> list[str] | None:
        """Return user-defined names for the room EQ profiles."""
        value = self._state.get(CommandCodes.ROOM_EQ_NAMES)
        if value is None:
            return None
        names = []
        for i in range(0, len(value), 20):
            name = value[i:i + 20].decode("ascii", errors="replace").rstrip("\x00").strip()
            names.append(name)
        return names

    # INCOMING_AUDIO_FORMAT (0x43)
    def get_incoming_audio_format(
        self,
    ) -> tuple[IncomingAudioFormat, IncomingAudioConfig] | tuple[None, None]:
        """Return the incoming audio format and config as a 2-tuple."""
        value = self._state.get(CommandCodes.INCOMING_AUDIO_FORMAT)
        if value is None:
            return None, None
        return (
            IncomingAudioFormat.from_int(value[0]),
            IncomingAudioConfig.from_int(value[1]),
        )

    # INCOMING_AUDIO_SAMPLE_RATE (0x44)
    def get_incoming_audio_sample_rate(self) -> int | None:
        """Return the incoming audio sample rate in Hz."""
        value = self._state.get(CommandCodes.INCOMING_AUDIO_SAMPLE_RATE)
        if value is None:
            return None
        return SAMPLE_RATE_MAP.get(value[0], 0)

    # BLUETOOTH_STATUS (0x50)
    def get_bluetooth_status(
        self,
    ) -> tuple[BluetoothAudioStatus, str] | tuple[None, None]:
        """Return Bluetooth audio status and track name."""
        if not self._is_command_supported_on_source(CommandCodes.BLUETOOTH_STATUS):
            return None, None
        value = self._state.get(CommandCodes.BLUETOOTH_STATUS)
        if value is None:
            return None, None
        status = BluetoothAudioStatus.from_int(value[0])
        if len(value) > 1:
            track = value[1:].decode("ascii", errors="replace").rstrip("\x00").strip()
        else:
            track = ""
        return status, track

    # NOW_PLAYING_INFO (0x64)
    def get_now_playing(self) -> NowPlayingInfo | None:
        """Return now-playing metadata (HDA series, NET/BT sources)."""
        if not self._is_command_supported_on_source(CommandCodes.NOW_PLAYING_INFO):
            return None
        return self._now_playing
