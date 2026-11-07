#!/usr/bin/env python3
"""Repopulate the FAT directory between boots without rebuilding firmware."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from make_sd import make_image,POOL_SIZE

with tempfile.TemporaryDirectory(prefix='zork-boot-menu-') as directory:
    image=Path(directory)/'card.img'
    pool=bytes(POOL_SIZE)

    def prepare(stories):
        image.write_bytes(make_image(stories+[('SAVES.BIN',pool)],16,8,False))

    def boot(commands,expected=0):
        result=subprocess.run([ROOT/'impl/zork-host'],input=commands,text=True,capture_output=True,
                              env=dict(os.environ,ZORK_SD_IMAGE=str(image)),timeout=10)
        assert result.returncode==expected,(result.stdout,result.stderr)
        return result.stdout

    cavern=make_story(name='cavern',release=41)
    orchard=make_story(name='orchard',release=42)
    prepare([('ORCHARD.DAT',orchard),('CAVERN.DAT',cavern)])
    output=boot('1\ns\nq\n')
    assert '1. CAVERN.DAT\n2. ORCHARD.DAT' in output and 'cavern ready' in output
    pool=FatImage(image.read_bytes()).file_bytes('SAVES.BIN')

    # Remove one file, add another and change copy order on the same card.
    forest=make_story(name='forest',release=43)
    prepare([('FOREST.DAT',forest),('CAVERN.DAT',cavern)])
    output=boot('2\nq\n')
    assert '1. CAVERN.DAT\n2. FOREST.DAT' in output and 'forest ready' in output
    assert 'ORCHARD.DAT' not in output
    assert 'restorefailed' not in boot('1\nr\nq\n')

    # Replacing content under the same filename loads the new header/program;
    # it cannot accidentally restore the replaced game's saved state.
    prepare([('CAVERN.DAT',make_story(name='replacement',release=44))])
    output=boot('r\nq\n')
    assert 'Starting CAVERN.DAT' in output and 'replacement ready' in output
    assert 'Select story number:' not in output and 'restorefailed' in output

    prepare([])
    before=image.read_bytes()
    output=boot('',expected=2)
    assert 'No compatible V3/V5 stories (.DAT/.Z3/.Z5) in /ZORK.' in output
    assert 'CAVERN.DAT' not in output and image.read_bytes()==before

print('PASS boot-time SD discovery: added/removed/replaced stories, alphabetical repopulation, single-story startup, retained saves and empty directory')
