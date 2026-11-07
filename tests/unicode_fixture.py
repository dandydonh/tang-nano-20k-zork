"""Small original bytecode programs for Unicode/ZSCII regression tests."""
import struct
from v3_fixture import make_story as v3_story
from v5_fixture import make_story as v5_story

DEFAULT = 'äöüÄÖÜß»«ëïÿËÏáéíóúýÁÉÍÓÚÝàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛåÅøØãñõÃÑÕæÆçÇþðÞÐ£œŒ¡¿'
CUSTOM = [0x100, 0x101, 0x3a9, 0x3c9, 0x754c, 0x301, 0x20ac]


def packed(codes, limit=None):
    z = []
    for c in codes:
        if c == 32:
            z.append(0)
        elif 97 <= c <= 122:
            z.append(c - 97 + 6)
        elif 65 <= c <= 90:
            z += [4, c - 65 + 6]
        else:
            z += [5, 6, c >> 5, c & 31]
    if limit:
        z = z[:limit]
    while len(z) % 3 or (limit and len(z) < limit):
        z.append(5)
    data = bytearray()
    for i in range(0, len(z), 3):
        value = (z[i] << 10) | (z[i + 1] << 5) | z[i + 2]
        if i + 3 == len(z):
            value |= 0x8000
        data += struct.pack('>H', value)
    return data


class Program:
    def __init__(self, version=5, table=None):
        self.version, self.table = version, table
        self.data = bytearray(v5_story() if version == 5 else v3_story(size=8192, dynamic=4096))
        self.start = struct.unpack_from('>H', self.data, 6)[0]
        self.code = bytearray()
        self.labels, self.fixups = {}, []
        self.data[0x700:0x702] = bytes((120, 0))
        self.data[0xa80] = 8
        if table is not None:
            struct.pack_into('>H', self.data, 54, 0x1d00)
            struct.pack_into('>H', self.data, 0x1d00, 3)
            struct.pack_into('>H', self.data, 0x1d06, 0x1d10)
            self.data[0x1d10] = len(table)
            for i, c in enumerate(table):
                struct.pack_into('>H', self.data, 0x1d11 + 2 * i, c)

    def op(self, group, number, *args, result=None):
        if group == 'ext':
            self.code += bytes((0xbe, number))
        else:
            self.code.append((0xe0 if group == 'var' else 0xc0) | number)
        types, operands = 255, bytearray()
        for i, value in enumerate(args):
            if isinstance(value, tuple):
                kind, value = 2, value[1]
            else:
                kind = 1 if 0 <= value < 256 else 0
            types = (types & ~(3 << (6 - 2 * i))) | (kind << (6 - 2 * i))
            operands += struct.pack('>H', value & 65535) if kind == 0 else bytes((value,))
        self.code.append(types)
        self.code += operands
        if result is not None:
            self.code.append(result)
        return self

    def char(self, c):
        return self.op('var', 5, c)

    def text(self, text):
        for c in text:
            self.char(ord(c))
        return self

    def nl(self):
        self.code.append(0xbb)
        return self

    def number(self, value):
        return self.op('var', 6, value)

    def values(self, address, count, word=False):
        self.nl().text('values ')
        for i in range(count):
            self.op('two', 15 if word else 16, address, i, result=22)
            self.number(('v', 22)).char(32)
        return self.nl()

    def read(self, parse=0, preload=False):
        if self.version == 5 and not preload:
            self.op('var', 2, 0x700, 1, 0)
        return self.op('var', 4, 0x700, parse, result=16 if self.version == 5 else None)

    def branch(self, label):
        self.fixups.append((len(self.code), label, True))
        self.code += b'\0\0'
        return self

    def jump(self, label):
        self.code.append(0x8c)
        self.fixups.append((len(self.code), label, False))
        self.code += b'\0\0'
        return self

    def label(self, label):
        self.labels[label] = len(self.code)
        return self

    def story(self):
        code = self.code + b'\xba'
        for offset, label, branch in self.fixups:
            relative = self.labels[label] - offset
            struct.pack_into('>H', code, offset, (0x8000 | (relative & 0x3fff)) if branch else relative & 65535)
        assert self.start + len(code) < len(self.data)
        self.data[self.start:self.start + len(code)] = code
        scale = 4 if self.version == 5 else 2
        length = struct.unpack_from('>H', self.data, 26)[0] * scale
        struct.pack_into('>H', self.data, 28, sum(self.data[64:length]) & 65535)
        return bytes(self.data)
