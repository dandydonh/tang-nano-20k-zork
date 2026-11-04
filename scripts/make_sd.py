#!/usr/bin/env python3
"""Prepare V3 stories and a save pool, or a FAT16/FAT32 image; never writes a block device."""
import argparse
import hashlib
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SAVE_SIZE = 131072
SAVE_SLOTS = 20
POOL_SIZE = SAVE_SLOTS * 2 * SAVE_SIZE


def validate_story(story):
    if not 64 <= len(story) <= 1048576:
        raise ValueError('V3 file size must be 64 bytes to 1 MiB including padding')
    if story[0] != 3:
        raise ValueError('Only Z-machine V3 stories are supported')
    word = lambda offset: struct.unpack_from('>H', story, offset)[0]
    length = word(26)*2 or len(story)
    dynamic = word(14)
    if (not 64 <= length <= min(len(story), 131072) or not 64 <= dynamic <= length
            or not dynamic <= word(4) < length or not 64 <= word(6) < length
            or not 64 <= word(10) <= dynamic-62 or not 64 <= word(12) <= dynamic-480
            or not 64 <= word(8) <= length-4 or not 64 <= word(24) <= length-192):
        raise ValueError('Invalid V3 memory layout')


def project_files(story, name='ZORK1.DAT'):
    validate_story(story)
    return [(name, story), ('SAVES.BIN', bytes(POOL_SIZE))]


def dir_entry(name, cluster, size=0, directory=False):
    entry = bytearray(32)
    if name in ('.', '..'):
        short = name.ljust(11)
    else:
        stem, _, suffix = name.partition('.')
        short = stem.ljust(8) + suffix.ljust(3)
    entry[:11] = short.encode('ascii')
    entry[11] = 0x10 if directory else 0x20
    struct.pack_into('<H', entry, 20, cluster >> 16)
    struct.pack_into('<HI', entry, 26, cluster & 0xffff, size)
    for offset in (16, 18, 24):
        struct.pack_into('<H', entry, offset, 0x21)  # 1980-01-01
    return entry


def make_image(files, fat=32, size_mib=None, partitioned=True):
    """Small standard FAT image, also usable as a disposable test fixture."""
    size_mib = size_mib if size_mib is not None else (64 if fat == 32 else 8)
    if not 4 <= size_mib <= 256:
        raise ValueError('Image size must be 4..256 MiB (use --directory for larger cards)')
    total = size_mib * 2048
    base = 2048 if partitioned else 0
    reserved, root_entries = (32, 0) if fat == 32 else (1, 512)
    root_sectors = root_entries // 16
    width, fat_size = fat // 8, 1
    while True:
        clusters = total - reserved - 2 * fat_size - root_sectors
        needed = ((clusters + 2) * width + 511) // 512
        if needed <= fat_size:
            break
        fat_size = needed
    if (fat == 16 and not 4085 <= clusters < 65525
            or fat == 32 and not 65525 <= clusters < 0x0ffffff0):
        raise ValueError(f'{size_mib} MiB does not produce a valid FAT{fat} cluster count')
    image = bytearray((base + total) * 512)
    if partitioned:
        # CHS fields are saturated; consumers use the LBA start and length.
        image[446:462] = struct.pack('<B3sB3sII', 0, b'\xfe\xff\xff',
                                     0x0c if fat == 32 else 0x0e,
                                     b'\xfe\xff\xff', base, total)
        image[510:512] = b'\x55\xaa'
    boot = bytearray(512)
    boot[:3] = bytes((0xeb, 0x58 if fat == 32 else 0x3c, 0x90))
    boot[3:11] = b'ZORKFAT '
    struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, 1, reserved, 2,
                     root_entries, total if total < 65536 else 0, 0xf8,
                     fat_size if fat == 16 else 0, 63, 255, base,
                     total if total >= 65536 else 0)
    if fat == 32:
        struct.pack_into('<IHHIHH', boot, 36, fat_size, 0, 0, 2, 1, 6)
        extended = 64
    else:
        extended = 36
    struct.pack_into('<BBBI', boot, extended, 0x80, 0, 0x29, 0x5a4f524b)
    boot[extended+7:extended+18] = b'ZORKSD     '
    boot[extended+18:extended+26] = f'FAT{fat}   '.encode()
    boot[510:512] = b'\x55\xaa'
    image[base*512:(base+1)*512] = boot
    data_start = base + reserved + 2*fat_size + root_sectors
    table = bytearray(fat_size*512)
    eoc = 0x0fffffff if fat == 32 else 0xffff

    def set_fat(cluster, value):
        struct.pack_into('<I' if fat == 32 else '<H', table, cluster*width, value)

    def write_cluster(cluster, data):
        start = (data_start + cluster - 2)*512
        image[start:start+len(data)] = data

    set_fat(0, 0x0ffffff8 if fat == 32 else 0xfff8)
    set_fat(1, eoc)
    root_cluster = 2 if fat == 32 else 0
    zork_cluster = 3 if fat == 32 else 2
    if root_cluster:
        set_fat(root_cluster, eoc)
    directory_clusters = (len(files)+3+15)//16
    for n in range(directory_clusters):
        set_fat(zork_cluster+n, zork_cluster+n+1 if n+1<directory_clusters else eoc)
    directory = bytearray(directory_clusters*512)
    directory[:32] = dir_entry('.', zork_cluster, directory=True)
    directory[32:64] = dir_entry('..', 0, directory=True)
    next_cluster = zork_cluster + directory_clusters
    for index, (name, data) in enumerate(files):
        count = (len(data)+511)//512
        first = next_cluster
        if next_cluster+count > clusters+2:
            raise ValueError('Files do not fit in the image; increase --size-mib')
        for n in range(count):
            set_fat(next_cluster, next_cluster+1 if n+1<count else eoc)
            write_cluster(next_cluster, data[n*512:(n+1)*512])
            next_cluster += 1
        directory[(index+2)*32:(index+3)*32] = dir_entry(name, first, len(data))
    write_cluster(zork_cluster, directory)
    root = bytearray(512)
    root[:11] = b'ZORKSD     '
    root[11] = 8  # Volume label matches the extended BPB label.
    root[32:64] = dir_entry('ZORK', zork_cluster, directory=True)
    if root_cluster:
        write_cluster(root_cluster, root)
    else:
        root_start = (base + reserved + 2*fat_size)*512
        image[root_start:root_start+512] = root
    for copy in range(2):
        start = (base + reserved + copy*fat_size)*512
        image[start:start+len(table)] = table
    if fat == 32:
        image[(base+6)*512:(base+7)*512] = boot
        info = bytearray(512)
        struct.pack_into('<I', info, 0, 0x41615252)
        struct.pack_into('<IIII', info, 484, 0x61417272,
                         clusters-(next_cluster-2), next_cluster, 0)
        struct.pack_into('<I', info, 508, 0xaa550000)
        for sector in (1, 7):
            image[(base+sector)*512:(base+sector+1)*512] = info
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--story', type=Path, action='append', help='V3 story path; repeat for up to 20 stories (default zork1.dat)')
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument('--output', type=Path, help='New image file (default assets/v3-sdram-fat.img)')
    parser.add_argument('--expand-saves', type=Path, help='Copy an existing 2 MiB ZMV5 pool into a new 5 MiB pool; requires --output')
    destination.add_argument('--directory', type=Path, help='Existing FAT root or staging directory; creates ZORK/')
    parser.add_argument('--prepare-saves', action='store_true', help='Create only a missing SAVES.BIN in an existing ZORK directory')
    parser.add_argument('--fat', type=int, choices=(16, 32), default=32)
    parser.add_argument('--size-mib', type=int, help='Image volume size; default 64 for FAT32 or 8 for FAT16')
    parser.add_argument('--superfloppy', action='store_true', help='Image without an MBR partition table')
    args = parser.parse_args()
    try:
        import re
        if args.expand_saves is not None:
            if args.output is None or args.story or args.prepare_saves or args.size_mib is not None or args.superfloppy or args.fat != 32:
                parser.error('--expand-saves requires --output and no story, preparation or image format options')
            old = args.expand_saves.read_bytes()
            if len(old) != 8*2*SAVE_SIZE:
                parser.error('--expand-saves requires a 2097152-byte ZMV5 pool')
            for offset in range(0, len(old), SAVE_SIZE):
                header = old[offset:offset+512]
                if any(header) and header[:4] != b'ZMV5':
                    parser.error('Source contains an unrecognized snapshot header; left unchanged')
            with args.output.open('xb') as stream:
                stream.write(old)
                stream.write(bytes(POOL_SIZE-len(old)))
            print(f'{args.output}: {POOL_SIZE} bytes; original eight slots preserved, 12 empty slots added')
            return
        if args.prepare_saves:
            if args.directory is None or args.story:
                parser.error('--prepare-saves requires --directory and no --story')
            files = [('SAVES.BIN', bytes(POOL_SIZE))]
        else:
            paths = args.story or [ROOT/'zork1.dat']
            if len(paths) > SAVE_SLOTS:
                parser.error('At most 20 stories can be prepared')
            files = []
            for path in paths:
                name = path.name.upper()
                if not re.fullmatch(r'[A-Z0-9_~\-]{1,8}\.DAT', name):
                    parser.error('Use a short story filename such as ZORK2.DAT (up to 8 characters before .DAT)')
                if name in [item[0] for item in files]:
                    parser.error(f'Duplicate story name: {name}')
                data = path.read_bytes()
                validate_story(data)
                files.append((name, data))
            files.append(('SAVES.BIN', bytes(POOL_SIZE)))
        if args.directory is not None:
            if args.size_mib is not None or args.superfloppy or args.fat != 32:
                parser.error('Image format options cannot be used with --directory')
            if not args.directory.is_dir():
                parser.error('--directory must name an existing directory')
            target = args.directory/'ZORK'
            if args.prepare_saves:
                if not target.is_dir(): parser.error('Existing ZORK directory required')
            else:
                target.mkdir()  # Never replace an existing game directory or saves.
            for name, data in files:
                with (target/name).open('xb') as stream:
                    stream.write(data)
            print(f'{target}: {len(files)} files; {POOL_SIZE}-byte save pool, {SAVE_SLOTS} stories')
        else:
            output = args.output if args.output is not None else ROOT/'assets/v3-sdram-fat.img'
            # Exclusive creation also refuses devices and existing images.
            image = make_image(files, args.fat, args.size_mib, not args.superfloppy)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('xb') as stream:
                stream.write(image)
            print(f'{output}: {len(image)} bytes; FAT{args.fat}')
        for name, data in files:
            if name.endswith('.DAT'): print(f'{name} SHA256 {hashlib.sha256(data).hexdigest()}')
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
