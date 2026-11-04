#!/usr/bin/env python3
"""Prepare fresh Zork files or a FAT16/FAT32 image; never writes a block device."""
import argparse
import hashlib
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SAVE_SIZE = 32768


def project_files(story):
    if (len(story) != 92160 or story[:4] != bytes.fromhex('03000058')
            or story[18:24] != b'840726'):
        raise ValueError('Requires Zork I V3 release 88, serial 840726, 92160 bytes')
    return [('ZORK1.DAT', story), ('SAVEA.BIN', bytes(SAVE_SIZE)),
            ('SAVEB.BIN', bytes(SAVE_SIZE))]


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
    set_fat(zork_cluster, eoc)
    directory = bytearray(512)
    directory[:32] = dir_entry('.', zork_cluster, directory=True)
    directory[32:64] = dir_entry('..', 0, directory=True)
    next_cluster = zork_cluster + 1
    for index, (name, data) in enumerate(files):
        count = (len(data)+511)//512
        first = next_cluster
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
    parser.add_argument('--story', type=Path, default=ROOT/'zork1.dat')
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument('--output', type=Path, help='New image file (default assets/zork-fat.img)')
    destination.add_argument('--directory', type=Path, help='Existing FAT card root or staging directory; creates ZORK/')
    parser.add_argument('--fat', type=int, choices=(16, 32), default=32)
    parser.add_argument('--size-mib', type=int, help='Image volume size; default 64 for FAT32 or 8 for FAT16')
    parser.add_argument('--superfloppy', action='store_true', help='Image without an MBR partition table')
    args = parser.parse_args()
    try:
        files = project_files(args.story.read_bytes())
        if args.directory is not None:
            if args.size_mib is not None or args.superfloppy or args.fat != 32:
                parser.error('Image format options cannot be used with --directory')
            if not args.directory.is_dir():
                parser.error('--directory must name an existing directory')
            target = args.directory/'ZORK'
            target.mkdir()  # Never replace an existing game directory or saves.
            for name, data in files:
                with (target/name).open('xb') as stream:
                    stream.write(data)
            print(f'{target}: story and two blank {SAVE_SIZE}-byte save files')
        else:
            output = args.output if args.output is not None else ROOT/'assets/zork-fat.img'
            # Exclusive creation also refuses devices and existing images.
            image = make_image(files, args.fat, args.size_mib, not args.superfloppy)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('xb') as stream:
                stream.write(image)
            print(f'{output}: {len(image)} bytes; FAT{args.fat}')
        print(f'Story SHA256 {hashlib.sha256(files[0][1]).hexdigest()}')
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
