#!/usr/bin/env python3
"""Unicode game text/input, parser bytes, streams, editing and table boundaries."""
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from sd_image_fixture import make_image, project_files
from unicode_fixture import Program, DEFAULT, CUSTOM, packed
from v3_fixture import make_story
from v5_fixture import make_story as make_v5_story

ROOT = Path(__file__).resolve().parents[1]


def run(program, keys=b'', expected=0, **extra):
    if isinstance(keys, str):
        keys = keys.encode()
    with tempfile.TemporaryDirectory(prefix='zork-unicode-text-') as directory:
        image = Path(directory) / 'card.img'
        image.write_bytes(make_image(project_files(program.story()), 16, 8, False))
        result = subprocess.run([ROOT / 'impl/zork-host'], input=keys, capture_output=True,
                                timeout=30, env=dict(os.environ, ZORK_SD_IMAGE=str(image), **extra))
        assert result.returncode == expected, (result.stdout, result.stderr)
        text = result.stdout.decode('utf-8')  # Every output sequence must be valid.
        if not expected:
            assert 'CORE ERROR' not in text, text
        return text


def values(text):
    return [list(map(int, match.split())) for match in re.findall(r'values ([0-9 ]+)', text)]


for version in (3, 5):
    p = Program(version)
    p.nl()
    for c in range(155, 224):
        p.char(c)
    p.nl()
    p.code.append(0xb2)
    p.code += packed(range(155, 224))
    output = run(p)
    assert output.replace('\n', '').count(DEFAULT) == 2, output

    # Stored line characters are lower-case ZSCII bytes, not UTF-8 bytes.
    p = Program(version).read().values(0x700 + (2 if version == 5 else 1), 5)
    assert values(run(p, 'ÉÑÖŸŒ\n')) == [[170, 206, 156, 166, 220]]
    # Incomplete, overlong, surrogate and out-of-range UTF-8 sequences do not
    # eat a following key/Enter or leak their bytes into the game.
    for bad in (b'\xc3', b'\x80\xbf', b'\xc0\xaf', b'\xed\xa0\x80',
                b'\xf4\x90\x80\x80', b'\xf0\x80\x80\xaf'):
        p = Program(version).read().values(0x700 + (2 if version == 5 else 1), 1)
        assert values(run(p, bad + b'X\n')) == [[120]], bad
    assert values(run(p, '🚀界X\n')) == [[120]]

    # History stores byte-sized ZSCII and redraws whole Unicode characters.
    p = Program(version)
    for _ in range(3):
        p.read().values(0x700 + (2 if version == 5 else 1), 2)
    output = run(p, 'Éx\n\x1b[A\x7fy\nzz\x1b[A\x1b[B\n')
    assert values(output) == [[170, 120], [170, 121], [122, 122]], output

    # Dictionary matching/parse positions refer to ZSCII bytes.
    p = Program(version).read(0xa80).values(0xa82, 1, word=True).values(0xa84, 2)
    key = packed([99, 97, 102, 170], 9 if version == 5 else 6)
    p.data[0x300:0x304] = bytes((0, len(key), 0, 1))
    p.data[0x304:0x304 + len(key)] = key
    assert values(run(p, 'CAFÉ\n')) == [[0x304], [4, 2 if version == 5 else 1]]
    print(f'PASS V{version}: default table, packed text, lowercase input, malformed UTF-8, history, dictionary ZSCII bytes')

p = Program(table=CUSTOM)
for _ in range(4):
    p.op('var', 22, 1, result=20).number(('v', 20)).nl()
output = run(p, 'ĀΩ界€')
assert re.search(r'\n155\n157\n159\n161\n', output), output
p = Program()
for _ in range(2):
    p.op('var', 22, 1, result=20).number(('v', 20)).nl()
assert '\n27\n66\n' in run(p, '\x1bxB'), 'Preserve the existing read_char Escape event'

p = Program(table=CUSTOM).read().values(0x702, 3)
assert values(run(p, 'ĀΩ界\n')) == [[156, 158, 159]]
# A combining mark is removed by redrawing the line; wide glyphs occupy cells,
# while each character still occupies exactly one byte in the input buffer.
p = Program(table=CUSTOM).read().values(0x701, 3)
assert values(run(p, 'Ā界\u0301\x7f\x7fZ\n')) == [[2, 156, 122]]
p = Program(table=CUSTOM).read().values(0x701, 3)
assert values(run(p, '\u0301Ā界\x7fZ\n')) == [[2, 156, 122]]
p = Program(table=CUSTOM)
p.char(155).char(159).read(preload=True).values(0x701, 3)
p.data[0x701:0x704] = bytes((2, 155, 159))
assert values(run(p, '\x7fZ\n')) == [[2, 155, 122]]

p = Program().read().values(0x701, 1).values(0x801, 1)
p.data[0x700] = 255
p.data[0x801] = 90
assert values(run(p, 'É'*255+'\n')) == [[255], [90]]

p = Program(table=CUSTOM).op('var', 19, 3, 0xb00)
p.char(155).op('ext', 11, 0x100).op('ext', 11, 0x20ac).op('ext', 11, 0xf1)
p.op('var', 19, -3).values(0xb00, 1, word=True).values(0xb02, 4)
assert values(run(p)) == [[4], [155, 155, 161, 63]]

p = Program(table=CUSTOM)
for c in (0x100, 0x754c, 0xe9, 0x9b, 0xd800, 0xffff):
    p.op('ext', 12, c, result=20).number(('v', 20)).char(32)
p.nl().text('unicode ')
for c in (0x100, 0x754c, 0x3a9):
    p.op('ext', 11, c)
output = run(p)
assert '3 3 1 0 0 0 ' in output and 'unicode Ā界Ω' in output.replace('\n', ''), output

p = Program(table=[]).char(170).op('ext', 12, 0xe9, result=20).number(('v', 20))
assert '?1' in run(p), 'An empty custom table must not fall back to the default'
p = Program(table=CUSTOM).char(155)
struct.pack_into('>H', p.data, 0x1d00, 2)
assert 'ä' in run(p), 'A short header extension must use the default table'
p = Program(table=CUSTOM).char(155)
p.op('var', 1, 0x1d11, 0, 0x754c).char(155)
assert 'Ā界' in run(p).replace('\n', ''), 'Dynamic translation tables must not be cached stale'
p = Program(table=CUSTOM)
struct.pack_into('>H', p.data, 52, 0x1c00)
alphabet = bytearray(b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ \n0123456789.,!?_#\'"/\\-:()')
alphabet[0] = 155
p.data[0x1c00:0x1c00+78] = alphabet
p.data[0x702] = 155
p.code.append(0xb2)
p.code += packed([97])  # A0 Z-character 6 now denotes ZSCII 155, Unicode Ā.
p.op('var', 28, 0x702, 1, 0, 0xb00).values(0xb00, 1, word=True)
output = run(p)
assert 'Ā' in output and values(output) == [[(6 << 10) | (5 << 5) | 5]], output
p = Program(table=CUSTOM).char(155)
p.data[0x1d10] = 98
assert 'Unicode table length' in run(p, expected=2)

# Full-word Unicode buffering must not reverse or drop non-ASCII characters.
for version, table, codes, expected in ((3, None, [99, 97, 102, 170], 'café'),
                                       (5, CUSTOM, [155, 159, 157], 'Ā界Ω')):
    p = Program(version, table=table)
    for _ in range(60):
        for c in codes:
            p.char(c)
        p.char(32)
    output = run(p)
    assert ''.join(output.split()).count(expected) == 60, output
print('PASS V5: custom/empty tables, U+0100 key collision, read_char, Unicode opcodes, memory-stream conversion and word wrapping')

# Unicode buffered words retain the existing V5 snapshot/undo layout. The
# story's live translation table must also roll back with dynamic memory.
p = Program(table=CUSTOM).op('ext', 0, result=20)
p.op('two', 1, ('v', 20), 2).branch('resumed')
p.op('var', 1, 0x1d11, 0, 0x754c).text('mutated ').char(155).nl()
p.op('ext', 1, result=20).text('restore failed').jump('done')
p.label('resumed').text('restored unicode ').char(155).nl().label('done')
output = run(p, ZORK_TEST_DEFAULT_SLOT='1')
assert 'mutated 界' in output and 'restored unicode Ā' in output, output

p = Program(table=CUSTOM).op('ext', 11, 0x754c).op('ext', 9, result=20)
p.op('two', 1, ('v', 20), 2).branch('resumed')
p.op('var', 1, 0x1d11, 0, 0x754c).op('ext', 10, result=20).text('undo failed').jump('done')
p.label('resumed').char(155).nl().label('done')
assert '界Ā' in run(p), 'Undo must restore pending UTF-8 words and the Unicode table'
print('PASS Unicode V5 disk save/restore and undo with a buffered UTF-8 word and mutable translation table')

reference = os.environ.get('DFROTZ') or shutil.which('dfrotz') or '/usr/games/dfrotz'
if Path(reference).exists():
    cases = []
    p = Program(3)
    for c in range(155, 224):
        p.char(c)
    cases.append((p, '', DEFAULT))
    p = Program(table=CUSTOM).read().values(0x702, 3)
    cases.append((p, 'ĀΩ界\n', None))
    p = Program(table=CUSTOM)
    for c in (0x100, 0x754c, 0x3a9):
        p.op('ext', 11, c)
    cases.append((p, '', 'Ā界Ω'))
    with tempfile.TemporaryDirectory(prefix='zork-unicode-frotz-') as directory:
        for i, (p, keys, expected) in enumerate(cases):
            story = Path(directory) / f'fixture{i}.z{p.version}'
            story.write_bytes(p.story())
            ref = subprocess.run([reference, '-q', '-m', '-w', '200', '-Z', '3', str(story)],
                                 input=keys.encode(), capture_output=True, timeout=20, check=True)
            theirs = ref.stdout.decode()
            ours = run(p, keys)
            if expected:
                assert expected in theirs.replace('\n', '') and expected in ours.replace('\n', ''), (theirs, ours)
            else:
                assert values(theirs) == values(ours) == [[156, 158, 159]], (theirs, ours)
    print('PASS independent dfrotz: all default extra characters, custom-table Unicode input bytes and print_unicode')

# Explicitly verify the prior firmware's disk snapshots remain readable.
baseline = os.environ.get('ZORK_COMPAT_HOST')
if baseline:
    for version, story in ((3, make_story()), (5, make_v5_story())):
        with tempfile.TemporaryDirectory(prefix='zork-unicode-compat-') as directory:
            image = Path(directory) / 'card.img'
            image.write_bytes(make_image(project_files(story), 16, 8, False))
            env = dict(os.environ, ZORK_SD_IMAGE=str(image), ZORK_TEST_DEFAULT_SLOT='1')
            old = subprocess.run([baseline], input='n\ns\nq\n', text=True, capture_output=True, env=env, check=True)
            assert 'saved' in old.stdout
            new = subprocess.run([ROOT / 'impl/zork-host'], input='r\nl\nq\n', text=True,
                                 capture_output=True, env=env, check=True)
            assert ('alpha moved' if version == 3 else 'restored') in new.stdout, new.stdout
            assert 'CORE ERROR' not in new.stdout and 'restorefailed' not in new.stdout
    print('PASS prior-firmware V3/V5 disk snapshots restore with Unicode text/input firmware')
