#!/usr/bin/env bash
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
tool_prefix="${RISCV_PREFIX:-/tmp/zork-tools/usr/bin/riscv64-unknown-elf-}"
export PATH="$(dirname "$tool_prefix"):$PATH"
mkdir -p impl/firmware
"${tool_prefix}gcc" -march=rv32im -mabi=ilp32 -Os -ffreestanding -fno-builtin \
  -ffunction-sections -fdata-sections -Wall -Wextra -Wno-misleading-indentation \
  -nostdlib -Wl,--gc-sections,-Map=impl/firmware/zork.map -T firmware/link.ld \
  firmware/start.S firmware/zmachine.c firmware/platform.c -lgcc -o impl/firmware/zork.elf
"${tool_prefix}objcopy" -O binary impl/firmware/zork.elf impl/firmware/zork.bin
"${tool_prefix}size" impl/firmware/zork.elf
python3 - <<'PY'
from pathlib import Path
b=Path('impl/firmware/zork.bin').read_bytes()
assert len(b)<=65536
b=b.ljust(65536,b'\0')
Path('assets/firmware.hex').write_text(''.join(f'{int.from_bytes(b[i:i+4],"little"):08x}\n' for i in range(0,len(b),4)))
PY
