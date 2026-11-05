"""Original V5 exercise program; no third-party story data."""
import struct
from v3_fixture import zstring


def make_story(size=262144, dynamic=8192):
    story = bytearray(size)
    story[0] = 5
    for offset, value in ((2, 501), (4, dynamic), (6, dynamic), (8, 0x300),
                          (10, 0x400), (12, 0x100), (14, dynamic),
                          (24, 0x700), (26, min(size//4, 65535))):
        struct.pack_into('>H', story, offset, value)
    story[18:24] = b'261104'
    story[0x300:0x304] = bytes((0, 6, 0, 1))
    key = zstring('lookxxxxx')
    story[0x304:0x30a] = key
    story[0x1800] = 8
    story[0x1900] = 120
    # Large object numbers, word links, and a two-byte property size header.
    object_at = lambda n: 0x400+126+14*(n-1)
    struct.pack_into('>H', story, object_at(299)+10, 300)
    struct.pack_into('>H', story, object_at(300)+6, 299)
    struct.pack_into('>H', story, object_at(300)+12, 0x1600)
    story[0x1600:0x1606] = bytes((0, 0x40|63, 0x12, 0x34, 0x80|62, 0x80))
    story[0x1646:0x1649] = bytes((1, 77, 0))
    code = bytearray()
    labels, fixups = {}, []

    def raw(*data):
        code.extend(data)

    def label(name):
        labels[name] = dynamic+len(code)

    def branch(name, when=True):
        fixups.append((len(code), name, when))
        raw(0, 0)

    def instruction(group, op, args=(), dest=None):
        if group == 'ext':
            raw(0xbe, op)
        elif group == 'one':
            raw(0x80|(args[0][0]<<4)|op, *operand(args[0]))
            if dest is not None:
                raw(dest)
            return
        else:
            raw((0xc0 if group == 'two' else 0xe0)|op)
        types = [t for t, _ in args]+[3]*8
        for start in (0, 4) if group == 'var' and op in (12, 26) else (0,):
            raw(sum(types[start+i] << (6-2*i) for i in range(4)))
        for arg in args:
            raw(*operand(arg))
        if dest is not None:
            raw(dest)

    def operand(arg):
        typ, value = arg
        return (value >> 8, value & 255) if typ == 0 else (value,)

    large = lambda x: (0, x & 65535)
    small = lambda x: (1, x)
    var = lambda x: (2, x)

    def text(message):
        raw(0xb2)
        code.extend(zstring(message))
        raw(0xbb)

    def equal(variable, value):
        target = f'check{len(fixups)}'
        instruction('two', 1, [var(variable), large(value)])
        branch(target)
        text('testfailed '+chr(97+len(fixups)%26))
        raw(0xba)
        label(target)

    # Address scaling and seven-argument calls into code beyond 128 KiB.
    instruction('var', 12, [large(0x8000)]+[small(i) for i in range(1, 8)], 16)
    equal(16, 7)
    instruction('one', 8, [large(0x8008)], 16)
    equal(16, 42)
    instruction('two', 26, [large(0x8008), small(9)])
    instruction('one', 15, [large(0x8008)])
    instruction('var', 26, [large(0x8000)]+[small(i) for i in range(1, 8)])
    raw(0x8d, 0xff, 0x80, 0xbb)  # print_paddr 0x3fe00.
    instruction('one', 3, [large(300)], 16)
    equal(16, 299)
    instruction('two', 17, [large(300), small(63)], 16)
    equal(16, 0x1234)
    instruction('two', 18, [large(300), small(63)], 16)
    equal(16, 0x1602)
    instruction('one', 4, [var(16)], 16)
    equal(16, 2)
    instruction('two', 19, [large(300), small(63)], 16)
    equal(16, 62)
    instruction('two', 18, [large(300), small(62)], 16)
    instruction('one', 4, [var(16)], 16)
    equal(16, 64)
    instruction('var', 3, [large(300), small(63), large(0x5678)])
    instruction('two', 17, [large(300), small(63)], 16)
    equal(16, 0x5678)
    instruction('two', 11, [large(300), small(47)])
    instruction('two', 10, [large(300), small(47)])
    branch('attribute')
    text('testfailed')
    raw(0xba)
    label('attribute')
    instruction('ext', 2, [large(0x8000), large(-15)], 16)
    equal(16, 1)
    instruction('ext', 3, [large(0x8000), large(-15)], 16)
    equal(16, 65535)
    # Encode/text parsing must use nine Z-characters, not the V3 six.
    for i, c in enumerate(b'lookxxxxx'):
        story[0x1902+i] = c
    story[0x1901] = 9
    instruction('var', 27, [large(0x1900), large(0x1800)])
    instruction('two', 15, [large(0x1800), small(1)], 16)
    equal(16, 0x304)
    instruction('var', 28, [large(0x1902), small(9), small(0), large(0x1b00)])
    instruction('two', 15, [large(0x1b00), small(2)], 16)
    equal(16, int.from_bytes(key[4:6], 'big'))
    # Copy overlapping bytes backwards; then scan the result.
    story[0x1b20:0x1b25] = b'abcde'
    instruction('var', 29, [large(0x1b20), large(0x1b21), small(4)])
    instruction('two', 16, [large(0x1b21), small(3)], 16)
    equal(16, ord('d'))
    instruction('var', 23, [small(ord('d')), large(0x1b21), small(4), small(1)], 16)
    branch('scan')
    text('testfailed')
    raw(0xba)
    label('scan')
    equal(16, 0x1b24)
    # Exercise upper-window cursor and inverse cells on actual hardware too.
    instruction('var', 10, [small(2)])
    instruction('var', 11, [small(1)])
    instruction('var', 15, [small(1), small(2)])
    instruction('var', 17, [small(1)])
    text('upper screen')
    instruction('var', 17, [small(0)])
    instruction('var', 11, [small(0)])
    # Undo must resume the save_undo instruction with result 2.
    instruction('ext', 9, [], 17)
    instruction('two', 1, [var(17), small(2)])
    branch('undone')
    instruction('ext', 10, [], 17)
    text('testfailed')
    raw(0xba)
    label('undone')
    text('vfive ready')
    label('loop')
    instruction('var', 1, [large(0x1900), small(0), large(0x7800)])  # max 120, preload 0
    instruction('var', 5, [small(62)])
    instruction('var', 4, [large(0x1900), large(0x1800)], 16)
    equal(16, 13)
    instruction('two', 16, [large(0x1900), small(2)], 16)
    for letter, target in [('s', 'save'), ('r', 'restore'), ('n', 'move'), ('q', 'quit')]:
        instruction('two', 1, [var(16), small(ord(letter))])
        branch(target)
    instruction('var', 6, [var(18)])
    raw(0xbb)
    instruction('one', 12, [large(0)])
    fixups.append((len(code)-2, 'loop', None))
    label('move')
    instruction('two', 13, [small(18), small(9)])
    text('moved')
    instruction('one', 12, [large(0)])
    fixups.append((len(code)-2, 'loop', None))
    label('save')
    instruction('ext', 0, [], 17)
    instruction('two', 1, [var(17), small(2)])
    branch('restored')
    equal(17, 1)
    text('saved')
    instruction('one', 12, [large(0)])
    fixups.append((len(code)-2, 'loop', None))
    label('restored')
    text('restored')
    instruction('one', 12, [large(0)])
    fixups.append((len(code)-2, 'loop', None))
    label('restore')
    instruction('ext', 1, [], 17)
    text('restorefailed')
    raw(0xba)
    label('quit')
    raw(0xba)
    for offset, name, when in fixups:
        relative = labels[name]-(dynamic+offset+2)+2
        value = (relative & 65535) if when is None else ((0x8000 if when else 0)|(relative & 0x3fff))
        struct.pack_into('>H', code, offset, value)
    story[dynamic:dynamic+len(code)] = code
    # Routine 1 returns local 7; check_arg_count is mandatory for optional args.
    story[0x20000:0x20007] = bytes((7, 0xff, 0x7f, 7, 0xc3, 0xb1, 0xab))
    story[0x20007] = 7
    story[0x20020:0x20024] = bytes((0, 0x9b, 42, 0xb0))
    tail = zstring('high address text')
    story[0x3fe00:0x3fe00+len(tail)] = tail
    struct.pack_into('>H', story, 28, sum(story[64:min(size//4,65535)*4]) & 65535)
    return bytes(story)
