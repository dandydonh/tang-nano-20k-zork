#!/usr/bin/env python3
"""Create a fresh indexed SAVES.BIN for up to 1000 stories; never overwrites."""
import argparse
from pathlib import Path
import struct

BANK_BYTES = 131072
MAX_GAMES = 1000
MAX_POSITIONS = 20
MAGIC = b'ZSP1000\0'


def checksum(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte)*16777619) & 0xffffffff
    return value


def pool_header(games=1000, positions=5):
    if not 1 <= games <= MAX_GAMES or not 1 <= positions <= MAX_POSITIONS:
        raise ValueError('Games must be 1..1000 and positions must be 1..20')
    index_sectors = (games+15)//16
    data_sector = 2+2*index_sectors
    size = data_sector*512+games*positions*2*BANK_BYTES
    if size > 0xffffffff:
        raise ValueError('Pool exceeds the single-file size limit; 1000 games support at most 16 positions')
    header = bytearray(512)
    header[:8] = MAGIC
    struct.pack_into('<8I', header, 8, 1, games, positions, BANK_BYTES,
                     index_sectors, data_sector, size, 32)
    struct.pack_into('<I', header, 508, checksum(header[:508]))
    return bytes(header), size


def create_pool(path, games=1000, positions=5):
    header, size = pool_header(games, positions)
    # Sparse on supporting staging filesystems; holes read as zero. Copying onto
    # FAT allocates the complete logical file. No whole-pool RAM allocation.
    with Path(path).open('xb') as stream:
        stream.write(header)
        stream.write(header)
        stream.truncate(size)
    return size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New staging file; copy as /ZORK/SAVES.BIN')
    parser.add_argument('--games', type=int, default=1000, help='Story identities (default 1000)')
    parser.add_argument('--positions', type=int, default=5, help='Save positions per story (default 5)')
    args = parser.parse_args()
    try:
        size = create_pool(args.output, args.games, args.positions)
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(f'{args.output}: {size} bytes; {args.games} games, {args.positions} positions per game; indexed pool v1')


if __name__ == '__main__':
    main()
