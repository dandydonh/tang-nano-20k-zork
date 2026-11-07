# SDRAM V3/V5 loader: build and validation

Updated 2026-11-07 for Tang Nano 20K, GW2AR-LV18QN88C8/I7, revision C.

This build loads the selected V3 or V5 story into integrated SDRAM, supports the full
16-bit writable-memory boundary, accepts legacy trailing file padding and uses
larger streaming snapshots. Current source corrects screen/memory output-stream selection and adds player-selected save positions,
with five per game and automatic same-stem `.sav` creation. Up to 1,000 DAT/Z3/Z5 entries in `/ZORK` can be selected
through UART or PS/2 with decimal labels and multi-digit input; a single compatible file starts automatically. This is a
memory-capacity expansion, not a complete Z-machine conformance claim.

## v0.6.5 preview package

The v0.6.5 preview packages the optimized automatic-save bitstream and the
unchanged Madman V3 and Mars, 2049 AD V5 stories. Release assets are `zork.fs`,
`madman.z3`, `mars2049ad.z5`, `STORY_NOTICES.md` and `SHA256SUMS`. The checksum
file covers the bitstream, both stories and their notices. Both story binaries
also remain in the tagged source under `story/` with their distribution terms.
No SD image, save file, copyrighted Zork data or private test input is included.

The bitstream is the exact sandbox-built image that passed persistent flash
programming/readback on 2026-11-07. Its SHA-256 is
`44be65544a6534f81250860846e5275791c495e472319d5ebf5be93ee0d1e2bd`.
Native/fault/independent FAT checks and focused CPU save/reset/restore passed;
physical optimized timing/restore/HDMI/power-cycle behavior remains unobserved.

## Faster initial save, 2026-11-07

First sidecar creation now writes only the four checked metadata sectors and
all ten bank commit-header sectors, plus FAT/directory updates and the selected
snapshot. Previously it zeroed every payload sector in the 1,312,768-byte file.
Unused payload retains previous card contents; it is inaccessible as a snapshot
until its payload is fully written and a checked header commits it. Directory
extension clusters remain completely zeroed before linking. Save file format,
size, five positions, two-bank recovery and existing sidecars are unchanged.

Native bundled Mars R8/250121 first SAVE drops from **2,618 to 68 sector writes**
(97.4% fewer); later SAVE stays at 29. Reset/restore in position five recovers
score 1 and standing state. This is a write-count comparison, not measured
physical speed. A new recycled-cluster test pre-populates valid snapshots for
this same story in both banks of all five positions, deletes/recreates the
file on the same chain, and verifies all old headers are invalidated. Corrupting
the sole new snapshot cannot resurrect an old bank. Generic fixture first SAVE
is 60 writes instead of 2,610; native/CPU test setup guards against >=100 writes.

The entire FAT16/FAT32 sidecar suite passes, including independent filesystem
checks, fragmented allocation, directory growth, read-only/full media, write
bounds, metadata replicas, interrupted and torn writes. Existing FAT/indexed
regressions pass. Logs: `impl/fast-save-native-tests.log`,
`impl/fast-save-fat-regressions.log`, `impl/fast-save-indexed-regressions.log`,
`impl/fast-save-mars-check.log`. Focused actual-CPU validation passes with
no writes on play/cancel, first-save creation, fifth-position save/reset/restore,
and no writes on RESTORE: **86,270,417 cycles / 164 reads / 60 writes**.
The previous otherwise identical fixture used 323,667,958 cycles / 164 reads /
2,610 writes. Simulation walltime is 85.069 seconds; this includes boot, menu
interaction and reset/restore, not just SAVE latency. Evidence:
`impl/auto-save-cpu.log`, `impl/fast-save-cpu-test.log`.
The full processor suite was not rerun.

Sandbox synthesis/place-route/timing pass with zero setup/hold violations.
Firmware text/data/BSS: **44,404 / 28 / 11,012 bytes**; stack guard passes.
Bitstream SHA-256:
`44be65544a6534f81250860846e5275791c495e472319d5ebf5be93ee0d1e2bd`.
Evidence: `impl/fast-save-build.log`, `impl/SHA256SUMS`.

This optimized bitstream passed persistent flash programming/readback on
2026-11-07 after explicit user request and successful manifest verification.
Unchanged ./program_flash.sh used approved direct USB access, GW2AR-18C ID
`0x0000081B`, cable 4/channel 0, flash `0x0B4017`, operation 9. Programmer:
"SPI program and verify success!", exit 0, 30.02 seconds.
Programmed SHA-256:
`44be65544a6534f81250860846e5275791c495e472319d5ebf5be93ee0d1e2bd`.
User confirmed faster subsequent saves and screenshots showed position five
recognized as Saved on the previous build. Optimized physical initial timing,
save/restore, HDMI and power-cycle behavior remain unobserved. Existing sidecars
remain compatible; measuring first creation requires a new sidecar.
No physical SD files, programming script, commit/push or release changed.

## Automatic per-story saves, 2026-11-07

Current source creates a same-stem `.sav` after the first confirmed SAVE.
Each new file is 1,312,768 bytes: two indexed headers, two owner-record copies, five positions
and two 128 KiB snapshot banks per position.

Missing sidecar reads produce empty positions without writes; play, cancellation
and absent RESTORE do not allocate. Allocation verifies free clusters and FAT
mirrors, supports FAT16/FAT32 active/mirrored mode and fragmented free space,
updates valid FSInfo copies to unknown hints, and grows the ZORK directory when
needed. VFAT records and collision-free short aliases preserve full ASCII names.
Non-ASCII stems and resulting names exceeding 255 units refuse save setup;
existing foreign/malformed/read-only sidecars are preserved. Metadata permission
is scoped to one synchronous sector write. The short directory entry publishes
the initialized file last. Reported earlier errors trigger best-effort rollback.
Power loss can leave orphan allocations, incomplete LFNs or mismatched mirrors;
a torn publication can require filesystem repair. This is not a journaled FAT
writer or a claim of universal creation atomicity.

SDRAM creation scratch: cluster list at `0x300e0000..0x300e2817` and directory
sector list at `0x300e4000..0x300e5fff`, disjoint from existing caches and VM.
Firmware text/data/BSS: **44,368 / 28 / 11,012 bytes**; the stack guard passes.
Sandbox synthesis/place-route/timing pass with zero setup/hold violations.
Bitstream SHA-256:
`475bb881c6b797a95db54b8d1877c53642638565a7910db0a6d90371c80323de`.
Evidence: `impl/sidecar-build.log`, `impl/SHA256SUMS`.

Native tests pass FAT16/FAT32 with MBR/superfloppy layouts, independent
mkfs/mtools/fsck, V3/V5 reset/restore, five positions, 255-unit names, alias
collisions, directory growth, 2,564 isolated free clusters, full/read-only cards,
active FAT isolation, malformed/foreign metadata, snapshot fallback, 30 selected
power-cut boundaries and 18 failed/torn writes, plus FAT32 FSInfo/backup and
directory-growth tail-link interruption/error cases. The direct storage API test
confirms metadata permission revocation and exactly 512 writable sectors for
the selected snapshot pair. Filesystem checks are clean after normal operation
and recoverable reported errors; abrupt allocation cuts deliberately expose
FAT's documented repair limitations. Evidence: `impl/sidecar-native-tests.log`.
The existing FAT regression passes; broader native checks pass (two optional
private-story checks skip because their files are not in the working copy).
Evidence: `impl/sidecar-fat-regressions.log`, `impl/sidecar-regressions.log`.
Focused actual-CPU SPI/SDRAM simulation passes: play/cancel issue no writes,
first SAVE creates the file, position five saves and restores after reset,
and RESTORE writes nothing. The SPI model permits only the exact FAT/directory/
new-file sectors observed in the independently checked native fixture.
323,667,958 cycles / 164 reads / 2,610 writes; 347.918 seconds simulation walltime.
Evidence: `impl/auto-save-cpu.log`, `impl/sidecar-cpu-test.log`.
The full processor suite was not rerun.

This automatic-save bitstream passed persistent flash programming/readback on
2026-11-07 after explicit user request. All manifest hashes passed before the
unchanged `./program_flash.sh` ran with approved direct USB access. Target:
GW2AR-18C ID `0x0000081B`, cable 4/channel 0, flash `0x0B4017`, operation 9.
The programmer reported "SPI program and verify success!", exit 0, 30.26 seconds.
Programmed SHA-256:
`475bb881c6b797a95db54b8d1877c53642638565a7910db0a6d90371c80323de`.
Physical sidecar creation/save/restore, HDMI and power-cycle behavior for this
exact build remain unobserved. No physical SD files, commit, push or release
were changed. Sections below retain earlier-build evidence.

## Historical build evidence

The dated sections below retain earlier implementation and validation evidence.
Current card usage consists of copying stories into `/ZORK`; the firmware creates
`.sav` files automatically. Earlier storage-format details are not setup steps.

## Paged 1,000-entry story menu, 2026-11-06

Current source discovers up to 1,000 compatible DAT/Z3/Z5 stories, sorted by
full displayed filename. A max heap retains the first thousand during overflow;
an index-only heapsort avoids quadratic copying of long-name records. Invalid
headers do not consume slots and later save-pool entries remain discoverable.

Global selections 1–1,000 work from every page, with four-digit input/editing.
N/P followed by Enter navigates pages without wrapping at either end. Pages
hold at most twenty entries, reduced to account for detected terminal height
and wrapped names within the 32-row HDMI display. Page redraw clears both sinks.
One compatible story still autostarts; a catalog fitting one page retains the
simple existing flow. More than 1,000 compatible stories produce an omission
warning without preventing startup.

The full-name table moves to `0x30100000..0x3014555f` (284,000 bytes); page starts
and sorted indexes use `0x300c0000` and `0x300c1000`. Directory protection uses
`0x300d0000..0x300d7fff`. These are disjoint from VM, undo, sector map, owner
flags and indexed-pool extents. Directory traversal supports 2,048 sectors and
4,096 protected extents, covering a thousand maximum-length VFAT filenames.
The host preparation CLI accepts up to a thousand short-named stories; legacy
save-owner sizing remains separate from story capacity.

New native tests pass on FAT16/FAT32 for all 1,000 candidates, alphabetical
copy-order independence, all fifty normal-height pages, direct selection 1000,
editing/overflow/backspace/arrow handling, N/P boundaries, shorter terminals,
over-capacity warnings and save/reset/restore isolation. An independent mtools
library of 1,000 names of 255 characters passes discovery, wrapped-row page
bounds and fsck.fat. Evidence: `impl/paged-menu-tests.log`. All twelve broader
native programs pass (`impl/paged-menu-native-tests.log`), including indexed
saves, legacy storage, VFAT, gameplay and output/paging checks.

The build passes synthesis, place/route and zero setup/hold
violations. Firmware text/data/BSS are 38,688 / 28 / 10,416 bytes; FPGA usage
remains 3,118 logic units and 37/46 BSRAMs. Build log:
`impl/paged-menu-build.log`. Bitstream SHA-256:

```text
a0e48b1a045991c0666c3ba7a4447e6cbefb0cb9aa09e3074ef4f5f0a8da3fe7
```

Focused actual-CPU integration passes: 1,000 independently allocated FAT32
stories in reverse copy order, UART N/P page navigation, PS/2 selection 1000,
correct last-story execution, and indexed owner claim/save/restore. Result:
277,807,403 cycles / 1,753 reads / 23 writes, with only the owner-index sectors
and selected snapshot pair writable in the SPI model. Evidence:
`impl/paged-menu-cpu.log`. No full processor-suite rerun. Manifest, shell syntax
and whitespace checks pass.

This menu build passed persistent flash programming/readback on 2026-11-06:
GW2AR-18C, cable 4/channel 0, operation 9, flash ID `0x0B4017`; programmer
exit 0 in 30.01 seconds. Physical pagination/PS2/HDMI/save/power-cycle behavior
for this exact build remains unobserved; no SD card files were written.

## Full VFAT story filenames, 2026-11-06

Current source reconstructs and validates VFAT long filenames across directory
sectors/clusters, displays up to 255 characters in the menu/startup/save menus,
and sorts the retained twenty compatible stories by display name. Short aliases
break sorting ties and remain the fallback for missing or invalid long-name
records. Unsupported non-ASCII characters display as `?`; V3's fixed status row
can clip long names. File allocation and save identity are unchanged.

Twenty 284-byte candidates occupy SDRAM `0x30081000..0x3008262f`, after the
save-header index and outside story/dynamic/undo storage. This preserves the
8 KiB native-stack reservation. New native FAT16/FAT32 tests cover fragmented
directories, crossing sectors/clusters, 13/26/255-unit names, corruption fallback,
Unicode substitution, display-name ordering/overflow, V3/V5 and save identity.
Independent mkfs.fat/mtools names pass, as do all eight prior native storage
regression programs. Logs: `impl/long-filename-native-tests.log`.

The FPGA build passes with zero setup/hold violations. Firmware text/data/BSS
are 34,320 / 28 / 20,880 bytes; FPGA usage remains 3,118 logic units and 37/46
BSRAMs. Build log: `impl/long-filename-build.log`; all manifest hashes pass.
Bitstream SHA-256:

```text
6d59a70ace081632e412f968c3ba83494ca9011e67f1fc6d54f701e5a3844389
```

The focused actual-CPU simulation passes in 54,450,350 cycles: genuine VFAT
records for twenty-one stories, SDRAM table/sorting/overflow, selecting the
twentieth entry, reset, and selecting a 255-character first name. The card
receives no writes. Evidence: `impl/long-filename-cpu.log`. A separate native
check selects the supplied `mars2049ad.z5` under its full name and reaches HELP
(`impl/long-filename-bundled-story.log`). No full processor-suite rerun.

This bitstream passed persistent flash programming/readback on 2026-11-06:
GW2AR-18C, cable 4/channel 0, operation 9, flash ID `0x0B4017`; programmer
exit 0 in 30.03 seconds. Physical full-name menu/play, HDMI, physical SD
saves and power-cycle behavior for this exact build remain unobserved.

## Graceful story-library overflow, 2026-11-06

Current source skips invalid headers before counting menu slots, retains the
alphabetically first twenty compatible DAT/Z3/Z5 files independently of copy
order, and warns how many compatible files were omitted. A larger library no
longer prevents startup. Discovery continues through additional directory entries.
Menu labels remain consecutive; one compatible story starts automatically.
The save identity/pool format and twenty-owner save capacity are unchanged.

New native FAT16/FAT32 regressions pass for overflow, invalid files before and
after valid files, reversed copy order, all three extensions, V5 execution,
save/reset/restore with a late save pool, unchanged story allocations, and
single/empty/all-invalid libraries. Existing V3/V5, FAT, save-slot, gameplay,
boot-menu and extension native regressions all pass. Evidence:
`impl/story-overflow-native-tests.log`. No new RTL or full processor regression
run was performed for this firmware-only change.

`./build.sh` passes synthesis, place/route and timing with zero setup/hold
violations. Firmware text/data/BSS are
33,732 / 28 / 21,440 bytes; FPGA usage remains 3,118 logic units and 37/46
BSRAMs. Evidence: `impl/story-overflow-build.log`; manifest checks pass.
Bitstream SHA-256:

```text
eff751ffc0729c395134070476b3f0dc6ce1328306baf326d3dd3e21329aa4f2
```

This build passed persistent flash programming/readback on 2026-11-06 using
the unchanged script: GW2AR-18C, cable 4/channel 0, operation 9, flash ID
`0x0B4017`; programmer exit 0 in 30.36 seconds. Physical overflow menu/play,
HDMI, SD save/restore and power-cycle checks remain pending.

## DAT/Z3/Z5 discovery build, 2026-11-06

Current source discovers `.dat`, `.z3` and `.z5` files in `/ZORK`, with
case-insensitive extension matching and one combined twenty-story limit.
Two-character extensions display without FAT padding. Header validation still
determines whether a file is a supported V3/V5 story. The SD preparation tool
accepts all three extensions with its existing maximum eight-character stem.
Story identities and save-pool formats are unchanged, so changing an extension
preserves saves. The published v0.5.0 bitstream remains DAT-only.

`./build.sh` passes synthesis, place/route and timing, with **zero setup and hold
violations**. Firmware text/data/BSS are 33,712 / 28 / 21,516 bytes; FPGA usage is
3,118 logic units and 37/46 BSRAMs. Build log:
`impl/story-extensions-build.log`. Bitstream SHA-256:

```text
cdcc59984b2658048c22c728b5698503279b61737ba2d24ac4e70b305d5433c1
```

New native regressions cover mixed DAT/Z3/Z5 menus on FAT16/FAT32, V3/V5
execution, saves and restore after extension renaming, unchanged story bytes,
case handling, unsupported suffixes, invalid headers, the combined file limit
and CLI staging. Existing native V3/V5, FAT and save-slot regressions pass.
Both bundled stories reach their openings under their Z3/Z5 extensions in the
host interpreter. SDRAM, peripheral, video and TMDS simulations pass, as do
the SDHC and SDSC processor cases for boot, gameplay, saves and reset restore.
The longer full processor suite was stopped after those two cases; its remaining
cases and final CPU paging/resize checks were not completed for this build.

This bitstream passed **persistent flash programming and readback verification**
on 2026-11-06 using the unchanged programming script: GW2AR-18C, cable 4/channel
0, operation 9, flash ID `0x0B4017`; programmer exit 0 in 30.15 seconds.
Physical three-extension discovery/play, HDMI, keyboard, SD save/restore and
power-cycle behavior for this build remain unobserved. The dated release and
hardware evidence below refers to earlier builds.

## v0.5.0 prerelease package (historical)

The [v0.5.0 prerelease](https://github.com/dandydonh/tang-nano-20k-zork/releases/tag/v0.5.0)
packages the earlier dynamic V3/V5 build, bitstream `93dfa647...268615`.
This section records publication history. Current card usage is documented in
[automatic per-story saves](README.md#automatic-per-story-saves); copy stories
into `/ZORK` and the current firmware creates their save files automatically.

## Dynamic V3 serial layout, 2026-11-05

V3 serial output now wraps at the detected terminal width minus one column,
independently of HDMI's 79-column transcript. Paging uses the serial height,
reserving one status row and one prompt row, without the previous 32-row cap.
Cursor-preserving ANSI size queries run at startup, before line commands and
after MORE acknowledgements. Successful V3 queries refresh the scrolling area;
already printed text is not reflowed. No-response fallback is 80x18; subsequent
failed queries retain the last detected size. Typeahead, arrows, CRLF and late
size replies are handled without becoming unintended commands. V5 retains its
fixed 79x32 windows and needs a serial terminal at least 80x32.

The 3200-byte save-header sector index moves to unused SDRAM at 0x30080000,
after the undo bank. Discovery fills the table before it is read; snapshot and
SD layouts are unchanged. The reserved 8 KiB C stack is retained.

Final `./build.sh` passes synthesis, placement/routing and setup/hold checks.
Resources remain 3118 logic and 37 BSRAM. Firmware text/data/BSS:
**33548/28/21516 = 55092 bytes**, 2252 bytes before the stack boundary.
Bitstream SHA-256:
`93dfa647e0a920ffa000e0cff692dd89b39af925742c228357b60d810b268615`.
Firmware SHA-256:
`03b702896b680c4805d441a7c8122af5904087020968a2d9457c31e55c0674a0`.
Build log: `impl/dynamic-final-build.log`.

Board-backend tests render 20/60/80/100/149/180/300-column UART output with
terminal autowrap off and on, preserve HDMI's margin, and erase wrapped input
at each width. They cover live 35-to-18-row paging, retained sizes after a
failed query, interleaved arrows/typeahead, delayed replies, bounded malformed
replies and V5 page limits. Exact private Zork III preserves the complete
introduction at 80/100/149/180 columns in a 35-row terminal. The original V3/V5
native gameplay, storage, save/restore and peripheral/video checks pass.
The final binary's actual-CPU resize fixture passes 149x35 -> live 100x18 ->
reset at 100x18: nine size replies, two MORE pauses, complete text and three
LOOK commands. Logs: `impl/dynamic-cpu.log`, `impl/dynamic-cpu-tests.log`.
All eight broader first-build processor regressions and serial/V5 rendering
checks pass, including maximum-memory V3, selected saves, and V5 at 377562252
cycles / 1870 reads / 145 writes. Final malformed-reply/long-word hardening is
separately checked with the final backend/native tests and final CPU resize
fixture. The guard build's isolated twelve-paragraph paging/save/reset CPU
fixture also passes. See `impl/dynamic-tests.log`,
`impl/dynamic-final-paging-tests.log` and PROGRESS.md for the build distinction.

This build was programmed at the user's explicit request with unchanged
`./program_flash.sh` and approved direct USB access: GW2AR-18C ID 0x0000081B,
flash 0x0B4017, cable 4/channel 0, operation 9. The programmer reports
**SPI program and verify success**, exit 0, 30.46 seconds. Persistent flash
now contains 93dfa647...268615, superseding 76d41088...2c07c.
Programming/readback is verified. The user reports improved serial appearance,
with all text disappearing when the terminal is resized. This was reproduced
in installed Minicom 2.10 using a simulated serial port: resizing alone emits
screen-clear commands with no board traffic. Minicom's resize handler closes
and recreates its display window. A new `scripts/serial_terminal.py` launcher
forwards UART/ANSI bytes directly to the desktop terminal, preserving its display
on resize. Four PTY tests cover repeated resizing, size replies, keys, exit,
termination and disconnect cleanup. No FPGA rebuild or reprogramming was needed
for this client fix. Physical launcher use, HDMI and power-cycle behavior remain
to be observed for this build. No physical SD data was changed.

## MORE paging build, 2026-11-04 (previous programmed build)

That firmware pauses long V3 and V5 lower-window output at `[MORE]`.
Space/Enter through UART or PS/2 resumes output without submitting a game
command. An initial ANSI cursor report detects terminal height (maximum 32);
the bounded no-response fallback is 18 rows. Status/upper rows and one prompt
row are reserved. V5 retains its fixed 79x32 screen requirement; resize during
play requires reset. Terminal and HDMI display use the same page pauses.

`./build.sh` passes synthesis/place/route and setup/hold checks. Resources:
3118 logic, 37 BSRAM. Firmware text/data/BSS: **32384/16/24604 = 57004 bytes**,
340 bytes before the reserved-stack boundary. Bitstream SHA-256:
`76d410881095b1828e2bb32dacf349e3c68957ee48d864c2ddbab190f992c07c`.
Firmware SHA-256:
`887ee7a414b0a38c01c999efe492100d2b795fb0fab020698cca2209cc1ee39d`.
Logs: `impl/paging-final-build.log`, `impl/paging-tests.log`.

Exact private Zork III startup passes page-boundary and complete-text checks
at 4/18/24/32 rows. Tests using the actual board backend pass height query,
fallback, UART/PS2 acknowledgement, CRLF handling, prompt restoration,
automatic wraps and V5 upper/lower-window separation. A final-firmware
actual-CPU run also passes two real UART page acknowledgements, complete
long paragraphs, wrapped editing, save/restore and reset: **75123001 cycles /
364 SD reads / 21 writes**. Its firmware binary is byte-identical to the final
FPGA build; logs are `impl/paging-cpu.log` and `impl/paging-cpu-tests.log`.
All eight broader processor regressions on the first paging build pass,
including V5 at **337284236 cycles / 1870 reads / 145 writes**. The first
runner invocation stopped at a test parser that rejected the new size query;
after updating the parser, all remaining transcript/terminal checks pass on
the completed CPU logs. The dedicated final-firmware paging CPU test is now
included in `tests/run.sh`, alongside the board-backend and optional private
Zork III checks. This paging bitstream was programmed at the user's request
using unchanged `./program_flash.sh` with approved direct USB access:
GW2AR-18C ID 0x0000081B, flash 0x0B4017, cable 4/channel 0, operation 9.
The programmer reports **SPI program and verify success**, exit 0, 30.17 seconds.
Programming/readback is verified; paging appearance, UART/PS2 acknowledgement,
HDMI and physical power-cycle behavior remain unobserved for this build.
No physical SD data was changed. This supersedes the V3/V5 programming below.

## V5 source build, 2026-11-04

Current source adds V5 packed addresses, objects/properties, call variants,
dictionary and input formats, table/extended instructions, one-level undo,
two-window cursor/erase/inverse output, and persistent save/restore. V5 logical
images fit in 256 KiB; trailing padding remains protected. V3 retains its
status/header and snapshot layout. V5 uses `ZMV6` snapshots with stream/screen
state and version-separated ownership within the unchanged save pool.

`./build.sh` passes synthesis, placement/routing and setup/hold checks.
Firmware text/data/BSS: **31492/16/24592 = 56100 bytes**, leaving 1244 bytes
before the linker's reserved-stack boundary. Bitstream SHA-256:
`ad979aea67a64c1f3048095dfb4c6dcb8ccc9a54cdc8b189da8415595c19d47e`.
Firmware SHA-256:
`d08455194883d03baa3e8a93b88073a220899bf70a59be8908f2391b7d4c67d5`.
Logs: `impl/v5-build.log`, `impl/v5-tests.log`.

Native original V5 bytecode passes high calls/text beyond 128 KiB, seven call
arguments, objects above 255, 48 attributes, long property headers, nine-character
dictionary entries, shifts/tables, undo and save/reset/restore. Independent
Frotz execution passes. Mixed V3/V5 saves and lossless pool expansion pass.
Optional private Hitchhiker's Guide V5 release 31 and Beyond Zork V5 release 57
pass startup, sampled gameplay, save/restore and fresh-process restore, with
independent Frotz narrative checks. Screen-grid tests cover independent
cursors, inverse cells, lower scrolling, erase and wrapped backspace.
Full `bash tests/run.sh` exits 0, including all eight processor fixtures,
SDRAM/peripherals/video/TMDS and final transcript/terminal checks. The V5 CPU
run verifies a 256 KiB story, 65,535 dynamic bytes, high calls, inverse upper
text-RAM cells, undo and save/reset/restore: **331387490 cycles / 1870 reads /
145 writes**. V3 CPU results (cycles/reads/writes): FAT16 SDHC
122980646/758/40; SDSC 122994821/758/40; FAT32 124120651/760/40; menu
129869327/796/40; maximum-memory 225666169/1360/145; wrapping 66062108/364/21;
selected saves 145831196/684/42.

Additional native checks pass all 145 maximum-memory V5 interrupted-save
boundaries, corrupted-screen-trailer fallback, two selected positions, ANSI
arrow keys, maximum/preloaded input, custom alphabets and CATCH/THROW. Rendered
native screens for both supplied games and actual V5 CPU UART checks pass.
Address/undefined-behavior sanitizers pass the maximum-memory original program
and both private V5 samples (leak checking disabled for the ptrace environment).
The runner now includes these additional separately verified native/display
checks; no firmware changed during final validation.

V5 controls the full fixed 79x32 display; serial terminals need at least 80x32.
Beyond Zork 57/871221/c5ad uses standard-described ASCII IBM border conversion.
Fonts 1/4 use the same fixed font. Font 3, color, bold/italic, accented glyphs,
timed input, sound, transcript/command files and auxiliary-file save/restore
are unavailable; full-game playthroughs have not been verified.

This V5 build was programmed into persistent board flash at the user's explicit
request with approved direct USB JTAG access. The unchanged script used
GW2AR-18C ID 0x0000081B, flash 0x0B4017, cable 4/channel 0, operation 9.
The programmer reports **SPI program and verify success**, exit 0, 30.28 seconds.
Programming/readback is verified; physical V3/V5 gameplay, windows, HDMI, PS/2,
save/restore and actual power-cycle behavior remain unobserved for this build.
No physical SD files were changed. The V5 build has not been published and the
published V3-only v0.4.0 assets remain unchanged. Historical build hashes/results
below refer to V3 and are superseded by this programming status.

## Output streams correction

`output_stream` now selects screen output (1) and memory output (3). Memory
capture takes precedence over the screen, stores raw ZSCII with newline 13,
ignores initial table counts and publishes the byte count when closed. Sixteen
nested tables resume independently. Capture bypasses display wrapping and the
selected display window. Bounds and nesting errors halt with clear messages.
Screen selection also controls story input echo. Streams 2/4 remain unavailable:
positive selections report that limitation, and transcript Flags 2 bit 0 stays
clear even after direct story writes. No transcript/command files are created.

Focused native original-bytecode tests pass screen routing, pending-word flush,
null/raw characters, numeric/text/newline output, nested/upper-window/long text
capture, sixteen levels, bad bounds and excess nesting. Active nested captures
and screen-off selection survive SAVE/RESTORE. Restoring a legacy-layout save
and RESTART reset routing correctly. Independent Frotz comparison agrees on
nested-table counts/newline bytes and suppression of captured text. The actual
CPU wrapping fixture verifies those counts/bytes at boot and reset; final
terminal/wrapping assertions and all seven CPU runs pass. Full `bash tests/run.sh`
and `./build.sh` exit 0. Logs: `impl/streams-tests.log`, `impl/streams-build.log`.
Optional private-story regressions skip because their inputs are absent.

The stream-fix bitstream was programmed into persistent flash at the user's
explicit request using the unchanged script with approved direct USB access.
GW2AR-18C ID 0x0000081B, flash 0x0B4017, cable 4/channel 0, operation 9.
Programmer reports **SPI program and verify success**, exit 0, 30.43 seconds.
Board flash now contains
`d0bb5fccbbe331262fac20bcabb25abb8b41739e10f83fab929af1d99dbac705`.
Programming/readback is verified. Physical streams/gameplay/HDMI/PS2/slot UI
and actual power-cycle persistence of this build remain unobserved. No physical
SD card writes occurred. This current status supersedes historical
board-state statements below.

## Deliverables and card contents

- `impl/pnr/zork.fs`: FPGA bitstream; the newest build/hash is recorded above.
- `assets/firmware.hex`, with ELF/bin/map under `impl/firmware/`.
- A FAT16/FAT32 card containing compatible `.DAT`, `.Z3` or `.Z5` stories in
  `/ZORK`. The first confirmed SAVE creates a matching `.sav` beside each story,
  with five positions and two-bank recovery. No PC save-file preparation is needed.

Keep the card inserted during play. Back up wanted `.sav` files with the board
powered off. See the main README for automatic-save behavior and validation limits.

## Memory and SDRAM controller

The original 27 MHz controller exposes the integrated 8 MiB SDR SDRAM on the
PicoRV32 wait-state bus at `0x30000000..0x307fffff`. Firmware and native stack
remain in 64 KiB initialized block RAM. The first 256 KiB of SDRAM holds a
pristine story; mutable bytes start at `0x30040000`, with a V5 undo cache at
`0x30060000`. Restart copies the initial
dynamic region from the pristine image; VERIFY reads the pristine image.
Story reads and game writes retain their logical/dynamic bounds checks.

The SDRAM runs at 27 MHz on the opposite clock edge, with CAS=2, BL=1,
auto-precharge and masked 32-bit writes. A 200 us power-up delay precedes
precharge, two refreshes and mode configuration. Refresh takes priority between
transactions and continues during input waits, SD transfers and held CPU
requests. The controller allows at least two clocks for tRCD/tRP, four for
refresh recovery and two for write recovery. Gowin's reserved top-level port
names map to dedicated internal memory pads; no board wiring is added.

Startup waits for initialization, tests walking data, all byte lanes, all
address lines and the final SDRAM word before mounting the SD card. A failed
check stops with an SDRAM error. The generated opposite-edge clock and SDRAM
I/O delays are constrained; successful static timing does not establish actual
hardware data retention or I/O behavior.

| Firmware allocation | Bytes |
| --- | ---: |
| Text | 22,860 |
| Data | 4 |
| BSS | 24,344 |
| End of static allocation | 47,208 (`0xb868`) |
| Linker limit retaining 8 KiB native stack | 57,344 |
| Remaining room before that limit | 10,136 |

The 2,048-word Z stack and 96 call frames remain in block RAM. There is no SD
story cache: the complete logical image is loaded once. The unified-RAM ELF
RWX warning is expected. Firmware binary SHA-256:
`09da2fe7d0aee16a52d97bbd9310610414770c96ce3b7f1496a3470ae96d6986`.

## Padded files and persistent saves

Logical V3 images range from 64 bytes through 128 KiB; V5 supports up to
256 KiB. Physical DAT files may
contain trailing bytes, up to a bounded 1 MiB allocation. A nonzero header
length must declare an image within the file and its version's limit. Zero-length
headers use actual EOF, which must fit that limit. The loader follows and
protects the entire physical chain, including padding, while executing only
the logical image. Unsupported versions and invalid layouts are rejected.

The current per-story `.sav` has five positions with two 128 KiB snapshot banks
each. Metadata and every bank header are initialized on first creation; payload
sectors are written when saved. The following snapshot details retain the
validation history of the earlier streaming implementation.
`ZMV5` snapshots
stream actual dynamic bytes plus interpreter stack/frames through one 512-byte
buffer. A compile-time bound ensures maximum state fits. Payload checksums are
verified before changing live state; payload sectors precede the commit header.
The stream fix retains the previous payload layout for default routing. With
screen output disabled or a memory stream active, a 68-byte trailer records
screen selection and up to sixteen memory table addresses/counts. This reader
accepts both sizes; old firmware cannot restore a snapshot with that trailer.
Only the selected pair's data sectors are writable. FAT/directory/FSInfo data,
stories, other slots and unrelated files remain untouched.

Ownership uses release, serial, checksum, logical size and dynamic size. Names
and trailing padding do not affect ownership. Unknown occupied slots are
preserved; mixed/duplicate ownership disables writes. Missing, wrong-size,
read-only or full pools permit gameplay with saves disabled. Directory bounds,
exact chain validation and FAT16/FAT32 MBR/superfloppy support are retained.

## Validation

Completed native/controller checks:

- Existing Zork gameplay, history, status/score, checksum, alternating saves,
  corruption fallback and cross-process reset/restore.
- Variable logical images from 4 KiB through the full 128 KiB, partial sectors,
  fragmented allocations, high-memory strings and old zero-length headers.
- Padded images with writable regions of 12,289, 16,384, 32,768, 49,152, 65,534
  and 65,535 bytes. The fixture checks its last writable byte on every input
  loop; saves restore both VM state and that byte after restart.
- All **145** interrupted-write boundaries of a maximum-memory save, plus all
  **40** boundaries of the supplied Zork snapshot. Previous committed state
  survives each interruption; completed saves advance to the new state.
- Menu editing, twenty-story selection, isolated ownership, renames, logical-size
  identity independent of padding, full/conflicting pools and old-pool rejection.
- FAT16/FAT32 independent mkfs.fat/mtools, VFAT coexistence, fragmentation,
  multi-sector directories, fsck and byte checks for unrelated-file preservation.
  Invalid media, geometry, chains, read errors, API bounds and permission revocation.
- Independent SDRAM command model checks initialization, bank/row/column mapping,
  CAS latency, command spacing, byte masks and refresh deadlines. Controller tests
  exercise data/address bits, continuous traffic, idle retention, held requests
  without duplication and reset/reinitialization.
- SPI/UART/PS2 tests, two video scans and 100,000 TMDS symbols.

Optional private-file validation (`python3 tests/test_local_stories.py`) passes
for the supplied Lurking Horror, Moonmist and Planetfall V3 releases. Original
padded files are unchanged. Each reaches its opening prompt, processes basic
commands, saves/restores, restores after a new process and uses an isolated
slot with a verified snapshot checksum. These are short native tests, not full
game playthroughs or FPGA hardware observations. Private files remain ignored
under `inspect_files/` and are not included in the project or release assets.

Gowin synthesis/place/route and static timing pass:

| FPGA item | Result |
| --- | --- |
| Logic | 3,118 / 20,736 |
| Registers | 1,347 / 15,915 |
| BSRAM | 37 / 46 |
| CPU / pixel routed Fmax | 83.331 / 170.773 MHz |
| Minimum reported setup / hold slack | +7.612 / +0.425 ns |
| Setup / hold violations | 0 / 0 |

All seven processor integrations pass with current firmware and the SDRAM
command model. The six legacy-flow fixtures use 5 MiB/single-position pools.
The new position-selection fixture uses a 10 MiB/two-position pool, selects
positions through UART and PS/2, saves different game states, declines an
overwrite, cancels without extra writes and restores position 2 after reset.
Native tests separately cover five/default and twenty/maximum player positions.
The maximum-memory fixture checks code/strings beyond 64 KiB, the last writable
byte and the largest tested snapshot. The SD model permits only the test
story's expected save pairs and rejects accesses beyond its 16 MiB backing.

| Processor fixture | CPU cycles | SD reads | SD writes |
| --- | ---: | ---: | ---: |
| Fragmented FAT16, SDHC | 117,518,204 | 758 | 40 |
| Fragmented FAT16, SDSC | 117,532,905 | 758 | 40 |
| Fragmented FAT32, MBR, SDHC | 118,658,356 | 760 | 40 |
| UART boot / PS2 reset menu selection 19 | 124,400,536 | 796 | 40 |
| Padded image, 65,535 writable bytes | 206,928,579 | 1,360 | 145 |
| Long paragraphs / wrapped input erase | 63,601,771 | 364 | 21 |
| Player-selected saves / cancellation / reset restore | 142,539,525 | 684 | 42 |

Full `bash tests/run.sh` completes with exit 0 for this build. Transcript,
terminal/status/menu rendering at 80/100/132 columns and wrapping at
80/100/132/180 columns with autowrap off/on all pass. All processor runs use
host -O3 and the one-billion-cycle watchdog. No production clock or RTL changes
accompany these settings. Bounding the story's physical sector range avoids
unneeded per-sector overlap comparisons; fragmented/overlapping allocation
checks remain covered. A redundant full-pool remap is also avoided for owner 0.

## Explicit word wrapping update

The serial screenshot from the programmed SDRAM build shows long Lurking Horror
paragraphs cut off at the right edge of a 180-column Minicom terminal. Serial
output previously contained no line breaks for these paragraphs; only HDMI
performed character wrapping. The exact terminal autowrap setting was not read.

The new shared formatter buffers story words and sends explicit line breaks
within 79 columns to both displays, leaving one unused column on an 80-column
terminal. It preserves normal word boundaries, splits overlong words without
losing bytes and flushes incomplete prompt words before input/status operations.
Input echo stays immediate. Erasing a wrapped input uses matching serial cursor
motion and HDMI row/column changes. Status updates bypass transcript wrapping.
No terminal settings, story data, SDRAM RTL or save format changed.

Focused formatter tests pass with autowrap disabled/enabled at 80/100/132/180
columns, long words, exact boundaries, explicit/blank lines, indentation, prompt
flush and 119-character input erasure across a wrap. Native/private-story tests
pass; all serial body lines stay within 79 characters, and startup paragraphs
match independent Frotz after whitespace normalization. Native FAT/save,
maximum-memory interruption and peripheral/video/controller checks also pass.
The focused real-CPU regression passes long paragraphs and wrapped input through
the actual UART/HDMI backends, SAVE/RESTORE and reset: **55,107,786 cycles,
282 SD reads, 21 writes**. The processor model rejects non-space writes in the
reserved HDMI margin. Actual UART bytes render without clipping at widths
80/100/132/180 with autowrap disabled or enabled, and all paragraph words remain.
The test paces repeated Backspace keys to allow each key's three echo bytes to
finish within the existing 16-byte receive FIFO. An initial unpaced test exceeded
that FIFO; pacing the test traffic resolved it without changing input hardware.

The original SDRAM and wrapping processor results are historical; the table
above records the current twenty-story rerun. The wrapping change uses unchanged hardware,
with passing synthesis/routing/timing and matching resource counts. Current
bitstream/firmware hashes and allocation above refer to the twenty-story build,
which also includes wrapping and alphabetical sorting.
Logs: `impl/wrap-build.log`, `impl/wrap-tests.log`,
`impl/wrap-private-tests.log`, `impl/wrap-serial-tests.log`, `impl/soc-wrap.log`.

## Alphabetical story menu

Candidates are sorted case-insensitively by displayed FAT short filename before
header validation and numbered selection. Each candidate moves with its file
allocation, preserving number-to-story mapping. Save identities remain independent
of menu position. Native tests cover reversed copy order, each selectable story,
directory reordering with existing saves, renames and capacity/layout checks.
The full native V3 suite (including all 145 maximum-memory save interruptions)
and all supplied private-story regressions pass. Synthesis/routing/timing pass;
hardware resources and save format are unchanged. That version of the processor menu fixture
selected ZORK1 as entry 2 after BETA. This small sorting change has native coverage;
the processor evidence at that stage came from preceding builds. The table
above now records the expanded-capacity rerun. Historical logs:
`impl/alphabetical-tests.log`, `impl/alphabetical-build.log`.

## Selectable player save positions

SAVE and RESTORE list numbered saved/empty positions, accept shared UART/PS2
numeric editing, Enter for position 1 and 0/q to cancel. Occupied saves require
explicit y confirmation; declined overwrites and empty restores return to
selection. The menus do not modify the story input buffer or command history.
Saved labels recognize headers; RESTORE checks complete payloads and falls back
to the older valid bank. The VM snapshot format itself is unchanged.

Native FAT16/FAT32 tests pass for five positions, different game states,
independent game/position writes, fresh-process restore, rename/reorder
continuity, UI cancellation/invalid input/backspace, declined/accepted overwrite,
corrupted-newest fallback and all 21 selected-position interruption boundaries.
Additional tests pass for lossless old-pool expansion, all twenty story owners,
the final pair of an expanded pool, two-digit position 20, and cross-position
mixed/duplicate ownership refusal. Storage API tests verify remapping revokes
writes to the previous position and failed remount revokes every write.
Logs: `impl/save-slot-final-tests.log`, `impl/selectable-saves-tests.log`.
Optional private story inputs are absent in this checkout, so their current
regression skips; earlier recorded private-story results are historical.

Gowin build passes with unchanged hardware resources/timing; manifest hashes
verify. All seven CPU integrations and final terminal assertions pass; full runner exits 0. The new bitstream is local,
not programmed or published. Board remains on released adc72860...fabd1dd;
physical slot menus, HDMI/PS2 and expanded save/power-cycle behavior remain
unverified. No physical card writes, programmer changes or release updates.

## Twenty-story menu and save capacity

Menu discovery and persistent ownership now each support 20 entries. Decimal
labels and two-digit editing work through shared UART/PS/2 input. The image
builder allocates directory chains for the expanded list and rejects full images.
Synthesis/place/route and setup/hold checks pass. Native FAT16/FAT32 fragmented
storage, independent formatter tests and all 40 Zork save interruptions pass.
All 20 choices and save identities pass FAT16/FAT32 native tests, including
fresh-process restores, multi-digit editing, capacity rejection and lossless
legacy expansion. All 145 maximum-memory save interruptions, boot rediscovery,
private-story regressions and controller/video/peripheral checks pass. All six
processor checks pass, including UART and PS/2 selection 19, maximum-memory
saves and reset restore. Full runner exits 0. Logs:
`impl/menu20-build.log`, `impl/menu20-fat-tests.log`, `impl/menu20-tests.log`.
The twenty-story bitstream was subsequently programmed and readback-verified
as recorded below. Physical behavior of this capacity change remains unverified.

## Hardware and publication status

The preceding SDRAM bitstream was programmed into persistent flash on 2026-11-04 at the
explicit request to update the board. All manifest hashes passed first. The
unchanged `./program_flash.sh` ran with approved direct USB JTAG access:
GW2AR-18C ID 0x0000081B, SPI flash 0x0B4017, cable 4/channel 0, operation 9.
The programmer reported **SPI program and verify success**, exit 0, 32.78 seconds.
Programmed SHA-256:
`54f1ebdc34549ff43e6e475dfc3154d36975974f42a189a3ea11f5f0eafeab87`.

Programming/readback is verified for that preceding build. The supplied
screenshot confirms physical SDRAM startup, menu selection and Lurking Horror
opening text on serial. Expanded saves, HDMI behavior and power-cycle persistence
still await observation.

The wrapping build was subsequently flashed and verified at the explicit request
to flash the board: unchanged script, target and operation, successful readback,
exit 0, 33.01 seconds. The board now contains SHA-256
`c4672775104492167c999acc2f25b87fcbb571bebcbe9129041fe834ec50f1ed`.
Actual wrapping/HDMI/save/power-cycle behavior of that build awaits observation.
The latest alphabetical-menu bitstream was then flashed at the explicit request
to update the board. All manifest hashes passed first; the unchanged script ran
with approved direct USB access on the same device/cable/channel/operation.
The programmer reported **SPI program and verify success**, exit 0, 33.03 seconds.
The board now contains SHA-256
`b83e5eb913d5110505ca88c072b58ac8c3d61126d3273860d9e057ee7eb2863f`.
Programming/readback is verified; actual alphabetical menu, wrapping, HDMI,
save/restore and power-cycle behavior of this build await observation.
Earlier fixed-story FAT save/power-cycle/HDMI observations do not establish
those behaviors for this build. Physical PS/2 input remains unverified.

No physical card writes, programmer/device changes, Git push or release
publication have been performed for the SDRAM implementation.

Fresh example image SHA-256:
`ecf36bab18ce14f997ad1775c698641b05fb28b18d0eef4e87cee2bb279e6f0f`.

## Twenty-story flash programming, 2026-11-04

At the user's explicit request, programmed persistent flash using the unchanged
script with approved direct USB JTAG access: GW2AR-18C ID 0x0000081B, flash
0x0B4017, cable 4/channel 0, operation 9. All manifest hashes passed first.
Programmer reports **SPI program and verify success**, exit 0, 31.42 seconds.
Board now contains `adc72860f024bd2fa48a392d1c545186afb1653caf7910bfb76fd0f07fabd1dd`.
Programming/readback is verified; physical expanded menu, HDMI, save/restore and
power-cycle behavior await observation. SD files were not modified.

## v0.3.0 publication

The source and the programmed twenty-story bitstream were published as the
v0.3.0 SDRAM V3 preview. Its release page/assets have been superseded by v0.4.0;
the [historical source commit](https://github.com/dandydonh/tang-nano-20k-zork/tree/6ea7a1991247396884790c52132377e8e137ea6a)
remains in Git history. Its release attachments were `zork.fs` and `SHA256SUMS`.
No story files or SD images are attached. V5 remains unsupported. The supplied
hardware serial screenshot confirms directory discovery/menu rendering through
entry 19; it does not validate expanded saves, HDMI or PS/2 on this build.

## v0.4.0 prerelease

The selectable-save and output-stream build is distributed as the
[v0.4.0 prerelease](https://github.com/dandydonh/tang-nano-20k-zork/releases/tag/v0.4.0),
with its bitstream and checksums. Current usage is the automatic `.sav` workflow
in the main README.
This is the exact tested and
flash/readback-verified bitstream identified above. Previous release pages and
assets and tags are removed at the user's request. Only v0.4.0 remains.
No story data or SD image is attached. Physical behavior of this build remains
unobserved as described above.
