#!/usr/bin/env bash
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
mkdir -p impl/tests
iverilog_bin="${IVERILOG:-iverilog}"
vvp_bin="${VVP:-vvp}"
ivl_args=()
if ! command -v "$iverilog_bin" >/dev/null 2>&1; then
  iverilog_bin=/tmp/zork-tools/usr/bin/iverilog
  vvp_bin=/tmp/zork-tools/usr/bin/vvp
  ivl_args=(-B /tmp/zork-tools/usr/lib/x86_64-linux-gnu/ivl)
fi
gcc -std=c99 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation \
  -DHOST -Ifirmware firmware/zmachine.c tests/host_platform.c -o impl/zork-host
python3 tests/test_story.py
"$iverilog_bin" "${ivl_args[@]}" -g2012 -s peripherals_tb -o impl/tests/peripherals \
  tests/peripherals_tb.v src/spi_byte.v src/ps2_receiver.v src/uart.v
"$vvp_bin" impl/tests/peripherals
"$iverilog_bin" "${ivl_args[@]}" -g2012 -s video_tb -o impl/tests/video \
  tests/video_tb.v src/text_video.v
"$vvp_bin" impl/tests/video
"$iverilog_bin" "${ivl_args[@]}" -g2012 -s tmds_encoder_tb -o impl/tests/tmds \
  tests/tmds_encoder_tb.v src/tmds_encoder.v
"$vvp_bin" impl/tests/tmds
./scripts/build_firmware.sh
python3 - <<'PY'
from pathlib import Path
import subprocess
p=Path('impl/tests/card.img')
# Test files are disposable; the delivery image and real saves are never touched.
if p.exists(): p.unlink()
subprocess.run(['python3','scripts/make_sd.py','--output',str(p)],check=True)
Path('impl/test-sd.hex').write_text(''.join(f'{v:02x}\n' for v in p.read_bytes()))
PY
verilator_bin="${VERILATOR:-verilator}"
if ! command -v "$verilator_bin" >/dev/null 2>&1; then
  verilator_bin=/tmp/zork-tools/usr/bin/verilator
  export VERILATOR_ROOT=/tmp/zork-tools/usr/share/verilator
fi
"$verilator_bin" --binary --timing -j 2 -Wno-fatal --top-module soc_tb \
  --Mdir impl/verilator-soc tests/soc_tb.v tests/sd_spi_model.v src/zork_soc.v \
  src/uart.v src/ps2_receiver.v src/input_fifo.v src/spi_byte.v third_party/picorv32.v \
  > impl/verilator-build.log 2>&1
impl/verilator-soc/Vsoc_tb | tee impl/soc-verilator.log
impl/verilator-soc/Vsoc_tb +sdsc | tee impl/soc-sdsc.log
python3 - <<'PY'
from pathlib import Path
import re
s=Path('impl/soc-verilator.log').read_text()
sdsc=Path('impl/soc-sdsc.log').read_text()
# Reproduce a terminal with gray ANSI palette black but a black default
# background. Check actual CPU output restores black before erasing the screen.
for transcript in (s,sdsc):
    boots=transcript.split('ZORK I - Tang Nano 20K')[:-1]
    assert len(boots)==2, 'startup/reset coverage missing'
    for boot in boots:
        background='gray';reverse=True;cleared=None;homed=False
        controls=re.findall(r'\x1b\[([0-9;]*)([mJH])',boot)
        for args,command in controls:
            if command=='m':
                for param in map(int,args.split(';')):
                    if param==0: background='black';reverse=False
                    elif param==40: background='gray'
                    elif param==49: background='black'
            elif command=='J' and args=='2': cleared=background
            elif command=='H': homed=True
        assert background=='black' and cleared=='black' and not reverse and homed
print('PASS startup uses black default background with gray ANSI palette black')
assert 'PASS soc boot' in sdsc and sdsc.count('West of House')==6
assert 'PASS soc boot' in s
assert 'CORE ERROR' not in s
assert s.count('West of House')==6, s
assert s.count('North of House')==1, s
assert s.count('Ok.')==3, s
print('PASS integrated transcript assertions and reset persistence')
PY
