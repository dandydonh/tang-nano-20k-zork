#!/usr/bin/env python3
"""VFAT story names: validation, directory boundaries, ordering and save identity."""
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story
from v5_fixture import make_story as make_v5_story

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from make_sd import make_image, POOL_SIZE

OFFSETS = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)
alpha = make_story(name='alpha', release=801)
beta = make_story(name='beta', release=802)
vfive = make_v5_story()


def lfn_records(name, short):
    stem, suffix = short.split('.')
    checksum = 0
    for value in (stem.ljust(8)+suffix.ljust(3)).encode():
        checksum = (((checksum & 1) << 7)+(checksum >> 1)+value) & 255
    encoded = name.encode('utf-16le')
    units = list(struct.unpack('<'+'H'*(len(encoded)//2), encoded))
    if len(units) % 13:
        units.append(0)
        units += [0xffff]*((-len(units)) % 13)
    result = []
    for ordinal in range(len(units)//13, 0, -1):
        entry = bytearray(32)
        entry[0] = ordinal | (0x40 if ordinal == len(units)//13 else 0)
        entry[11], entry[13] = 0x0f, checksum
        for offset, value in zip(OFFSETS, units[(ordinal-1)*13:ordinal*13]):
            struct.pack_into('<H', entry, offset, value)
        result.append(entry)
    return result


with tempfile.TemporaryDirectory(prefix='zork-long-names-') as directory:
    work = Path(directory)
    image = work/'card.img'

    def boot(commands, expected=0):
        result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                                capture_output=True, timeout=30,
                                env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
        assert result.returncode == expected, (result.stdout, result.stderr)
        if expected == 0:
            assert 'CORE ERROR' not in result.stdout and 'testfailed' not in result.stdout, result.stdout
        return result.stdout, result.stderr

    def prepare(records, fat=16, mutate=None, fragment=False):
        # Thirteen leading entries position the first LFN at the end of a sector.
        padding = [(f'PAD{i:03}.TXT', b'padding') for i in range(100)]
        files = [(alias, data) for alias, name, data in records]+[('SAVES.BIN', bytes(POOL_SIZE))]+padding
        layout = FatImage(make_image(files, fat, 8 if fat == 16 else 64, False))
        first = layout.entry_cluster(layout.entry('ZORK'))
        chain = layout.chain(first)
        offsets = [layout.cluster_offset(c)+off for c in chain for off in range(0, 512, 32)]
        entries = [bytes(layout.data[layout.file_entry(alias):layout.file_entry(alias)+32])
                   for alias, _, _ in records]
        pool = bytes(layout.data[layout.file_entry('SAVES.BIN'):layout.file_entry('SAVES.BIN')+32])
        packed = [bytes(layout.data[offsets[i]:offsets[i]+32]) for i in range(2)]
        packed += [bytes(layout.data[layout.file_entry(name):layout.file_entry(name)+32]) for name, _ in padding[:13]]
        for (alias, name, _), entry in zip(records, entries):
            long = lfn_records(name, alias) if name is not None else []
            if mutate:
                mutate(long)
            packed += long+[entry]
        packed.append(pool)
        assert len(packed) < len(offsets)
        for i, offset in enumerate(offsets):
            layout.data[offset:offset+32] = packed[i] if i < len(packed) else bytes(32)
        if fragment:
            new = [14000+3*i for i in range(len(chain))]
            for old, target in zip(chain, new):
                assert layout.next(target) == 0
                at, to = layout.cluster_offset(old), layout.cluster_offset(target)
                layout.data[to:to+512] = layout.data[at:at+512]
            for i, target in enumerate(new):
                layout.set_next(target, new[i+1] if i+1 < len(new) else layout.eoc)
            for old in chain:
                layout.set_next(old, 0)
            layout.set_entry_cluster(layout.entry('ZORK'), new[0])
            layout.set_entry_cluster(layout.cluster_offset(new[0]), new[0])
        image.write_bytes(layout.data)
        return layout

    for fat in (16, 32):
        records = [('AAA~1.Z3', 'Zulu story.z3', beta),
                   ('ZZZ~1.Z5', 'Alpha adventure.z5', vfive),
                   ('MARS20~1.Z3', 'mars2049ad.z3', alpha)]
        prepare(records, fat, fragment=True)
        before = image.read_bytes()
        output, _ = boot('3\nn\ns\nq\n')
        assert '1. Alpha adventure.z5\n2. mars2049ad.z3\n3. Zulu story.z3\n' in output, output
        assert 'Starting Zulu story.z3\n' in output and 'beta moved' in output
        assert 'saved' in output and 'savefailed' not in output
        assert 'AAA~1' not in output and 'MARS20~1' not in output
        FatImage(image.read_bytes()).assert_only_saves_changed(before)
        assert 'vfive ready' in boot('1\nq\n')[0]

        # Removing only the LFN leaves the same content identity and saved state.
        layout = FatImage(image.read_bytes())
        target = layout.file_entry('AAA~1.Z3')
        # This sequence is on the first sector's last slot and the next cluster.
        first = layout.entry_cluster(layout.entry('ZORK'))
        offsets = [layout.cluster_offset(c)+i for c in layout.chain(first) for i in range(0, 512, 32)]
        index = offsets.index(target)-1
        while layout.data[offsets[index]+11] == 0x0f:
            layout.data[offsets[index]] = 0xe5
            index -= 1
        image.write_bytes(layout.data)
        output, _ = boot('1\nr\nl\nq\n')
        assert 'Starting AAA~1.Z3\n' in output and 'beta moved' in output and 'restorefailed' not in output

        # Boundary lengths: exactly 13/26 units have no terminator, 255 is maximal.
        for length in (13, 26, 255):
            name = 'a'*(length-3)+'.z3'
            prepare([('LONG~1.Z3', name, alpha)], fat)
            output, status = boot('q\n')
            assert 'Starting '+name in output.replace('\n', ''), output
            assert 'Select story number:' not in output
            assert 'Score: 0' in status and 'Moves: 0' in status

        prepare([('UNICOD~1.Z3', 'Café on Mars.z3', alpha)], fat)
        assert 'Starting Caf? on Mars.z3\n' in boot('q\n')[0]

        # Pagination sorts display names, rather than misleading aliases.
        records = [(f'Z{i:02}~1.Z3', f'Adventure {24-i:02}.z3', alpha) for i in range(25)]
        prepare(records, fat)
        output, _ = boot('N\n25\nq\n')
        assert 'more omitted' not in output and 'Starting Adventure 24.z3\n' in output
        assert re.findall(r'^\d+\. (.+)$', output, re.M) == [f'Adventure {i:02}.z3' for i in range(25)]

    # Corrupt/incomplete/orphan LFN records must always fall back to the alias.
    mutations = {
        'checksum': lambda records: records[-1].__setitem__(13, records[-1][13] ^ 1),
        'type': lambda records: records[-1].__setitem__(12, 1),
        'cluster': lambda records: records[-1].__setitem__(26, 1),
        'ordinal': lambda records: records[-1].__setitem__(0, 2),
        'reserved ordinal bit': lambda records: records[0].__setitem__(0, records[0][0] | 0x20),
        'deleted': lambda records: records[-1].__setitem__(0, 0xe5),
        'missing last flag': lambda records: records[0].__setitem__(0, records[0][0] & ~0x40),
        'incomplete': lambda records: records.pop(),
        'bad padding': lambda records: struct.pack_into('<H', records[0], 30, 65),
        'terminal escape': lambda records: struct.pack_into('<H', records[-1], 1, 27),
        'too long': lambda records: None,
    }
    for label, mutate in mutations.items():
        name = 'a'*253+'.z3' if label == 'too long' else 'A longer adventure.z3'
        prepare([('SAFE~1.Z3', name, alpha)], mutate=mutate)
        output, _ = boot('q\n')
        assert 'Starting SAFE~1.Z3\n' in output, (label, output)

    # Independent formatter/mtools produces genuine VFAT records and preserves
    # long filenames. No fixture encoder participates here.
    if all(shutil.which(tool) for tool in ('mkfs.fat', 'mmd', 'mcopy')):
        for fat, size in ((16, 16), (32, 64)):
            with image.open('wb') as stream:
                stream.truncate(size*1024*1024)
            subprocess.run(['mkfs.fat', '-F', str(fat), str(image)], check=True, capture_output=True)
            subprocess.run(['mmd', '-i', str(image), '::/ZORK'], check=True)
            for name, data in [('Zulu adventure.z3', alpha), ('A Mars adventure.z5', vfive)]:
                source = work/name
                source.write_bytes(data)
                subprocess.run(['mcopy', '-i', str(image), str(source), '::/ZORK/'], check=True)
            output, _ = boot('1\nq\n')
            assert '1. A Mars adventure.z5\n2. Zulu adventure.z3\n' in output and 'vfive ready' in output
    else:
        print('SKIP independent VFAT formatter/mtools checks (tools unavailable)')

print('PASS VFAT names: FAT16/FAT32, fragmented directories, sector/cluster boundaries, displayed-name ordering/overflow, V3/V5, save identity, 13/26/255-unit names, Unicode substitution and malformed-chain fallback')
