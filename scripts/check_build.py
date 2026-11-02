#!/usr/bin/env python3
"""Require clean setup/hold timing and record deliverable hashes."""
from pathlib import Path
import hashlib
import re
root=Path(__file__).resolve().parents[1]
timing=(root/'impl/pnr/zork.tr').read_text()
for kind in ('Setup','Hold'):
    match=re.search(rf'<Numbers of {kind} Violated Endpoints>:(\d+)',timing)
    if not match or int(match[1]): raise SystemExit(f'{kind} timing did not pass')
files=['impl/pnr/zork.fs','impl/firmware/zork.bin','zork1.dat','assets/font.hex']
manifest=''.join(f'{hashlib.sha256((root/p).read_bytes()).hexdigest()}  {p}\n' for p in files)
(root/'impl/SHA256SUMS').write_text(manifest)
print('PASS setup and hold timing; bitstream hashes in impl/SHA256SUMS')
