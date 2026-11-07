#!/usr/bin/env python3
"""Discover mixed story extensions and preserve saves across extension changes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story
from v5_fixture import make_story as make_v5_story

ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image, POOL_SIZE

with tempfile.TemporaryDirectory(prefix='zork-extensions-') as directory:
    temp = Path(directory)
    image = temp/'card.img'
    alpha, beta, gamma = make_story(name='alpha'), make_story(name='beta', release=2), make_v5_story()

    def boot(commands, expected=0):
        result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                                capture_output=True, timeout=30,
                                env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
        assert result.returncode == expected, (result.stdout, result.stderr)
        assert (expected != 0 or 'CORE ERROR' not in result.stdout) and 'testfailed' not in result.stdout, result.stdout
        return result.stdout

    for fat, size in ((16, 8), (32, 64)):
        # Copy order differs from menu order; unsupported suffixes are ignored.
        files = [('GAMMA.Z5', gamma), ('BETA.Z3', beta), ('ALPHA.DAT', alpha),
                 ('IGNORE.Z4', alpha), ('IGNORE.Z30', alpha), ('SAVES.BIN', bytes(POOL_SIZE))]
        image.write_bytes(make_image(files, fat, size, False))
        for choice, phrase in ((1, 'alpha ready'), (2, 'beta ready'), (3, 'vfive ready')):
            output = boot(f'{choice}\ns\nq\n')
            assert '1. ALPHA.DAT\n2. BETA.Z3\n3. GAMMA.Z5\n' in output, output
            assert phrase in output and 'saved' in output and 'savefailed' not in output, output
            assert 'IGNORE' not in output and '.Z3 ' not in output and '.Z5 ' not in output, output
        before = image.read_bytes()
        output = boot('3\nr\nq\n')
        assert 'restored' in output, output
        assert image.read_bytes() == before

        # Change only a saved game's extension. Identity and restore still work.
        layout = FatImage(before)
        entry = layout.file_entry('BETA.Z3')
        layout.data[entry+8:entry+11] = b'Z5 '
        image.write_bytes(layout.data)
        output = boot('2\nr\nq\n')
        assert 'Starting BETA.Z5\n' in output and 'restorefailed' not in output, output
        assert image.read_bytes() == layout.data
        for name, data in files:
            assert FatImage(image.read_bytes()).file_bytes('BETA.Z5' if name == 'BETA.Z3' else name) == (
                FatImage(before).file_bytes(name) if name == 'SAVES.BIN' else data)

    # Matching is case-insensitive even for noncanonical lowercase FAT entries.
    for extension in ('DAT', 'Z3', 'Z5'):
        layout = FatImage(make_image([('LOWER.'+extension, alpha)], 16, 8, False))
        entry = layout.file_entry('LOWER.'+extension)
        layout.data[entry+8:entry+11] = extension.lower().ljust(3).encode()
        image.write_bytes(layout.data)
        assert 'Starting LOWER.'+extension.lower()+'\n' in boot('q\n')

    # More than twenty stories remain selectable across pages.
    files = [(f'GAME{i:02}.'+('DAT', 'Z3', 'Z5')[i%3], alpha) for i in range(21)]
    image.write_bytes(make_image(files, 16, 8, False))
    output = boot('N\n21\nq\n')
    assert 'Page 2/2' in output and 'more omitted' not in output
    assert 'Starting GAME20.Z5\n' in output and '21. GAME20.Z5' in output

    # The header decides compatibility, rather than trusting the suffix.
    invalid = bytearray(alpha)
    invalid[0] = 4
    image.write_bytes(make_image([('BAD.Z5', invalid)], 16, 8, False))
    output = boot('', expected=2)
    assert 'Skipping BAD.Z5:' in output and 'No compatible V3/V5 stories' in output

    # CLI accepts lowercase source extensions, retaining file bytes and suffixes.
    for suffix, data in (('dat', alpha), ('z3', beta), ('z5', gamma)):
        source = temp/f'input.{suffix}'
        source.write_bytes(data)
        stage = temp/suffix
        stage.mkdir()
        result = subprocess.run([sys.executable, ROOT/'tests/sd_image_fixture.py', '--directory', stage,
                                 '--story', source, '--save-slots', '1'],
                                text=True, capture_output=True, check=True)
        assert (stage/'ZORK'/f'INPUT.{suffix.upper()}').read_bytes() == data
        assert f'INPUT.{suffix.upper()} SHA256' in result.stdout

print('PASS DAT/Z3/Z5: FAT16/FAT32 mixed menu, V3/V5 execution, saves, extension rename, ignored suffixes, case handling, header validation and CLI staging')
