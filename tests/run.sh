#!/usr/bin/env bash
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
mkdir -p impl/tests
python3 tests/test_serial_terminal.py
iverilog_bin="${IVERILOG:-iverilog}"
vvp_bin="${VVP:-vvp}"
ivl_args=()
if ! command -v "$iverilog_bin" >/dev/null 2>&1; then
  iverilog_bin=/tmp/zork-tools/usr/bin/iverilog
  vvp_bin=/tmp/zork-tools/usr/bin/vvp
  ivl_args=(-B /tmp/zork-tools/usr/lib/x86_64-linux-gnu/ivl)
fi
"$iverilog_bin" "${ivl_args[@]}" -g2012 -s companion_keyboard_tb -o impl/tests/companion_keyboard \
  tests/companion_keyboard_tb.v src/companion_keyboard.v
"$vvp_bin" impl/tests/companion_keyboard
"$iverilog_bin" "${ivl_args[@]}" -g2012 -s startup_mode_tb \
  -o impl/tests/startup_mode tests/startup_mode_tb.v src/startup_mode.v
"$vvp_bin" impl/tests/startup_mode
"$iverilog_bin" "${ivl_args[@]}" -g2012 -DZORK_USB_HOST -s mode_routing_tb \
  -o impl/tests/mode_routing tests/mode_routing_tb.v src/zork_top.v src/startup_mode.v \
  src/zork_soc.v src/companion_keyboard.v src/input_fifo.v src/ps2_receiver.v \
  src/uart.v src/spi_byte.v src/sdram_controller.v src/text_video.v \
  src/tmds_encoder.v third_party/picorv32.v
"$vvp_bin" impl/tests/mode_routing
"$vvp_bin" impl/tests/mode_routing +serial
"$iverilog_bin" "${ivl_args[@]}" -g2012 -DZORK_USB_HOST -s input_queues_tb \
  -o impl/tests/input_queues tests/input_queues_tb.v src/zork_soc.v \
  src/companion_keyboard.v src/input_fifo.v src/ps2_receiver.v src/uart.v \
  src/spi_byte.v src/sdram_controller.v third_party/picorv32.v
"$vvp_bin" impl/tests/input_queues
gcc -std=c99 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation \
  -DHOST -Ifirmware firmware/zmachine.c firmware/output.c firmware/unicode.c firmware/ps2.c firmware/screen.c firmware/storage.c tests/host_platform.c -o impl/zork-host
python3 tests/test_output.py
gcc -std=c99 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation -Ifirmware \
  firmware/ps2.c tests/ps2_tb.c -o impl/ps2-test
impl/ps2-test
gcc -std=c99 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation \
  -fno-builtin -ffunction-sections -fdata-sections -Ifirmware \
  tests/input_sources_tb.c firmware/ps2.c firmware/unicode.c \
  -Wl,--gc-sections -o impl/input-sources-test
impl/input-sources-test
gcc -std=c99 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation -DHOST \
  -ffunction-sections -fdata-sections -Ifirmware tests/key_events_tb.c \
  -Wl,--gc-sections -o impl/key-events-test
impl/key-events-test
gcc -std=c99 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation \
  -fno-builtin -ffunction-sections -fdata-sections -Ifirmware \
  tests/paging_tb.c firmware/output.c firmware/unicode.c firmware/ps2.c -Wl,--gc-sections -o impl/paging-test
impl/paging-test
python3 tests/test_dynamic_terminal.py
python3 tests/test_paging.py
gcc -std=c99 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation -Ifirmware \
  firmware/screen.c firmware/unicode.c tests/v5_screen_tb.c -o impl/v5-screen-test
impl/v5-screen-test
python3 tests/test_streams.py
python3 tests/test_story.py
python3 tests/test_fat.py
python3 tests/test_v3.py
python3 tests/test_v5.py
python3 tests/test_v5_stories.py
python3 tests/test_v5_io.py
python3 tests/test_v5_display.py
python3 tests/test_save_slots.py
python3 tests/test_indexed_saves.py
python3 tests/test_auto_saves.py
python3 tests/test_boot_menu.py
python3 tests/test_story_extensions.py
python3 tests/test_story_overflow.py
python3 tests/test_paged_menu.py
python3 tests/test_long_filenames.py
python3 tests/test_unicode_names.py
python3 tests/test_unicode_text.py
python3 tests/test_ps2_unicode.py
python3 tests/test_local_stories.py
python3 tests/test_planetfall.py
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
python3 tests/test_input_modes_cpu.py
python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,'tests')
from fat_helpers import FatImage
from sd_image_fixture import make_image, project_files
from v3_fixture import make_story
from v5_fixture import make_story as make_v5_story
files=project_files(Path('zork1.dat').read_bytes())
# Disposable fragmented fixtures; delivery images and real saves are untouched.
for fat,tag,partitioned in ((16,'sd',False),(32,'fat32',True),(16,'menu',False),(16,'v3',False),(16,'wrap',False),(16,'slots',False),(16,'v5',False)):
    fixture=project_files(make_story(131070,dynamic=65535)+b'\x1a'+b'^'*24529) if tag=='v3' else files+([(f'GAME{i:02}.DAT',make_story(release=i+1)) for i in range(18)] if tag=='menu' else [])
    if tag=='wrap':
        intro=' '.join(['a lengthy paragraph must remain complete when the terminal does not wrap automatically']*6)
        fixture=project_files(make_story(intro=intro,input_size=120,stream_check=True))
    if tag=='v5':
        fixture=project_files(make_v5_story(dynamic=65535),'VFIVE.DAT')
    if tag=='slots':
        fixture=project_files(make_story())
    layout=FatImage(make_image(fixture,fat,16 if fat==16 else 64,partitioned))
    for name,first in (() if tag=='slots' else (('VFIVE.DAT' if tag=='v5' else 'ZORK1.DAT',11000),('VFIVE.SAV' if tag=='v5' else 'ZORK1.SAV',12000))):
        layout.fragment(name,first,stride=1 if (tag=='v5' and name=='VFIVE.DAT') or (fat==32 and name.endswith('.SAV')) else 2)
    save_name='VFIVE.SAV' if tag=='v5' else 'ZORK1.SAV'
    sectors=layout.sectors(save_name)[4:516]
    if tag=='slots':sectors+=layout.sectors(save_name)[516:1028]
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
      ('soc-fat32.log',['+fat32']),('soc-menu.log',['+menu']),('soc-v3.log',['+v3']),('soc-wrap.log',['+wrap']),
      ('soc-slots.log',['+slots']),('soc-v5.log',['+v5'])]
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
python3 - <<'PYSLOTS'
from pathlib import Path
s=Path('impl/soc-slots.log').read_text()
assert 'PASS selectable saves:' in s and 'CORE ERROR' not in s and 'memoryfailed' not in s
assert 'alpha home' in s and s.count('alpha moved')==2 and s.count('saved\n') == 4, s
assert 'Overwrite cancelled.' in s and 'Cancelled.' in s and 'savefailed' in s
print('PASS actual CPU selected-save states, UART/PS2 menu input, cancellation and reset persistence')
PYSLOTS
python3 tests/test_terminal.py
python3 tests/test_output.py --cpu-log impl/soc-wrap.log

python3 - <<'PYV5'
from pathlib import Path
import re
s=Path('impl/soc-v5.log').read_text()
assert 'PASS V5 CPU' in s and 'testfailed' not in s and 'CORE ERROR' not in s
clean=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',s)
assert clean.count('restored')==2 and 'high address text' in clean and clean.count('vfive ready')==2, clean
print('PASS V5 actual CPU: 256 KiB story, 65535 dynamic bytes, high calls, undo, windows, persistent save/reset/restore')
PYV5

python3 tests/test_v5_display.py impl/soc-v5.log
python3 tests/test_paging_cpu.py

python3 tests/test_dynamic_cpu.py
python3 tests/test_long_filename_cpu.py
python3 tests/test_indexed_save_cpu.py
python3 tests/test_auto_save_cpu.py
python3 tests/test_unicode_text_cpu.py
python3 tests/test_paged_menu_cpu.py
