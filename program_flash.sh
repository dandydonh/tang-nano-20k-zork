#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Persist the circuit across power cycles; erase, program, and verify flash.
exec /home/donh/Programmer/bin/programmer_cli \
  --device GW2AR-18C \
  --operation_index 9 \
  --cable-index 4 \
  --channel 0 \
  --fsFile "$project_dir/impl/pnr/zork.fs"
