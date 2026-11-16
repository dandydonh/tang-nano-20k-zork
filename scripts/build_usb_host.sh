#!/usr/bin/env bash
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
gowin_home="${GOWIN_HOME:-/home/donh/IDE}"
cd "$project_dir"
# Isolate generated project/output so the normal zork.fs stays available.
# Uses the checked-in CPU firmware image; does not program either chip.
python3 - <<'PY'
from pathlib import Path
import hashlib
import shutil
import xml.etree.ElementTree as ET
root = Path.cwd()
stage = root / 'impl/usb-host'
stage.mkdir(parents=True, exist_ok=True)
(stage / 'impl').mkdir(exist_ok=True)
assets = stage / 'assets'
assets.mkdir(exist_ok=True)
for name in ('firmware.hex', 'font.hex', 'text_blank.hex'):
    shutil.copy2(root / 'assets' / name, assets / name)
for kind, base in (('cst', 'tang_nano_20k'), ('sdc', 'zork')):
    (stage / f'usb.{kind}').write_text(
        (root / f'constraints/{base}.{kind}').read_text() + '\n' +
        (root / f'constraints/usb_host.{kind}').read_text())
tree = ET.parse(root / 'zork.gprj')
files = tree.getroot().find('FileList')
for item in files:
    kind = item.attrib['type']
    if item.attrib['path'] in ('src/zork_top.v', 'src/zork_soc.v'):
        staged_source = stage / Path(item.attrib['path']).name
        staged_source.write_text('`define ZORK_USB_HOST\n' + (root / item.attrib['path']).read_text())
        item.set('path', str(staged_source))
        continue
    item.set('path', str(stage / f'usb.{kind[5:]}') if kind in ('file.cst', 'file.sdc')
             else str(root / item.attrib['path']))
ET.SubElement(files, 'File', path=str(root / 'src/companion_keyboard.v'),
              type='file.verilog', enable='1')
tree.write(stage / 'zork_usb.gprj', encoding='UTF-8', xml_declaration=True)
inputs = [Path(item.attrib['path']) for item in files
          if item.attrib.get('enable') == '1']
inputs += [assets / name for name in ('firmware.hex', 'font.hex', 'text_blank.hex')]
(stage / 'SOURCE_SHA256SUMS').write_text(''.join(
    f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p}\n' for p in inputs))
shutil.copy2(root / 'ide/zork_process_config.json', stage / 'impl/zork_usb_process_config.json')
(stage / 'build.tcl').write_text('''open_project zork_usb.gprj
set_option -top_module zork_top
set_option -output_base_name zork_usb
set_option -gen_text_timing_rpt 1
if {[catch {run all} build_error]} {
  puts stderr $build_error
  exit 1
}
''')
PY
cd "$project_dir/impl/usb-host"
mkdir -p tool_cache
export QT_QPA_PLATFORM=minimal
export QT_QPA_PLATFORM_PLUGIN_PATH="$gowin_home/plugins/qt/platforms"
export XDG_CACHE_HOME="$PWD/tool_cache"
touch build_started
"$gowin_home/bin/gw_sh" build.tcl
test -s impl/pnr/zork_usb.fs
test impl/pnr/zork_usb.fs -nt build_started
python3 - <<'PY'
from pathlib import Path
import hashlib
import re
timing = Path('impl/pnr/zork_usb.tr').read_text()
for kind in ('Setup', 'Hold'):
    match = re.search(rf'<Numbers of {kind} Violated Endpoints>:(\d+)', timing)
    if not match or int(match[1]):
        raise SystemExit(f'USB profile {kind} timing did not pass')
files = ['impl/pnr/zork_usb.fs', 'assets/firmware.hex']
Path('SHA256SUMS').write_text(''.join(
    f'{hashlib.sha256(Path(p).read_bytes()).hexdigest()}  {p}\n' for p in files))
print('PASS USB profile setup/hold timing; output: impl/usb-host/impl/pnr/zork_usb.fs')
PY
