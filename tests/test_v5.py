#!/usr/bin/env python3
"""Shared V3/V5 loader, V5 bytecode, windows and persistent/undo snapshots."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
from v5_fixture import make_story
from fat_helpers import FatImage
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from make_sd import make_image, project_files, validate_story


def run(image, commands):
    result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                            capture_output=True, timeout=30,
                            env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert 'testfailed' not in result.stdout and 'CORE ERROR' not in result.stdout, result.stdout
    return result.stdout


with tempfile.TemporaryDirectory(prefix='zork-v5-') as d:
    image = Path(d)/'card.img'
    story = make_story()
    validate_story(story)
    layout = FatImage(make_image(project_files(story, 'VFIVE.DAT'), 16, 8, False))
    layout.fragment('VFIVE.DAT', 11000)
    image.write_bytes(layout.data)
    before = image.read_bytes()
    output = run(image, 's\nn\nl\nr\nl\nq\n')
    assert 'high address text' in output and 'vfive ready' in output, output
    assert 'upper screen' in output and 'saved' in output and 'restored' in output, output
    assert re.search(r'\n9\n', output) and re.search(r'\n0\n', output), output
    output = run(image, 'r\nl\nq\n')
    assert 'restored' in output and '\n0\n' in output, output
    after = FatImage(image.read_bytes())
    after.assert_only_saves_changed(before)
    assert after.file_bytes('VFIVE.DAT') == story
    assert after.file_bytes('SAVES.BIN')[:4] == b'ZMV6'
    print('PASS V5: 256 KiB/fragmented story, high calls/text, seven args, large objects/properties, 48 attributes, nine-character dictionary, tables, shifts, windows, undo, save/restore/reset and write bounds')
    frotz = shutil.which('dfrotz') or '/usr/games/dfrotz'
    if Path(frotz).is_file():
        path = Path(d)/'original.z5'
        path.write_bytes(story)
        reference = subprocess.run([frotz, '-q', '-m', '-p', '-Z', '3', str(path)],
                                   input='n\nl\nq\n', text=True, capture_output=True, timeout=20)
        assert reference.returncode == 0 and 'testfailed' not in reference.stdout, (reference.stdout, reference.stderr)
        assert 'vfive ready' in reference.stdout and '>9' in reference.stdout
        print('PASS independent Frotz execution of original V5 instruction fixture')

# Real V3 and V5 programs coexist in one pool; existing V3 saves stay usable.
from v3_fixture import make_story as make_v3_story
with tempfile.TemporaryDirectory(prefix='zork-mixed-') as d:
    image = Path(d)/'mixed.img'
    image.write_bytes(make_image([('ALPHA.DAT',make_v3_story()),('BETA.DAT',make_story()),
                                  ('SAVES.BIN',bytes(5242880))],16,8,False))
    assert 'saved' in run(image,'1\ns\nn\ns\nq\n')
    vfive = run(image,'2\ns\nn\nr\nl\nq\n')
    assert 'V3/V5 stories:' in vfive and 'restored' in vfive and '\n0\n' in vfive
    assert 'alpha moved' in run(image,'1\nr\nl\nq\n')
    pool = FatImage(image.read_bytes()).file_bytes('SAVES.BIN')
    assert pool[:4] == b'ZMV5' and pool[262144:262148] == b'ZMV6'
    backup = Path(d)/'saves.bin'
    expanded = Path(d)/'expanded.bin'
    backup.write_bytes(pool)
    subprocess.run([sys.executable,ROOT/'scripts/make_sd.py','--expand-saves',backup,
                    '--save-slots','2','--output',expanded],check=True,capture_output=True)
    assert expanded.read_bytes()[:len(pool)] == pool
    print('PASS mixed V3/V5 menu and save ownership, retained V3 snapshots, lossless mixed-pool expansion')

with tempfile.TemporaryDirectory(prefix='zork-v5-atomic-') as d:
    image = Path(d)/'card.img'
    image.write_bytes(make_image(project_files(make_story(dynamic=65535)),16,8,False))
    run(image,'s\nq\n')
    baseline = image.read_bytes()
    pool = FatImage(baseline).file_bytes('SAVES.BIN')
    size = int.from_bytes(pool[8:12],'little')
    writes = (size+511)//512+1
    for cut in range(writes):
        image.write_bytes(baseline)
        interrupted = subprocess.run([ROOT/'impl/zork-host'],input='n\ns\nq\n',text=True,
                                     capture_output=True,timeout=30,
                                     env=dict(os.environ,ZORK_SD_IMAGE=str(image),ZORK_CUT_AFTER_WRITES=str(cut)))
        assert interrupted.returncode == 99,(cut,interrupted.stdout,interrupted.stderr)
        restored = run(image,'r\nl\nq\n')
        assert 'restored' in restored and '\n0\n' in restored,(cut,restored)
    image.write_bytes(baseline)
    run(image,'n\ns\nq\n')
    layout = FatImage(image.read_bytes())
    # Corrupt the newest bank's screen trailer; checksum must select old state.
    sectors = layout.sectors('SAVES.BIN')
    payload_byte = 131072+512+size-1
    layout.data[sectors[payload_byte//512]*512+payload_byte%512] ^= 1
    image.write_bytes(layout.data)
    assert '\n0\n' in run(image,'r\nl\nq\n')
    print(f'PASS V5 maximum-memory snapshot: all {writes} interrupted writes and corrupted-screen-trailer fallback')

with tempfile.TemporaryDirectory(prefix='zork-v5-slots-') as d:
    image = Path(d)/'card.img'
    image.write_bytes(make_image(project_files(make_story(),save_slots=2),16,16,False))
    output = run(image,'s\n1\nn\ns\n2\nr\n1\nl\nr\n2\nl\nq\n')
    assert '\n0\n' in output and '\n9\n' in output and 'Slot number' in output,output
    assert '\n9\n' in run(image,'r\n2\nl\nq\n')
    print('PASS V5 selected positions: distinct states, in-game restore and reset restore')
