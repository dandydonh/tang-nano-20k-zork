"""Test-side FAT inspection/mutation; no firmware or image-builder internals."""
import struct


def get16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def get32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


class FatImage:
    def __init__(self, data):
        self.data = bytearray(data)
        self.base = 0 if get16(data, 11) == 512 else get32(data, 454)
        b = self.base * 512
        self.spc = data[b+13]
        self.reserved = get16(data, b+14)
        self.fats = data[b+16]
        self.root_sectors = (get16(data, b+17)*32+511)//512
        self.fat_size = get16(data, b+22) or get32(data, b+36)
        self.total = get16(data, b+19) or get32(data, b+32)
        self.root_lba = self.base+self.reserved+self.fats*self.fat_size
        self.data_lba = self.root_lba+self.root_sectors
        self.clusters = (self.total-(self.data_lba-self.base))//self.spc
        self.width = 4 if self.clusters >= 65525 else 2
        self.root_cluster = get32(data, b+44) if self.width == 4 else None
        self.eoc = 0x0fffffff if self.width == 4 else 0xffff

    def fat_offset(self, cluster, copy=0):
        return (self.base+self.reserved+copy*self.fat_size)*512+cluster*self.width

    def next(self, cluster):
        return (get32 if self.width == 4 else get16)(self.data, self.fat_offset(cluster)) & self.eoc

    def set_next(self, cluster, value):
        for copy in range(self.fats):
            struct.pack_into('<I' if self.width == 4 else '<H', self.data,
                             self.fat_offset(cluster, copy), value)

    def chain(self, cluster):
        result = []
        while cluster < self.eoc-7:
            assert cluster >= 2 and cluster not in result
            result.append(cluster)
            cluster = self.next(cluster)
        return result

    def cluster_lba(self, cluster):
        return self.data_lba+(cluster-2)*self.spc

    def cluster_offset(self, cluster):
        return self.cluster_lba(cluster)*512

    def entry(self, name, directory=None):
        if directory is None and self.root_cluster is None:
            offsets = range(self.root_lba*512, (self.root_lba+self.root_sectors)*512, 32)
        else:
            directory = self.root_cluster if directory is None else directory
            offsets = [self.cluster_offset(c)+off for c in self.chain(directory)
                       for off in range(0, self.spc*512, 32)]
        stem, _, suffix = name.partition('.')
        target = (stem.ljust(8)+suffix.ljust(3)).encode()
        for offset in offsets:
            if self.data[offset:offset+11] == target:
                return offset
        raise AssertionError(f'Missing {name}')

    def entry_cluster(self, entry):
        return get16(self.data, entry+26) | (get16(self.data, entry+20)<<16 if self.width == 4 else 0)

    def set_entry_cluster(self, entry, cluster):
        struct.pack_into('<H', self.data, entry+26, cluster & 0xffff)
        struct.pack_into('<H', self.data, entry+20, cluster >> 16)

    def file_entry(self, name):
        directory = self.entry_cluster(self.entry('ZORK'))
        return self.entry(name, directory)

    def sectors(self, name):
        entry = self.file_entry(name)
        size = get32(self.data, entry+28)
        result = [self.cluster_lba(c)+s for c in self.chain(self.entry_cluster(entry))
                  for s in range(self.spc)]
        return result[:(size+511)//512]

    def file_bytes(self, name):
        entry = self.file_entry(name)
        return b''.join(self.data[s*512:(s+1)*512] for s in self.sectors(name))[:get32(self.data, entry+28)]

    def fragment(self, name, first):
        entry = self.file_entry(name)
        old = self.chain(self.entry_cluster(entry))
        new = [first+3*i for i in range(len(old))]
        for cluster in new:
            assert self.next(cluster) == 0
        for src, dst in zip(old, new):
            size = self.spc*512
            self.data[self.cluster_offset(dst):self.cluster_offset(dst)+size] = \
                self.data[self.cluster_offset(src):self.cluster_offset(src)+size]
        for i, cluster in enumerate(new):
            self.set_next(cluster, new[i+1] if i+1<len(new) else self.eoc)
        for cluster in old:
            self.set_next(cluster, 0)
        self.set_entry_cluster(entry, new[0])
        if self.width == 4:
            # Allocation count unchanged, but the old next-free hint is stale.
            for sector in (1, 7):
                struct.pack_into('<I', self.data, (self.base+sector)*512+492, 0xffffffff)

    def assert_only_saves_changed(self, before):
        allowed = set(self.sectors('SAVEA.BIN')+self.sectors('SAVEB.BIN'))
        assert len(before) == len(self.data)
        for sector in range(len(before)//512):
            if sector not in allowed:
                start = sector*512
                assert before[start:start+512] == self.data[start:start+512], f'Unexpected write to LBA {sector}'
