"""Sparse independent FAT32 fixtures for GiB-sized indexed save pools."""
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import dir_entry
from save_pool_fixture import pool_header


def sparse_card(path, story, games=1000, positions=5, fragmented=False, spc=64, directory_clusters=1):
    header, size = pool_header(games, positions)
    clusters, reserved = 100000, 32
    needed = (size+spc*512-1)//(spc*512)
    story_clusters = max(1, (len(story)+spc*512-1)//(spc*512))
    story_cluster = 3+directory_clusters
    clusters = max(clusters, needed+story_clusters+directory_clusters+1000)
    fat_sectors = ((clusters+2)*4+511)//512
    data = reserved+2*fat_sectors
    total = data+clusters*spc
    pool_chain = list(range(story_cluster+story_clusters, story_cluster+story_clusters+needed))
    if fragmented == 'excessive':
        pool_chain = pool_chain[::2]+pool_chain[1::2]
    elif fragmented:
        chunks = [pool_chain[i:i+128] for i in range(0, len(pool_chain), 128)]
        pool_chain = [cluster for chunk in reversed(chunks) for cluster in chunk]
    def lba(cluster):
        return data+(cluster-2)*spc
    boot = bytearray(512)
    boot[:3] = b'\xeb\x58\x90'
    boot[3:11] = b'ZORKTEST'
    struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, spc, reserved, 2, 0, 0, 0xf8, 0, 63, 255, 0, total)
    struct.pack_into('<IHHIHH', boot, 36, fat_sectors, 0, 0, 2, 1, 6)
    struct.pack_into('<BBBI', boot, 64, 0x80, 0, 0x29, 1234)
    boot[71:82], boot[82:90], boot[510:512] = b'ZORKTEST   ', b'FAT32   ', b'\x55\xaa'
    info = bytearray(512)
    struct.pack_into('<I', info, 0, 0x41615252)
    struct.pack_into('<IIII', info, 484, 0x61417272, clusters-1-directory_clusters-story_clusters-needed,
                     story_cluster+story_clusters+needed, 0)
    info[510:512] = b'\x55\xaa'
    fat = bytearray(fat_sectors*512)
    for cluster, value in ((0, 0x0ffffff8), (1, 0x0fffffff), (2, 0x0fffffff)):
        struct.pack_into('<I', fat, cluster*4, value)
    for cluster in range(3, 3+directory_clusters):
        struct.pack_into('<I', fat, cluster*4, cluster+1 if cluster+1 < 3+directory_clusters else 0x0fffffff)
    for cluster in range(story_cluster, story_cluster+story_clusters):
        struct.pack_into('<I', fat, cluster*4, cluster+1 if cluster+1 < story_cluster+story_clusters else 0x0fffffff)
    for index, cluster in enumerate(pool_chain):
        struct.pack_into('<I', fat, cluster*4,
                         pool_chain[index+1] if index+1 < len(pool_chain) else 0x0fffffff)
    label = bytearray(32)
    label[:11], label[11] = b'ZORKTEST   ', 8
    root = label+dir_entry('ZORK', 3, directory=True)+bytes(448)
    directory = (dir_entry('.', 3, directory=True)+dir_entry('..', 0, directory=True)+
                 dir_entry('STORY.Z3' if story[0] == 3 else 'STORY.Z5', story_cluster, len(story))+
                 dir_entry('SAVES.BIN', pool_chain[0], size)+bytes(512-128))
    with Path(path).open('wb') as stream:
        stream.truncate(total*512)
        for sector, content in ((0, boot), (6, boot), (1, info), (7, info),
                                (reserved, fat), (reserved+fat_sectors, fat),
                                (lba(2), root), (lba(3), directory), (lba(story_cluster), story)):
            stream.seek(sector*512)
            stream.write(content)
    result = dict(story_lba=lba(story_cluster), story_cluster=story_cluster, chain=pool_chain, data_lba=data, spc=spc,
                  size=size, header=header, root_lba=lba(2), directory_lba=lba(3),
                  fat_lba=reserved, fat_sectors=fat_sectors)
    pool_write(path, result, 0, header+header)
    return result


def pool_lba(layout, sector):
    return layout['data_lba']+(layout['chain'][sector//layout['spc']]-2)*layout['spc']+sector%layout['spc']


def pool_write(path, layout, sector, data):
    assert len(data) % 512 == 0
    with Path(path).open('r+b') as stream:
        for index in range(len(data)//512):
            stream.seek(pool_lba(layout, sector+index)*512)
            stream.write(data[index*512:(index+1)*512])


def pool_read(path, layout, sector, count=1):
    with Path(path).open('rb') as stream:
        result = []
        for index in range(count):
            stream.seek(pool_lba(layout, sector+index)*512)
            result.append(stream.read(512))
        return b''.join(result)
