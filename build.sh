#!/usr/bin/env bash
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
gowin_home="${GOWIN_HOME:-/home/donh/IDE}"
cd "$project_dir"
./scripts/build_firmware.sh
mkdir -p impl/tool_cache
export QT_QPA_PLATFORM=minimal
export QT_QPA_PLATFORM_PLUGIN_PATH="$gowin_home/plugins/qt/platforms"
export XDG_CACHE_HOME="$project_dir/impl/tool_cache"
touch impl/build_started
"$gowin_home/bin/gw_sh" "$project_dir/scripts/build.tcl"
test -s impl/pnr/zork.fs
test impl/pnr/zork.fs -nt impl/build_started
python3 scripts/check_build.py
