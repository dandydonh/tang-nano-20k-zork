"""Original tiny V3 program for loader/interpreter regression; no game data."""
import struct


def zstring(text):
    chars = []
    for c in text:
        if c == ' ':
            chars.append(0)
        elif 'a' <= c <= 'z':
            chars.append(ord(c)-ord('a')+6)
        else:
            raise ValueError(c)
    while len(chars) % 3:
        chars.append(5)
    result = bytearray()
    for i in range(0, len(chars), 3):
        word = (chars[i]<<10)|(chars[i+1]<<5)|chars[i+2]
        if i+3 == len(chars):
            word |= 0x8000
        result += struct.pack('>H', word)
    return result


def make_story(size=4096, name='alpha', release=1, dynamic=2048, clock=False, intro=None, input_size=80):
    assert size >= 4096
    story = bytearray(size)
    story[0] = 3
    story[1] = 2 if clock else 0
    length = min(size & ~1, 131070)
    for offset, value in ((2, release), (4, dynamic), (6, dynamic), (8, 0x300),
                          (10, 0x80), (12, 0x100), (14, dynamic),
                          (24, 0x380), (26, length//2)):
        struct.pack_into('>H', story, offset, value)
    story[18:24] = f'{release:06d}'.encode()
    story[0x300:0x304] = bytes((0, 4, 0, 0))  # Empty dictionary.
    story[0x500] = input_size
    story[0x580] = 16
    struct.pack_into('>H', story, 0x100, 1)  # Status location = object 1.
    struct.pack_into('>H', story, 0x80+62+7, 0x400)
    room = zstring('room')
    story[0x400] = len(room)//2
    story[0x401:0x401+len(room)] = room
    if clock:
        struct.pack_into('>HH', story, 0x102, 13, 7)
    code = bytearray()
    labels, fixups = {}, []

    def emit(*data):
        code.extend(data)

    def text(message):
        emit(0xb2)
        code.extend(zstring(message))
        emit(0xbb)

    def label(name):
        labels[name] = dynamic+len(code)

    def branch(target):
        fixups.append((len(code), target, True))
        emit(0x80, 0)

    def jump(target):
        emit(0x8c)
        fixups.append((len(code), target, False))
        emit(0, 0)

    text(name+' ready')
    if intro:text(intro)
    tail = (length-64) & ~1
    emit(0x8d, (tail//2)>>8, (tail//2)&255, 0xbb)  # print_paddr beyond 64 KiB in large fixtures.
    label('loop')
    # Check a byte at the top of dynamic memory against the saved VM state.
    # The 65535-byte fixture exercises the final legal writable byte (0xfffe).
    probe=dynamic-1
    emit(0xd0, 0x1f, probe>>8, probe&255, 0, 21)
    emit(0x61, 19, 21)
    branch('checked')
    text('memoryfailed')
    emit(0xba)
    label('checked')
    emit(0xe5, 0x7f, 62)  # Visible input prompt, also used by processor tests.
    emit(0xe4, 0x0f, 5, 0, 5, 0x80)  # sread text=0x500, parse=0x580.
    emit(0xd0, 0x1f, 5, 0, 1, 20)   # loadb text,1 -> global 4.
    for letter, target in [('s', 'save'), ('r', 'restore'), ('n', 'move'), ('q', 'quit')]:
        emit(0x41, 20, ord(letter))
        branch(target)
    emit(0x41, 19, 1)
    branch('away')
    text(name+' home')
    jump('loop')
    label('away')
    text(name+' moved')
    jump('loop')
    label('move')
    emit(0xe2, 0x17, probe>>8, probe&255, 0, 1)  # storeb probe,0,1.
    emit(0x0d, 19, 1)  # store global 3,1.
    text(name+' moved')
    jump('loop')
    label('save')
    emit(0xb5)
    branch('saved')
    text('savefailed')
    jump('loop')
    label('saved')
    text('saved')
    jump('loop')
    label('restore')
    emit(0xb6)
    branch('saved')
    text('restorefailed')
    jump('loop')
    label('quit')
    emit(0xba)
    for offset, target, is_branch in fixups:
        relative = labels[target]-(dynamic+offset+2)+2
        if is_branch:
            assert -8192 <= relative < 8192
            value = 0x8000|(relative & 0x3fff)
        else:
            value = relative & 0xffff
        struct.pack_into('>H', code, offset, value)
    assert dynamic+len(code) < tail
    story[dynamic:dynamic+len(code)] = code
    encoded = zstring('tail data')
    story[tail:tail+len(encoded)] = encoded
    struct.pack_into('>H', story, 28, sum(story[64:length]) & 0xffff)
    return bytes(story)
