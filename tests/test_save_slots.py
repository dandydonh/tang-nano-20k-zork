#!/usr/bin/env python3
"""Player-selected saves: UI, isolation, upgrade and interrupted commits."""
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from fat_helpers import FatImage
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image, POOL_SIZE, SAVE_SIZE


def run(image, commands, cut=None):
    env = dict(os.environ, ZORK_SD_IMAGE=str(image))
    if cut is not None:
        env['ZORK_CUT_AFTER_WRITES'] = str(cut)
    result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                            capture_output=True, env=env)
    assert result.returncode == (99 if cut is not None else 0), result
    assert 'CORE ERROR' not in result.stdout, result.stdout
    return result.stdout


def only_pair_changed(before, after, player_slot, owner):
    layout = FatImage(before)
    start = (player_slot*20+owner)*2*SAVE_SIZE//512
    allowed = set(layout.sectors('SAVES.BIN')[start:start+2*SAVE_SIZE//512])
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
        image.write_bytes(make_image([('ALPHA.DAT', alpha), ('BETA.DAT', beta),
                                      ('SAVES.BIN', bytes(5*POOL_SIZE))], fat, mib, False))
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
        only_pair_changed(saved, image.read_bytes(), 2, 0)
        for slot in (4, 5):
            before = image.read_bytes()
            out = run(image, f'1\ns\n{slot}\nq\n')
            assert 'savefailed' not in out, out
            only_pair_changed(before, image.read_bytes(), slot-1, 0)
        # Every player slot is isolated from other games, even with the same
        # player slot number; renaming and menu reordering retain ownership.
        before = image.read_bytes()
        out = run(image, '2\nr\n1\n0\nn\ns\n2\nq\n')
        assert '1. Empty' in out and 'beta moved' in out and 'savefailed' not in out, out
        only_pair_changed(before, image.read_bytes(), 1, 1)
        assert 'alpha home' in run(image, '1\nr\n1\nl\nq\n')
        layout = FatImage(image.read_bytes())
        pool = layout.file_bytes('SAVES.BIN')
        image.write_bytes(make_image([('ZZZ.DAT', alpha), ('AAA.DAT', beta),
                                      ('SAVES.BIN', pool)], fat, mib, False))
        assert 'alpha moved' in run(image, '2\nr\n2\nl\nq\n')
        assert 'beta moved' in run(image, '1\nr\n2\nl\nq\n')
        print(f'PASS FAT{fat}: five selectable saves, UI editing/cancel/confirmation, game/slot isolation and rename continuity', flush=True)

    # Recover slot 3's older bank if the newest payload is corrupt. Both banks
    # remain confined to that player slot, including interrupted overwrites.
    layout = FatImage(image.read_bytes())
    sectors = layout.sectors('SAVES.BIN')
    offset = (2*20)*2*SAVE_SIZE//512
    damaged = bytearray(layout.data)
    damaged[sectors[offset+SAVE_SIZE//512+1]*512+123] ^= 128
    image.write_bytes(damaged)
    out = run(image, '2\nr\n3\nl\nq\n')
    assert 'alpha home' in out and 'restorefailed' not in out, out
    baseline = bytes(layout.data)
    payload = struct.unpack_from('<I', layout.file_bytes('SAVES.BIN'), 2*POOL_SIZE+8)[0]
    writes = (payload+511)//512+1
    for cut in range(writes):
        image.write_bytes(baseline)
        run(image, '2\ns\n3\ny\n', cut=cut)
        out = run(image, '2\nr\n3\nl\nq\n')
        assert 'alpha moved' in out and 'restorefailed' not in out, (cut, out)
        only_pair_changed(baseline, image.read_bytes(), 2, 0)
    print(f'PASS selected-slot corruption fallback and all {writes} interrupted-overwrite boundaries', flush=True)

    # Expand a real old-format pool as a copy. Its entire prefix must remain
    # identical, and slot 1 must restore the old state after expansion.
    image.write_bytes(make_image([('ALPHA.DAT', alpha), ('SAVES.BIN', bytes(POOL_SIZE))], 16, 8, False))
    assert 'saved' in run(image, 'n\ns\nq\n')
    old = temp/'old.bin'
    old.write_bytes(FatImage(image.read_bytes()).file_bytes('SAVES.BIN'))
    expanded = temp/'expanded.bin'
    args = [sys.executable, ROOT/'tests/sd_image_fixture.py', '--expand-saves', old, '--output', expanded]
    subprocess.run(args, check=True, capture_output=True)
    assert len(expanded.read_bytes()) == 5*POOL_SIZE
    assert expanded.read_bytes() == old.read_bytes()+bytes(4*POOL_SIZE)
    assert subprocess.run(args, capture_output=True).returncode != 0
    image.write_bytes(make_image([('ALPHA.DAT', alpha), ('SAVES.BIN', expanded.read_bytes())], 16, 30, False))
    assert 'alpha moved' in run(image, 'r\n1\nl\nq\n')
    before = image.read_bytes()
    assert 'savefailed' not in run(image, 's\n5\nq\n')
    only_pair_changed(before, image.read_bytes(), 4, 0)
    subprocess.run([ROOT/'impl/storage-test', image], check=True, capture_output=True)
    print('PASS lossless 5-to-25 MiB expansion, old slot-1 restore and new-slot writes', flush=True)

    # Conflicting owners across player positions or duplicated story ownership
    # must disable writes, rather than claiming or overwriting another game.
    layout = FatImage(image.read_bytes())
    sectors = layout.sectors('SAVES.BIN')
    baseline = bytes(layout.data)
    header = baseline[sectors[0]*512:(sectors[0]+1)*512]
    for index, conflicting in ((2*20*SAVE_SIZE//512, True), ((20+1)*2*SAVE_SIZE//512, False)):
        bad = bytearray(baseline)
        off = sectors[index]*512
        bad[off:off+512] = header
        if conflicting:
            bad[off+16] ^= 1
        image.write_bytes(bad)
        out = run(image, 's\nq\n')
        assert 'Saves disabled' in out and 'savefailed' in out, out
        assert image.read_bytes() == bad
    print('PASS cross-position mixed/duplicate ownership disables all writes', flush=True)

    # Allocate all twenty story owners, then write the final pair of plane 2.
    files = [(f'GAME{i:02}.DAT', make_story(release=i+1)) for i in range(20)]
    image.write_bytes(make_image(files+[('SAVES.BIN', bytes(2*POOL_SIZE))], 16, 16, False))
    for choice in range(1, 21):
        out = run(image, f'{choice}\ns\n1\nq\n')
        assert 'savefailed' not in out and 'Saves disabled' not in out, out
    before = image.read_bytes()
    out = run(image, '20\nn\ns\n2\nq\n')
    assert 'savefailed' not in out, out
    only_pair_changed(before, image.read_bytes(), 1, 19)
    assert 'alpha moved' in run(image, '20\nr\n2\nl\nq\n')
    print('PASS all twenty story owners and the last pair of an expanded pool', flush=True)

    # Maximum supported configuration exercises two-digit player slot input.
    image.write_bytes(make_image([('ALPHA.DAT', alpha), ('SAVES.BIN', bytes(20*POOL_SIZE))], 32, 128, False))
    out = run(image, 'n\ns\n20\nq\n')
    assert '20. Empty' in out and 'savefailed' not in out, out
    assert 'alpha moved' in run(image, 'r\n20\nl\nq\n')
    print('PASS twenty selectable player slots and two-digit save/restore', flush=True)
