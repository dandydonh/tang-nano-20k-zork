#!/usr/bin/env python3
"""PS/2 scan bytes through the real decoder, interpreter and save backend."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata
from sd_image_fixture import make_image, project_files
from unicode_fixture import Program, CUSTOM, DEFAULT
from ps2_fixture import key, text, compose, hex_entry, hex_start, tap
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]


def run(program, scans, uart=b''):
    with tempfile.TemporaryDirectory(prefix='zork-ps2-unicode-') as directory:
        work = Path(directory)
        image, keys = work / 'card.img', work / 'keys.bin'
        image.write_bytes(make_image(project_files(program.story()), 16, 8, False))
        keys.write_bytes(scans)
        result = subprocess.run([ROOT / 'impl/zork-host'], input=uart, capture_output=True, timeout=30,
                                env=dict(os.environ, ZORK_SD_IMAGE=str(image), ZORK_PS2_SCANS=str(keys)))
        assert result.returncode == 0, (result.stdout, result.stderr)
        output = result.stdout.decode()
        assert 'CORE ERROR' not in output, output
        return output


def values(output):
    return [list(map(int, match.split())) for match in re.findall(r'values ([0-9 ]+)', output)]


for version in (3, 5):
    # Canonical accent sequences are derived independently from Unicode data.
    for prefix, combining, letters in (("'", '\u0301', 'AEIOUYaeiouy'),
                                       ('`', '\u0300', 'AEIOUaeiou'),
                                       ('"', '\u0308', 'AEIOUaeiouy'),
                                       ('^', '\u0302', 'AEIOUaeiou'),
                                       ('~', '\u0303', 'ANOano'), (',', '\u0327', 'Cc')):
        for letter in letters:
            char = unicodedata.normalize('NFC', letter + combining)
            assert len(char) == 1 and char in DEFAULT
            p = Program(version).read().values(0x702 if version == 5 else 0x701, 1)
            expected = DEFAULT.index(char.lower()) + 155
            output = run(p, compose(prefix, letter) + key('\n'))
            assert values(output) == [[expected]], (version, char, output)
    p = Program(version).read().values(0x702 if version == 5 else 0x701, 3)
    output = run(p, compose("'", 'E') + hex_entry('00d1') + text('X\n'))
    assert values(output) == [[170, 206, 120]], output
    # Invalid, canceled and incomplete entries never become command characters.
    p = Program(version).read().values(0x702 if version == 5 else 0x701, 1)
    scans = compose('x', 'z') + hex_entry('d800') + hex_entry('110000')
    scans += hex_start() + text('e9') + key('\x1b') + text('X\n')
    assert values(run(p, scans)) == [[120]]
    p = Program(version)
    for _ in range(2):
        p.read().values(0x702 if version == 5 else 0x701, 2)
    scans = compose("'", 'e') + text('x\n') + tap(0x75, True) + key('\b') + hex_entry('f1') + key('\n')
    assert values(run(p, scans)) == [[170, 120], [170, 206]]
    print(f'PASS V{version}: PS/2 Compose accent/case mapping, hex, mixed US text, invalid/canceled entry and ZSCII parser bytes')

p = Program(table=CUSTOM)
for _ in range(3):
    p.op('var', 22, 1, result=20).number(('v', 20)).nl()
output = run(p, hex_entry('0100') + hex_entry('754c') + hex_entry('20ac', ' '))
assert '\n155\n159\n161\n' in output, output

p = Program(table=CUSTOM).read().values(0x701, 4)
output = run(p, hex_entry('0100') + hex_entry('03a9') + hex_entry('754c') + key('\n'))
assert values(output) == [[3, 156, 158, 159]], output

# PS/2 entries and ordinary serial input share the same command buffer.
p = Program().read().values(0x702, 3)
assert values(run(p, compose("'", 'e'), b'Xy\n')) == [[170, 120, 121]]

# First save and reset/restore with a PS/2-composed command; preserve the legacy
# pool and unrelated core file bytes on this disposable shared-card image.
with tempfile.TemporaryDirectory(prefix='zork-ps2-save-') as directory:
    work = Path(directory)
    image, keys = work / 'card.img', work / 'keys.bin'
    from fat_helpers import FatImage
    from sd_image_fixture import POOL_SIZE
    story = make_story(unicode_input=True)
    image.write_bytes(make_image([('ALPHA.Z3', story), ('SAVES.BIN', bytes(POOL_SIZE)),
                                  ('OTHER.BIN', b'other core data')], 16, 8, False))
    keys.write_bytes(compose("'", 'E') + text('\ns\n5\nq\n'))
    env = dict(os.environ, ZORK_SD_IMAGE=str(image), ZORK_PS2_SCANS=str(keys))
    saved = subprocess.run([ROOT / 'impl/zork-host'], input=b'', capture_output=True, env=env, check=True).stdout.decode()
    assert 'alpha moved' in saved and 'saved\n' in saved, saved
    before = image.read_bytes()
    keys.write_bytes(text('r\n5\nl\nq\n'))
    restored = subprocess.run([ROOT / 'impl/zork-host'], input=b'', capture_output=True, env=env, check=True).stdout.decode()
    assert 'alpha moved' in restored and image.read_bytes() == before, restored
    layout = FatImage(image.read_bytes())
    assert layout.file_bytes('SAVES.BIN') == bytes(POOL_SIZE)
    assert layout.file_bytes('OTHER.BIN') == b'other core data' and layout.file_bytes('ALPHA.Z3') == story
print('PASS PS/2 Unicode: custom V5 read_char/AREAD, U+0100, CJK, UART mixing and V3 save/reset/restore with shared data preserved')
