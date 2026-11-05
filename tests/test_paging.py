#!/usr/bin/env python3
"""Compare paged and uninterrupted exact private Zork III startup output."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from make_sd import make_image,POOL_SIZE
story=ROOT/'inspect_files/zork3.dat'
if not story.exists():
    print('SKIP private Zork III pagination (story unavailable)')
    sys.exit(0)
with tempfile.TemporaryDirectory(prefix='zork-paging-') as directory:
    card=Path(directory)/'card.img'
    card.write_bytes(make_image([('ZORK3.DAT',story.read_bytes()),('SAVES.BIN',bytes(POOL_SIZE))],16,8,False))
    def run(rows=None,keys=''):
        env=dict(os.environ,ZORK_SD_IMAGE=str(card))
        if rows is not None:env['ZORK_PAGE_ROWS']=str(rows)
        return subprocess.run([ROOT/'impl/zork-host'],input=keys,text=True,capture_output=True,env=env,check=True,timeout=30).stdout
    original=run()
    stopped=run(18)
    assert stopped.endswith('[MORE]')
    assert 'As in a dream' in stopped and '>\n' not in stopped
    assert len(stopped.splitlines())==17, repr(stopped)
    erase='\b'*6+' '*6+'\b'*6
    for rows in (4,18,24,32):
        # Exactly enough acknowledgements for startup, without feeding a game command.
        pauses=(len(original.splitlines())-1)//(rows-2)
        paged=run(rows,' '*pauses)
        assert paged.count('[MORE]')==pauses,(rows,paged)
        assert paged.replace('[MORE]'+erase,'')==original,rows
    # The space acknowledging the short-terminal page cannot leak into LOOK.
    paged=run(18,' look\n')
    assert paged.replace('[MORE]'+erase,'')==run(keys='look\n')
print('PASS exact Zork III: pause before 18-row overflow, all text retained at 4/18/24/32 rows, acknowledgement separate from LOOK')
