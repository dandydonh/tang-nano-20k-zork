# Zork I on Tang Nano 20K

A dedicated Zork appliance for the Sipeed Tang Nano 20K (GW2AR-18C,
GW2AR-LV18QN88C8/I7). No operating system or external computer runs the game.
The FPGA contains a PicoRV32 processor and a bare-metal Z-machine V3 interpreter.
It runs the not supplied `zork1.dat`, release 88 / serial 840726.


## Clone this project

```bash
git clone https://github.com/dandydonh/tang-nano-20k-zork.git
cd tang-nano-20k-zork
```

See the build instructions below for required tools,
FPGA programming, and SD card preparation.

Zork I story data is not included.


Download the prebuilt FAT bitstream and checksum from the
[v0.2.0 release](https://github.com/dandydonh/tang-nano-20k-zork/releases/tag/v0.2.0).

The bitstream is **`impl/pnr/zork.fs`**. This firmware reads story and save
files from a **FAT16/FAT32 microSD card**, alongside your other files.
The story is on SD; firmware is in the bitstream. The FAT build has been
programmed and verified, and the user confirms SD save/restore and persistence
across power cycles work on hardware. The earlier raw-format release was also
verified for serial and HDMI output.
PS/2 input still needs hardware validation. See [build and validation results](BUILD_RESULT.md).

The original project code is licensed under Apache 2.0; see [LICENSE](LICENSE).
Zork story data (`zork1.dat` and copies in SD images) is copyrighted third-party
material and is excluded from that license. Other third-party components retain
their own licenses; see [third_party/README.md](third_party/README.md).

## Play

<table>
  <tr>
    <td width="1676">
      <a href="zork_startup_screen.png">
        <img src="zork_startup_screen.png" width="1676" height="280" alt="Zork serial startup screen with a single project title at left and score and moves at right">
      </a><br>
      <!-- Nonbreaking spacer keeps GitHub's table from shrinking the screenshot. -->
      <samp aria-hidden="true">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</samp>
    </td>
  </tr>
</table>

[Open the full-size screenshot](zork_startup_screen.png). Scroll horizontally
above to see the full terminal at its original size.

Serial output from the Tang Nano 20K after the corrected firmware was flashed.
The fixed header shows `ZORK I - Tang Nano 20K` on the left and **Score** and
**Moves** at the terminal’s right edge; the game transcript scrolls below it.

1. Prepare a FAT16/FAT32 microSD card with the `ZORK` directory described
   below. Existing unrelated files can remain on the card. The older raw-format
   bitstream/release requires its old card image; it cannot use these FAT files.
2. Insert the card into the board's microSD slot. Leave it inserted during play.
3. Connect HDMI to a display accepting 1280x720 at 60 Hz, or use serial I/O.
4. Connect a keyboard using either method below, and program the new
   `impl/pnr/zork.fs` when ready. The existing `./program_flash.sh` uses device
   GW2AR-18C, cable 4, channel 0, flash operation 9.
5. Press the reset button on package pin 88 if necessary. The game opens at
   West of House. Enter commands such as `look`, `open mailbox`, `read leaflet`.

Type `save` to save, and `restore` to load the latest valid save. There is one
logical save slot with two alternating physical snapshots for recovery. Saves
persist on the SD card across reset and loss of board power. 
Save format is private to this firmware, not Frotz/Quetzal compatible.

### Standalone PS/2 keyboard

Use a PS/2 keyboard supporting scan code set 2, through a **3.3 V-safe PS/2
adapter**. A USB keyboard with a passive adapter only works if the keyboard
itself supports PS/2. A generic USB-only keyboard needs an external host adapter;
this core does not implement a USB host.

| Signal | FPGA package pin / header label |
| --- | --- |
| PS/2 clock, adapter's 3.3 V side | 25 |
| PS/2 data, adapter's 3.3 V side | 26 |
| Ground | GND |

PS/2 keyboards commonly use 5 V power and pull-ups. Do not connect 5 V signals
to the FPGA pins; use bidirectional open-drain level shifting and appropriate
pull-ups. Pins 25/26 refer to the board labels, not connector position numbers.
The receiver is input-only, so keyboard LEDs and host commands are not supported.
US layout letters, numbers, punctuation, Shift, Caps Lock, Enter and Backspace
are supported. Up recalls the last nonempty command; Down restores your draft.
Press Enter to submit a recalled command. History holds one command in RAM.
Cursor editing is not supported.

### Keyboard through USB serial

Connect the board's programming USB cable to a computer and open its onboard
serial port at **115200 baud, 8 data bits, no parity, 1 stop bit, no flow control**.
Serial Up/Down support ANSI CSI and SS3 sequences. Unsupported navigation
sequences are ignored; Backspace/Delete removes the last typed character.
Use a terminal with local echo disabled and CR or LF on Enter. Firmware emits
CRLF line endings. With the original LF-only build, Minicom Ctrl+A followed by
U enables "Add carriage return" to correct stair-stepped output. The onboard
BL616 bridge carries serial RX/TX on FPGA pins 70/69. HDMI and serial show the
same transcript. This uses the computer only as a keyboard/display terminal;
the FPGA runs the game. Close the terminal before programming if USB is busy.

At boot/reset, firmware sends ANSI sequences to reset text attributes, select
white text on the terminal's default background, clear the screen and move to
row 2 before the startup banner. The fixed first row shows
`ZORK I - Tang Nano 20K` on the left and score/moves at the right edge of the
terminal, with one blank column of margin. The project title appears only in
this header. Values refresh before each command while the transcript scrolls
below it. Use an ANSI/VT100 terminal at least 80 columns wide with
a black default background. Palette color 0 is deliberately avoided because
some themes render it gray even when the default background is black.
With Minicom inside Terminator, the default background can still resolve to
palette color 0. In Terminator's profile color preferences, set the first palette
color (black) to `#000000` if it is gray. The local default profile has been
corrected this way; its original config is backed up in
`impl/terminator-config.before-black`.

The UART receive FIFO is 16 bytes; type normally rather than pasting multiple
commands while the game is producing output. PS/2 and serial inputs can both
be connected. User serial output has been observed in Minicom; PS/2 hardware
remain unverified.

## SD files and preparation

Use a **FAT16 or FAT32** filesystem with 512-byte sectors. A normal FAT32 card
can also hold unrelated files and directories, including VFAT long filenames.
Cards sold formatted as exFAT need a FAT32 filesystem instead; exFAT is not
supported. Formatting removes existing contents, so back them up first.

Create these files in a directory named `ZORK` at the filesystem root:

| File | Size | Use |
| --- | --- | --- |
| `ZORK/ZORK1.DAT` | 92,160 bytes | User-supplied Zork I V3, release 88 / serial 840726 |
| `ZORK/SAVEA.BIN` | 32,768 bytes | Snapshot bank A, initially all zeros |
| `ZORK/SAVEB.BIN` | 32,768 bytes | Snapshot bank B, initially all zeros |

The easiest preparation is to create a staging directory on your computer:

```bash
mkdir -p /tmp/zork-card-files
python3 scripts/make_sd.py --directory /tmp/zork-card-files
```

Copy the resulting **`ZORK` directory** to your FAT card using your normal file
manager, then safely eject it. You can also pass the root of an already mounted
FAT card to `--directory` to create the files there directly. The script refuses
an existing `ZORK` directory so it cannot replace saved games. To back up saves,
copy both save files off the card while the board is powered off.

For a fresh disk-image workflow instead:

```bash
python3 scripts/make_sd.py --output /tmp/zork-fat.img
```

This creates a 65 MiB disk image containing a 64 MiB FAT32 partition and blank
saves. `--fat 16` selects an 8 MiB FAT16 volume; `--superfloppy` omits the MBR.
The script refuses existing image paths and never writes a physical device.
Writing a disk image to a physical card replaces its existing contents; normal
file copying above preserves unrelated files. The former raw `zork-sd.img`
format is unsupported by this firmware. Migration is not included.

### Filesystem behavior and limits

The firmware resolves each file's cluster chain at startup. Fragmented files
work; contiguous allocation is not required. A compact sector map translates
story-cache misses and snapshot operations to file data sectors. This is an
original, restricted FAT implementation in `firmware/storage.c`: it does not
create, resize, delete or rename files, or write FAT tables, FSInfo or directory
entries. Keep both save files at exactly 32 KiB; don't edit them as text.
File timestamps remain unchanged after saving.

Each save includes dynamic memory, evaluation stack, call frames, locals, PC
and random generator state. The inactive snapshot's payload is written before
its commit header, and each SD write waits for the card to finish being busy.
A 32-bit FNV-1a hash is checked before restoring. A corrupted newest snapshot
falls back to the previous valid bank. Keeping allocation metadata unchanged
reduces filesystem exposure, but card-internal flash behavior still limits
power-loss guarantees. Save files remain private snapshots, not Quetzal files.

Supported layouts: an unpartitioned FAT volume (superfloppy), or the first
supported FAT16/FAT32 primary partition in an MBR. FAT12, exFAT, GPT and logical
partitions in extended partitions are unsupported. Project paths use fixed 8.3
names; other long-named files are ignored. Cluster sizes of 1–128 sectors are
accepted. Each root/game directory chain is limited to 256 sectors (4,096
entries, including long-filename records). File chains must match their file
sizes, rounded to clusters. Malformed or overlapping project chains, wrong file
sizes, missing files and read-only save files cause a startup error. Use a
healthy filesystem; the firmware does not run a whole-volume filesystem check.

The SPI driver supports SD v1/v2 initialization and SDSC byte addressing or
SDHC/SDXC block addressing. Clock starts at 337.5 kHz, then rises to 3.375 MHz.
Reset after inserting a card. The firmware caches sector mappings until reset:
**do not hot swap the card or modify it from another device while playing**.
Power the board off before moving the card to your computer.

## Build and test

### Open in Gowin FPGA Designer

From this directory, run `./prepare_ide.sh`, then select **File > Open** in
Gowin FPGA Designer and open **zork.gprj**. The local IDE executable is
`/home/donh/IDE/bin/gw_ide`. The current checkout is already prepared.

The project selects **GW2AR-LV18QN88C8/I7**, device revision **C**, with
**zork_top** as the top module and **zork** as the output base name. It includes
all nine Verilog sources and the board pin/timing constraints. Memory images
and firmware sources appear under Other Files; they are excluded as synthesis
inputs, but the RTL loads the three memory images through `$readmemh`.

Run **Synthesize**, then **Place & Route** to generate `impl/pnr/zork.fs`.
The included `assets/firmware.hex` contains the current firmware, so an FPGA-only
IDE build does not require a RISC-V compiler. After editing C or assembly, run
`./scripts/build_firmware.sh` before rebuilding in the IDE. Gowin does not compile
the firmware sources automatically. Keep the `assets/` directory with the project.

Gowin keeps process settings in `impl/zork_process_config.json`.
`prepare_ide.sh` restores these from `ide/zork_process_config.json` when missing,
while preserving existing IDE settings. Build output and per-user `.gprj.user`
state remain generated files. Opening/building does not program the board.

### Command-line build and validation

```bash
./build.sh
bash tests/run.sh
bash -n build.sh scripts/build_firmware.sh tests/run.sh program_flash.sh
```

Tools: Gowin V1.9.11.03 Education at `/home/donh/IDE` (override `GOWIN_HOME`),
RISC-V GCC/binutils supporting `rv32im/ilp32`, Python 3, native GCC, Icarus Verilog
12 and Verilator 5 with G++/make. Filesystem tests also require `dosfstools`
(`mkfs.fat`, `fsck.fat`) and `mtools` (`mcopy`, `mmd`). Current compiler/simulator installations were
extracted under `/tmp/zork-tools`; these are temporary and may need restoring.
Set `RISCV_PREFIX` to the RISC-V tool prefix, such as
`/opt/riscv/bin/riscv64-unknown-elf-`. `IVERILOG`, `VVP`, `VERILATOR`,
`VERILATOR_ROOT`, and `DFROTZ` can select alternative test tools.

The generated font and initialized RAM hex files are included. Font regeneration
uses Pillow and DejaVu Sans Mono: `python3 scripts/prepare_font.py`.
`./build.sh` compiles firmware, builds FPGA implementation and checks setup/hold
timing. It rejects stale bitstream output. SHA-256 hashes are in `impl/SHA256SUMS`.
The SD generator is separate so builds cannot overwrite saves or card images.

Tests cover native gameplay against Frotz, save/restore across processes,
corrupted snapshots, interrupted saves at every sector boundary, FAT16/FAT32
with MBR/superfloppy layouts, fragmented files, VFAT coexistence, independent
mkfs.fat/mtools images, invalid media and unchanged metadata/unrelated files.
They also cover all SPI/UART byte values, PS/2
parity and timeout recovery, two full video frames and 100,000 TMDS symbols.
A compiled RTL integration test runs the real firmware through the processor,
SPI SDHC and SDSC card models with fragmented FAT16 files and an MBR FAT32
SDHC fixture, PS/2 and UART, then resets and restores from the retained card.

## Design and limits

- 27 MHz RV32IM CPU; 64 KiB on-chip initialized RAM. No SDRAM controller.
- 16 KiB static-story cache; 12 KiB dynamic memory allocation; 2,048-word Z stack;
  96 call frames. Linker reserves at least 8 KiB of native stack.
- HDMI carries DVI-compatible video, no audio. 80 columns by 32 rows, including
  a fixed inverse status row showing score and turns. Glyphs are 8x16 pixels,
  doubled horizontally; console occupies 1280x512 centered in 720p.
- Character wrapping, scrolling, basic line editing. No scrollback or MORE pause.
- Dedicated V3 implementation for this supplied game, not a general Z-machine
  conformance claim. No printer/transcript stream, split window or sound support.
  No complete 350-point playthrough has been validated.
- LED on pin 20 lights when HDMI PLL is locked and CPU has not trapped;
  that does not prove successful HDMI reception or game startup.

Sources and references:
[Z-machine standard](https://www.inform-fiction.org/zmachine/standards/z1point1/),
[PicoRV32](https://github.com/YosysHQ/picorv32),
[Microsoft FAT specification](https://www.scs.stanford.edu/~zyedidia/docs/_other/fat.pdf),
[Sipeed board examples](https://github.com/sipeed/TangNano-20K-example),
[Sipeed board documentation and schematics](https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html).
PicoRV32's ISC license is included in `third_party/PICORV32_COPYING`; the font
license is in `third_party/DEJAVU_COPYRIGHT`. HDMI/TMDS starts from the user's
adjacent `../hdmi_out` design. The supplied game file is retained unchanged.
