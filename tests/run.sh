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
  -DHOST -Ifirmware firmware/zmachine.c firmware/output.c firmware/storage.c tests/host_platform.c -o impl/zork-host
python3 tests/test_output.py
python3 tests/test_story.py
python3 tests/test_fat.py
python3 tests/test_v3.py
python3 tests/test_boot_menu.py
python3 tests/test_local_stories.py
"$iverilog_bin" "${ivl_args[@]}" -g2012 -s sdram_tb -o impl/tests/sdram \
  tests/sdram_tb.v tests/sdram_model.v src/sdram_controller.v
"$vvp_bin" impl/tests/sdram
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
from v3_fixture import make_story
files=project_files(Path('zork1.dat').read_bytes())
# Disposable fragmented fixtures; delivery images and real saves are untouched.
for fat,tag,partitioned in ((16,'sd',False),(32,'fat32',True),(16,'menu',False),(16,'v3',False),(16,'wrap',False)):
    fixture=project_files(make_story(131070,dynamic=65535)+b'\x1a'+b'^'*24529) if tag=='v3' else files+([(f'GAME{i:02}.DAT',make_story(release=i+1)) for i in range(18)] if tag=='menu' else [])
    if tag=='wrap':
        intro=' '.join(['a lengthy paragraph must remain complete when the terminal does not wrap automatically']*6)
        fixture=project_files(make_story(intro=intro,input_size=120))
    layout=FatImage(make_image(fixture,fat,16 if fat==16 else 64,partitioned))
    for name,first in (('ZORK1.DAT',11000),('SAVES.BIN',12000)):
        layout.fragment(name,first,stride=1 if fat==32 and name=='SAVES.BIN' else 2)
    # FAT32 pool remains contiguous so all headers fit the model's 16 MiB.
    assert max(layout.sectors('SAVES.BIN'))<32768
    sectors=layout.sectors('SAVES.BIN')[:512]
    assert max(sectors)<32768
    Path(f'impl/test-{tag}-save-sectors.hex').write_text(''.join(f'{v:08x}\n' for v in sectors))
    # Only the first 16 MiB is backed by the model. All accessed sectors,
    # including the two FATs and fragmented files, are in that range.
    Path(f'impl/test-{tag}.hex').write_text(''.join(f'{v:02x}\n' for v in layout.data[:16*1024*1024]))
PY
verilator_bin="${VERILATOR:-verilator}"
if ! command -v "$verilator_bin" >/dev/null 2>&1; then
  verilator_bin=/tmp/zork-tools/usr/bin/verilator
  export VERILATOR_ROOT=/tmp/zork-tools/usr/share/verilator
fi
"$verilator_bin" --binary --timing -j 2 -Wno-fatal -CFLAGS -O3 --top-module soc_tb \
  --Mdir impl/verilator-soc tests/soc_tb.v tests/sd_spi_model.v tests/sdram_model.v src/sdram_controller.v src/zork_soc.v \
  src/uart.v src/ps2_receiver.v src/input_fifo.v src/spi_byte.v third_party/picorv32.v \
  > impl/verilator-build.log 2>&1
python3 - <<'PY'
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
# Isolated card RAM per process; shared fixture files are read-only.
runs=[('soc-verilator.log',[]),('soc-sdsc.log',['+sdsc']),
      ('soc-fat32.log',['+fat32']),('soc-menu.log',['+menu']),('soc-v3.log',['+v3']),('soc-wrap.log',['+wrap'])]
def simulate(item):
    name,args=item
    with Path('impl',name).open('w') as log:
        subprocess.run(['impl/verilator-soc/Vsoc_tb',*args],stdout=log,stderr=subprocess.STDOUT,check=True)
    return name
with ThreadPoolExecutor(max_workers=2) as pool:
    for future in as_completed([pool.submit(simulate,item) for item in runs]):
        name=future.result()
        print(Path('impl',name).read_text(),flush=True)
PY
python3 - <<'PY'
from pathlib import Path
for name in ('soc-verilator.log','soc-sdsc.log','soc-fat32.log','soc-menu.log'):
    s=Path('impl',name).read_text()
    assert 'PASS soc boot' in s, name
    assert 'CORE ERROR' not in s, name
    assert s.count('West of House')==6, (name,s)
    assert s.count('North of House')==1, (name,s)
    assert s.count('Ok.')==3, (name,s)
print('PASS integrated transcript assertions and reset persistence')
PY
python3 - <<'PYV3'
from pathlib import Path
s=Path('impl/soc-v3.log').read_text()
assert 'PASS soc boot' in s and 'memoryfailed' not in s and 'CORE ERROR' not in s
assert s.count('saved')==3 and 'alpha home' in s
print('PASS maximum dynamic memory and padded high-memory V3 processor save/reset/restore')
PYV3
python3 tests/test_terminal.py
python3 tests/test_output.py --cpu-log impl/soc-wrap.log
