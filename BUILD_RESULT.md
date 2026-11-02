# Zork bitstream build result

Built 2026-11-02 for Tang Nano 20K, GW2AR-LV18QN88C8/I7, device revision C.
Gowin V1.9.11.03 Education synthesis and implementation completed in the normal
workspace sandbox. The latest build combines the project title and counters on
one fixed header row: ZORK I - Tang Nano 20K at left, Score and Moves aligned to
the terminal's right edge with one blank margin column. The standalone project
startup title was removed. White text/default background, scrolling and cursor
save/restore are retained. This combined-header build was programmed and
verified on 2026-11-02: exit 0, 30.06 seconds. The user confirmed the corrected layout;
`zork_startup_screen.png` shows a single title and right-aligned counters.
The previous serial-status build was programmed and verified on 2026-11-02
(exit 0, 29.92 seconds); the user's screenshot confirms its duplicated labels.
User Minicom output confirms basic serial communication; HDMI, PS/2, SD saves
and power-cycle behavior remain physically unvalidated.

## Deliverables

- FPGA bitstream: `impl/pnr/zork.fs` (7,262,008 bytes; see actual file and hash below).
- Required whole-card image: `assets/zork-sd.img` (1,048,576 bytes).
- Firmware: `impl/firmware/zork.elf`, `.bin`, `.map`; embedded in the bitstream.
- GUI project: `zork.gprj`; command-line build: `./build.sh`.
- Setup/wiring/card instructions: `README.md`.

The SD image contains the exact supplied `zork1.dat` and blank save banks.
It uses a dedicated raw layout, not FAT. The bitstream needs this card to play.
PS/2 uses pins 25/26 through a 3.3 V-safe adapter; the onboard serial keyboard
interface uses 115200 8N1, RX/TX pins 70/69. No USB host is implemented.

## Final resource and timing results

| Item | Result |
| --- | --- |
| Logic | 2,966 / 20,736 (15%) |
| Registers | 1,217 / 15,750 (8%) |
| Block RAM | 37 / 46 (81%) |
| CPU clock | 27 MHz; routed Fmax 82.782 MHz |
| Pixel clock | 74.25 MHz; routed Fmax 147.659 MHz |
| Minimum setup slack | +6.696 ns |
| Minimum hold slack | +0.227 ns |
| Setup / hold violated endpoints | 0 / 0 |
| Firmware text / data / BSS | 12,128 / 4 / 37,516 bytes |

Reports: `impl/pnr/zork.rpt.txt`, `impl/pnr/zork.tr`, `impl/build.log`.
The two clock domains share only true dual-port text RAM. Input pins are
synchronized; the timing constraints exclude asynchronous clock-domain paths.
External asynchronous input timing and physical SD/HDMI signals have not been
measured. Warnings include upstream PicoRV32 width truncation/case directives,
unused outputs and PR1014 generic oscillator routing; routed timing passes.
The freestanding firmware link's RWX segment warning is expected for unified
FPGA RAM without memory protection.

## Validation

- Bash syntax checks passed for build, firmware build, tests and the unchanged
  programming script.
- Native interpreter booted the supplied game, handled mailbox/leaflet/inventory,
  traversed Kitchen, Living Room and Cellar, reached 35 points, and successfully
  ran the game's `$verify` story checksum check.
- Initial gameplay responses compared with independent Frotz 2.55.
- Saves restored in a new host process. Alternating banks, corrupted newest-bank
  fallback, both-bank failure and SD write-area boundaries tested.
- SPI: all 256 byte values at four dividers. UART: all 256 byte values.
  PS/2: valid scan codes, break sequence, parity rejection and timeout recovery.
- HDMI console: two complete raster scans, every glyph pixel, inverse status
  row and CPU text access. TMDS: 100,000 symbols, decoding and DC balance.
- Terminal regression runs actual CPU startup output with gray palette-black
  and black default background, verifying screen clears on black at boot/reset.
- Full CPU integration checks startup attribute reset, white-on-default-background,
  clear screen and reserved status row at boot/reset. Serial control sequences
  are restricted to initialization and complete cursor-preserving status updates.
  Terminal models at 24/32 rows and 80/100/132 columns verify a single project
  title and right-aligned counters, fixed status through scrolling, cursor
  preservation, move increments, RESTORE rollback and reset to zero. Host
  walkthrough also checks nonzero score/moves against the SCORE response.
- Host regression tests cover CSI/SS3 Up recall, Down draft recovery, deletion,
  parameterized CSI and rejection of unsupported navigation sequences.
- Full processor/firmware simulation: boot, PS/2 LOOK and extended Up, serial
  Down/draft recovery, Delete, SS3 Up, ignored CSI Right, recalled LOOK, UART SAVE, NORTH,
  RESTORE, LOOK, then CPU/peripheral reset and RESTORE/LOOK again. SDHC run:
  59,133,875 CPU cycles, 356 SD reads, 41 sector writes. The SD model accepts
  actual SPI commands/data; no host save shortcuts or preloaded story RAM.

- The same full integration sequence also passed with SDSC CMD8 rejection,
  CMD16 block-size setup and byte addressing: 59,141,448 CPU cycles, 356 reads,
  41 writes. Both transcript assertions passed on the serial-status build. Each run
  additionally checked 55 CRLF pairs, with no bare LF or CR.

Logs: `impl/soc-sdsc.log`, `impl/header-tests.log`, `impl/soc-verilator.log`, `impl/host-transcript.txt`,
`impl/host-walkthrough.txt`, `impl/frotz-reference.txt`.

## Hardware status

The combined-header build was programmed and verified on 2026-11-02 with the
unchanged ./program_flash.sh and approved direct USB access: exit 0,
"SPI program and verify success!", 30.06 seconds. Programmed SHA-256:
`2d82e3def8b96e770c5175faa6362420e4cb7a89b70c55ee73e0f707d151d21a`.
SD/saves unchanged. The updated startup screenshot and user confirmation
validate the combined serial header on hardware (186-column terminal). HDMI,
PS/2, physical SD save/restore and power-cycle persistence remain unverified.

The serial score/moves build was programmed and verified on 2026-11-02 using
the unchanged ./program_flash.sh with approved direct USB access: exit 0,
"SPI program and verify success!", 29.92 seconds. Programmed SHA-256:
`e9917fbee1046e0af1162530462c2a2e8c4fce33f3e5b7a192f52a785468d032`.
SD/saves unchanged; physical serial status appearance awaits observation.

The preceding build (SHA-256 b609f0d2c992be56ea0a52c660d405ec7284842e40e74c4dc965076f2170eda1)
was programmed and verified using the unchanged
`./program_flash.sh` with approved direct USB access: exit 0,
"SPI program and verify success!", 29.15 seconds. Detected device GW2AR-18C
ID 0x0000081B, flash ID 0x0B4017. HDMI observation, physical keyboard tests,
SD save writes and actual power-cycle persistence remain unconfirmed. The preceding
CRLF-corrected bitstream was programmed and verified successfully in 28.45 seconds.
The newer terminal_arrorws.png shows aligned output but unhandled arrow escapes
on that build. The new command-history build was programmed and verified in 29.89 seconds,
exit 0, "SPI program and verify success!". Physical arrow-key behavior awaits
user confirmation.
The preceding SGR-40 terminal-initialization build was programmed and verified successfully
in 29.91 seconds, exit 0. User reports that build shows gray. The preceding SGR-49 correction was programmed
and verified in 29.95 seconds, exit 0; actual background awaits user confirmation.
The existing programmer still selects GW2AR-18C, external flash operation 9,
cable 4, channel 0. Programming needs a separate explicit user request and USB
access approval. A full 350-point playthrough has not been validated.

## SHA-256

```text
2d82e3def8b96e770c5175faa6362420e4cb7a89b70c55ee73e0f707d151d21a  impl/pnr/zork.fs
a7cee166c65497d91e014a10a02b24766e409af4e917766e68566ca45c91fe6b  impl/firmware/zork.bin
0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd  zork1.dat
0a986be8649bf154c0cbd420f41348c2673e9ce8ef72182052e606030c6fb764  assets/font.hex
084e9839c60834126907471614fce6c015f39f4ceabb94ba817ddd9f4e28d945  assets/zork-sd.img
```

## Host terminal palette correction

User observed gray even after SGR-49 firmware. The screenshot color #2e3436
matches installed Terminator palette black exactly. With approved host access,
changed only default-profile palette color 0 to #000000 and ran
`terminator --reload` successfully. Other colors/settings preserved; backup at
`impl/terminator-config.before-black`. No bitstream changes. Actual display
appearance awaits user confirmation.

## IDE project validation

`zork.gprj` now includes firmware and memory assets under Other Files.
`ide/zork_process_config.json` preserves the verified GUI build settings;
`prepare_ide.sh` restores them on a clean checkout without replacing existing
IDE settings. See README for opening and firmware rebuild instructions.

A clean copy built with Gowin `open_project` / `run all` and no option overrides.
Setup/hold violations were zero; resource usage and Fmax unchanged. Configuration
payload matches the programmed bitstream exactly (only creation timestamp comment
differs). No C compiler or hardware programming was involved. Evidence:
`impl/ide-validation.log`, `impl/ide-validation-result.txt`.
