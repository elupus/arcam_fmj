# Firmware dump

## 1. Introduction

This document describes the Arcam AVRx1-series (AVR11/AVR21/AVR31/AV41) firmware bundle: how to obtain and unpack it, what's inside, and a step-by-step walkthrough of the code path that handles control-protocol traffic — from a TCP byte arriving on port 50000, through the on-device software stack, down to the host MCU, and back. The walkthrough is followed by a correlation section that maps the observed black-box behaviour of the live device onto the internal code path, identifies a structural issue in the design, and discusses workarounds available to clients.

All references in this document are to artifacts produced by `nix run '.#fetch-firmware'`. Disassemblies named below are in the build derivation, not the repo — fetch first to read them.

## 2. Extraction methodology

`nix run '.#fetch-firmware'` performs the entire pipeline:

1. **Download** the official update bundle `AVRx1_1v62_2148.zip` from `arcam.co.uk` using `pkgs.fetchurl` with a pinned SHA-256.
2. **Unzip** to obtain `AVRx0_System*.fw` (the composite host-side firmware blob), `image.swu` (the network-side SWUpdate payload), and `AVR11_AVR21_AVR31_AV41_Software_Release_Notes_*.pdf`.
3. **Unpack `image.swu`** with `cpio -idv` (it's a cpio archive) to obtain the SoC payload's individual components.
4. **Decompress the UBIFS rootfs** with `xz -dc` (the `yocto-…-arcam.ubifs` blob is XZ-compressed; this matches `compressed = true` in the bundled `sw-description` manifest).
5. **Extract the UBIFS contents** with `ubireader_extract_files` to produce a complete Linux rootfs tree.
6. **Extract the FIT images** with `dumpimage` (from `u-boot-tools`) — splits the signed FIT into kernel/dtb/ramdisk subimages; the kernel and ramdisk are gzip-compressed inside the FIT and are decompressed after extraction. The SWU updater's ramdisk is then further extracted as a cpio archive into `ramdisk.cpio.d/`.
7. **Untar `u-boot.tar.gz`** to obtain the bootloader binaries.
8. **Extract STM32 code regions** from the host `.fw` blob and **disassemble** them with `arm-none-eabi-objdump` (Thumb-2, `armv7e-m`). Two regions are extracted, identified by the vector-table pattern (initial-SP + reset-handler-Thumb-address pair) at the start of each contiguous run of non-`0xFF` bytes; see [flake.nix](../flake.nix) `firmwareHostAnalysis` for the offsets.
9. **Disassemble** every `libnsdk_*.so` and binary on the Linux side plausibly involved in protocol handling, using `llvm-objdump --demangle`. The target list is in [flake.nix](../flake.nix) `firmwareNetAnalysis`.

The full pipeline is defined in [flake.nix](../flake.nix). The bundle URL, SHA-256, and exact extraction recipes are all there.

## 3. Layout of extracted contents

```
.firmware/
├── AVR11_AVR21_AVR31_AV41_Software_Release_Notes_1v62_2148.pdf
├── host/
│   ├── AVRx0_System(HDMI2p1Plus)0v1p62.fw          ← original 90 MB composite bundle
│   └── analysis/
│       ├── extracted/
│       │   ├── stm32_bootloader.bin                ← file offset 0x000000–0x010000
│       │   └── stm32_app.bin                       ← file offset 0x010000–0x0ea020
│       └── disasm/
│           ├── stm32_bootloader.S                  ← arm-none-eabi-objdump, VMA 0x08000000
│           └── stm32_app.S                         ← arm-none-eabi-objdump, VMA 0x08010000
└── net/
    ├── fitImage-a113d-arcam-signed                 ← raw FIT (kernel + dtb)
    ├── fitImage-swu-a113d-arcam-signed             ← raw FIT (SWU updater)
    ├── u-boot.tar.gz                               ← raw u-boot bundle
    ├── yocto-nsdk-ip-image-swu-a113d-arcam.ubifs   ← raw UBIFS (XZ-compressed)
    ├── sw-description, sw-description.sig          ← SWUpdate manifest
    ├── swupdate_preinstall.sh, swupdate_postinstall.sh
    ├── rootfs/                                     ← unpacked Yocto rootfs
    ├── fit/                                        ← extracted kernel + fdt.dtb
    ├── fit-swu/                                    ← extracted SWU kernel + dtb + ramdisk(.d)
    ├── u-boot/                                     ← extracted u-boot tarball
    └── analysis/
        └── disasm/                                 ← llvm-objdump --demangle of selected libs
            ├── nSDK.S
            ├── hostlink_cli.S, nsdk_cli.S
            ├── libnsdk_hostLink.so.S
            ├── libnsdk_hostLinkLib.so.S
            ├── libnsdk_serialComm.so.S
            ├── libnsdk_thrift_api.so.S
            ├── libnsdk_api.so.S
            ├── libnsdk_webserver.so.S
            ├── libnsdk_machine.so.S
            ├── libnsdk_systemManager.so.S
            ├── libnsdk_networking.so.S
            ├── libnsdk_services.so.S
            ├── libnsdk_simple_ipc.so.S
            ├── libnsdk_processhandler.so.S
            ├── libnsdk_powerHandler.so.S
            ├── libnsdk_powerManager.so.S
            ├── libnsdk_constpartition.so.S
            ├── libnsdk_sysfs.so.S
            ├── libnsdk_mLib.so.S
            ├── libnsdk_miscUtils.so.S
            ├── libnsdk_mdnsHelpers.so.S
            └── libnsdk_mdnsSystemMembers.so.S
```

Absolute symlinks inside the extracted Linux filesystems (e.g. busybox shims like `flashcp -> /usr/sbin/flashcp.mtd-utils`) are preserved as symlinks and appear broken on the host. They resolve correctly on the target device.

## 4. Hardware architecture (from the firmware image)

Evidence for each claim is the artifact path + a brief description of the indicator.

| Claim | Evidence |
|---|---|
| Host control MCU is an STM32 Cortex-M (Thumb-2, ARMv7E-M). | Vector-table-shaped bytes at file offsets 0x000000 and 0x010000 of `host/AVRx0_System*.fw`: initial-SP word followed by a `0x080000?? \| 1` (Thumb) reset-handler address. The image contains references to STM32 HAL routines (`HAL_I2C_SlaveRxCpltCallback`, `HAL_I2C_AddrCallback`, `HardwareI2C_ID1Enable`, `HardwareI2C_SendData`, `HardwareI2C_ReadData`) as string constants — see [host/analysis/disasm/stm32_app.S](../.firmware/host/analysis/disasm/stm32_app.S) (search for the strings near rodata). |
| Network/streaming SoC is an Amlogic A113D running Linux. | [net/sw-description](../.firmware/net/sw-description) declares `hardware-compatibility: ["a113d-arcam", "a113d-arcam-V1", "a113dArcam", "a113dArcam-V1", "Generic", "Generic-V1"]`. The FIT image (`net/fit/`) targets `a113d-arcam`. |
| Audio decoding/processing is on a Texas Instruments DSP (separate from STM32). | Path strings inside the composite `.fw` blob (use `strings -t x` on the .fw): `/home/anam.dev/ti/ANAM_KOR_18_004_PA_processor_sdk_audio_1_03_00_00/…/simulate_dma/simulate_dma.c`, `src/I2C_drv.c`, `src/v0/I2C_v0.c`. DTS/Dolby decoder file paths also present (e.g. `dlb_jocdeclib/src/parser.c`, `dtshd-c-decoder/src/…`). |
| A separate sub-component, codename "Bach", talks to the rest over SPI. | Strings inside the composite `.fw`: `bach_set_channel_db2`, `bach_handle_service_info`, `Bach Boot Done...`, `Bach command i/f: SPI`. |
| The STM32 ↔ SoC link is I²C, not UART (despite the "hostlink"/"serial" naming in the Linux-side library). | [net/rootfs/usr/lib64/libnsdk_hostLink.so](../.firmware/net/rootfs/usr/lib64/libnsdk_hostLink.so): `CMHostLinkWorker::CMHostLinkWorker` (flash addr `0x27950` in [net/analysis/disasm/libnsdk_hostLink.so.S](../.firmware/net/analysis/disasm/libnsdk_hostLink.so.S)) loads the literal `"i2c"` (rodata at flash `0xb0248`) and passes it as `name` to `HostLinkPhysicalLayer::create`. The factory at [net/analysis/disasm/libnsdk_hostLinkLib.so.S](../.firmware/net/analysis/disasm/libnsdk_hostLinkLib.so.S) `0x1c228` instantiates `I2cPhysicalLayer` when name == `"i2c"`. |
| The MCU asserts a GPIO IRQ to signal the SoC that response data is ready. | SoC-side `SyncSerialLayer::gpioIrqLoop` at `0x24168` in [net/analysis/disasm/libnsdk_hostLinkLib.so.S](../.firmware/net/analysis/disasm/libnsdk_hostLinkLib.so.S) polls `/sys/class/gpio/gpioN/value` via the sysfs interface and enqueues a wake-up to `readLoop`. Strings `/sys/class/gpio/export`, `/sys/class/gpio/gpio`, `IRQ GPIO falling edge` appear in the same library. |

## 5. Software architecture overview

### Network-streaming SoC (Amlogic A113D, Linux)

- Yocto-built Linux rootfs at [net/rootfs/](../.firmware/net/rootfs/).
- Boot sequence: [net/u-boot/uboot/u-boot-signed.bin](../.firmware/net/u-boot/uboot/u-boot-signed.bin) → signed FIT kernel ([net/fit/kernel](../.firmware/net/fit/kernel)) → SWUpdate verifies signed payload → installs rootfs.
- The main userspace control daemon is `nSDK` at [net/rootfs/usr/share/nsdk/nSDK](../.firmware/net/rootfs/usr/share/nsdk/nSDK), launched under `nsdk_watchdog` by [net/rootfs/etc/init.d/nsdk](../.firmware/net/rootfs/etc/init.d/nsdk).
- `nSDK` `dlopen`s `libnsdk_hostLink.so` at runtime (the lib name appears only as a string literal in the `nSDK` rodata, not as a `DT_NEEDED` entry — verified with `readelf -d`).
- Inside `libnsdk_hostLink.so`, the class `CMHostLinkWorker` owns three `HostLinkMessageHandler` subclasses: `UInputHandler`, `TcpTunneling`, `LedApi`. They are stored polymorphically in a `QList<HostLinkMessageHandler*>` at `this+0x68`. The shared transport-layer pointer is at `this+0x48`.
- `TcpTunneling` is the part that exposes port 50000.

### Host MCU (STM32)

- Two code regions in the host `.fw` blob: a small **update bootloader** at flash `0x08000000` and the **main app** at flash `0x08010000`.
- The bootloader's role is firmware update (string evidence in [host/analysis/disasm/stm32_bootloader.S](../.firmware/host/analysis/disasm/stm32_bootloader.S): `[Boot] Open File: %s`, `AVRx0 Update Result.txt`, `BOOTLOADER Ver. %s`, `AVRx0_System*.fw`, `AVRx0_LCD*.bin`).
- The main app handles normal runtime, including I²C slave for the SoC-side host-link protocol.
- The remainder of the .fw bundle (file offsets beyond `0x0ea020`, mostly past `0x200000` after a long 0xFF padding) contains TI Performance Audio DSP firmware and the "Bach" sub-component. These are different processor architectures and are not relevant to the protocol path analysed here, so are not disassembled.

### Protocol layering, top to bottom

```
TCP client (port 50000)
  │
  ▼
TcpTunneling                       libnsdk_hostLink.so       (TCP server + per-client slot id; bin16 wrapper)
  │
  ▼
HostLinkTransportLayer             libnsdk_hostLinkLib.so    (HostLink message framing, packetisation)
  │
  ▼
SyncSerialLayer / I2cPhysicalLayer libnsdk_hostLinkLib.so    (per-packet I²C transaction, GPIO IRQ wait)
  │
  ▼
I2c                                libnsdk_serialComm.so     (ioctl(I2C_RDWR) wrapper, stateless)
  │
  ▼  /dev/i2c-N (Linux)  ⇆  I²C2 peripheral  (STM32)
  │
  ▼
I²C-RX dispatcher                  stm32_app.S               (HostLink fragment reassembly)
  │
  ▼
HostLink message parser            stm32_app.S               (value-entry loop)
  │
  ▼
0xC5 (bin16) sub-handler           stm32_app.S               (Arcam frame handling + reply build)
  │
  ▼
I²C TX kick → GPIO IRQ → SoC reads response
```

## 6. Methodology for software analysis

| Layer | Tool | Notes |
|---|---|---|
| AArch64 ELF shared objects on the Linux side | `llvm-objdump --disassemble --demangle` | C++ symbols are demangled inline. Function bodies are recognisable; cross-references are grep-able by mangled name. |
| ARMv7E-M raw binary on the STM32 side | `arm-none-eabi-objdump -D -b binary -m armv7e-m -M force-thumb --adjust-vma=…` | No ELF metadata; functions must be found by patterns and cross-references. The image contains some symbol-name strings (e.g. `HAL_I2C_SlaveRxCpltCallback`) referenced for hard-fault diagnostics — useful as anchors. |
| Both | `nm -D --demangle` | Linux side has dynamic symbol tables; STM32 side does not. |
| Both | `strings -t x` | Anchor functions via referenced string literals (log messages, file paths, function-name diagnostics). |

For both sides, the disassembled `.S` files at `.firmware/{host,net}/analysis/disasm/` are the canonical reference. Line numbers in this document refer to those files unless otherwise stated.

Two facts about the disassembly format are useful to know when following along:

- `arm-none-eabi-objdump` output line format: `   <hex_addr>:	<bytes>	<mnemonic> <operands>`. PC-relative loads are annotated with `@ <effective addr>`.
- `llvm-objdump --demangle` output begins each function body with `<hex_addr> <DemangledSignature>:` then per-instruction lines. Mangled-name grep (`_ZN…`) finds function entry points; demangled grep finds call sites with operands.

## 7. Walkthrough: port 50000 to MCU and back

This is a step-by-step trace of a single Arcam protocol command and its reply. Every step cites the precise file, function, and offset where the behaviour is implemented. Statements marked **observed** are directly read from disassembly; those marked **inferred** are structural deductions explicitly built on cited observations.

### 7.1. TCP server setup

**Step 1.** At nSDK startup, `CMHostLinkWorker::CMHostLinkWorker` (`libnsdk_hostLink.so` flash addr `0x27950`, [net/analysis/disasm/libnsdk_hostLink.so.S](../.firmware/net/analysis/disasm/libnsdk_hostLink.so.S)) constructs three `HostLinkMessageHandler` subclasses and stores them in a `QList` at `this+0x68`. One of these is the `TcpTunneling` instance.

**Step 2.** `TcpTunneling::TcpTunneling` (`libnsdk_hostLink.so` flash addr `0x30e48`) reads its `port` and `maxOpenConnections` parameters from a `NsdkValue::tcpTunnelingConf` configured at [net/rootfs/settings-default/hostlink/tcpTunnelingConf](../.firmware/net/rootfs/settings-default/hostlink/tcpTunnelingConf) (JSON: `port=50000, maxOpenConnections=10`). It constructs a `QTcpServer` at `this+0x28` and calls `QTcpServer::listen()` with those values. Per-client state is held in a `QHash<QTcpSocket*, signed_char>` at `this+0x30`. **Observed.**

### 7.2. Client connect → slot assignment

**What a slot is, and what it's for.** The SoC-side bridge multiplexes up to `maxOpenConnections` (default 10) concurrent TCP clients over a **single** I²C link to the MCU. To let the MCU and the bridge identify which client a given byte stream belongs to, the bridge assigns each new TCP connection a 1-byte **slot id** and uses it as a routing tag: every outbound byte stream sent to the MCU on this client's behalf will be prefixed with the slot id (step 5), and every reply byte stream from the MCU destined for this client will arrive at the SoC with the same slot id at offset 0 of the reply's payload (step 21, mirrored back by the MCU somewhere along the unresolved code path in step 14). The slot is a per-TCP-connection routing tag, **not** a per-thread identifier — all TCP-client servicing runs on the single Qt event-loop thread (step 4), and all outbound I²C transactions serialise through one `pthread_mutex_t` on the physical-layer object (step 8), so concurrency-wise the slot id makes no difference.

**Step 3.** When a client connects, Qt invokes `TcpTunneling::on_tcpServer_newConnection` (flash `0x33018`). The handler walks the existing slot values in the hash, picks the lowest integer `s` in `[0, maxOpenConnections)` not already in use, and stores it as the new socket's value at the hash node's `+0x18` offset (`strb w21, [x1]` at flash `0x33230`, where `x1 = node+0x18` and `w21` holds the slot id). If all slot ids are taken the connection is rejected by calling the socket's `close` vtable slot and `QObject::deleteLater()`. **Observed.**

**Step 4.** `nsdkConnect` ([net/analysis/disasm/libnsdk_api.so.S](../.firmware/net/analysis/disasm/libnsdk_api.so.S) flash `0x64dc8`) wires three Qt signals on the new socket — `readyRead`, `disconnected`, `error(QAbstractSocket::SocketError)` — to `TcpTunneling`'s slots, with `Qt::ConnectionType=0` (`AutoConnection`). Since `TcpTunneling` and the socket share a thread, this resolves to `DirectConnection`. **Observed.**

### 7.3. Client send → bin16 wrap

**Step 5.** Bytes arrive on the kernel TCP receive buffer. Qt emits `readyRead` once for each new batch (Qt does not re-emit until all bytes have been read or new bytes arrive). The slot is `TcpTunneling::on_socket_readyRead` (flash `0x328c0`). The handler does:

1. `QObject::sender()` → the originating socket. **Observed.**
2. `QHash<QTcpSocket*, signed_char>::findNode` → locates the slot byte; if not found, the handler logs `"Unknown connection ready to read"` and calls the socket's vtable+0x70 (close). **Observed.**
3. Loads the slot byte with `ldrsb` (sign-extended). If equal to `-1` (`0xff`), the handler also takes the "Unknown connection" path. **Observed.** (Note: no code path in this binary writes `-1` to a hash node value — verified by exhaustive search for `strb` of an immediate `0xff` against any QHash node offset. The check is defensive.) **Observed (negative result).**
4. **`QIODevice::read(socket, 8192)`** — reads **up to** 8192 bytes (immediate `#0x2000` in `mov x1, …` at `0x329fc`). No loop; one call per `readyRead`. **Observed.**
5. Builds a 1-byte `QByteArray` containing the slot id assigned at step 3, prepends it to the just-read data → final payload is `[slot_id, ...bytes_read]`. The leading byte is the routing tag the MCU side uses to identify which client owns this byte stream (relied on indirectly through step 14 and recovered from the reply at step 21).
6. Constructs `HostLinkValueMessage` with `messageId = 8` and calls `HostLinkValueMessage::addValueBin16` **exactly once** with the prepended payload (single bin16 entry).
7. Calls `HostLinkTransportLayer::writeMessage` via the transport-layer vtable. The return value is discarded.

**Key observation**: there is **no Arcam-protocol-aware parsing** in this handler. Whatever bytes `QIODevice::read` returns are passed as a single opaque blob.

### 7.4. Transport-layer packetisation

**Step 6.** `HostLinkTransportLayer::writeMessage` ([net/analysis/disasm/libnsdk_hostLinkLib.so.S](../.firmware/net/analysis/disasm/libnsdk_hostLinkLib.so.S) flash `0x1a7e8`):

1. Calls `physicalLayer->nextFrameId()` (vtable+0x20) to obtain a monotonic frame id. **Observed.**
2. Constructs a `HostLinkMsgFrame` with `(message_bytes, frame_id, max_packet_size)`.
3. Iterates over the resulting packets (`HostLinkMsgFrame::packetCount`).
4. For each packet, calls `physicalLayer->writeData(packet)` (vtable+0x28). Status codes:
   - `0` → success, continue to next packet
   - `1` → transient busy; sleeps 10 ms (`usleep(10000)` at `0x1a95c`), retries up to 3 attempts; if still `1` after 3, logs `"Unable to write data to the physical layer: rejected after 3 retries"` and returns 0.
   - `2`, `3` → error; logs `"Unable to write data to the physical layer: <code>"` and returns 0.

**Observed.** There is no per-message-id, per-slot, or per-frame state on the transport layer object beyond the frame-id counter (and a `std::map<int, HostLinkFrame*>` used only by the reassembly path on the read side — see step 12).

### 7.5. Physical layer is I²C

**Step 7.** `HostLinkPhysicalLayer::create("i2c", props)` returns an `I2cPhysicalLayer` instance ([net/analysis/disasm/libnsdk_hostLinkLib.so.S](../.firmware/net/analysis/disasm/libnsdk_hostLinkLib.so.S) ctor at `0x1e3a8`). The `I2cPhysicalLayer` vtable (`_ZTV16I2cPhysicalLayer` at `0x3eaa8` in the same library) overrides only the destructor; every other slot points to a `SyncSerialLayer` method. So in practice, all writes go through `SyncSerialLayer::writeData` at `0x22bf8`. **Observed.**

**Step 8.** `SyncSerialLayer::writeData`:

1. Unconditionally `pthread_mutex_lock(this + 0xf0)` at `0x22c9c` ("writeMutex"). Concurrent callers block. **Observed.**
2. Calls `SyncSerialLayer::writeReadPacket(buf, 2 * minFrameSize)` at `0x22478` — this both sends the packet and waits for the I²C-level response sentinel:
   - `usleep(5000)` (5 ms minimum dwell), then calls the device's `read` (vtable+0x18) and polls for a 16-bit response sentinel `0xFEFF`. Backoff: 5 ms → 10 → 20 → 40 → 80 ms, max 5 attempts.
   - Returns the response bytes (or empty on timeout).
3. Parses the response; returns one of `{0=OK, 1=busy/retry, 2=error, 3=unexpected}` to the transport layer.
4. Unconditionally `pthread_mutex_unlock` at `0x22e74` on every return path.

**Observed.** **Inferred**: because the mutex is unconditionally taken on every entry and there is no `trylock`/`wait_for`/single-slot-replace pattern, second writers cannot drop — they block until they acquire the mutex.

**Step 9.** `SyncSerialLayer` underlying byte transfer goes through `I2c::write` / `I2c::writeRead` in [net/rootfs/usr/lib64/libnsdk_serialComm.so](../.firmware/net/rootfs/usr/lib64/libnsdk_serialComm.so). These classes are stateless syscall wrappers: `I2c::writeRead` issues a single `ioctl(I2C_RDWR)` (cmd `0x707`, 2 messages); `I2c::write` uses the raw `write(2)` syscall on the open `/dev/i2c-N` fd. No threading primitives, no buffers, no statics. **Observed.**

### 7.6. MCU I²C-RX

**Step 10.** Bytes arrive on the STM32's I²C2 peripheral. The HAL invokes `HAL_I2C_SlaveRxCpltCallback` (function-name string present at file offset `0x97cc0` in `stm32_app.bin`, flash `0x080a7cc0`). Standard STM32 HAL: this callback is `__weak` in the library and overridden by the application.

**Step 11.** The application's I²C-RX dispatcher (flash `0x080a74d0` in [host/analysis/disasm/stm32_app.S](../.firmware/host/analysis/disasm/stm32_app.S)) reads the HostLink message header from the I²C buffer and branches on a tag byte at `[r6,#4]` (the dispatcher masks the byte to its low nibble for the `0x02`/`0x03` comparisons and tests the full byte for `0x23`/`0x63`):

- `tag == 0x02` (TX-ready signalling): stores 4-byte payload at `[r5+0x754]` and toggles the GPIO IRQ via `0x0807608e` (the only direct caller of this GPIO toggle inside the dispatcher). **Observed.**
- `tag == 0x03` (non-final HostLink fragment): `memcpy` payload from `r6+8` into one of three **HostLink fragment-reassembly buffers** at `r5+0x44d8`, `r5+0x54d6`, `r5+0x64cc`, then increment a **fragment counter** at `[r5+0x72f]` (saturating at 3). `r5 = 0x20000000` (literal at `0x080a7c90`). So the fragment counter lives at RAM `0x2000072f` and the buffers at `0x200044d8`, `0x200054d6`, `0x200064cc`. **Observed.** (These reassembly buffers are an internal MCU mechanism for stitching together a multi-packet HostLink message; they are distinct from the TcpTunneling slot id of step 3 — the TcpTunneling slot id is embedded as the first byte of the bin16 payload **inside** the reassembled HostLink message.)
- `tag == 0x23` (final HostLink fragment): append payload into fragment-buffer[counter] at offsets `0xffe`/`0x1ff4`/`0x2fea` relative to `+0x44d8`, **zero the fragment counter** (`strb.w r0(=0), [r5, #1839]` at `0x080a75a2`), then call the parser at `0x080a46f0` **exactly once**. If the fragment counter was already 0 (no pending fragments), the dispatcher skips the memcpy and calls the parser directly on the just-arrived I²C buffer `r6`. **Observed.**
- `tag == 0x63`: 532-byte `memset` starting at `[r5,#16]` (buffer reset).

**Key observation**: the parser is invoked **once per I²C-RX dispatch**, regardless of the size of the reassembled buffer. There is no loop here, no second parser pass, no scan over the buffer. **Observed.**

### 7.7. MCU HostLink message parser

**Step 12.** Parser entry: `0x080a46f0`. The function:

1. Prologue: `push {r4..fp, lr}`, 36 bytes of locals; `r4 = buffer pointer (caller arg)`.
2. Validates a 16-bit header at `[r4+0..1]` against `0xff 0xfe`. **Observed.**
3. Reads a field count at `[r4+10]`. **Observed.**
4. Runs a fixed `for (i=0; i < count; ++i)` loop (iterator at `[sp+1]`, loop body roughly `0x080a4788..0x080a7462`, with the back-branch at `0x080a7462` and exit at `0x080a7466`). Per iteration:
   - Reads a one-byte type tag from the current cursor in `r4`.
   - Dispatches by tag: known tags include `0xCC`, `0xC5` (bin16), `0xCE`, `0xD3`.
   - Advances the cursor `r7` by the field size for that tag.
5. Loop exit at `0x080a7466`; epilogue at `0x080a747c` (`pop {r4..fp, pc}`).

**Observed.** The dispatch tags `0xCC`/`0xC5`/`0xCE`/`0xD3` are HostLink value-entry type tags, **not Arcam `<St>=0x21`/`<Et>=0x0d` framing bytes**. The loop iterates over HostLink fields, not over Arcam frames.

### 7.8. Bin16 sub-handler

**Step 13.** When the type tag is `0xC5` (bin16), the dispatch lands at flash `0x080a5790`. The handler:

1. Confirms tag (`cmp r0, #197` at `0x080a5792`). **Observed.**
2. Computes a destination pointer in RAM at `r8 + 0x4480` (32-byte staging area immediately preceding the slot-0 RX buffer at `+0x44d8`). **Observed.**
3. Loads a 16-bit length from the local stack at `[sp+2]`.
4. Calls **`bl 0x080a0b18`** with `(r0=staging_dst, r1=src=bin16 payload, r2=tag-related, r3=u16_len)`. **Observed; the call is unconditional and made exactly once.** The buffer at `r1` is the full bin16 payload from the bridge — its first byte is the TcpTunneling slot id from step 5, and the remainder is the Arcam frame.
5. `memcmp` the result at the staging area against a 32-byte reference buffer at `r8+0x44a0` (`bl 0x801a268`); if equal, take the "no change" exit path. **Observed.**
6. If different, copy 32 bytes from staging into the reference buffer (via `ldmia/stmia` at `0x080a57c2`–`0x080a57ca`). **Observed.**
7. Call `bl 0x080895fe` — a 3-instruction accessor that returns the byte at `[r0+#0x44a]` (a TX-state flag) — then `cmp r0, #1` / `bne 0x80a5810` at `0x080a57d4`–`0x080a57d6`. The two branches diverge from here:
   - If the state byte was 1 (TX path taken): clear flags at `[r8, #0x706]` and `[r8, #0x708]` (`0x080a57da`–`0x080a57de`), then run a per-slot housekeeping loop (sdiv/mls modular arithmetic over slot index, slot-state writes via `[r1, #0x238]`) and exit into the outer parser loop at `0x080a7450`.
   - Otherwise (`0x080a5810`+): perform a second 32-byte memcmp against a reference buffer at `r8+0x8560`, then either clear the same `+0x706`/`+0x708` flags and continue, or read another state byte at `[r8, #0x726]` and branch further. Not fully traced.
8. The actual I²C-TX write and GPIO-IRQ assertion — the **reply emission** — must lie further along one of these branches, not at `0x080895fe` itself (which is a getter with ~72 callers across the image and does not touch the I²C peripheral or GPIO). Precise location of the kick and its relation to the five `0x0807608e` (GPIO toggle) call sites is not identified in this pass. **Observed (negative result for the cited address); downstream path not traced.**

The flash trampoline at `0x080a0b18`:

```
080a0b18:  df f8 00 f0    LDR.W  PC, [PC]
080a0b1c:  f5 c0 00 20    .word  0x2000c0f5
```

`PC ← 0x2000c0f5` (Thumb-mode, code at RAM `0x2000c0f4`). **Observed.**

**Static limit**: the actual code at RAM `0x2000c0f4` is not initialised by anything in the STM32 firmware images we have. Exhaustive search of both `stm32_bootloader.S` and `stm32_app.S` finds no init-time `memcpy` writing to that RAM region, no literal-pool entry containing `0x2000c0c8`/`0x2000c0f4`/`0x2000c0c9`/`0x2000c0f5` except the trampoline itself, and no `MOVW`/`MOVT` pair computing those addresses. The bootloader's startup is BSS-clear-only — no flash-to-RAM `.data` copy loop. **Observed (exhaustive negative search).** **Deduction**: the destination is populated by a mechanism outside the firmware images extractable from this `.fw` (candidates not investigated: a separate firmware partition, runtime upload from the SoC, DMA descriptor loading).

**Structural observations** about the trampoline's calling convention:

- ~20 call sites use `bl 0x080a0b18` with identical 4-arg register signature `(dst, src, tag, u16_len)`. **Observed.**
- The companion trampoline at `0x080a0b20` (target `0x2000c0c9` → RAM `0x2000c0c8`) is paired and adjacent. **Observed.**

**Step 14.** The Arcam-protocol-level parsing of the bin16 payload bytes — that is, recognising the `<St>=0x21 <Zn> <Cc> <Dl> <data> <Et>=0x0d` framing — must happen either inside the call at step 13.4 (the RAM trampoline target) or downstream of the state-machine branches in step 13.7. The `0xC5` sub-handler itself does not iterate over the bin16 payload bytes; it makes the single trampoline call, then transitions through the state-flag check and exits via one of those branches. **Observed.**

**Image-wide negative search**: across the entire STM32 main app and bootloader disassembly, no function contains a loop with `cmp #0x21` (the Arcam `<St>` byte) on successive memory bytes. The only function that compares a buffer byte to `#0x21` and then computes `Dl + N` (the Arcam-frame-length pattern) is at flash `0x08076c68`. That function reads exactly `Dl + 5` bytes, makes a single dispatch via an indirect call, and returns — it contains no loop or second `<St>` scan. Its only inbound call site is a `b.w` tail-branch from `0x080a2876` inside what appears to be a periodic test/injector routine (the only caller computes `r0 = table_base + 101*(global_tick % 30) + 223` before the tail-branch). It is **not** reachable from the I²C-RX path. **Observed (exhaustive grep over both `stm32_bootloader.S` and `stm32_app.S`).**

### 7.9. MCU reply transmission

**Step 15.** The reply is emitted by writing bytes to the I²C2 TX peripheral and asserting a GPIO IRQ line, signalling the SoC that response data is ready. The GPIO toggle helper at `0x0807608e` has exactly **five call sites** in `stm32_app.S`: one inside the I²C-RX dispatcher's tag-`0x02` path (step 11) and four others elsewhere. Which of those four lies on the bin16-reply path (downstream of step 13.7) is not identified in this pass. **Observed (call-site enumeration); reply-path identification not completed.**

**Slot id in the reply.** The reply payload's bin16 entry contains, at offset 0, the same TcpTunneling slot id the request carried at step 5 — confirmed indirectly because the SoC-side `TcpTunneling::handleDataMessage` at step 21 reads that byte from the inbound bin16 and reverse-looks-up the matching socket. The MCU code that writes the slot byte into the outgoing reply bin16 sits inside the unresolved code at step 14 (RAM trampoline target at `0x2000c0f4` or downstream from it); not statically visible. **Deduced** from step 21's reverse lookup being the only way the bridge could route the reply correctly.

### 7.10. SoC reads reply over I²C

**Step 16.** On the Linux side, `SyncSerialLayer::gpioIrqLoop` (`libnsdk_hostLinkLib.so` flash `0x24168`) is one of two threads spawned by `SyncSerialLayer::init` (flash `0x250d0`). It blocks in `poll(POLLPRI)` on a `/sys/class/gpio/gpioN/value` file descriptor. When the MCU asserts the GPIO IRQ, the loop reads 4 bytes to discharge the event, allocates a 0x18-byte work-queue node (with flag byte `1` at node+0x10), hooks it into the work queue at `this+0xd8`, and `cv.notify_all`s. **Observed.**

**Step 17.** The other thread, `SyncSerialLayer::readLoop` (`libnsdk_hostLinkLib.so` flash `0x23d48`), waits on the same condition variable, pops the work node, and calls `SyncSerialLayer::readFromSlave` (flash `0x23440`). `readFromSlave` reads the response packet via the I²C device and dispatches it via observer pattern. **Observed.**

**Step 18.** `HostLinkTransportLayer::on_data_received` (`libnsdk_hostLinkLib.so` flash `0x1b460`) reassembles inbound packets keyed by frame id into a `std::map<int, HostLinkFrame*>` at `this+0x10` (guarded by `pthread_mutex_t` at `this+0x58`). When a complete `HostLinkFrame` arrives, the transport invokes the registered observer callbacks (stored in a `std::list<std::function<…>>` at `this+0x40`). **Observed.**

### 7.11. Cross-thread marshal back to the Qt thread

**Step 19.** `CMHostLinkWorker::CMHostLinkWorker` (`libnsdk_hostLink.so` flash `0x27950`, around `0x27fa0`) registers an observer with the transport layer whose `std::function` body is `QMetaObject::invokeMethod(worker, "on_message_received", Qt::QueuedConnection=2, …)`. This marshals the received-frame bytes from `readLoop`'s thread (non-Qt) onto the Qt event loop. **Observed.**

**Step 20.** The Qt event loop processes the queued invocation. The receiver dispatches by `messageId`; for `messageId == 8`, control reaches `TcpTunneling::handleMessage` (`libnsdk_hostLink.so` flash inside the `0x32` range — exact address present as the virtual method). `handleMessage` constructs a response `HostLinkValueMessage(0x8009)` and iterates the input message's value entries:

- For each entry: if `tag == 1 && enc == 0xc5`, call `handleDataMessage`; if `tag == 2 && enc == 0xcd`, call `handleCommandMessage`; else log `"Unsupported tcp tunneling message"`.

After the loop, `writeMessage` is called on the transport layer to emit the response. **Observed.**

**Step 21.** `TcpTunneling::handleDataMessage` (flash `0x31240`) is the relevant path for command replies:

1. `HostLinkValueMessage::getBin16` to extract the response payload `QByteArray`. **Observed.**
2. The **first byte** of the payload is the **slot id** the MCU response is addressed to (`local_99 = local_98[offset_of_bin16_data]`). **Observed.**
3. `QHash::key(slot_id, &found_socket)` — **reverse lookup**: scans the per-socket slot-id hash for a socket whose value matches `slot_id`. **Observed.**
4. If a socket is found: `QByteArray::remove(0)` strips the slot id, then `QIODevice::write(socket, data)` ships the rest to the client over TCP. Reply marker `addValueUint8(response, 1)` (success). **Observed.**
5. If no socket is found: `addValueUint8(response, 1)` and log `"Tcp connection N doesn't exist"`. **Observed.**

The `QIODevice::write` is a direct call, not marshalled via `QMetaObject::invokeMethod`. Since `handleDataMessage` is itself reached via `Qt::QueuedConnection` (step 19), it executes on the same thread as the socket; the call is thread-safe. **Observed.**

**Step 22.** The TCP-layer kernel pushes the bytes back to the client. The client receives a complete Arcam reply frame `<St> <Zn> <Cc> <Ac> <Dl> <data> <Et>`.

### 7.12. Cross-connection state-update broadcast (incidental, but observable)

**Step 23.** When the MCU reports certain state changes (e.g. POWER), the SoC-side delivery loop emits the resulting response frame to **all** connected `TcpTunneling` clients, not only the one that sent the originating request. This is implemented via the same observer-list dispatch (step 18); the response message arriving with `messageId == 8` and certain sub-tags causes `handleMessage` to write to multiple sockets in turn. Direct evidence of which sub-tags trigger broadcasts: not traced. Observed black-box: a POWER query on one connection results in one reply packet on every currently-open TCP connection (tested with N=2 and N=3).

## 8. Correlation with observed behaviour

The following black-box behaviours of the live device have been independently measured against an AV41 running firmware v1.62 build 2148 (single-connection probes use `/tmp/arcam_probe*.py`; multi-connection probes verify symmetric behaviour):

### 8.1. Pair-send coalescing window

Two POWER queries sent on one TCP connection with inter-send gap `g`, count of trials (out of 10) where only one reply was received:

| g | 0 ms | 100 µs | 500 µs | 1 ms | 2 ms | 5 ms+ |
|---|---|---|---|---|---|---|
| drops/10 | 9 | 9 | 5 | 1 | 0 | 0 |

### 8.2. Trailing-zero tolerance, single frame

One POWER query plus N trailing zero bytes in a single `send()`:

| N trailing zeros | reply latency |
|---|---|
| 10 | 75 ms |
| 100 | 79 ms |
| 1 000 | 168 ms |
| 2 000 | 253 ms |
| 3 000 | 349 ms |
| 4 000 | 440 ms (one run); no reply within 20 s (another run) |
| 6 000–16 000 | no reply within 20 s, every run |

### 8.3. Leading-zero tolerance

Any number of leading zeros (`N ∈ {10, 100, 8192}`) before `<St>` causes the entire packet to be silently dropped — no reply within 20 s.

### 8.4. Pipelined multi-frame

A single `send()` of 10 POWER queries each followed by N trailing zeros (N ∈ {1000, 1500, 2000, 2500, 3000, 3500, 8186, 8192}): in every test, zero replies were received within 20 s.

### 8.5. Sustained rate

N back-to-back POWER queries on one connection at gap `g`, count of replies received within 3 s after the last send:

| g | N=2 | N=3 | N=5 | N=8 | N=10 | N=15 | N=20 | N=30 | N=50 |
|---|---|---|---|---|---|---|---|---|---|
| 2 ms | 2/2 | 2/3 | 2/5 | 3/8 | 3/10 | 4/15 | 5/20 | 7/30 | 0/50 |
| 5 ms | 2/2 | 2/3 | 4/5 | 5/8 | 0/10 | 8/15 | 0/20 | 0/30 | 2/50 |
| 10 ms | 2/2 | 3/3 | 0/5 | 8/8 | 0/10 | 15/15 | 0/20 | 0/30 | 3/50 |
| 50 ms | 2/2 | 3/3 | 4/5 | 8/8 | 10/10 | 11/15 | 16/20 | 24/30 | 37/50 |
| 100 ms | 2/2 | 3/3 | 5/5 | 8/8 | 10/10 | 15/15 | 20/20 | 30/30 | 50/50 |
| 200 ms | 2/2 | 3/3 | 5/5 | 8/8 | 10/10 | 15/15 | 20/20 | 30/30 | 50/50 |

### 8.6. Cross-connection broadcast

When N TCP connections are open simultaneously and one of them sends a POWER query, all N connections receive an identical reply packet (tested with N=2 and N=3). When two connections each send one POWER query within ~50 µs of each other, each connection receives 2 reply packets (its own reply plus the other connection's broadcast).

### 8.7. Mapping observation to walkthrough

| Observation | Walkthrough step | Mechanism |
|---|---|---|
| Two consecutive sends with ≥2 ms gap both reply (§8.1). | Steps 5 (TCP-buffer drain), 6 (I²C-bus serialisation) | At ≥2 ms gap the two segments are reliably separate kernel TCP segments AND the first segment has reliably been drained from the kernel buffer by `QIODevice::read` before the second arrives. Two `readyRead` signals, two HostLink messages, two MCU dispatches, two replies. |
| Two consecutive sends with 0 ms gap (same `send()` call): only first reply (§8.1). | Step 5 (`read(8192)` reads the entire kernel-buffered chunk in one shot; `addValueBin16` called once with the merged bytes) → step 12 (HostLink parser loops by **value-entry count**, which is 1, not by Arcam-frame scanning) → step 13 (bin16 sub-handler runs once with the full merged payload) → step 14 (no `<St>`-scanning loop exists anywhere) | The Arcam frames after the first `<Et>` in the merged payload are inside a single bin16 value entry. The MCU parser sees one value entry, dispatches once to the bin16 sub-handler with the full payload pointer + length, and the bin16 sub-handler does not iterate within that payload. The trailing frames are unreached code-wise. |
| Cross-connection sends do not drop (§8.6). | Step 8 (`writeMutex` is blocking, not dropping). | Both connections' bytes arrive as separate `readyRead` signals → separate HostLink messages → serialised at the SoC-side I²C `writeMutex` (no concurrency, no drops) → independent MCU dispatches → both reply. |
| Postpad latency scales linearly with `N` until ~3 kB, then no reply (§8.2). | Steps 6, 7, 8 (transport layer chunks payload, I²C bus carries each chunk, MCU reassembles). | The latency curve fits an I²C-transport-rate-bounded model: at the observed slope (~+1 ms per ~25 bytes), effective rate ≈ 25 kB/s, consistent with I²C fast-mode (400 kHz). The cliff above 3 kB is **observed** but its mechanism is not traced from disassembly — it could be MCU buffer size (the reassembly slot is at `0x200044d8` in a fixed-size memory region), HostLink protocol length limit, or transport-layer timeout. Not investigated further. |
| Prepad zeros cause silent drop (§8.3). | Step 13 (bin16 sub-handler) | Inferred: the (unresolved) RAM-resident byte processor at `0x2000c0f4` validates the leading byte. Since prepended garbage breaks parsing for any N ≥ 10, the byte-0-must-be-`<St>` rule lives somewhere along the path from the bin16 sub-handler. The exact code is not statically visible because it sits at the unresolved RAM trampoline target. |

## 9. Identified structural issue

The walkthrough shows that the **only** loop in the MCU's receive path that iterates over the received byte buffer is the HostLink **value-entry** loop in step 12 — and its iteration count is the HostLink field count read from the message header, **not** the number of Arcam `<St>...<Et>` frames in the payload.

The SoC-side `TcpTunneling::on_socket_readyRead` (step 5) is the point where Arcam-protocol framing **would** need to be parsed in order to chunk a multi-frame TCP read into multiple HostLink value entries. It does not do this: it wraps the entire `read(8192)` result as a single `addValueBin16` value.

The combination — the SoC sending one value per `readyRead`, and the MCU dispatching once per value entry without further `<St>`-scanning — is the design issue: **any Arcam protocol frame after the first `<St>...<Et>` in a single `readyRead`'s output is unreachable** by the receive path.

This is consistent with all observed drop behaviour for the single-connection multi-frame case, with no remaining unexplained behaviour at the static-analysis level.

## 10. Workarounds

Workarounds available to a client that uses the Linux-side TCP interface.

### 10.1. Wait for matching reply before sending again

Conservative, completely reliable, no static-analysis risk. Per-request latency is the round-trip time (~75 ms baseline for a POWER query). Maximum sustained rate: ~13 commands/second. This is what the python library at [src/arcam/fmj/client.py](../src/arcam/fmj/client.py) already implements via `_request_lock` + the 200 ms `_REQUEST_THROTTLE`.

### 10.2. Inter-send gap ≥ 2 ms for occasional back-to-back sends

For two commands sent close together, a measured 2 ms gap between `send()` calls (with `TCP_NODELAY`) is sufficient to keep them in separate kernel TCP segments AND to give the SoC's `on_socket_readyRead` time to drain the buffer between them. Drop rate 0/10 in the pair-send measurement (§8.1).

### 10.3. Pair pattern with truly-silent fill command

For mixing a fire-and-forget command (today gated by the library's 200 ms `_REQUEST_THROTTLE`) with a reply-gated command: send the fire-and-forget first, wait ~2 ms, then send a reply-generating command and wait for its matching reply. Measured against an AV41 over 500 iterations with `21 01 00 00 0D` (POWER frame with `Dl=0` — the MCU parses and silently drops with no echo) as the fill: 489/500 matched (97.8% success), 0 unsolicited packets, p50 latency 98 ms, p95 104 ms.

The fill command must be **legitimately silent** (no echo reply); the only commands documented in the spec [.specs/markdown/RS232_5_10_20_30_40_11_21_31_41__SH289E_F_07Oct21.md](../.specs/markdown/RS232_5_10_20_30_40_11_21_31_41__SH289E_F_07Oct21.md) generate replies, but several inputs the MCU silently discards have been measured:

- Any non-`<St>` leading-byte stream
- `<St> <Zn> <Cc> <Dl=0> <Et>` (e.g. `21 01 00 00 0D`)
- `<St> <Zn> <Cc=0xFE> <Dl> <data> <Et>` (unknown command code 0xFE — note that 0xFF and 0x7F do generate `AC=0x83 CMD_NOT_RECOGNISED` replies, so not all unknown CCs are silent)

### 10.4. Sustained pipelining at ≥100 ms gap

For sustained throughput without per-reply gating, the table in §8.5 shows 100 ms inter-send gap is the first reliably-safe sustained rate for batches of up to N=50 commands (50/50 success). 50 ms suffices for N ≤ 10 but degrades beyond that. Below 50 ms, behaviour is unstable across N.

### 10.5. Not workarounds

The following do **not** help:

- **Prepad** with any number of bytes (≥10 tested) → drops the entire packet.
- **Postpad** to make a single padded unit exceed 8 kB → MCU stops replying (size cliff at ~3–4 kB).
- **Pipelined postpad** (multiple padded units in one `send()`) → drops all replies; the bridge's `read(8192)` still merges multiple units into one bin16.
