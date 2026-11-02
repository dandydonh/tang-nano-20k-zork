# Zork core progress

Updated 2026-11-02. Initial checkout contains only zork1.dat, board reference,
tool paths, programmer, and AGENTS.md. No prior PROGRESS.md existed.

## Current status: combined header programmed and verified

- Latest deliverable bitstream: `impl/pnr/zork.fs`, SHA-256
  `2d82e3def8b96e770c5175faa6362420e4cb7a89b70c55ee73e0f707d151d21a`.
  Single header: ZORK I - Tang Nano 20K at left, Score/Moves at right edge.
  Standalone project-title banner removed. Full build/tests pass.
  Programmed and verified 2026-11-02, exit 0, 30.06 seconds.
- Board now runs the combined-header build above. Prior serial-status SHA-256
  `e9917fbee1046e0af1162530462c2a2e8c4fce33f3e5b7a192f52a785468d032`,
  programmed/verified 2026-11-02, exit 0, 29.92 seconds. User's startup screenshot
  confirms its status row appears, but project labels repeat and counters need
  right alignment. The latest screenshot and user confirmation now verify the
  combined header on serial: one title, counters at right, black background.
- Host Terminator palette black was separately corrected to #000000.
- Required SD image: `assets/zork-sd.img`, 1 MiB raw whole-card format, exact
  supplied story plus blank save banks. SHA-256
  `084e9839c60834126907471614fce6c015f39f4ceabb94ba817ddd9f4e28d945`.
- Full `bash tests/run.sh` passed, including host score/moves matching Zork's
  SCORE command with nonzero points, command history, gameplay, save fallback,
  peripherals/video/TMDS and SDHC/SDSC processor integration.
- Actual CPU serial output rendered in a terminal model at 24/32 rows and 80/100/132 columns: fixed
  status survives scrolling, updates with movement, restores saved moves and
  resets on restart; cursor preserved and screen clears on black.
- CPU integration: SDHC 59,133,875 cycles; SDSC 59,141,448; each 356 reads,
  41 writes, 55 checked CRLF pairs, ten complete serial status updates.
- Final build: 2,966 logic, 1,217 registers, 37/46 BSRAM; zero setup/hold violations,
  minimum setup +6.696 ns and hold +0.227 ns. SHA manifest: `impl/SHA256SUMS`.
- Firmware text/data/BSS: 12,128 / 4 / 37,516 bytes. SD/save format unchanged.
- User tried a USB-C hub/keyboard on the board, then switched to a computer
  serial terminal after clarification that direct USB hosting is unsupported.
  Built both optional
  PS/2 on pins 25/26 (3.3 V-safe adapter required) and onboard serial on pins
  RX70/TX69, 115200 8N1. A USB-only keyboard requires a host adapter.
- Source/project/build/test documentation and detailed results are in README.md
  and BUILD_RESULT.md. `zork.gprj` is the new project (the initial AGENTS.md's
  hdmi_picture.gprj did not exist in this checkout).
- User requested programming. Persistent flash erase/program/verify succeeded
  2026-11-02 via escalated `./program_flash.sh`, exit 0, 28.45 seconds
  for the corrected build (initial build took 29.15 seconds).
  Device GW2AR-18C ID 0x0000081B; SPI flash ID 0x0B4017; cable 4/channel 0.
  Programmer script/device/operation unchanged. User previously demonstrated
  basic serial communication; corrected terminal alignment, HDMI, PS/2, SD saves
  and actual power-cycle persistence remain unconfirmed.

## Current serial output issue and fix

- User now uses Minicom on /dev/ttyUSB1 at 115200 8N1.
- Inspected supplied terminal_skew.png: Zork replies are readable but each LF
  advances downward without returning left, producing stair-stepped output.
  Screenshot demonstrates basic serial communication, not SAVE/RESTORE or HDMI.
- Root cause: firmware/platform.c console_put sent LF without preceding CR.
- Fixed serial output to emit CR+LF; HDMI still processes one logical newline.
- Immediate old-firmware workaround: Minicom Ctrl+A, release, U toggles
  "Add carriage return" (verified in local installed minicom manual).
- Rebuilt bitstream in sandbox; timing remains setup +6.696 ns, hold +0.227 ns,
  zero violations, resources unchanged. Firmware text now 11,124 bytes.
- Added full-CPU integration assertions that every transmitted LF follows CR
  and every CR is followed by LF. Full suite passed, 52 CRLF pairs in each
  SDHC/SDSC integration run; gameplay/save/reset/restore assertions passed.
- Corrected build programmed and verified, exit 0, 28.45 seconds; no
  programmer/script changes. Physical terminal alignment awaits user observation.

## Next work: hardware validation when requested

Prepare a dedicated card with the whole-card image, connect HDMI and selected
keyboard. Flash programming/readback is complete. Confirm HDMI, keyboard entry,
SAVE, move, RESTORE and persistence after an actual
power cycle. No complete 350-point playthrough has been tested. Do not overwrite
an existing SD image containing saves. Future firmware layout changes need a
save-format version change if snapshot compatibility is affected.

## Initial design and milestone history



- Target: Tang Nano 20K, GW2AR-LV18QN88C8/I7, revision C, 27 MHz oscillator.
- Supplied story: Z-machine V3, Zork I release 88, serial 840726,
  92,160 bytes, dynamic memory boundary 11,859 bytes.
- Dedicated bare-metal RISC-V interpreter, HDMI text console, SD SPI storage.
  Use a generated SD image holding the supplied story plus persistent save slots;
  on-chip RAM holds firmware, dynamic game memory, interpreter stack, and caches.
- Keyboard interface preference requested; pending. Board USB is not a USB host.
- Reuse locally available HDMI/TMDS design from ../hdmi_out as a starting point.
- Compiler and simulation tools absent from PATH. Download/extract under /tmp.
- No board programming authorized or performed; programmer remains unchanged.
- No HDMI, keyboard, SD, or power-cycle hardware behavior observed.

## Initial next steps (historical)

Implement and validate interpreter, SD protocol, keyboard and text display;
build firmware and FPGA bitstream; record resource/timing results. Hardware
validation will require the user-selected keyboard wiring and a prepared SD card.

## Interpreter and firmware milestone

- Implemented dedicated V3 interpreter in firmware/zmachine.c, freestanding RV32IM.
- Native host test booted the supplied game, LOOK, OPEN MAILBOX, READ LEAFLET,
  INVENTORY, SAVE, NORTH, RESTORE, LOOK, QUIT all produced expected responses.
  Restore returned to West of House and restored move count and leaflet inventory.
- Firmware currently approximately 11 KiB text, 21 KiB BSS in 64 KiB initialized RAM.
- Added SD SPI byte engine, serial, PS/2 receiver/FIFOs, 80x32 HDMI text console.
- Serial RX/TX package 70/69 verified from Sipeed official uart/src/top.cst.
  SD SPI CS/MOSI/CLK/MISO package 81/82/83/84 per board schematics.
  Optional PS/2 uses exposed GPIO 25(clock)/26(data), 3.3 V-safe adapter required.
- SD image is a dedicated raw format, not FAT. Image generator never writes devices.
  Two alternating 32 KiB snapshot banks, hash verification and commit header last.
- Initial synthesis caught Gowin's 2000-iteration initialization limit; changed text
  RAM initialization to a hex file. Rebuilding. No bitstream validated yet.
- Downloaded compiler, binutils, Icarus and reference dfrotz under /tmp/zork-tools.

## First bitstream milestone

- First complete Gowin synthesis/place/route/bitstream build succeeded in sandbox.
  impl/pnr/zork.fs generated, 2,966/20,736 logic, 1,218 registers, 37/46 BSRAM.
  Setup and hold violations: zero. CPU Fmax 75.170 MHz versus 27 MHz target;
  pixel Fmax 163.679 MHz versus 74.25 MHz target. Final firmware changes below
  require rebuilding before this can be considered the delivery bitstream.
- Gowin dual-port text RAM cannot use read-before-write mode; inferred normal
  mode by holding CPU read output during writes. Rebuild passed.
- Native tests passed: supplied story exploration into Kitchen/Living Room/Cellar,
  mailbox/leaflet/inventory, Frotz reference comparison, cross-process restore,
  alternating save banks, corrupt newest bank fallback, both-bank failure and
  unchanged story / writes confined to save area.
- Expanded static story cache to 32 sector lines (16 KiB) to avoid repeated SD
  reads between game code and strings. Firmware now ~48 KiB including BSS;
  link asserts at least 8 KiB C stack remains. Rebuild and full RTL tests pending.
- No board programming or hardware observations made.

## RTL and persistence milestone

- Peripheral simulations passed: 1,024 SPI loopback transfers over four dividers,
  all 256 UART bytes, PS/2 valid frames, bad parity rejection and timeout recovery.
- HDMI text test passed two full 1650x750 scans, checking every active glyph pixel,
  inversion and CPU read/write. Fixed inverse-video pipeline alignment found
  during test development. TMDS reference test passed 100,000 symbols.
- Full compiled RTL integration passed actual RV32IM firmware boot, PS/2 LOOK,
  UART SAVE/NORTH/RESTORE/LOOK, then hardware reset and RESTORE/LOOK.
  55,066,162 CPU cycles, 350 SD reads, 41 SD writes; latest transcript at
  impl/soc-verilator.log. This models reset persistence, not observed power cycling.
- Final firmware initializes console cursor after reset. 11,108 bytes text,
  4 bytes data, 37,312 bytes BSS. Bitstream rebuilt with this exact firmware.
- Final timing: zero setup/hold violations; minimum setup +6.696 ns, hold +0.227 ns.
  CPU Fmax 82.782 MHz; pixel Fmax 147.659 MHz. Hashes in impl/SHA256SUMS.
- Corrected test transcript's expected room occurrence count from six to five;
  rerunning full suite and adding SDSC addressing branch integration coverage.
- Delivery SD image cleaned to blank save banks. README describes whole-card raw
  image preparation, keyboard wiring and serial operation. No board programming.

## Flash programming milestone, 2026-11-02

- User explicitly requested uploading the bitstream to the board.
- Verified all impl/SHA256SUMS hashes before programming.
- Ran unchanged ./program_flash.sh outside sandbox with USB access approval.
- Target GW2AR-18C (0x0000081B), flash 0x0B4017, cable 4, channel 0, operation 9.
- Programmer reported "SPI program and verify success!", exit 0, 29.15 seconds.
- Programmed bitstream SHA-256: b609f0d2c992be56ea0a52c660d405ec7284842e40e74c4dc965076f2170eda1.
- No monitor/keyboard/SD hardware observations or power-cycle test yet.

## Serial output diagnosis/build milestone, 2026-11-02

- Screenshot terminal_skew.png confirms stair-stepped LF-only output in Minicom.
- CRLF fix built as impl/pnr/zork.fs, b0a18bbe70325319ee0b10599f0cf44b8ee246c2725ae32c2629db023263bd5d.
- SD image/save format unchanged; no card re-imaging needed.

## Serial CRLF validation milestone, 2026-11-02

- Full tests/run.sh passed: host gameplay and save corruption checks, I/O units,
  video, TMDS and both SDHC/SDSC full processor integration runs.
- Each integration run checked 52 UART CRLF pairs, no bare LF or CR.
- SDHC: 55,188,264 cycles; SDSC: 55,195,831 cycles; each 350 reads/41 writes.
- Latest bitstream and firmware verified against impl/SHA256SUMS.
- No new board programming performed. Minicom Ctrl+A,U is the immediate workaround
  for the still-programmed original LF-only build; corrected image is ready.

## CRLF-corrected flash programming milestone, 2026-11-02

- User explicitly requested uploading the corrected bitstream.
- All impl/SHA256SUMS checks passed before programming.
- Ran unchanged ./program_flash.sh with escalated USB access.
- GW2AR-18C ID 0x0000081B, flash 0x0B4017, cable 4/channel 0, operation 9.
- "SPI program and verify success!", exit 0, 28.45 seconds.
- Programmed SHA-256: b0a18bbe70325319ee0b10599f0cf44b8ee246c2725ae32c2629db023263bd5d.
- No SD re-imaging needed. Actual corrected terminal appearance, HDMI and
  power-cycle behavior not observed by the assistant.

## Arrow-key diagnosis and implementation, 2026-11-02

- Inspected terminal_arrorws.png: Up-arrow CSI bytes appear as `[a` in commands;
  original line editor has no terminal escape parsing or command history.
- Added one-command recall: Up recalls, Down restores the current draft, Enter
  submits. Supports serial CSI/SS3 and extended PS/2 Up/Down. Unsupported CSI
  navigation sequences are consumed without becoming game input.
- Backspace now echoes backspace-space-backspace so serial deletion clears the
  character visually as well as deleting it in game input.
- History lives outside saved VM state; SD layout/save format unchanged.
- Added host history/escape regression and full-CPU mixed PS/2/serial recall test.
  Validation/build pending. Board still runs the previously verified CRLF build.

## Arrow-key bitstream build milestone, 2026-11-02

- ./build.sh completed in sandbox; zero setup/hold violations, unchanged FPGA
  resources and timing. New SHA-256 is in current status and impl/SHA256SUMS.
- Firmware text/data/BSS: 11,668 / 4 / 37,436 bytes; 8 KiB stack guard passes.
- Host history and gameplay checks, peripheral/video/TMDS checks passed.
  Full SDHC/SDSC CPU integration still running. No new programming performed.

## Arrow-key validation milestone, 2026-11-02

- Full tests/run.sh passed with new firmware: host command recall/draft recovery,
  CSI and SS3 escape handling, unsupported navigation rejection and deletion;
  existing gameplay, save corruption, peripheral/video/TMDS checks all passed.
- Actual processor integration exercised PS/2 extended Up, serial Down, Delete,
  serial SS3 Up and ignored CSI Right, then Enter submitted recalled LOOK.
- SDHC: 57,550,261 cycles; SDSC: 57,557,834; each 356 reads, 41 writes,
  57 CRLF pairs. Save/restore and reset persistence transcript assertions passed.
- Bitstream manifest verified. Not programmed; explicit new programming request
  needed. SD card and existing saves do not need changing.
- New screenshot shows aligned serial output on previously flashed CRLF build.

## Command-history flash programming milestone, 2026-11-02

- User explicitly requested upload; all impl/SHA256SUMS checks passed.
- Ran unchanged ./program_flash.sh with escalated direct USB hardware access.
- GW2AR-18C ID 0x0000081B; flash 0x0B4017; cable 4/channel 0, operation 9.
- Programmer reported "SPI program and verify success!", exit 0, 29.89 seconds.
- Programmed bitstream SHA-256:
  1de915b6e274d80c984be9231e91db33889c96bd67dc545654a1e83806add560.
- No SD image changes. Arrow-key operation, HDMI and physical power-cycle
  persistence of this build have not yet been observed.

## Terminal background observation, 2026-11-02

- Inspected background.png: serial terminal has irregular gray highlighting over
  portions of startup text, consistent with terminal text selection or retained
  terminal attributes. This is not an HDMI screenshot.
- Current startup sends plain text; status_put inverse bit writes only HDMI RAM.
  Both latest CPU integration serial logs contain zero ESC bytes and no control
  bytes other than backspace, tab, CR and LF. No firmware color commands found.
- Recommend clearing mouse selection by clicking blank terminal space; if it
  persists, close/reopen the terminal session to clear retained display state.
- No source/bitstream changes or programming performed for this observation.
  Clearing the highlight on the user's terminal remains unconfirmed.

## Startup terminal attributes correction, 2026-11-02

- User explicitly reports nothing was selected and highlighting appears on
  startup. Previous selection diagnosis was unconfirmed and is withdrawn.
- Only background.png is currently available locally; requested terminal app
  and launch command while continuing investigation.
- Firmware had no serial terminal initialization. Added startup-only ANSI SGR
  reset, explicit white-on-black, clear screen and cursor home before banner
  or SD errors. These bytes go directly to UART, not HDMI text RAM.
- This addresses inherited terminal attributes/stale screen contents; actual
  cause of the screenshot remains unproven pending terminal details/observation.
- Added full CPU startup-stream assertions at both initial boot and reset;
  unexpected gameplay ESC bytes rejected. Full tests running; build pending.
- No SD/save format changes or board programming performed.

## Terminal startup bitstream build milestone, 2026-11-02

- ./build.sh passed in sandbox, zero setup/hold violations, unchanged resources
  and timing. Bitstream SHA-256 is recorded in current status/impl/SHA256SUMS.
- Firmware text/data/BSS: 11,724 / 4 / 37,436 bytes.
- Full CPU tests still running. No programming performed. Physical background
  behavior remains unconfirmed; root cause has not been established.

## Terminal startup validation milestone, 2026-11-02

- Full tests/run.sh passed, including exact serial attribute reset/color/clear/
  home sequence before text at both boot and reset, no later gameplay ESCs.
- SDHC: 57,634,649 CPU cycles; SDSC: 57,642,222; each 356 SD reads, 41 writes
  and 57 checked CRLF pairs. Command history, gameplay, save corruption, reset
  persistence, peripherals/video/TMDS checks all passed. Manifest hashes match.
- New build not programmed. Physical background resolution unverified.
  Awaiting user terminal details; only background.png was locally available.

## Terminal initialization flash programming milestone, 2026-11-02

- User explicitly requested uploading the updated bitstream. Manifest checks passed.
- Ran unchanged ./program_flash.sh outside sandbox with approved direct USB access.
- GW2AR-18C ID 0x0000081B; SPI flash 0x0B4017; cable 4/channel 0, operation 9.
- Programmer reported "SPI program and verify success!", exit 0, 29.91 seconds.
- Programmed SHA-256:
  8c3c47b23f4d022dcbcbaf8473eaf50810b525a70a2d1bfadfe0eb80284f6d09.
- SD card unchanged. Actual startup background, HDMI and power-cycle behavior
  of this build have not been observed by the assistant.

## Gray ANSI palette background correction, 2026-11-02

- Updated background.png now shows a uniform dark-gray background after previous
  startup initialization. User confirms white-on-gray, wants black.
- Previous firmware explicitly selected SGR 40 (ANSI palette black). Earlier
  screenshot has true black outside drawn text; consistent with theme palette
  color 0 being gray while terminal default background is black.
- Changed startup SGR 37;40 to 37;49: retain white foreground and restore terminal
  default background before clearing screen. Does not modify host palette/theme.
- Added regression applying actual full CPU startup bytes to a terminal model
  with gray palette-black and black default, verifying clear occurs on black.
- Full tests running. Build pending; board still has previous 40-background build.
  Actual user terminal app/theme details and physical fix remain unconfirmed.

## Default-background bitstream build milestone, 2026-11-02

- ./build.sh passed in sandbox, zero setup/hold violations. FPGA resources,
  timing and firmware sizes unchanged (11,724 text / 4 data / 37,436 BSS).
- New bitstream SHA-256 recorded in current status and impl/SHA256SUMS.
- Full CPU simulations still running. Not programmed. SD image unchanged.
- ANSI default background semantics verified against primary xterm.js docs:
  https://xtermjs.org/docs/api/vtfeatures/ (SGR 49).

## Default-background validation milestone, 2026-11-02

- Full tests/run.sh passed. Regression processes actual CPU UART startup bytes
  using a gray palette-black / black default model: both initial boot and reset
  clear on black, normal attributes and homed cursor in SDHC/SDSC runs.
- CPU cycles unchanged: SDHC 57,634,649; SDSC 57,642,222. Each 356 reads,
  41 writes, 57 checked CRLF pairs. Existing gameplay/history/save/video/TMDS
  checks passed. impl/SHA256SUMS verified. No SD or save-format changes.
- New bitstream not programmed; actual black background awaits hardware check.

## Default-background flash programming milestone, 2026-11-02

- User explicitly requested upload. All impl/SHA256SUMS checks passed.
- Ran unchanged ./program_flash.sh with approved direct USB access outside sandbox.
- GW2AR-18C ID 0x0000081B; flash 0x0B4017; cable 4/channel 0, operation 9.
- "SPI program and verify success!", exit 0, 29.95 seconds.
- Programmed SHA-256:
  273d64ac85f56a2e71c6e06e15f6baa2d63e80b272d89f093e0aab1370abf4df.
- SD unchanged. Actual default-background appearance, HDMI and physical
  power-cycle persistence of this build remain unobserved by the assistant.

## Host terminal palette diagnosis and correction, 2026-11-02

- User reports SGR-49 build still renders gray. Prior terminal-model test assumed
  default black survives the serial program's rendering; that assumption did not
  establish actual terminal behavior and is insufficient as physical validation.
- Inspected local Terminator configuration and installed defaults. Active default
  profile inherited palette color 0 #2e3436 while default background is #000000.
  Updated screenshot's dominant background is exactly RGB(46,52,54) = #2e3436.
- Prepared a one-line profile palette override and reviewed its diff. With explicit
  escalated approval (config outside project sandbox), changed only palette color
  0 to #000000 in /home/donh/.config/terminator/config. Other 15 colors/settings
  preserved. Original config: impl/terminator-config.before-black.
- Ran terminator --reload successfully, exit 0. Parsed config and compared against
  backup/defaults: only palette black differs, now true black. No board programming
  or bitstream changes needed. User observation of new background still pending.

## IDE project preparation milestone, 2026-11-02

- User requests opening project in Gowin IDE. Existing zork.gprj already selected
  correct FPGA and RTL/constraints, but GUI process settings lived only in impl/.
- Added checked-in ide/zork_process_config.json using verified build settings,
  plus prepare_ide.sh to restore missing process settings without overwriting
  GUI changes and validate all source/asset paths and memory image sizes.
- Added firmware C/assembly/linker files and all three memory images as disabled
  Other Files in zork.gprj. RTL still reads initialized RAM/font/text directly;
  these files are not compiled as Verilog. Device and programming unchanged.
- README now documents opening zork.gprj, GUI synthesis/place-route, output path,
  and separate firmware compilation after C/assembly changes.
- Shell syntax and current project/asset checks passed. Fresh-copy IDE-equivalent
  build validation pending. No hardware programming or new behavior observed.

## IDE project validation milestone, 2026-11-02

- Prepared a fresh copy at /tmp/zork-ide-validation-2bbot7vy with no impl output;
  ran prepare_ide.sh from /tmp to verify caller-independent paths. Re-running
  preparation preserved existing process settings byte-for-byte.
- Opened fresh zork.gprj with installed Gowin engine and ran all with no Tcl
  set_option overrides: synthesis/place-route/bitstream succeeded. Saved GUI
  settings selected zork_top, output zork, initialized BSRAM and text timing report.
- No RISC-V compiler was invoked; firmware.hex supplied all initial CPU RAM.
- Initial reuse of CLI check_build.py could not create its manifest because it
  expects a compiled firmware .bin; a GUI FPGA-only build intentionally has none.
  Checked timing/bitstream directly instead: zero setup/hold violations,
  unchanged resources/Fmax, configuration payload byte-identical to programmed
  bitstream (only //Created Time comment differs).
- Logs: impl/ide-validation.log and impl/ide-validation-result.txt. Current root
  bitstream manifest still verifies. No board programming or GUI desktop launch.
- User can now open /home/donh/fpga/zork/zork.gprj directly in Gowin FPGA Designer.

## Project licensing milestone, 2026-11-02

- User requests Apache licensing instead of MIT, with copyrighted Zork data
  explicitly excluded. No existing license or LICENSE file was present on disk.
- Created uppercase LICENSE with full Apache 2.0 text from installed standard
  license, copyright 2026 Don H., and clear original-project licensing scope.
- Explicitly excludes zork1.dat and story copies in SD/generated images; no
  permission to redistribute or relicense game data is granted by this file.
- Preserves third-party ISC/PicoRV32 and DejaVu license notices. README links
  LICENSE and third-party licensing details. Verified complete standard text
  is present unchanged. No firmware/build/board changes or GitHub publication.

## Serial score/moves diagnosis and implementation, 2026-11-02

- User reports no score/moves during testing and clarifies this is via serial.
- Confirmed status_put wrote only HDMI RAM; UART never received status updates.
- Added serial status flush with labeled Score and Moves. ANSI/VT100 startup
  reserves row 1 and scrolls rows 2 through the terminal bottom; save/restore
  cursor keeps the existing command prompt intact. Status remains plain white
  on default background; HDMI retains its inverse row. Requires >=80 columns.
- SD layout and VM snapshot structure unchanged. No programming performed.
- Adding host score/moves and full CPU terminal rendering regressions; build
  and validation pending. Physical serial appearance remains unverified.

## Serial status bitstream build milestone, 2026-11-02

- ./build.sh passed in sandbox; setup/hold violation counts both zero.
- Firmware text/data/BSS: 11,908 / 4 / 37,516 bytes; stack guard passes.
- Latest deliverable hash is in impl/SHA256SUMS. Host gameplay, including
  nonzero score/moves matching SCORE output, and peripheral/video/TMDS passed.
- SDHC/SDSC processor/terminal simulations still running. No programming.

## Serial status validation milestone, 2026-11-02

- Full bash tests/run.sh passed. SDHC 59,259,822 cycles, SDSC 59,267,395;
  each 356 reads/41 writes, 57 CRLF pairs and ten serial status updates.
- Native walkthrough reached nonzero points and verified status score/moves
  match the game's SCORE response. Existing gameplay/history/save corruption
  tests, peripherals, two video scans and 100,000 TMDS symbols all passed.
- Terminal model processes actual CPU UART bytes for 24/32-row screens, verifies
  status remains on row 1 during scrolling, cursor restoration, initial moves,
  NORTH increments, RESTORE rollback, reset to zero and black startup background.
- Bitstream manifest verified after tests. No programming performed. New status
  needs a separately requested flash upload and physical terminal observation;
  HDMI and power-cycle hardware validation remain pending. SD/saves unchanged.

## Serial status flash programming milestone, 2026-11-02

- User explicitly requested bitstream upload. All impl/SHA256SUMS checks passed.
- Ran unchanged ./program_flash.sh with escalated direct USB hardware access.
- GW2AR-18C ID 0x0000081B; SPI flash 0x0B4017; cable 4/channel 0, operation 9.
- Programmer reported "SPI program and verify success!", exit 0, 29.92 seconds.
- Programmed bitstream SHA-256:
  e9917fbee1046e0af1162530462c2a2e8c4fce33f3e5b7a192f52a785468d032.
- SD card/saves unchanged. Serial score/moves rendering, HDMI and physical
  power-cycle persistence remain to be observed; programming/readback alone
  does not validate those behaviors.

## Combined terminal header implementation, 2026-11-02

- User's updated zork_startup_screen.png confirms serial status is visible,
  but shows duplicate project labels and counters too far left.
- Combined project title into the fixed header: ZORK I - Tang Nano 20K at left,
  Score and Moves at right. Removed standalone startup project-title line;
  original story title/copyright remain intact.
- Serial horizontal cursor positioning anchors counters to actual terminal
  width with one blank right margin; HDMI uses its 80-column row. No terminal
  size query or input parsing changes. SD/save format unchanged.
- Expanded actual UART rendering checks to 80/100/132 columns and checks for
  duplicate startup title. Build/tests pending. No new programming performed.

## Combined header build milestone, 2026-11-02

- ./build.sh passed in sandbox with zero setup/hold violations. Manifest in
  impl/SHA256SUMS updated for the combined-title/right-aligned-counters build.
- Host gameplay/save/history and peripheral/video checks passed. Full CPU
  integration and serial layout regressions still running. No programming.
- Board remains on e9917fbee1046e0af1162530462c2a2e8c4fce33f3e5b7a192f52a785468d032;
  user screenshot confirms prior serial status display but requests new layout.

## Combined header validation milestone, 2026-11-02

- Full bash tests/run.sh passed: host score/moves and gameplay, history/save
  corruption regressions, peripherals, two video scans, 100,000 TMDS symbols,
  and full CPU SDHC/SDSC integration.
- SDHC 59,133,875 cycles; SDSC 59,141,448; each 356 reads, 41 writes,
  55 checked CRLF pairs and ten complete header updates.
- Actual UART rendering at 80/100/132 columns and 24/32 rows verifies single
  project-title header, counters ending one column before right edge, fixed row
  during scrolling, cursor restore, score/moves and save/restore/reset behavior.
- Build passed with unchanged FPGA resources/timing; firmware text/data/BSS
  12,128 / 4 / 37,516 bytes. All manifest hashes verify after tests.
- New bitstream not programmed. SD card/saves unchanged. Await separately
  requested upload and physical serial/HDMI/power-cycle observation.

## Combined header flash programming milestone, 2026-11-02

- User explicitly requested upload. All impl/SHA256SUMS checks passed.
- Ran unchanged ./program_flash.sh outside sandbox with approved USB access.
- Target GW2AR-18C ID 0x0000081B; SPI flash 0x0B4017; cable 4/channel 0;
  external flash erase/program/verify operation 9 unchanged.
- Programmer reported "SPI program and verify success!", exit 0, 30.06 seconds.
- Programmed SHA-256:
  2d82e3def8b96e770c5175faa6362420e4cb7a89b70c55ee73e0f707d151d21a.
- SD card and saves unchanged. Physical appearance of combined serial header,
  HDMI and actual power-cycle persistence remain unverified by observation.

## Serial header hardware observation and GitHub preparation, 2026-11-02

- User confirms corrected formatting and supplies updated zork_startup_screen.png.
- Inspected screenshot: 186x22 terminal, single ZORK I - Tang Nano 20K header
  at left, Score: 0 / Moves: 0 at far right, black background and intact prompt.
  This confirms actual serial appearance, independently of flash readback.
- Updated README screenshot description and hardware-validation notes, plus
  BUILD_RESULT. Preparing firmware/test/documentation/screenshot changes for
  publication to origin/main, dandydonh/tang-nano-20k-zork.
- Latest full build/tests passed before programming; documentation-only update
  does not alter bitstream. SD images/save data and local tool/board-reference
  files are not part of this update. HDMI, PS/2, SD save/restore and physical
  power-cycle persistence remain unvalidated.
