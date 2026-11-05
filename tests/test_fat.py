#!/usr/bin/env python3
"""Filesystem interoperability, fragmentation, isolation and interrupted saves."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from fat_helpers import FatImage, get32

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from make_sd import make_image, project_files


def tool(name):
    path = shutil.which(name)
    for directory in ('usr/sbin', 'usr/bin', 'usr/games'):
        candidate = Path('/tmp/zork-tools')/directory/name
        if not path and candidate.exists():
            path = str(candidate)
    if not path:
        raise SystemExit(f'Required FAT test utility missing: {name} (install dosfstools/mtools)')
    return path


def command(args, expected=0, **kwargs):
    result = subprocess.run(list(map(str, args)), capture_output=True, **kwargs)
    assert result.returncode == expected, (args, result.returncode, result.stdout, result.stderr)
    return result


def play(image, commands, cut=None):
    env = dict(os.environ, ZORK_SD_IMAGE=str(image))
    if cut is not None:
        env['ZORK_CUT_AFTER_WRITES'] = str(cut)
    return command([ROOT/'impl/zork-host'], expected=99 if cut is not None else 0,
                   input=commands.encode(), env=env).stdout.decode()


def check_fs(path, scratch):
    layout = FatImage(path.read_bytes())
    # fsck operates on a filesystem, so extract just the partition for checking.
    volume = scratch/'volume.img'
    volume.write_bytes(layout.data[layout.base*512:])
    command([FSCK, '-n', volume])


FSCK, MKFS, MCOPY, MMD = map(tool, ('fsck.fat', 'mkfs.fat', 'mcopy', 'mmd'))
subprocess.run(['gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
                '-DHOST', '-Ifirmware', 'firmware/storage.c', 'tests/storage_tb.c',
                '-o', 'impl/storage-test'], cwd=ROOT, check=True)
files = project_files((ROOT/'zork1.dat').read_bytes())
with tempfile.TemporaryDirectory(prefix='zork-fat-') as directory:
    temp = Path(directory)
    image = temp/'card.img'
    unrelated = temp/'unrelated.txt'
    unrelated.write_text('Unrelated long filename data must survive SAVE and RESTORE.\n')
    for fat in (16, 32):
        for partitioned in (False, True):
            image.write_bytes(make_image(files, fat, 16 if fat==16 else 64, partitioned))
            layout = FatImage(image.read_bytes())
            drive = f'{image}@@{layout.base*512}'
            command([MCOPY, '-i', drive, unrelated, '::/A completely unrelated long filename.txt'])
            # Also put LFN records in the game's directory before save files.
            command([MCOPY, '-i', drive, unrelated, '::/ZORK/Extra notes for this game.txt'])
            layout = FatImage(image.read_bytes())
            for name, first in (('ZORK1.DAT', 11000), ('SAVES.BIN', 12000)):
                layout.fragment(name, first, stride=2)
            image.write_bytes(layout.data)
            check_fs(image, temp)
            command([ROOT/'impl/storage-test', image])
            original = image.read_bytes()
            response = play(image, 'save\nnorth\nsave\nwest\nrestore\nlook\n')
            assert 'Failed.' not in response and response.count('North of House')==2, response
            restored = play(image, 'restore\nlook\n')
            assert 'North of House' in restored, restored
            after = FatImage(image.read_bytes())
            after.assert_only_saves_changed(original)
            assert after.file_bytes('ZORK1.DAT') == files[0][1]
            copied = temp/'readback.txt'
            command([MCOPY, '-o', '-i', drive, '::/A completely unrelated long filename.txt', copied])
            assert copied.read_bytes() == unrelated.read_bytes()
            check_fs(image, temp)
            print(f'PASS FAT{fat} {"MBR" if partitioned else "superfloppy"}, fragmented story/saves, VFAT coexistence, unchanged metadata/unrelated files')

    # Independent formatter and allocator, including multi-sector clusters and
    # directories spanning clusters: avoids validating only our own generator.
    stage = temp/'stage'
    stage.mkdir()
    (stage/'unrelated.txt').write_bytes(b'keep me')
    command([sys.executable, ROOT/'scripts/make_sd.py','--save-slots','1', '--directory', stage])
    assert (stage/'unrelated.txt').read_bytes() == b'keep me'
    saved = (stage/'ZORK/SAVES.BIN').read_bytes()
    refused = subprocess.run([sys.executable, ROOT/'scripts/make_sd.py','--save-slots','1', '--directory', stage], capture_output=True)
    assert refused.returncode != 0 and (stage/'ZORK/SAVES.BIN').read_bytes() == saved
    for fat, mib, spc in ((16, 16, 4), (32, 128, 2)):
        with image.open('wb') as stream:
            stream.truncate(mib*1024*1024)
        command([MKFS, '-F', fat, '-s', spc, image])
        command([MMD, '-i', image, '::/ZORK'])
        # Force directory growth before the project names, skipping deleted and
        # VFAT entries and traversing FAT links to the next directory cluster.
        for n in range(36):
            command([MCOPY, '-i', image, unrelated, f'::/ZORK/Unrelated notes number {n}.txt'])
        for name, _ in files:
            command([MCOPY, '-i', image, stage/'ZORK'/name, f'::/ZORK/{name}'])
        command([ROOT/'impl/storage-test', image])
        baseline = image.read_bytes()
        result = play(image, 'save\nnorth\nrestore\nlook\n')
        assert 'Failed.' not in result and result.count('West of House')==2, result
        FatImage(image.read_bytes()).assert_only_saves_changed(baseline)
        check_fs(image, temp)
        print(f'PASS independent mkfs.fat/mtools FAT{fat}, {spc}-sector clusters and extended directory')

    # Use a small image to cover every interruption point in a save cheaply.
    image.write_bytes(make_image(files, 16, 8, False))
    play(image, 'save\nnorth\nsave\n')
    baseline = image.read_bytes()
    saved_layout = FatImage(baseline)
    snapshot_bytes = get32(saved_layout.file_bytes('SAVES.BIN'), 8)
    save_writes = (snapshot_bytes+511)//512+1
    for cut in range(save_writes):  # Payload sectors, then the commit header.
        image.write_bytes(baseline)
        play(image, 'restore\nwest\nsave\n', cut=cut)
        recovered = play(image, 'restore\nlook\n')
        assert recovered.count('North of House')==1 and 'Failed.' not in recovered, (cut, recovered)
        FatImage(image.read_bytes()).assert_only_saves_changed(baseline)
    image.write_bytes(baseline)
    play(image, 'restore\nwest\nsave\n')
    assert play(image, 'restore\nlook\n').count('West of House')==2
    print(f'PASS all {save_writes} interrupted-save boundaries retain the previous valid snapshot; complete save commits')

    # Torn header and payload writes are rejected by snapshot validation.
    completed = FatImage(image.read_bytes())
    target = completed.sectors('SAVES.BIN')[:256]
    for offset in (0, 12, 512+123):
        damaged = bytearray(completed.data)
        damaged[target[offset//512]*512+offset%512] ^= 0x80
        image.write_bytes(damaged)
        assert play(image, 'restore\nlook\n').count('North of House')==1
    print('PASS corrupt commit headers and payloads fall back')

    image.write_bytes(make_image(files, 16, 8, False))
    valid = FatImage(image.read_bytes())
    bad_cases = []
    def mutation(label, fn):
        candidate = FatImage(valid.data)
        fn(candidate)
        bad_cases.append((label, candidate.data))
    pool_cases = []
    def pool_mutation(label, fn):
        candidate = FatImage(valid.data)
        fn(candidate)
        pool_cases.append((label, candidate.data))
    pool_mutation('missing pool', lambda x: x.data.__setitem__(x.file_entry('SAVES.BIN'), 0xe5))
    pool_mutation('wrong pool size', lambda x: struct.pack_into('<I', x.data, x.file_entry('SAVES.BIN')+28, 123))
    pool_mutation('read-only pool', lambda x: x.data.__setitem__(x.file_entry('SAVES.BIN')+11, 0x21))
    pool_mutation('truncated pool chain', lambda x: x.set_next(x.entry_cluster(x.file_entry('SAVES.BIN')), x.eoc))
    pool_mutation('pool cycle', lambda x: x.set_next(x.chain(x.entry_cluster(x.file_entry('SAVES.BIN')))[-1], x.entry_cluster(x.file_entry('SAVES.BIN'))))
    pool_mutation('free pool cluster', lambda x: x.set_next(x.entry_cluster(x.file_entry('SAVES.BIN')), 0))
    pool_mutation('bad pool cluster', lambda x: x.set_next(x.entry_cluster(x.file_entry('SAVES.BIN')), 0xfff7))
    pool_mutation('pool outside volume', lambda x: x.set_next(x.entry_cluster(x.file_entry('SAVES.BIN')), x.clusters+2))
    pool_mutation('story/pool overlap', lambda x: x.set_entry_cluster(x.file_entry('SAVES.BIN'), x.entry_cluster(x.file_entry('ZORK1.DAT'))))
    for label, damaged in pool_cases:
        image.write_bytes(damaged)
        command([ROOT/'impl/storage-test', image], expected=3)
        assert image.read_bytes() == damaged, label
        assert 'Saves disabled' in play(image, 'save\n')
    print('PASS missing/malformed/read-only save pools allow play with all writes disabled')
    mutation('directory overlap', lambda x: x.set_next(x.entry_cluster(x.entry('ZORK')), x.entry_cluster(x.file_entry('SAVES.BIN'))))
    mutation('directory loop', lambda x: x.set_next(x.entry_cluster(x.entry('ZORK')), x.entry_cluster(x.entry('ZORK'))))
    mutation('invalid cluster size', lambda x: x.data.__setitem__(13, 3))
    mutation('wrong sector size', lambda x: struct.pack_into('<H', x.data, 11, 4096))
    mutation('zero FATs', lambda x: x.data.__setitem__(16, 0))
    mutation('too short FAT', lambda x: struct.pack_into('<H', x.data, 22, 1))
    mutation('BPB overflow', lambda x: (struct.pack_into('<H', x.data, 19, 0), struct.pack_into('<I', x.data, 32, 0xffffffff)))
    bad_cases.append(('legacy raw', b'ZKSD'+bytes(1024*1024-4)))
    for label, damaged in bad_cases:
        image.write_bytes(damaged)
        command([ROOT/'impl/storage-test', image], expected=2)
        assert image.read_bytes() == damaged, label
    image.write_bytes(valid.data)
    # Simulated sector-read errors in BPB, directory, FAT and story validation.
    for sector in (0, valid.root_lba, valid.base+valid.reserved,
                   valid.cluster_lba(valid.entry_cluster(valid.entry('ZORK'))), valid.sectors('ZORK1.DAT')[0]):
        command([ROOT/'impl/storage-test', image, sector], expected=2)
    print(f'PASS {len(bad_cases)} invalid-media cases and read failures reject mount without writes')

    # FAT32 may disable mirroring and select FAT #1 instead of FAT #0.
    alternate = FatImage(make_image(files, 32, 64, True))
    struct.pack_into('<H', alternate.data, alternate.base*512+40, 0x81)
    start = (alternate.base+alternate.reserved)*512
    alternate.data[start:start+alternate.fat_size*512] = bytes(alternate.fat_size*512)
    image.write_bytes(alternate.data)
    command([ROOT/'impl/storage-test', image])
    assert 'West of House' in play(image, 'save\nrestore\nlook\n')
    for label, offset, fmt, value in (
            ('invalid active FAT', 40, '<H', 0x82),
            ('unsupported FAT32 version', 42, '<H', 1),
            ('invalid root cluster', 44, '<I', 0)):
        broken = bytearray(alternate.data)
        struct.pack_into(fmt, broken, alternate.base*512+offset, value)
        image.write_bytes(broken)
        command([ROOT/'impl/storage-test', image], expected=2)
        assert image.read_bytes() == broken, label
    for label, offset, value in (('partition too short', 458, 1),
                                 ('partition wraps LBA', 454, 0xfffffff0)):
        broken = bytearray(alternate.data)
        struct.pack_into('<I', broken, offset, value)
        image.write_bytes(broken)
        command([ROOT/'impl/storage-test', image], expected=2)
    image.write_bytes(valid.data)
    refused = subprocess.run([sys.executable, ROOT/'scripts/make_sd.py','--save-slots','1', '--output', image], capture_output=True)
    assert refused.returncode != 0 and image.read_bytes() == valid.data
    print('PASS active FAT32 table selection, invalid FAT32/partition geometry and existing-image preservation')
