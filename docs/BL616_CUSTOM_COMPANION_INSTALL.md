# Install the experimental Zork BL616 Companion

This is a **separate microcontroller firmware installation**, for Tang Nano 20K
**revision 3923 only**. The v0.8.0 `zork-companion-v0.8.0.zip` bundle contains a custom
FPGA-Companion based on v1.4.33 with the proposed readiness announcements enabled.
It is an experimental Zork build, not an upstream release. No upstream
submission has been made. Users do not need a compiler or SDK to install it.

The firmware has compiled successfully. Inspection of the linked ELF confirms
that the readiness wrappers intercept the USB host controller calls, and TLS
metadata is present. This exact binary was installed on a project board on
2026-11-11: independent readback verified Companion, unchanged Partner/lower
flash and unchanged bytes above the erased region. Normal USB debugger
enumeration returned after a power cycle. Keyboard/serial operation of the
matching release pair and startup reliability remain unconfirmed. Inherited
application/SDK compiler warnings remain.

Automatic serial/USB selection also requires the matching FPGA implementation.
The v0.8.0 FPGA image passed simulation, timing and flash program/verify;
physical automatic selection remains unconfirmed. Installing this Companion
alone does not add automatic selection to an older bitstream. The announcement
protocol is provisional; keep the Companion and FPGA versions paired.

## Requirements and package contents

Use a board already running a known-compatible FPGA Partner. On the project
board, this is Partner2025030317 with Companion v1.4.33. This procedure replaces
**only Companion at BL616 flash address `0x40000`**, retaining Partner below it.
If Partner compatibility is unknown, resolve that first using
`REFERENCE_BL616_USB_KEYBOARD_UPGRADE.md` included with the bundle. This guide does not
install Partner, change eFuses, or program FPGA flash.

The bundle contains:

- `fpga_companion_nano20k_v3923_zork_status_v1_exp1.bin`: raw install image.
- `install-companion.ini`: Companion-only section-erase configuration.
- `SHA256SUMS`, `BUILD_INFO.json`, `SOURCE_CHANGES.patch`, and `licenses/`.
- `INSTALL.md`: this guide.

Retain this bundle for recovery and identification. Upstream version strings
still identify the v1.4.33 base; they do not prove the custom image is installed.
Use hashes and independent flash readback.

## 1. Prepare the tool and verify the bundle

Linux examples use Bouffalo's `BLFlashCommand-ubuntu` from the Flash Cube tool
in SDK revision `eba87edced5a03ce8bcad8cf6002494982f83a5f` (the same tool revision
used for this project's earlier installation). Obtain its complete directory,
including `chips/`, as described in `REFERENCE_BL616_USB_KEYBOARD_UPGRADE.md`.
That reference covers the older stock firmware; use only this guide and the
supplied custom INI for this experimental Companion installation.

Set absolute paths to the extracted bundle and tool directory:

```bash
bundle_dir=/absolute/path/to/zork-companion-v0.8.0
tool_dir=/absolute/path/to/bouffalo_flash_cube
cd "$bundle_dir"
sha256sum -c SHA256SUMS
cd "$tool_dir"
./BLFlashCommand-ubuntu --help
```

All checksums must pass. In the tool's
`chips/bl616/eflash_loader/eflash_loader_cfg.ini`, confirm `[EFUSE_CFG]` has
`burn_en = false`. The supplied install INI must have `erase = 1` (section erase)
and exactly one payload at `0x40000`. Do not use the SDK build-generated
`flash_prog_cfg.ini`: it writes bootloader and partition regions for standalone
boards. Do not use whole-chip erase or any fuse/OTP/key/lock operation.

Close serial terminals and disconnect the keyboard hub. Connect the board
USB-C directly to the PC using a data cable.

## 2. Enter download mode and back up twice

Disconnect all power, hold **UPDATE**, reconnect the USB-C data cable, then
release UPDATE. Identify the resulting Bouffalo CDC download port using
`lsusb` and `ls -l /dev/serial/by-id/`. Set the actual port reported by your PC:

```bash
bl616_port=/dev/serial/by-id/usb-Bouffalo_Bouffalo_CDC_DEMO-if00
```

Run the following commands from `tool_dir`. Stop on any failure; resolve access
or connection problems before writing. Re-enter download mode if necessary.

```bash
./BLFlashCommand-ubuntu --interface=uart --chipname=bl616 \
  --port="$bl616_port" --baudrate=2000000 --flash --read --start=0x0 \
  --len=0x100000 --file="$bundle_dir/before-first-1MiB-a.bin"
./BLFlashCommand-ubuntu --interface=uart --chipname=bl616 \
  --port="$bl616_port" --baudrate=2000000 --flash --read --start=0x0 \
  --len=0x100000 --file="$bundle_dir/before-first-1MiB-b.bin"
wc -c "$bundle_dir"/before-first-1MiB-*.bin
cmp "$bundle_dir/before-first-1MiB-a.bin" "$bundle_dir/before-first-1MiB-b.bin"
sha256sum "$bundle_dir"/before-first-1MiB-*.bin
```

Each backup must be exactly **1,048,576 bytes**, `cmp` must succeed, and both
hashes must match. Keep an additional private copy outside this working directory.
This covers the affected region, not the entire flash chip. Never distribute
board-specific backups with the public firmware bundle.

## 3. Write Companion only

With the board in download mode, use the supplied configuration:

```bash
./BLFlashCommand-ubuntu --interface=uart --baudrate=2000000 \
  --port="$bl616_port" --chipname=bl616 --cpu_id= \
  --config="$bundle_dir/install-companion.ini"
```

Save the tool output privately. Check actual erase, programming and verification
results; a generic success message alone is insufficient. If an operation fails,
retain its log and investigate before attempting another write.

## 4. Verify an independent readback

Read the same region again while in download mode:

```bash
./BLFlashCommand-ubuntu --interface=uart --chipname=bl616 \
  --port="$bl616_port" --baudrate=2000000 --flash --read --start=0x0 \
  --len=0x100000 --file="$bundle_dir/after-first-1MiB.bin"
python3 - "$bundle_dir" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
before = (p / 'before-first-1MiB-a.bin').read_bytes()
after = (p / 'after-first-1MiB.bin').read_bytes()
image = (p / 'fpga_companion_nano20k_v3923_zork_status_v1_exp1.bin').read_bytes()
start = 0x40000
end = start + len(image)
erase_end = (end + 0xfff) & ~0xfff  # 4 KiB sector boundary
assert len(before) == len(after) == 0x100000
assert start < end <= erase_end <= 0x100000
assert after[start:end] == image, 'Companion payload mismatch'
assert after[:start] == before[:start], 'Partner/lower flash changed'
assert after[erase_end:] == before[erase_end:], 'Flash above erased region changed'
assert after[end:erase_end] == b'\xff' * (erase_end-end), 'Unexpected sector padding'
print('PASS: Companion matches; Partner and bytes outside erase range preserved')
PY
```

This accounts for erased padding in the final 4 KiB sector. Unexpected changes
need investigation. Readback confirms stored bytes, not execution.

## 5. Power-cycle and validate separately

Disconnect power, release UPDATE, then power on normally. Confirm the normal
USB debugger returns and existing FPGA programming/serial functionality remains
available. Failure here requires investigation/recovery before further changes.

After separately installing the matching v0.8.0 FPGA image, validate cold
boots with direct-PC serial wiring and powered-hub keyboard wiring, both S1
manual overrides, keyboard reconnect, game reset, PS/2 and full power cycles.
Capture selected mode, diagnostics and readiness frames. The existing intermittent
startup issue is not proven fixed by this patch. Do not interpret a present
Companion as necessarily ready: automatic USB selection requires fresh host-ready
reports. Silence can also mean inactive or failed firmware; it is not proof of
an empty flash slot.

FPGA installation is a separate operation with its own instructions and approval
when assisted by an agent. No SD formatting or save-file conversion is involved.

## Recovery

Re-enter download mode using UPDATE. Restore only from this board's verified
backup. Save `restore-original.ini` beside `before-first-1MiB-a.bin`:

```ini
[cfg]
erase = 1
skip_mode = 0x0, 0x0
boot2_isp_mode = 0

[FW]
filedir = ./before-first-1MiB-a.bin
address = 0x000000
```

After checking the backup is the correct 1,048,576-byte file, restore it using
the command from step 3 with `--config="$bundle_dir/restore-original.ini"`.
Read back the first 1 MiB again and compare it byte-for-byte with the backup,
then power-cycle normally. This restores only that region, not FPGA flash.
Recovery has not been exercised for this experimental build. Do not change
fuses or repeatedly write different firmware to diagnose a failure.
