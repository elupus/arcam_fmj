"""Zone state"""

import asyncio
import logging
from typing import Any, TypeVar

import attr

from .codecs import (
    AnswerCodes,
    BluetoothAudioStatus,
    DecodeMode2CH,
    DecodeModeMCH,
    HdmiOutput,
    IncomingAudioConfig,
    IncomingAudioFormat,
    NowPlayingInfo,
    PresetDetail,
    SAVE_RESTORE_CONFIRMATION,
    SaveRestoreSubCommand,
    SourceCodes,
)
from .commands import (
    BLUETOOTH_STATUS,
    COMMANDS,
    CURRENT_SOURCE,
    CommandFlags,
    Command,
    DECODE_MODE_2CH,
    DECODE_MODE_MCH,
    INCOMING_AUDIO_FORMAT,
    INPUT_NAME,
    NOW_PLAYING_INFO,
    PRESET_DETAIL,
    ReadCommand,
    SAVE_RESTORE_COPY_OF_SETTINGS,
    SIMULATE_RC5_IR_COMMAND,
    SOURCE_WRITE_SUPPORTED,
    StepCommand,
    WriteCommand,
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
    RC5CODE_COLOR,
    RC5CODE_DECODE_MODE_2CH,
    RC5CODE_DECODE_MODE_MCH,
    RC5CODE_HDMI_OUTPUT,
    RC5CODE_MENU_ACCESS,
    RC5CODE_NAVIGATION,
    RC5CODE_PLAYBACK,
    RC5CODE_SOURCE,
    RC5CODE_TOGGLE,
    RC5CodeColor,
    RC5CodeMenuAccess,
    RC5CodeNavigation,
    RC5CodePlayback,
    RC5CodeToggle,
)
from .client import Client, UpdateTask, _UPDATE_PRIORITY
from .utils import run_tasks, wait_any

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


class State:
    _state: dict[int, bytes | None]
    _presets: dict[int, PresetDetail]

    def __init__(self, client: Client, zn: int) -> None:
        self._zn = zn
        self._client = client
        self._state = dict()
        self._presets = dict()
        self._now_playing: NowPlayingInfo | None = None
        self._amxduet: AmxDuetResponse | None = None
        self._unsupported_commands: set[int] = set()
        self._updated = asyncio.Event()

    async def start(self) -> None:
        # pylint: disable=protected-access
        self._client._listen.add(self._listen)
        self._client.register_update_provider(self.get_update_tasks)

    async def stop(self) -> None:
        # pylint: disable=protected-access
        self._client._listen.remove(self._listen)
        self._client.unregister_update_provider(self.get_update_tasks)

    async def __aenter__(self) -> "State":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def to_dict(self) -> dict[str, Any]:
        """All readable state, keyed by command name."""
        result: dict[str, Any] = {
            command.name: self.get(command)
            for command in COMMANDS
            if isinstance(command, ReadCommand)
        }
        result["SOURCE"] = self.get_source()
        result["DECODE_MODE"] = self.get_decode_mode()
        result["INCOMING_AUDIO_FORMAT"] = self.get_incoming_audio_format()
        result["BLUETOOTH_STATUS"] = self.get_bluetooth_status()
        result["NOW_PLAYING"] = self.get_now_playing()
        result["PRESET_DETAIL"] = self.get_preset_details()
        return result

    def __repr__(self) -> str:
        return "State ({}) Amx ({})".format(
            self.to_dict(), self._amxduet.values if self._amxduet else {}
        )

    @property
    def zn(self) -> int:
        return self._zn

    @property
    def client(self) -> Client:
        return self._client

    @property
    def model(self) -> str | None:
        if self._amxduet:
            return self._amxduet.device_model
        return None

    @property
    def revision(self) -> str | None:
        if self._amxduet:
            return self._amxduet.device_revision
        return None

    @property
    def api_model(self) -> ApiModel:
        return api_model_for(self.model)

    # --- Generic typed accessors ---

    def get(self, command: ReadCommand[_T]) -> _T | None:
        if not self.supported_on_source(command):
            return None
        raw = self.get_cached(command.cc)
        if raw is None:
            return None
        return command.read(raw)

    async def set(self, command: WriteCommand[_T], value: _T) -> None:
        await command.write(self, value)

    async def inc(self, command: StepCommand[Any]) -> None:
        await command.step(self, True)

    async def dec(self, command: StepCommand[Any]) -> None:
        await command.step(self, False)

    # --- CommandContext: the surface typed commands call back into ---

    def get_cached(self, cc: int) -> bytes | None:
        return self._state.get(cc)

    def set_cached(self, cc: int, data: bytes | None) -> None:
        self._state[cc] = data

    def supported_on_source(self, command: Command[Any]) -> bool:
        """True iff `command` has no source gate, the gate is satisfied, or the source is unknown."""
        if command.sources is None:
            return True
        src = self.get_source()
        return src is None or src in command.sources

    def get_rc5code(
        self, table: dict[tuple[ApiModel, int], dict[_T, bytes]], value: _T
    ) -> bytes:
        lookup = table.get((self.api_model, self._zn))
        if not lookup:
            raise ValueError(
                "Unkown mapping for model {} and zone {}".format(self.api_model, self._zn)
            )

        command = lookup.get(value)
        if not command:
            raise ValueError(
                "Unkown command for model {} and zone {} and value {}".format(
                    self.api_model, self._zn, value
                )
            )
        return command

    async def request(self, command: Command[Any], data: bytes, priority: int = 0) -> bytes:
        self._require_command(command)
        try:
            return await self._client.request(self._zn, command.cc, data, priority)
        except CommandNotRecognised:
            _LOGGER.debug("Command not recognised, marking %s as unsupported", command)
            self._unsupported_commands.add(command.cc)
            raise

    async def send_rc5(self, table: dict, value: Any) -> None:
        code = self.get_rc5code(table, value)
        await self.request(SIMULATE_RC5_IR_COMMAND, code)

    # --- Internal helpers ---

    def _listen(self, packet: ResponsePacket | AmxDuetResponse) -> None:
        if isinstance(packet, AmxDuetResponse):
            self._amxduet = packet
            return

        if packet.zn != self._zn:
            return

        if packet.ac == AnswerCodes.STATUS_UPDATE:
            self._state[packet.cc] = packet.data
        else:
            self._state[packet.cc] = None

    def _is_command_supported(self, command: Command[Any]) -> bool:
        if command.cc in self._unsupported_commands:
            return False
        if command.version is not None and self.model is not None:
            return self.model in command.version
        return True

    def _should_update(self, command: Command[Any]) -> bool:
        if not self._is_command_supported(command):
            return False
        if not (command.flags & CommandFlags.ZONE_SUPPORT) and self._zn != 1:
            return False
        if not (command.flags & CommandFlags.UPDATE):
            return False
        # Pushed commands are fetched only during the initial pass.
        if not (command.flags & CommandFlags.NOT_PUSHED) and self._updated.is_set():
            return False
        if not self.supported_on_source(command):
            return False
        return True

    def _require_command(self, command: Command[Any]) -> None:
        if not self._is_command_supported(command):
            raise UnsupportedCommand(cc=command, model=self.model)

    # --- Update provider ---

    async def get_update_tasks(self) -> list[UpdateTask]:
        """Return a list of update coroutines for the current device state."""
        priority = _UPDATE_PRIORITY

        async def _update(command: Command[Any]):
            try:
                data = await self.request(command, bytes([0xF0]), priority)
                self._state[command.cc] = data
            except UnsupportedZone:
                _LOGGER.debug("Unsupported zone %s for %s", self._zn, command)
            except CommandNotRecognised:
                self._state[command.cc] = None
            except ResponseException as e:
                _LOGGER.debug("Response error skipping %s - %s", command, e.ac)
                self._state[command.cc] = None
            except NotConnectedException as e:
                _LOGGER.debug("Not connected skipping %s", command)
                self._state[command.cc] = None
            except TimeoutError:
                _LOGGER.error("Timeout requesting %s", command)

        async def _update_presets() -> None:
            presets = {}
            for preset in range(1, 51):
                try:
                    data = await self.request(PRESET_DETAIL, bytes([preset]), priority)
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
                    data = await self.request(
                        NOW_PLAYING_INFO, bytes([field.metadata["request"]]), priority
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
        for command in COMMANDS:
            if not self._should_update(command):
                continue
            if command is NOW_PLAYING_INFO:
                tasks.append(_update_now_playing())
            elif command is PRESET_DETAIL:
                tasks.append(_update_presets())
            else:
                tasks.append(_update(command))

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

    # --- Manual accessors (ordered by CC) ---

    # SAVE_RESTORE_COPY_OF_SETTINGS (0x06)
    async def save_settings(self, pin: tuple[int, int, int, int] = (1, 2, 3, 4)) -> None:
        """Save a secure backup of device settings.

        The PIN defaults to (1, 2, 3, 4), the factory default installer PIN.
        """
        await self.request(
            SAVE_RESTORE_COPY_OF_SETTINGS,
            bytes([SaveRestoreSubCommand.SAVE, *SAVE_RESTORE_CONFIRMATION, *pin]),
        )

    async def restore_settings(self, pin: tuple[int, int, int, int] = (1, 2, 3, 4)) -> None:
        """Restore settings from the secure backup.

        The PIN defaults to (1, 2, 3, 4), the factory default installer PIN.
        Raises CommandInvalidAtThisTime if no backup exists.
        """
        await self.request(
            SAVE_RESTORE_COPY_OF_SETTINGS,
            bytes([SaveRestoreSubCommand.RESTORE, *SAVE_RESTORE_CONFIRMATION, *pin]),
        )

    # SIMULATE_RC5_IR_COMMAND (0x08) — RC5 command senders
    async def set_hdmi_output(self, output: HdmiOutput) -> None:
        """Switch the HDMI output via RC5."""
        await self.send_rc5(RC5CODE_HDMI_OUTPUT, output)

    async def send_navigation(self, code: RC5CodeNavigation) -> None:
        """Send a navigation RC5 command."""
        await self.send_rc5(RC5CODE_NAVIGATION, code)

    async def send_playback(self, code: RC5CodePlayback) -> None:
        """Send a playback RC5 command."""
        await self.send_rc5(RC5CODE_PLAYBACK, code)

    async def send_toggle(self, code: RC5CodeToggle) -> None:
        """Send a toggle RC5 command."""
        await self.send_rc5(RC5CODE_TOGGLE, code)

    async def send_menu_access(self, code: RC5CodeMenuAccess) -> None:
        """Send a menu-access RC5 command."""
        await self.send_rc5(RC5CODE_MENU_ACCESS, code)

    async def send_numeric(self, digit: int) -> None:
        """Send a numeric digit (0-9) via RC5."""
        if not 0 <= digit <= 9:
            raise ValueError(f"Digit must be 0-9, got {digit}")
        if self.model and self.model not in APIVERSION_RC5_NUMERIC_SERIES:
            raise ValueError(f"Numeric RC5 not supported on {self.model}")
        await self.request(SIMULATE_RC5_IR_COMMAND, bytes([0x10, digit]))

    async def send_color(self, color: RC5CodeColor) -> None:
        """Send a color-button RC5 command."""
        await self.send_rc5(RC5CODE_COLOR, color)

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
            return self.get(DECODE_MODE_2CH)
        else:
            return self.get(DECODE_MODE_MCH)

    def get_decode_modes(
        self,
    ) -> list[DecodeModeMCH] | list[DecodeMode2CH] | None:
        """Return available decode modes for the current channel count."""
        if self.get_2ch():
            return list(RC5CODE_DECODE_MODE_2CH.get((self.api_model, self._zn), {}))
        else:
            return list(RC5CODE_DECODE_MODE_MCH.get((self.api_model, self._zn), {}))

    async def set_decode_mode(self, mode: str | DecodeModeMCH | DecodeMode2CH) -> None:
        """Set the decode mode, dispatching to 2CH or MCH by current channel count."""
        if self.get_2ch():
            if isinstance(mode, str):
                mode = DecodeMode2CH[mode]
            elif not isinstance(mode, DecodeMode2CH):
                raise ValueError("Decode mode not supported at this time")
            await self.set(DECODE_MODE_2CH, mode)
        else:
            if isinstance(mode, str):
                mode = DecodeModeMCH[mode]
            elif not isinstance(mode, DecodeModeMCH):
                raise ValueError("Decode mode not supported at this time")
            await self.set(DECODE_MODE_MCH, mode)

    # PRESET_DETAIL (0x1B)
    def get_preset_details(self) -> dict[int, PresetDetail] | None:
        """Return the buffered preset detail map, or None when the current source isn't a tuner."""
        if not self.supported_on_source(PRESET_DETAIL):
            return None
        return self._presets

    # CURRENT_SOURCE (0x1D)
    def get_source(self) -> SourceCodes | None:
        """Return the currently selected source."""
        value = self._state.get(CURRENT_SOURCE.cc)
        if value is None:
            return None
        try:
            return SourceCodes.from_bytes(value, self.api_model, self._zn)
        except ValueError:
            return None

    def get_source_list(self) -> list[SourceCodes]:
        """Return the list of sources available for this model and zone."""
        return list(RC5CODE_SOURCE.get((self.api_model, self._zn), {}).keys())

    async def set_source(self, src: SourceCodes) -> None:
        """Select a source, using direct CC or RC5 per model support."""
        if self.api_model in SOURCE_WRITE_SUPPORTED:
            value = src.to_bytes(self.api_model, self._zn)
            await self.request(CURRENT_SOURCE, value)
        else:
            await self.send_rc5(RC5CODE_SOURCE, src)

    # INPUT_NAME (0x20)
    async def get_input_name(self) -> str | None:
        """Fetch the name of the currently selected input (uncached)."""
        if not self.supported_on_source(INPUT_NAME):
            return None
        data = await self.request(INPUT_NAME, bytes([0xF0]))
        return data.decode("utf-8", errors="replace").rstrip("\x00").strip()

    # INCOMING_AUDIO_FORMAT (0x43)
    def get_incoming_audio_format(
        self,
    ) -> tuple[IncomingAudioFormat, IncomingAudioConfig] | tuple[None, None]:
        """Return the incoming audio format and config as a 2-tuple."""
        value = self._state.get(INCOMING_AUDIO_FORMAT.cc)
        if value is None:
            return None, None
        return (
            IncomingAudioFormat.from_int(value[0]),
            IncomingAudioConfig.from_int(value[1]),
        )

    # BLUETOOTH_STATUS (0x50)
    def get_bluetooth_status(
        self,
    ) -> tuple[BluetoothAudioStatus, str] | tuple[None, None]:
        """Return Bluetooth audio status and track name."""
        if not self.supported_on_source(BLUETOOTH_STATUS):
            return None, None
        value = self._state.get(BLUETOOTH_STATUS.cc)
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
        if not self.supported_on_source(NOW_PLAYING_INFO):
            return None
        return self._now_playing
