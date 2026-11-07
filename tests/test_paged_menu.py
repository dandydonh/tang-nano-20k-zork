#!/usr/bin/env python3
"""A thousand accessible games, bounded pages, editing and oversized libraries."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image, POOL_SIZE

first = make_story(name='first', release=1)
middle = make_story(name='middle', release=2)
last = make_story(name='last', release=1000)
files = [(f'G{i:04}.{("DAT", "Z3", "Z5")[i%3]}', first if i == 0 else last if i == 999 else middle)
         for i in range(1000)]
bad = [(f'BAD{i:04}.Z3', bytes(64)) for i in range(25)]

with tempfile.TemporaryDirectory(prefix='zork-paged-menu-') as directory:
    temp = Path(directory)
    image = temp/'card.img'

    def boot(commands, rows=None):
        env = dict(os.environ, ZORK_SD_IMAGE=str(image))
        if rows is not None:
            env['ZORK_PAGE_ROWS'] = str(rows)
        result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                                capture_output=True, timeout=60, env=env)
        assert result.returncode == 0 and 'CORE ERROR' not in result.stdout, (result.stdout, result.stderr)
        return result.stdout

    for fat, size in ((16, 16), (32, 64)):
        for order in (files, list(reversed(files))):
            image.write_bytes(make_image(bad+order+[('SAVES.BIN', bytes(POOL_SIZE))], fat, size, False))
            before = image.read_bytes()
            out = boot('P\nN\nP\n1000\nn\ns\nq\n')
            pages = re.findall(r'Page (\d+)/(\d+) \(stories (\d+)-(\d+) of (\d+)\)', out)
            assert pages == [('1','50','1','20','1000'), ('2','50','21','40','1000'), ('1','50','1','20','1000')], pages
            assert 'Already on first page.' in out and '1000 compatible files;' not in out
            assert out.count('Skipping BAD') == len(bad)
            assert 'Starting G0999.DAT\n' in out and 'last moved' in out and 'saved' in out, out[-1000:]
            after = FatImage(image.read_bytes())
            after.assert_only_saves_changed(before)
            assert after.file_bytes('G0999.DAT') == last
            assert 'last moved' in boot('1000\nr\nl\nq\n')
            assert 'first ready' in boot('1\nq\n')
            # Four-digit selection, overflow repair, delete and ANSI arrows.
            for keys in ('999\x7f\x7f\x7f1000', '10000\x7f', '\x1b[A1000', '0\n1001\n99999\nx\n\n1000'):
                out = boot(keys+'\nq\n')
                assert 'Starting G0999.DAT\n' in out, (keys, out[-1000:])
        print(f'PASS FAT{fat}: all 1000 candidates, copy-order independent pages, direct four-digit selection, editing and selected-game save/reset/restore')

    # Every page can be reached without leaving the menu; the last entry remains
    # addressable directly from page 1 or after navigating all fifty pages.
    image.write_bytes(make_image(files, 16, 16, False))
    out = boot('N\n'*49+'N\nP\nN\n1000\nq\n')
    assert 'Page 50/50 (stories 981-1000 of 1000)' in out
    assert 'Already on last page.' in out and '1000. G0999.DAT\n' in out
    assert 'Starting G0999.DAT\n' in out
    out = boot('N\n1000\nq\n', rows=18)
    assert 'Page 1/84 (stories 1-12 of 1000)' in out and 'Page 2/84 (stories 13-24 of 1000)' in out
    assert '[MORE]' not in out

    # The 1001st compatible file warns rather than aborting, keeping the same
    # alphabetical first thousand regardless of directory copy order.
    extra = ('G1000.Z3', middle)
    for order in ([extra]+list(reversed(files)), files+[extra]):
        image.write_bytes(make_image(bad+order, 16, 16, False))
        out = boot('N\n1000\nq\n')
        assert 'Story menu limited to 1000 compatible files; 1 more omitted.' in out
        assert '1 additional compatible stories omitted.' in out
        assert 'Starting G0999.DAT\n' in out

    # The CLI story limit is independent of the legacy save-owner count.
    paths = []
    for index in range(1000):
        path = temp/f'G{index:04}.z3'
        path.write_bytes(first)
        paths += ['--story', str(path)]
    stage = temp/'stage'
    stage.mkdir()
    subprocess.run([sys.executable, ROOT/'tests/sd_image_fixture.py', '--directory', stage,
                    '--save-slots', '1', *paths], check=True, capture_output=True)
    assert len(list((stage/'ZORK').glob('*.Z3'))) == 1000
    refused = temp/'refused'
    refused.mkdir()
    assert subprocess.run([sys.executable, ROOT/'tests/sd_image_fixture.py', '--directory', refused,
                           *paths, '--story', str(temp/'G0000.z3')], capture_output=True).returncode != 0
    assert not (refused/'ZORK').exists()

    # Real VFAT records at maximum length exceed the old 256-sector/32-extent
    # bounds. All 1000 long names must fit discovery and row-aware pagination.
    if all(shutil.which(tool) for tool in ('mkfs.fat', 'mmd', 'mcopy')):
        with image.open('wb') as stream:
            stream.truncate(16*1024*1024)
        subprocess.run(['mkfs.fat', '-F', '16', str(image)], check=True, capture_output=True)
        subprocess.run(['mmd', '-i', str(image), '::/ZORK'], check=True)
        longest = None
        for index in range(999, -1, -1):
            prefix = f'Adventure {index:04} '
            name = prefix+'x'*(255-len(prefix)-3)+'.z3'
            assert len(name) == 255
            source = temp/name
            source.write_bytes(last if index == 999 else middle)
            subprocess.run(['mcopy', '-i', str(image), str(source), '::/ZORK/'], check=True)
            if index == 999:
                longest = name
        out = boot('N\nP\n1000\nq\n')
        assert 'Page 1/167 (stories 1-6 of 1000)' in out
        assert 'Starting '+longest in out.replace('\n', '')
        assert 'last ready' in out
        for frame in out.split('\x1b[0m\x1b[2J\x1b[2;1H')[1:]:
            visible = frame.split('Select story number:')[0]
            assert len(visible.splitlines()) <= 30, len(visible.splitlines())
        subprocess.run(['fsck.fat', '-n', str(image)], check=True, capture_output=True)
        print('PASS independent 1000x255-character VFAT library, fragmented growing directory and row-aware pages')
    else:
        print('SKIP independent maximal-VFAT library (mtools unavailable)')

print('PASS paged 1000-story menu, N/P boundaries, all pages, four-digit editing, row limits, overflow and CLI capacity')
