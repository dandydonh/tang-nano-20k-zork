#!/usr/bin/env python3
"""Unicode VFAT sidecars, using independent mtools/fsck on shared-card images."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from fat_helpers import FatImage
from sd_image_fixture import make_image
from v3_fixture import make_story
from v5_fixture import make_story as make_v5_story

ROOT = Path(__file__).resolve().parents[1]
OFFSETS = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)


def command(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True)
    assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result.stdout


def directory_entries(image):
    fat = FatImage(image.read_bytes())
    units = {}
    result = []
    for cluster in fat.chain(fat.entry_cluster(fat.entry('ZORK'))):
        for offset in range(0, fat.spc * 512, 32):
            at = fat.cluster_offset(cluster) + offset
            entry = fat.data[at:at + 32]
            if not entry[0]:
                return result
            if entry[0] == 0xe5:
                units = {}
            elif entry[11] == 15:
                for i, off in enumerate(OFFSETS):
                    units[((entry[0] & 31) - 1) * 13 + i] = struct.unpack_from('<H', entry, off)[0]
            else:
                if units:
                    name_units = [units[i] for i in sorted(units)]
                    name_units = name_units[:name_units.index(0)] if 0 in name_units else name_units
                    name = struct.pack('<' + 'H' * len(name_units), *name_units).decode('utf-16le')
                else:
                    name = entry[:8].decode('cp437').rstrip() + '.' + entry[8:11].decode('cp437').rstrip()
                result.append((name, at))
                units = {}
    return result


def rewrite_lfn(image, target, replacement):
    fat = FatImage(image.read_bytes())
    offsets = [fat.cluster_offset(c) + off
               for c in fat.chain(fat.entry_cluster(fat.entry('ZORK')))
               for off in range(0, fat.spc * 512, 32)]
    alias = next(at for name, at in directory_entries(image) if name == target)
    index = offsets.index(alias) - 1
    assert fat.data[offsets[index] + 11] == 15
    encoded = replacement.encode('utf-16le')
    assert len(encoded) == len(target.encode('utf-16le'))
    units = list(struct.unpack('<' + 'H' * (len(encoded) // 2), encoded))
    while index >= 0 and fat.data[offsets[index] + 11] == 15:
        at = offsets[index]
        start = ((fat.data[at] & 31) - 1) * 13
        for j, off in enumerate(OFFSETS):
            n = start + j
            value = units[n] if n < len(units) else 0 if n == len(units) else 0xffff
            struct.pack_into('<H', fat.data, at + off, value)
        index -= 1
    image.write_bytes(fat.data)


def read_file(image, target):
    fat = FatImage(image.read_bytes())
    at = next(at for name, at in directory_entries(image) if name == target)
    # Use the short alias so older mtools builds do not truncate surrogate pairs.
    alias = fat.data[at:at+8].decode('cp437').rstrip() + '.' + fat.data[at+8:at+11].decode('cp437').rstrip()
    return command('mtype', '-i', image, '::/ZORK/' + alias)


with tempfile.TemporaryDirectory(prefix='zork-unicode-') as directory:
    work = Path(directory)
    image = work / 'card.img'
    source = work / 'story.z3'
    source.write_bytes(make_story(name='alpha', release=1150))
    unrelated = work / 'unrelated.bin'
    unrelated.write_bytes(bytes(range(256)) * 17)

    def play(commands):
        result = subprocess.run([ROOT / 'impl/zork-host'], input=commands, text=True,
                                capture_output=True, timeout=45,
                                env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert 'CORE ERROR' not in result.stdout and 'Saves disabled' not in result.stdout, result.stdout
        return result.stdout

    for fat in (16, 32):
        for name in ('Café', 'Ελληνικά', 'Приключение', '冒険', 'Cafe\u0301', '𐐨 adventure', 'Rocket 🚀',
                     '界' * 251, 'a' * 250 + '🚀'):
            # Last stem is 252 UTF-16 units; with .z3 it fits 255, but .sav does not.
            too_long = name == 'a' * 250 + '🚀'
            image.write_bytes(make_image([('SAVES.BIN', b'legacy pool must stay unchanged')], fat,
                                         8 if fat == 16 else 64, False))
            command('mmd', '-i', image, '::/OTHERCORE')
            command('mcopy', '-i', image, unrelated, '::/OTHERCORE/DATA.BIN')
            needs_fixture = any(ord(c) > 65535 for c in name) or len((name + '.z3').encode()) > 255
            copied = 'X' * (len(name.encode('utf-16le')) // 2) if needs_fixture else name
            command('mcopy', '-i', image, source, '::/ZORK/' + copied + '.z3')
            if needs_fixture:
                rewrite_lfn(image, copied + '.z3', name + '.z3')
            before = image.read_bytes()
            # Playing, canceling SAVE, and absent RESTORE allocate nothing.
            output = play('s\n0\nr\n0\nq\n') if not too_long else ''
            if not too_long:
                assert image.read_bytes() == before
                assert 'Starting ' + name + '.z3' in output.replace('\n', ''), output
                output = play('n\ns\n5\nq\n')
                assert 'saved\n' in output, output
                entries = directory_entries(image)
                assert sum(n == name + '.sav' for n, _ in entries) == 1, entries
                assert 'alpha moved' in play('r\n5\nl\nq\n')
                snapshot = read_file(image, name + '.sav')
                assert len(snapshot) == 1312768
                # A case-only renamed sidecar must be reused, never shadowed.
                if name.upper() != name and len(name.upper().encode('utf-16le')) == len(name.encode('utf-16le')):
                    rewrite_lfn(image, name + '.sav', (name + '.sav').upper())
                    assert 'alpha moved' in play('r\n5\nl\nq\n')
                    assert 'saved\n' in play('s\n1\nq\n')
                    assert sum(n.lower().endswith('.sav') and n != 'SAVES.BIN'
                               for n, _ in directory_entries(image)) == 1
            else:
                result = subprocess.run([ROOT / 'impl/zork-host'], input='s\nq\n', text=True,
                                        capture_output=True, check=True,
                                        env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
                assert 'Saves disabled' in result.stdout and image.read_bytes() == before
            assert command('mtype', '-i', image, '::/OTHERCORE/DATA.BIN') == unrelated.read_bytes()
            assert command('mtype', '-i', image, '::/ZORK/SAVES.BIN') == b'legacy pool must stay unchanged'
            assert read_file(image, name + '.z3') == source.read_bytes()
            command('fsck.fat', '-n', image)
            print(f'PASS FAT{fat}: {name[:28]!r}, Unicode sidecar/recovery or length refusal; shared files intact')

        image.write_bytes(make_image([], fat, 8 if fat == 16 else 64, False))
        command('mcopy', '-i', image, source, '::/ZORK/Café.z3')
        assert 'saved\n' in play('s\n1\nq\n')
        unrelated.write_bytes(read_file(image, 'Café.sav'))
        command('mcopy', '-i', image, unrelated, '::/ZORK/Test.sav')
        rewrite_lfn(image, 'Test.sav', 'CAFÉ.SAV')
        before = image.read_bytes()
        result = subprocess.run([ROOT / 'impl/zork-host'], input='s\nq\n', text=True,
                                capture_output=True, check=True,
                                env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
        assert 'Saves disabled' in result.stdout and image.read_bytes() == before
        unrelated.write_bytes(bytes(range(256)) * 17)
        print(f'PASS FAT{fat}: ambiguous Unicode case variants refused without writes')

        legacy = FatImage(make_image([('ALPHA.Z3', source.read_bytes())], fat,
                                    8 if fat == 16 else 64, False))
        at = legacy.file_entry('ALPHA.Z3')
        legacy.data[at:at+11] = b'CAF\x90    Z3 '
        image.write_bytes(legacy.data)
        output = play('n\ns\n5\nq\n')
        assert 'Starting CAFÉ.Z3' in output and 'saved\n' in output, output
        assert 'alpha moved' in play('r\n5\nl\nq\n')
        assert any(n == 'CAFÉ.sav' for n, _ in directory_entries(image))
        command('fsck.fat', '-n', image)
        print(f'PASS FAT{fat}: CP437 legacy alias converted to Unicode display and sidecar')

        image.write_bytes(make_image([], fat, 8 if fat == 16 else 64, False))
        source.write_bytes(make_v5_story())
        command('mcopy', '-i', image, source, '::/ZORK/Café 冒険.z5')
        output = play('s\n5\nq\n')
        assert 'saved\n' in output and 'Save slots for Café 冒険.z5' in output.replace('\n', ''), output
        output = play('r\n5\nl\nq\n')
        assert 'restored' in output and 'Restore slots for Café 冒険.z5' in output.replace('\n', ''), output
        command('fsck.fat', '-n', image)
        print(f'PASS FAT{fat}: V5 Unicode filename labels, save and reset/restore')
        source.write_bytes(make_story(name='alpha', release=1150))
