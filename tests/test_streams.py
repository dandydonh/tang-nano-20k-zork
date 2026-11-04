#!/usr/bin/env python3
"""Execute original V3 bytecode to check screen/memory routing and saved streams."""
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from v3_fixture import make_story, zstring

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from make_sd import make_image, project_files


class Program:
    def __init__(self):
        self.code = bytearray()

    def emit(self, *data):
        self.code.extend(data)

    def stream(self, number, table=None):
        self.emit(0xf3, 0x3f if table is None else 0x0f)
        self.code.extend(struct.pack('>H', number & 65535))
        if table is not None:
            self.code.extend(struct.pack('>H', table))

    def char(self, c):
        self.emit(0xe5, 0x7f, c)

    def text(self, text):
        self.emit(0xb2)
        self.code.extend(zstring(text))

    def value(self, address, word=False):
        self.emit(0xcf if word else 0xd0, 0x1f, address >> 8, address & 255, 0, 22)
        self.emit(0xe6, 0xbf, 22)
        self.char(32)

    def story(self):
        data = bytearray(make_story(size=8192))
        data[0x600:0x602] = b'\xff\xff'  # Initial table count must be ignored.
        data[0x800:0x800+len(self.code)] = self.code
        struct.pack_into('>H', data, 28, sum(data[64:]) & 65535)
        return bytes(data)


def run(program, commands='', expected=0):
    with tempfile.TemporaryDirectory(prefix='zork-streams-') as directory:
        image = Path(directory)/'card.img'
        image.write_bytes(make_image(project_files(program.story(), save_slots=1), 16, 8, False))
        result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                                capture_output=True, env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
        assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
        return result.stdout


p = Program()
p.text('visible')  # Pending word must flush before the route changes.
p.stream(-1)
p.text('hidden')
p.stream(3, 0x600)
p.text('abc')
p.char(13)
p.emit(0xbb)  # new_line also stores ZSCII 13.
p.emit(0xe6, 0x3f, 0xff, 0xd6)  # print_num -42
p.stream(3, 0x640)
p.text('nested')
p.char(155)  # Memory preserves ZSCII, independently of the ASCII display.
p.char(0)  # Null does not count.
p.stream(-3)
p.char(ord('z'))
p.stream(-3)
p.stream(1)
p.char(32)
for address in (0x600, 0x640):
    p.value(address, word=True)
for address in (0x605, 0x606, 0x607, 0x60a, 0x648):
    p.value(address)
# Stream 3 still works in the currently unsupported upper display window.
p.emit(0xea, 0x7f, 1, 0xeb, 0x7f, 1)
p.stream(3, 0x660)
p.text('upper')
p.stream(-3)
p.emit(0xeb, 0x7f, 0)
p.value(0x660, word=True)
# No word wrapping, even across many screen widths.
p.stream(3, 0x100)
for _ in range(200):
    p.char(ord('w'))
p.stream(-3)
p.value(0x100, word=True)
p.emit(0xba)
out = run(p)
assert 'visible 9 7 13 13 45 122 155 5 200 ' in out, out
assert all(text not in out for text in ('hidden', 'abc', 'nested', 'upper', 'wwww')), out

# All sixteen nesting levels resume their own table/count; a seventeenth fails.
p = Program()
for i in range(16):
    p.stream(3, 0x600+4*i)
    p.char(65+i)
for i in reversed(range(16)):
    p.stream(-3)
for i in range(16):
    p.value(0x600+4*i, word=True)
p.emit(0xba)
assert ('1 '*16) in run(p)
p.code = p.code[:0]
for i in range(17):
    p.stream(3, 0x600)
assert 'memory stream nesting exceeds 16' in run(p, expected=2)

for table, message in ((0x7ff, 'outside dynamic memory'), (None, 'requires table')):
    p = Program()
    p.stream(3, table)
    assert message in run(p, expected=2)
p = Program()
p.stream(3, 0x7fe)
p.char(65)
assert 'outside dynamic memory' in run(p, expected=2)

p = Program()
p.emit(0xe2, 0x57, 17, 0, 0xab)  # Direct Flags 2 write must not enable transcript.
p.value(17)
for stream in (2, -2, 4, -4):
    p.stream(stream)
p.value(17)
p.emit(0xba)
out = run(p)
assert out.count('170 ') == 2 and out.count('output is unavailable.') == 2, out

# SAVE inside nested stream 3 with screen disabled; RESTORE must resume both.
p = Program()
p.stream(-1)
p.stream(3, 0x600)
p.char(65)
p.stream(3, 0x640)
p.char(66)
p.emit(0xb5, 0xc2)  # save, branch to next instruction on success
p.emit(0xe4, 0x0f, 5, 0, 5, 0x80)  # sread
p.emit(0xd0, 0x1f, 5, 0, 1, 20)
p.emit(0x41, 20, ord('r'), 0x45)  # if 'r', skip jump and restore
p.emit(0x8c, 0, 4)  # skip restore
p.emit(0xb6, 0xc2)
p.char(67)
p.stream(-3)
p.char(68)
p.stream(-3)
p.text('hidden')
p.stream(1)
for address in (0x600, 0x640):
    p.value(address, word=True)
for address in (0x602, 0x603, 0x642, 0x643):
    p.value(address)
p.emit(0xba)
out = run(p, 'r\nx\n')
assert '2 2 65 68 66 67 ' in out and 'hidden' not in out, out

# Legacy snapshots omit the trailer. Loading one, or restarting, must clear
# the current capture stack and restore the initial screen selection.
for opcode in (0xb6, 0xb7):
    p = Program()
    if opcode == 0xb6:
        p.emit(0xb5, 0xc2)
    p.emit(0xe4, 0x0f, 5, 0, 5, 0x80)
    p.emit(0xd0, 0x1f, 5, 0, 1, 20)
    p.emit(0x41, 20, ord('r'), 0x45)
    p.emit(0x8c, 0, 0)
    jump = len(p.code)-2
    p.stream(-1)
    p.stream(3, 0x600)
    p.char(65)
    p.emit(opcode)
    if opcode == 0xb6:
        p.emit(0xc2)
    struct.pack_into('>H', p.code, jump, len(p.code)-jump)
    p.text('screen restored')
    p.emit(0xba)
    out = run(p, 'r\nx\n')
    assert 'screen restored' in out, out
print('PASS V3 screen selection, raw/nested memory streams, bounds, overflow and active-stream save/restore')
