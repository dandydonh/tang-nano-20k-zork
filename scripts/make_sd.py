#!/usr/bin/env python3
"""Create a dedicated Zork SD image; never writes a physical device."""
import hashlib
import pathlib
import struct
import argparse
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--story', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1]/'zork1.dat')
p.add_argument('--output', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1]/'assets/zork-sd.img')
a = p.parse_args()
story = a.story.read_bytes()
if len(story) != 92160 or story[:4] != bytes.fromhex('03000058') or story[18:24] != b'840726':
    p.error('This core targets the supplied Zork I V3 release 88, serial 840726, 92160-byte file')
image = bytearray(1024*1024)
struct.pack_into('<4sIII', image, 0, b'ZKSD', 1, len(story), 256)
image[16:48] = hashlib.sha256(story).digest()
image[512:512+len(story)] = story
a.output.parent.mkdir(parents=True, exist_ok=True)
if a.output.exists():
    p.error(f'{a.output} already exists; choose a new path to preserve saved games')
a.output.write_bytes(image)
print(f'{a.output}: {len(image)} bytes; story SHA256 {hashlib.sha256(story).hexdigest()}')
