# FAT storage build and validation

Updated 2026-11-04 for Tang Nano 20K, GW2AR-LV18QN88C8/I7, revision C.

The firmware now loads `/ZORK/ZORK1.DAT` and saves to two existing 32 KiB files,
`/ZORK/SAVEA.BIN` and `/ZORK/SAVEB.BIN`, on FAT16/FAT32. Unrelated files may
share the filesystem. The original restricted FAT layer follows fragmented
cluster chains at boot and writes only save-file data sectors during gameplay;
it never modifies FAT tables, directories or FSInfo. The existing alternating
snapshots, commit-header-last writes and integrity/fallback checks are retained.

No migration is required or implemented. The new firmware requires FAT files;
the previous raw-format card image remains untouched and works only with the
previous bitstream. No physical card was written by the assistant. The new board-programming result
is recorded under Hardware status below.

## Deliverables

- FPGA bitstream: `impl/pnr/zork.fs` (7,262,008 bytes), SHA-256
  `7969727e9ea432b9bd2e3fe3ecd40bd4d7c8cd6c50314652c900be0c6e98c71b`.
- Initialized firmware: `assets/firmware.hex`; sources under `firmware/`.
- Fresh FAT32 disk image: `assets/zork-fat.img`, 68,157,440 bytes (65 MiB),
  containing a 64 MiB FAT32 partition, the supplied story and blank save files.
- File-copy preparation: `python3 scripts/make_sd.py --directory EXISTING_DIR`
  creates `ZORK/`; refuses an existing game directory. Copy that directory onto
  a FAT card. Generated images also refuse existing paths.
- Usage, supported layouts and limits: `README.md`. No physical device writes
  are performed by the preparation script. Story data and SD images are excluded
  from project licensing/distribution as described in `LICENSE`.

## Firmware memory

RV32IM GCC 14.2.0, `-Os`, freestanding, unified 64 KiB initialized RAM:

| Item | Bytes |
| --- | ---: |
| Text | 15,264 |
| Data | 4 |
| BSS | 39,808 |
| End of static allocation | 55,076 (`0xd724`) |
| Linker limit reserving 8 KiB stack | 57,344 (`0xe000`) |
| Remaining room before that limit | 2,268 |

The original 16 KiB story cache is retained. Added storage state includes the
308-entry sector map, a directory/BPB buffer and a single-sector FAT cache.
The cache avoids rereading the same FAT sectors for successive cluster links.
The unified-RAM ELF RWX segment warning is expected for this FPGA.

## Filesystem and native validation

- Existing gameplay/history/status regression passes on FAT16, including
  nonzero score/moves, story checksum, cross-process restore, corrupt-newest
  fallback and failure of both snapshots without modifying live state.
- FAT16/FAT32, each with superfloppy and MBR layouts, pass with all three files
  fragmented and unrelated VFAT long filenames. Whole-image comparisons prove
  writes remain inside the two save files; story, allocation metadata and
  unrelated file contents remain unchanged.
- Independent `mkfs.fat` and `mtools` images pass with multi-sector clusters and
  game directories spanning multiple clusters. `fsck.fat -n` passes before and
  after save/restore. Long-named files remain accessible with mtools.
- All 41 sector-boundary interruptions during SAVE preserve the previous valid
  snapshot. Corrupted headers and payloads fall back. A complete save commits.
  This models software-visible interruptions, not card-internal power failures.
- 19 invalid-media cases plus read failures reject mounting without writes;
  checks cover missing/wrong-sized/read-only files, malformed BPBs, short/free/
  bad/out-of-range/cyclic chains, project-file and directory overlap, and raw
  legacy media. Additional checks cover active FAT32 table selection, invalid
  FAT32 versions/root clusters/active FAT indexes, MBR extent bounds, API bounds,
  failed-remount permission revocation and existing-output preservation.
- Original peripheral, video and TMDS checks pass: SPI/UART bytes, PS/2 parity/
  break/timeout, two complete video scans, and 100,000 TMDS symbols.
- Shell syntax and IDE project/file preparation checks pass. Firmware storage
  sources are included under Other Files in `zork.gprj`.

## FPGA implementation and processor integration

Gowin V1.9.11.03 Education synthesis/place/route/bitstream generation passed
in the normal sandbox, using the firmware above. The firmware build followed
by `gw_sh scripts/build.tcl` and `scripts/check_build.py` runs the same build
stages as `./build.sh`.

| Item | Result |
| --- | --- |
| Logic | 2,966 / 20,736 |
| Registers | 1,217 / 15,750 |
| BSRAM | 37 / 46 |
| CPU routed Fmax | 82.782 MHz (27 MHz target) |
| Pixel routed Fmax | 147.659 MHz (74.25 MHz target) |
| Minimum setup / hold slack | +6.696 ns / +0.227 ns |
| Setup / hold violated endpoints | 0 / 0 |

Resources and routed timing are unchanged from the raw-format build. Hashes
are recorded in `impl/SHA256SUMS`. The processor fixtures exercise fragmented
FAT16 over SDHC and SDSC, plus an MBR FAT32 SDHC image; the model rejects writes
outside the mapped save files. All fixtures exercise gameplay, SAVE/RESTORE and
restore after reset. The complete `bash tests/run.sh` passed on the final
firmware, including all native/filesystem/peripheral/video/TMDS checks and
terminal rendering at 80/100/132 columns and 24/32 rows.

| Processor fixture | CPU cycles | SD reads | SD writes |
| --- | ---: | ---: | ---: |
| Fragmented FAT16, SDHC | 68,740,466 | 382 | 41 |
| Fragmented FAT16, SDSC | 68,751,449 | 382 | 41 |
| Fragmented FAT32, MBR, SDHC | 69,403,612 | 390 | 41 |

Each run checks boot, PS/2 LOOK/history, serial input/history, SAVE, movement,
RESTORE, reset and RESTORE again, ten fixed-header updates and 55 CRLF pairs.
The metadata cache reduces the FAT16 integration run from 982 SD reads in the
initial uncached implementation to 382. Manifest verification passed again
after the suite rebuilt firmware; the tested binary matches the FPGA build.
Only the first 4 MiB of the FAT32 image is backed by simulation RAM; all accessed
metadata and file sectors lie in that region, and out-of-range reads fail.

Logs: `impl/fat-filesystem-tests.log`, `impl/fat-tests.log`,
`impl/soc-verilator.log`, `impl/soc-sdsc.log`,
`impl/soc-fat32.log`, `impl/fat-build.log` and the Gowin reports under `impl/pnr/`.

## Hardware status

The FAT bitstream was programmed into persistent flash on 2026-11-04 at the
user's explicit request, after the user reported preparing a FAT card.
All manifest hashes passed before programming. The unchanged `./program_flash.sh`
ran with approved direct USB access: GW2AR-18C ID 0x0000081B, flash 0x0B4017,
cable 4/channel 0, operation 9. Programmer reported **SPI program and verify
success**, exit 0, 28.65 seconds. Programmed SHA-256:
`7969727e9ea432b9bd2e3fe3ecd40bd4d7c8cd6c50314652c900be0c6e98c71b`.

Programming/readback is verified. On 2026-11-04 the user also confirmed that
SAVE/RESTORE works on physical hardware with the prepared FAT card, establishing
actual FAT startup and save/restore operation. The user subsequently confirmed
save persistence across physical power cycles with this FAT build. Physical
preservation of unrelated files remains unconfirmed.
The previous raw-format release had user-confirmed serial/HDMI output, SD
save/restore and power-cycle persistence; those observations do not validate
this FAT build. PS/2 input remains physically unverified. The programmer script,
target device and flash operation are unchanged.

## Fresh FAT32 image hash

```text
34c74aeca534cc05d702a2d3fb3fd27539ff79e3e0d67b3c9f90c93dbbd7ab29  assets/zork-fat.img
```
