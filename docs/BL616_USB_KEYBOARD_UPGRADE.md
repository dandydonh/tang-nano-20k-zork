# Upgrade BL616 firmware for USB keyboard support

This procedure enables the onboard BL616 USB host on a **Tang Nano 20K revision
3923** for the Zork USB keyboard bitstream. It uses FPGA-Companion **v1.4.33**,
the release tested with this project. Linux command examples use Bouffalo's
`BLFlashCommand-ubuntu` tool.

The FPGA and BL616 have separate firmware. Programming Zork's `.fs` file does
not install BL616 firmware. Holding **UPDATE** during power-on enters the BL616
download mode; pressing the button alone does not install anything.

## Firmware and board requirements

The BL616 needs two components:

| Component | BL616 flash address | Purpose |
| --- | --- | --- |
| FPGA Partner | `0x000000` | FPGA programming interface and support for secondary firmware |
| FPGA Companion for `nano20k_v3923` | `0x040000` | USB host, hub and keyboard handling |

Confirm the board revision before selecting firmware. The 3921 and 3923 boards
use different BL616 SPI pins. This guide covers 3923; do not substitute the
generic `nano20k` binary. See the upstream [board revision guide](https://github.com/MiSTle-Dev/.github/wiki/Versions_TangNano20k).

Some early Nano 20K boards cannot run the signed Partner firmware because of
their encryption configuration. Do not change eFuses to force compatibility;
follow the upstream recovery guidance for that board instead. See the
[Partner installation notes](https://github.com/MiSTle-Dev/FPGA-Companion/blob/main/src/bl616/bl616_fpga_partner/README.md).

On the tested 3923 board, the installed Partner already matched the release,
so only Companion needed installation. Do not infer firmware contents from the
USB device name or version string: compare the readback as described below.

## 1 Prepare the files and flashing tool

Use a direct USB data connection from the PC to the board for firmware
installation. Disconnect the keyboard hub and close serial terminal programs.
Keep the original firmware backups somewhere persistent and private.

Download these files from [FPGA-Companion v1.4.33](https://github.com/MiSTle-Dev/FPGA-Companion/releases/tag/v1.4.33)
into one working directory:

- `bl616_fpga_partner_nano20k_v3923.bin`
- `fpga_companion_nano20k_v3923.bin`

Expected SHA256 values for these exact release files:

```text
bc5b1f733a13562c898ff66b540038c116c3d77ca202d0afebd1e7af1c3b3203  bl616_fpga_partner_nano20k_v3923.bin
d4a0f6b0346cdb773b14d65283e8f51c334fb3c2488a4ce34d5c8fde492109dd  fpga_companion_nano20k_v3923.bin
```

Save those two lines as `firmware.sha256`, then run:

```bash
sha256sum -c firmware.sha256
```

Both must report `OK`. These hashes apply to v1.4.33, not arbitrary newer releases.

Obtain the Bouffalo Flash Cube tool with its support files from the
[Bouffalo SDK](https://github.com/bouffalolab/bouffalo_sdk/tree/eba87edced5a03ce8bcad8cf6002494982f83a5f/tools/bflb_tools/bouffalo_flash_cube).
That SDK revision supplied the tool used for the tested installation. Preserve
the tool directory structure, including `chips/`; the executable alone is insufficient.
No firmware compilation is required.

In `chips/bl616/eflash_loader/eflash_loader_cfg.ini` under the tool directory,
check that `[EFUSE_CFG]` has `burn_en = false`. Use section erase (`erase = 1`)
in installation INI files. Do not use whole-chip erase, eFuse programming,
OTP programming, key generation or lock options for this procedure.

Set absolute paths in a terminal, replacing the examples with your locations:

```bash
upgrade_dir=/absolute/path/to/bl616-upgrade
tool_dir=/absolute/path/to/bouffalo_flash_cube
cd "$tool_dir"
./BLFlashCommand-ubuntu --help
```

The following commands run from `tool_dir`. The firmware binaries and INI files
live in `upgrade_dir`; binary paths inside an INI resolve relative to that INI.
For Codex-assisted hardware operations, request direct USB execution outside
the sandbox. Building Zork remains inside the normal sandbox.

## 2 Enter BL616 download mode

1. Disconnect board power, including any powered hub connection.
2. Hold the button marked **UPDATE** on the Nano 20K.
3. Connect the board's USB-C port directly to the PC while holding UPDATE.
4. Release UPDATE after connection.
5. Check that the PC detects **Bouffalo CDC DEMO** and identify its serial port.

On Linux, inspect `lsusb` and `ls -l /dev/serial/by-id/`. Set the actual port:

```bash
bl616_port=/dev/serial/by-id/usb-Bouffalo_Bouffalo_CDC_DEMO-if00
```

That path was present on the tested system; use the path your PC reports.
Do not assume `/dev/ttyACM0` belongs to this board. Resolve connection or access
errors before writing. See [Sipeed's download mode instructions](https://wiki.sipeed.com/hardware/en/tang/common-doc/update_debugger.html).

## 3 Back up the existing firmware twice

Read the first 1 MiB, which covers both firmware regions used here:

```bash
./BLFlashCommand-ubuntu --interface=uart --chipname=bl616 \
  --port="$bl616_port" --baudrate=2000000 --flash --read --start=0x0 \
  --len=0x100000 --file="$upgrade_dir/before-first-1MiB-a.bin"

./BLFlashCommand-ubuntu --interface=uart --chipname=bl616 \
  --port="$bl616_port" --baudrate=2000000 --flash --read --start=0x0 \
  --len=0x100000 --file="$upgrade_dir/before-first-1MiB-b.bin"

wc -c "$upgrade_dir"/before-first-1MiB-*.bin
cmp "$upgrade_dir/before-first-1MiB-a.bin" "$upgrade_dir/before-first-1MiB-b.bin"
sha256sum "$upgrade_dir"/before-first-1MiB-*.bin
```

Each file must contain **1,048,576 bytes**, `cmp` must succeed, and both hashes
must match. Stop if reads are blocked or disagree. Re-enter download mode if
the tool loses the device between operations.

This is a backup of the affected region, not the entire flash chip. The tested
board has 4 MiB of BL616 flash; this procedure leaves the remaining 3 MiB alone.

## 4 Check whether Partner needs installation

Compare the installed Partner bytes with the verified release binary:

```bash
python3 - "$upgrade_dir" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
partner = (p / 'bl616_fpga_partner_nano20k_v3923.bin').read_bytes()
before = (p / 'before-first-1MiB-a.bin').read_bytes()
assert len(before) == 0x100000
print('Partner matches; retain it.' if before[:len(partner)] == partner
      else 'Partner differs; review board compatibility before replacing it.')
PY
```

**If Partner matches, skip to step 5.** This was the path tested on this project.

If it differs, confirm the board supports Partner using the revision and
installation references above. A difference alone does not establish that the
existing firmware is defective. For a compatible board needing Partner, save
the following as `install-partner.ini` in `upgrade_dir`:

```ini
[cfg]
erase = 1
skip_mode = 0x0, 0x0
boot2_isp_mode = 0

[FW]
filedir = ./bl616_fpga_partner_nano20k_v3923.bin
address = 0x000000
```

Install it in download mode:

```bash
./BLFlashCommand-ubuntu --interface=uart --baudrate=2000000 \
  --port="$bl616_port" --chipname=bl616 --cpu_id= \
  --config="$upgrade_dir/install-partner.ini"
```

Check the complete log for successful programming and verification. Power-cycle
without UPDATE held and confirm the normal USB debugger and FPGA programmer
still work. If the board remains in download mode, stop and use the recovery
section. Then re-enter download mode for Companion installation. Replacing
Partner was not required or physically tested during this project's upgrade.

## 5 Install Companion at address 0x40000

Save this as `install-companion.ini` in `upgrade_dir`:

```ini
[cfg]
erase = 1
skip_mode = 0x0, 0x0
boot2_isp_mode = 0

[custom]
filedir = ./fpga_companion_nano20k_v3923.bin
address = 0x40000
```

With the board in download mode, run:

```bash
./BLFlashCommand-ubuntu --interface=uart --baudrate=2000000 \
  --port="$bl616_port" --chipname=bl616 --cpu_id= \
  --config="$upgrade_dir/install-companion.ini"
```

Check the program and verification results and save the log. A generic final
success message alone is insufficient: this tool also prints a success message
after read-only operations.

## 6 Verify an independent readback

While in download mode, read the first 1 MiB again:

```bash
./BLFlashCommand-ubuntu --interface=uart --chipname=bl616 \
  --port="$bl616_port" --baudrate=2000000 --flash --read --start=0x0 \
  --len=0x100000 --file="$upgrade_dir/after-first-1MiB.bin"

python3 - "$upgrade_dir" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
before = (p / 'before-first-1MiB-a.bin').read_bytes()
after = (p / 'after-first-1MiB.bin').read_bytes()
companion = (p / 'fpga_companion_nano20k_v3923.bin').read_bytes()
partner = (p / 'bl616_fpga_partner_nano20k_v3923.bin').read_bytes()
assert len(before) == len(after) == 0x100000
assert after[:len(partner)] == partner, 'Partner mismatch'
assert after[0x40000:0x40000+len(companion)] == companion, 'Companion mismatch'
expected = bytearray(before)
expected[:len(partner)] = partner
expected[0x40000:0x40000+len(companion)] = companion
assert after == expected, 'Unexpected change outside firmware payloads'
print('PASS Partner, Companion and preservation of other bytes in first 1 MiB')
PY
```

An unexpected difference needs investigation; do not continue with repeated
writes. Preserve the backup, readback and tool log.

## 7 Program Zork and test the keyboard

1. Power-cycle normally, without UPDATE held, and confirm the USB debugger returns.
2. Build the USB profile from the Zork repository with
   `bash scripts/build_usb_host.sh`. Normal `./build.sh` builds the PS/2/UART profile.
3. Preserve any previous `impl/pnr/zork.fs`, then copy
   `impl/usb-host/impl/pnr/zork_usb.fs` to `impl/pnr/zork.fs`. Gowin output can be
   read-only; ensure the copy succeeds and compare the two SHA256 hashes before
   programming. Stop if they differ.
4. Confirm the connected board, `GW2AR-18C` device, cable index 4 and channel 0
   match `program_flash.sh`, then run `./program_flash.sh` with direct USB access.
   It erases, programs and verifies FPGA external flash. Leave its settings unchanged.
5. Power off before moving the USB connection from the PC to the powered
   keyboard hub. Connect the hub upstream connection to the Nano and the keyboard
   to a hub downstream port. Connect HDMI and power the setup normally.
6. During the flashing-LED startup window, leave S1 released for USB mode.
   To select serial instead, power off, connect directly to the PC, power on
   with buttons released, then press and release S1 during the two-second
   window. Do not hold S1/S2 before power-on. Later S1 presses reset the game
   while retaining the mode. Test both modes, PS/2, reset and cold boot.

No SD formatting or save-file conversion is required. The USB profile leaves
the SD card under Zork's control. The selectable revision retains physical PS/2
in both modes and enables either Companion USB keyboard or onboard serial.
S1 changes FPGA routing; Partner must independently enter the corresponding
USB role. Detected Companion keyboard payloads disable UART and flash the LED,
while HDMI and physical PS/2 remain available. Discovery/configuration requests
do not block serial. Power-cycle with matching connection/selection to recover. This is a
development revision requiring physical validation; see the README for detail.

Physical testing on the earlier USB-only image covers two keyboards, reconnect,
cold/warm boot and HDMI appearance. The v0.7.0 serial image also works with
installed Partner/Companion, without BL616 restoration. These are separate
images and do not validate the new selectable revision. Keyboard repeat, bursts and broader hub
compatibility still need separate coverage.

## Recovery

If the normal debugger does not return, disconnect power and re-enter download
mode with UPDATE held. Use the same board's verified backup, not a backup from
another board. Do not attempt fuse changes or whole-chip erase.

To restore the original first 1 MiB, put this `restore-original.ini` beside
`before-first-1MiB-a.bin` in `upgrade_dir`:

```ini
[cfg]
erase = 1
skip_mode = 0x0, 0x0
boot2_isp_mode = 0

[FW]
filedir = ./before-first-1MiB-a.bin
address = 0x000000
```

After checking that the backup is the correct 1,048,576-byte file for this board,
restore it using the same command form as step 5 with
`--config="$upgrade_dir/restore-original.ini"`. Read back and compare the region
with the backup, then power-cycle normally. This restores only the backed-up
region. The project prepared this recovery approach but did not need to execute it.

For early incompatible boards, follow the upstream
[factory firmware recovery instructions](https://github.com/MiSTle-Dev/FPGA-Companion/tree/main/src/bl616/friend_20k).
Restoring a known Partner binary alone is different from restoring the board's
original firmware. Restoring BL616 firmware also does not restore the FPGA
bitstream; program the normal Zork PS/2/UART image separately if needed.
