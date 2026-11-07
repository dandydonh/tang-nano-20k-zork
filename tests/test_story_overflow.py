#!/usr/bin/env python3
"""Bounded compatible-story selection must survive oversized FAT libraries."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story
from v5_fixture import make_story as make_v5_story

ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image, POOL_SIZE

alpha = make_story(name='alpha', release=701)
vfive = make_v5_story()
bad = bytes(64)
extensions = ('DAT', 'Z3', 'Z5')
valid = [(f'GAME{i:02}.{extensions[i%3]}', alpha) for i in range(25)]
# Include real V5 execution and a compatible file that alphabetically displaces
# an earlier candidate only after the in-memory array has filled.
valid += [('FIRST.Z5', vfive)]
invalid = [(f'BAD{i:02}.{extensions[i%3]}', bad) for i in range(24)]

with tempfile.TemporaryDirectory(prefix='zork-overflow-') as directory:
    image = Path(directory)/'card.img'

    def prepare(files, fat):
        image.write_bytes(make_image(files+[('SAVES.BIN', bytes(POOL_SIZE))],
                                     fat, 8 if fat == 16 else 64, False))

    def boot(commands, expected=0):
        result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                                capture_output=True, timeout=30,
                                env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
        assert result.returncode == expected, (result.stdout, result.stderr)
        if expected == 0:
            assert 'CORE ERROR' not in result.stdout and 'testfailed' not in result.stdout, result.stdout
        return result.stdout

    expected_menu = sorted(name for name, _ in valid)
    for fat in (16, 32):
        menus = []
        for files in (invalid+list(reversed(valid)), valid+list(reversed(invalid))):
            prepare(files, fat)
            baseline = image.read_bytes()
            output = boot('27\nN\n26\nn\ns\nq\n')
            assert 'more omitted' not in output and 'Page 2/2' in output, output
            assert output.count('Skipping BAD') == len(invalid), output
            menu = re.findall(r'^\d+\. (\S+)$', output, re.M)
            assert menu == expected_menu, menu
            menus.append(menu)
            assert 'Choose a compatible story number.' in output
            assert f'Starting {expected_menu[-1]}\n' in output and 'alpha moved' in output
            assert 'saved' in output and 'savefailed' not in output and 'Saves disabled' not in output
            # SAVES.BIN occurs after overflow and bad files. Saves must remain
            # discoverable and confined to their own allocation.
            after = FatImage(image.read_bytes())
            after.assert_only_saves_changed(baseline)
            for name, data in files:
                assert after.file_bytes(name) == data
            before_restore = image.read_bytes()
            assert 'alpha moved' in boot('26\nr\nl\nq\n')
            assert image.read_bytes() == before_restore
            assert 'vfive ready' in boot('1\nq\n')
        assert menus[0] == menus[1]

        # Many bad files leave every valid slot available, with contiguous labels.
        prepare(invalid+valid[1:21], fat)
        output = boot('20\nq\n')
        assert 'more omitted' not in output and 'Starting GAME20.Z5\n' in output
        assert len(re.findall(r'^\d+\. (\S+)$', output, re.M)) == 20

        prepare(invalid+[('ONLY.Z3', alpha)], fat)
        output = boot('q\n')
        assert 'Starting ONLY.Z3\n' in output and 'Select story number:' not in output
        assert 'more omitted' not in output

        prepare(invalid, fat)
        before = image.read_bytes()
        output = boot('', expected=2)
        assert 'No compatible V3/V5 stories' in output and 'more omitted' not in output
        assert image.read_bytes() == before

        prepare([], fat)
        assert 'No compatible V3/V5 stories' in boot('', expected=2)

print('PASS larger catalog: FAT16/FAT32, alphabetical pages independent of copy order, invalid-file filtering, compact numbering, late save pool, save/reset/restore, V5, empty/single-story cases and unchanged story allocations')
