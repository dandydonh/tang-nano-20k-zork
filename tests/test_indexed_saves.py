#!/usr/bin/env python3
"""Indexed pool capacity, real snapshots, atomic ownership and corruption tests."""
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from indexed_pool_helpers import sparse_card, pool_read, pool_write, pool_lba
from v3_fixture import make_story
from v5_fixture import make_story as make_v5_story

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from make_sd import make_image
from prepare_save_pool import pool_header, create_pool, checksum


def fresh_pool(games=3, positions=2):
    header, size = pool_header(games, positions)
    return header+header+bytes(size-1024)


with tempfile.TemporaryDirectory(prefix='zork-indexed-') as directory:
    temp = Path(directory)
    image = temp/'card.img'

    def run(commands, cut=None):
        env = dict(os.environ, ZORK_SD_IMAGE=str(image))
        if cut is not None:
            env['ZORK_CUT_AFTER_WRITES'] = str(cut)
        result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                                capture_output=True, env=env, timeout=30)
        assert result.returncode == (99 if cut is not None else 0), (result.stdout, result.stderr)
        assert 'CORE ERROR' not in result.stdout and 'testfailed' not in result.stdout, result.stdout
        return result.stdout

    alpha, beta = make_story(), make_story(name='beta', release=2)
    for fat in (16, 32):
        image.write_bytes(make_image([('ALPHA.Z3', alpha), ('BETA.Z3', beta),
                                      ('SAVES.BIN', fresh_pool())], fat, 8 if fat == 16 else 64, False))
        before = image.read_bytes()
        assert 'Saves disabled' not in run('1\nq\n') and image.read_bytes() == before
        out = run('1\ns\n1\nn\ns\n2\nq\n')
        assert out.count('saved\n') == 2 and 'savefailed' not in out, out
        assert 'alpha home' in run('1\nr\n1\nl\nq\n')
        assert 'alpha moved' in run('1\nr\n2\nl\nq\n')
        assert 'saved' in run('2\nn\ns\n2\nq\n')
        assert 'beta moved' in run('2\nr\n2\nl\nq\n')
        layout = FatImage(image.read_bytes())
        layout.assert_only_saves_changed(before)
        assert layout.file_bytes('ALPHA.Z3') == alpha and layout.file_bytes('BETA.Z3') == beta
        pool = layout.file_bytes('SAVES.BIN')
        assert pool[1024:1028] == b'ZOWN' and pool[1056:1060] == b'ZOWN'
        # Only the selected owner record in each index replica may change.
        assert pool[1024:1088] == pool[1536:1600]
        assert pool[1088:1536] == bytes(448) and pool[1600:2048] == bytes(448)
        header, size = pool_header(3, 2)
        image.write_bytes(make_image([('ZZZ.Z3', alpha), ('AAA.Z3', beta), ('SAVES.BIN', pool)],
                                    fat, 8 if fat == 16 else 64, False))
        assert 'alpha moved' in run('2\nr\n2\nl\nq\n')
        assert 'beta moved' in run('1\nr\n2\nl\nq\n')
        print(f'PASS FAT{fat} indexed pool: deferred claims, independent positions/owners, rename/reorder, metadata replicas and write bounds')

    # V3/V5 snapshots retain their existing payload formats within indexed pools.
    image.write_bytes(make_image([('ALPHA.Z3', alpha), ('VFIVE.Z5', make_v5_story()),
                                  ('SAVES.BIN', fresh_pool())], 16, 8, False))
    assert 'saved' in run('1\nn\ns\n2\nq\n')
    assert 'saved' in run('2\ns\n1\nn\nr\n1\nq\n')
    assert 'restored' in run('2\nr\n1\nq\n')
    assert 'alpha moved' in run('1\nr\n2\nl\nq\n')
    print('PASS indexed mixed V3/V5 persistent snapshots')

    # Interrupt each write of first ownership allocation and snapshot creation.
    image.write_bytes(make_image([('ALPHA.Z3', alpha), ('BETA.Z3', beta),
                                  ('SAVES.BIN', fresh_pool())], 16, 8, False))
    assert 'saved' in run('1\nn\ns\n1\nq\n')
    baseline = image.read_bytes()
    assert 'saved' in run('2\ns\n1\nq\n')
    completed = FatImage(image.read_bytes()).file_bytes('SAVES.BIN')
    data_sector = struct.unpack_from('<I', completed, 28)[0]
    payload = struct.unpack_from('<I', completed, data_sector*512+2*2*131072+8)[0]
    writes = 2+(payload+511)//512+1
    for cut in range(writes):
        image.write_bytes(baseline)
        run('2\ns\n1\n', cut=cut)
        assert 'alpha moved' in run('1\nr\n1\nl\nq\n')
        assert 'saved' in run('2\ns\n1\nq\n')
        assert 'beta home' in run('2\nr\n1\nl\nq\n')
    print(f'PASS all {writes} interrupted initial-claim/snapshot boundaries preserve neighboring owners and allow retry')

    # Each redundant header/index copy can recover independently. Damage both
    # records for one owner: existing other owners still restore; no new claims.
    image.write_bytes(baseline)
    for description, offsets in [('header A', [100]), ('header B', [612]),
                                  ('owner A', [1024+28]), ('owner B', [1536+28])]:
        layout = FatImage(baseline)
        sectors = layout.sectors('SAVES.BIN')
        for offset in offsets:
            layout.data[sectors[offset//512]*512+offset%512] ^= 0x80
        image.write_bytes(layout.data)
        assert 'alpha moved' in run('1\nr\n1\nl\nq\n'), description
    layout = FatImage(baseline)
    sectors = layout.sectors('SAVES.BIN')
    for offset in (1024+32, 1536+32):
        layout.data[sectors[offset//512]*512+offset%512] = 0xff
    image.write_bytes(layout.data)
    assert 'alpha moved' in run('1\nr\n1\nl\nq\n')
    before = image.read_bytes()
    out = run('2\ns\nq\n')
    assert 'Save index damaged' in out and 'savefailed' in out and image.read_bytes() == before
    print('PASS redundant headers/owner records and fail-closed damaged-owner allocation')

    # Repair an interrupted/corrupt replica before writing another snapshot.
    layout = FatImage(baseline)
    sectors = layout.sectors('SAVES.BIN')
    layout.data[sectors[2]*512+28] ^= 0x80
    image.write_bytes(layout.data)
    assert 'saved' in run('1\ns\n2\nq\n')
    repaired = FatImage(image.read_bytes()).file_bytes('SAVES.BIN')
    assert repaired[1024:1056] == repaired[1536:1568]
    assert checksum(repaired[1024:1052]) == struct.unpack_from('<I', repaired, 1052)[0]

    # Conflicting headers and duplicate ownership fail without writing anything.
    for kind in ('both headers', 'conflicting headers', 'duplicate owner'):
        layout = FatImage(baseline)
        sectors = layout.sectors('SAVES.BIN')
        if kind == 'both headers':
            layout.data[sectors[0]*512+100] ^= 1
            layout.data[sectors[1]*512+100] ^= 1
        elif kind == 'conflicting headers':
            header = bytearray(layout.file_bytes('SAVES.BIN')[:512])
            header[40] = 1
            struct.pack_into('<I', header, 508, checksum(header[:508]))
            layout.data[sectors[1]*512:(sectors[1]+1)*512] = header
        else:
            record = bytearray(layout.file_bytes('SAVES.BIN')[1024:1056])
            struct.pack_into('<I', record, 24, 1)
            struct.pack_into('<I', record, 28, checksum(record[:28]))
            for sector in (2, 3):
                layout.data[sectors[sector]*512+32:sectors[sector]*512+64] = record
        image.write_bytes(layout.data)
        before = image.read_bytes()
        assert 'Saves disabled' in run('1\ns\nq\n') and image.read_bytes() == before, kind

    # A damaged newest snapshot still falls back inside its own indexed pair.
    image.write_bytes(baseline)
    assert 'saved' in run('1\ns\n1\ny\nq\n')
    layout = FatImage(image.read_bytes())
    sectors = layout.sectors('SAVES.BIN')
    layout.data[sectors[data_sector+256+1]*512+100] ^= 128
    image.write_bytes(layout.data)
    assert 'alpha moved' in run('1\nr\n1\nl\nq\n')
    print('PASS replica repair, conflicting headers, duplicate ownership and snapshot corruption fallback')

    for kind in ('read only', 'story overlap', 'directory overlap', 'short chain', 'cycle'):
        layout = FatImage(baseline)
        entry = layout.file_entry('SAVES.BIN')
        cluster = layout.entry_cluster(entry)
        if kind == 'read only':
            layout.data[entry+11] |= 1
        elif kind == 'story overlap':
            layout.set_entry_cluster(entry, layout.entry_cluster(layout.file_entry('ALPHA.Z3')))
        elif kind == 'directory overlap':
            layout.set_entry_cluster(entry, layout.entry_cluster(layout.entry('ZORK')))
        else:
            layout.set_next(cluster, layout.eoc if kind == 'short chain' else cluster)
        image.write_bytes(layout.data)
        before = image.read_bytes()
        assert 'Saves disabled' in run('1\ns\nq\n') and image.read_bytes() == before, kind
    print('PASS indexed read-only pools, protected-allocation overlap and malformed/cyclic FAT chains fail without writes')

    # Default-size pool and all owners use a sparse multi-GiB FAT32 card; no
    # whole-card or whole-pool bytearray allocation or physical SD access.
    layout = sparse_card(image, alpha)
    subprocess.run(['gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-Wno-misleading-indentation', '-DHOST', '-Ifirmware', 'firmware/storage.c',
                    'tests/indexed_capacity_tb.c', '-o', 'impl/indexed-capacity-test'], cwd=ROOT, check=True)
    result = subprocess.run([ROOT/'impl/indexed-capacity-test', image, str(layout['story_lba'])],
                            text=True, capture_output=True, timeout=120, check=True)
    print(result.stdout.strip())
    # Independently check the sparse filesystem and its large file geometry.
    subprocess.run(['fsck.fat', '-n', str(image)], check=True, capture_output=True)

    layout = sparse_card(image, alpha, games=1000, positions=5, fragmented=True)
    assert 'saved' in run('n\ns\n5\nq\n')
    assert 'alpha moved' in run('r\n5\nl\nq\n')
    print('PASS fragmented default-size indexed pool and final-position gameplay/save/reset/restore')

    layout = sparse_card(image, alpha, fragmented='excessive')
    metadata = pool_read(image, layout, 0, 128)
    out = run('s\nq\n')
    assert 'Saves disabled' in out and 'savefailed' in out
    assert pool_read(image, layout, 0, 128) == metadata
    print('PASS excessive fragmentation safely disables indexed writes without overrunning the extent cache')

    output = temp/'SAVES.BIN'
    subprocess.run([sys.executable, ROOT/'scripts/prepare_save_pool.py', '--output', output], check=True, capture_output=True)
    header, size = pool_header()
    assert output.stat().st_size == size == 1310785536
    with output.open('rb') as stream:
        assert stream.read(1024) == header+header
        stream.seek(size-512)
        assert stream.read() == bytes(512)
    assert subprocess.run([sys.executable, ROOT/'scripts/prepare_save_pool.py', '--output', output], capture_output=True).returncode != 0
    for positions in (17, 20):
        refused = temp/f'refused-{positions}.bin'
        assert subprocess.run([sys.executable, ROOT/'scripts/prepare_save_pool.py', '--positions', str(positions), '--output', refused], capture_output=True).returncode != 0
        assert not refused.exists()
    assert pool_header(1000, 16)[1] < 2**32
    print('PASS streaming fresh-pool tool: exact 1000x5 size, zero data, overwrite refusal and 32-bit file-size bounds')
