#!/usr/bin/env python3
"""Player-selected saves: UI, isolation, paired rename and interrupted commits."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from fat_helpers import FatImage
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image, SAVE_SIZE, project_files


def run(image, commands, cut=None):
    env = dict(os.environ, ZORK_SD_IMAGE=str(image))
    if cut is not None:
        env['ZORK_CUT_AFTER_WRITES'] = str(cut)
    result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                            capture_output=True, env=env)
    assert result.returncode == (99 if cut is not None else 0), result
    assert 'CORE ERROR' not in result.stdout, result.stdout
    return result.stdout


def only_pair_changed(before, after, player_slot, name):
    layout = FatImage(before)
    start = 4+player_slot*2*SAVE_SIZE//512
    allowed = set(layout.sectors(name)[start:start+2*SAVE_SIZE//512])
    assert len(before) == len(after)
    for sector in range(len(before)//512):
        if sector not in allowed:
            off = sector*512
            assert before[off:off+512] == after[off:off+512], sector


with tempfile.TemporaryDirectory(prefix='zork-save-slots-') as directory:
    temp = Path(directory)
    image = temp/'card.img'
    alpha, beta = make_story(), make_story(name='beta', release=2)
    for fat, mib in ((16, 30), (32, 64)):
        image.write_bytes(make_image(project_files(alpha,'ALPHA.DAT')+project_files(beta,'BETA.DAT'), fat, mib, False))
        baseline = image.read_bytes()
        # Save at home in slot 1; moved in slot 2. Menu input never enters
        # the story parser or command history. Escape keys are consumed.
        out = run(image, '1\ns\n\nn\ns\n2\nq\n')
        assert out.count('saved\n') == 2 and '1. Saved' in out and '2. Empty' in out, out
        assert 'alpha home' in run(image, '1\nr\n1\nl\nq\n')
        out = run(image, '1\nr\n2\nl\nq\n')
        assert 'alpha moved' in out and 'restorefailed' not in out, out
        saved = image.read_bytes()
        # Reject bad selections, overflow and empty restore; cancellation is
        # read-only, including a declined occupied-slot overwrite.
        out = run(image, '1\ns\n99\n12345678901234567890\nx\n1\nn\n0\nr\n5\nq\nq\n')
        assert 'Invalid slot number.' in out and 'Overwrite cancelled.' in out, out
        assert 'Slot is empty.' in out and 'Cancelled.' in out, out
        assert image.read_bytes() == saved
        out = run(image, '1\ns\n0\n\x1b[A\n0\nq\n')
        assert out.count('Save slots for ALPHA.DAT:') == 2, out
        assert image.read_bytes() == saved  # Up recalls SAVE, not menu input.
        # Backspace edits the slot selection; save slot 3 at home then moved.
        out = run(image, '1\ns\n\x1b[A2\x7f3\nn\ns\n3\ny\nq\n')
        assert out.count('saved\n') == 2 and 'Overwrite slot 3?' in out, out
        only_pair_changed(saved, image.read_bytes(), 2, 'ALPHA.SAV')
        for slot in (4, 5):
            before = image.read_bytes()
            out = run(image, f'1\ns\n{slot}\nq\n')
            assert 'savefailed' not in out, out
            only_pair_changed(before, image.read_bytes(), slot-1, 'ALPHA.SAV')
        # Every player slot is isolated from other games, even with the same
        # player slot number; renaming and menu reordering retain ownership.
        before = image.read_bytes()
        out = run(image, '2\nr\n1\n0\nn\ns\n2\nq\n')
        assert '1. Empty' in out and 'beta moved' in out and 'savefailed' not in out, out
        only_pair_changed(before, image.read_bytes(), 1, 'BETA.SAV')
        assert 'alpha home' in run(image, '1\nr\n1\nl\nq\n')
        layout = FatImage(image.read_bytes())
        saves=[('ZZZ.SAV',layout.file_bytes('ALPHA.SAV')),('AAA.SAV',layout.file_bytes('BETA.SAV'))]
        image.write_bytes(make_image([('ZZZ.DAT',alpha),('AAA.DAT',beta)]+saves,fat,mib,False))
        assert 'alpha moved' in run(image, '2\nr\n2\nl\nq\n')
        assert 'beta moved' in run(image, '1\nr\n2\nl\nq\n')
        print(f'PASS FAT{fat}: five selectable saves, UI editing/cancel/confirmation, game/slot isolation and rename continuity', flush=True)

    # Recover slot 3's older bank if the newest payload is corrupt. Both banks
    # remain confined to that player slot, including interrupted overwrites.
    layout = FatImage(image.read_bytes())
    sectors = layout.sectors('ZZZ.SAV')
    offset = 4+2*2*SAVE_SIZE//512
    damaged = bytearray(layout.data)
    damaged[sectors[offset+SAVE_SIZE//512+1]*512+123] ^= 128
    image.write_bytes(damaged)
    out = run(image, '2\nr\n3\nl\nq\n')
    assert 'alpha home' in out and 'restorefailed' not in out, out
    baseline = bytes(layout.data)
    payload = struct.unpack_from('<I', layout.file_bytes('ZZZ.SAV'), 2048+2*2*SAVE_SIZE+8)[0]
    writes = (payload+511)//512+1
    for cut in range(writes):
        image.write_bytes(baseline)
        run(image, '2\ns\n3\ny\n', cut=cut)
        out = run(image, '2\nr\n3\nl\nq\n')
        assert 'alpha moved' in out and 'restorefailed' not in out, (cut, out)
        only_pair_changed(baseline, image.read_bytes(), 2, 'ZZZ.SAV')
    print(f'PASS selected-slot corruption fallback and all {writes} interrupted-overwrite boundaries', flush=True)
