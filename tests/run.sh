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
  -DHOST -Ifirmware firmware/zmachine.c firmware/storage.c tests/host_platform.c -o impl/zork-host
python3 tests/test_story.py
python3 tests/test_fat.py
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
import sys
sys.path.insert(0,'tests')
sys.path.insert(0,'scripts')
from fat_helpers import FatImage
from make_sd import make_image, project_files
files=project_files(Path('zork1.dat').read_bytes())
# Disposable fragmented fixtures; delivery images and real saves are untouched.
for fat,tag,partitioned in ((16,'sd',False),(32,'fat32',True)):
    layout=FatImage(make_image(files,fat,4 if fat==16 else 64,partitioned))
    for name,first in (('ZORK1.DAT',1000),('SAVEA.BIN',2000),('SAVEB.BIN',2500)):
        layout.fragment(name,first)
    sectors=layout.sectors('SAVEA.BIN')+layout.sectors('SAVEB.BIN')
    assert max(sectors)<8192
    Path(f'impl/test-{tag}-save-sectors.hex').write_text(''.join(f'{v:08x}\n' for v in sectors))
    # Only the first 4 MiB is backed by the model. All accessed sectors,
    # including the two FATs and fragmented files, are in that range.
    Path(f'impl/test-{tag}.hex').write_text(''.join(f'{v:02x}\n' for v in layout.data[:4*1024*1024]))
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
impl/verilator-soc/Vsoc_tb +fat32 | tee impl/soc-fat32.log
python3 - <<'PY'
from pathlib import Path
for name in ('soc-verilator.log','soc-sdsc.log','soc-fat32.log'):
    s=Path('impl',name).read_text()
    assert 'PASS soc boot' in s, name
    assert 'CORE ERROR' not in s, name
    assert s.count('West of House')==6, (name,s)
    assert s.count('North of House')==1, (name,s)
    assert s.count('Ok.')==3, (name,s)
print('PASS integrated transcript assertions and reset persistence')
PY
python3 tests/test_terminal.py
