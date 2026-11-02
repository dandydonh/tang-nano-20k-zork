#!/usr/bin/env bash
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

# Gowin stores GUI process settings under impl, separate from the .gprj file.
# Restore them on a clean checkout without overwriting settings edited in the IDE.
mkdir -p impl
if [[ ! -e impl/zork_process_config.json ]]; then
  cp ide/zork_process_config.json impl/zork_process_config.json
fi

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

for item in ET.parse('zork.gprj').getroot().findall('FileList/File'):
    path = Path(item.attrib['path'])
    if not path.is_file():
        raise SystemExit(f'Missing project file: {path}')
for name, words in (('firmware', 16384), ('font', 2048), ('text_blank', 4096)):
    path = Path(f'assets/{name}.hex')
    if len(path.read_text().split()) != words:
        raise SystemExit(f'Invalid memory initialization file: {path}')
print(f'IDE project ready: {Path("zork.gprj").resolve()}')
print('Open it with File > Open in Gowin FPGA Designer.')
PY
