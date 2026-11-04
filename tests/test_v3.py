#!/usr/bin/env python3
"""Variable V3 loader, menus, identity-isolated save slots and rejection paths."""
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from make_sd import make_image, project_files, POOL_SIZE, SAVE_SLOTS, validate_story


def run(image, commands='', expected=0):
    result = subprocess.run([ROOT/'impl/zork-host'], input=commands, text=True,
                            capture_output=True, env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
    assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
    return result.stdout, result.stderr


def image_for(image, stories):
    files = list(stories)+[('SAVES.BIN', bytes(POOL_SIZE))]
    image.write_bytes(make_image(files, 16, 8, False))


def unchanged_except(before, after, sectors):
    for sector in range(len(before)//512):
        if sector not in sectors:
            start=sector*512
            assert before[start:start+512] == after[start:start+512], sector


with tempfile.TemporaryDirectory(prefix='zork-v3-') as directory:
    temp = Path(directory)
    image = temp/'card.img'
    for size in (4096, 4097, 65538, 100001, 131070, 131072):
        story = make_story(size)
        if size==131072:
            # The nonzero V3 length field tops out at 131070; early zero-length
            # headers use actual EOF and must cover the complete 128 KiB image.
            old=bytearray(story);struct.pack_into('>HH',old,26,0,0);story=bytes(old)
        validate_story(story)
        layout = FatImage(make_image(project_files(story, 'ALPHA.DAT'), 16, 8, False))
        layout.fragment('ALPHA.DAT', 11000)
        image.write_bytes(layout.data)
        output, status = run(image, 's\nn\nl\nr\nl\nq\n')
        assert 'alpha ready\ntail data' in output, output
        assert output.count('saved') == 2 and output.count('alpha moved') == 2, output
        assert 'alpha home' in output and 'ALPHA.DAT - Tang Nano 20K' in status
        restored, _ = run(image, 'r\nl\nq\n')
        assert 'alpha home' in restored and 'restorefailed' not in restored
        FatImage(image.read_bytes()).assert_only_saves_changed(layout.data)
    print('PASS variable/non-sector-aligned 4 KiB..128 KiB V3 stories, fragmented reads beyond 64 KiB, snapshot/reset restore')

    alpha = make_story(4096, 'alpha', 1)
    beta = make_story(65538, 'beta', 2)
    image_for(image, [('ALPHA.DAT', alpha), ('BETA.DAT', beta)])
    # Invalid choices, CSI arrows and backspace must not become game commands.
    output, _ = run(image, '9\n\x1b[A\n2\x7f1\ns\nn\ns\nq\n')
    assert 'Choose a compatible story number.' in output and 'alpha ready' in output
    baseline = image.read_bytes()
    output, status = run(image, '2\nr\ns\nq\n')
    assert 'beta ready' in output and 'restorefailed' in output and 'saved' in output
    assert 'BETA.DAT - Tang Nano 20K' in status
    layout = FatImage(image.read_bytes())
    pool = layout.sectors('SAVES.BIN')
    unchanged_except(baseline, layout.data, set(pool[512:1024]))
    # Switching back restores Alpha's moved state, not Beta's home state.
    output, _ = run(image, '1\nr\nl\nq\n')
    assert 'alpha moved' in output and 'restorefailed' not in output, output
    # Names are not save identities: renaming keeps the original save pair.
    renamed = FatImage(image.read_bytes())
    entry = renamed.file_entry('ALPHA.DAT')
    renamed.data[entry:entry+11] = b'RENAMED DAT'
    image.write_bytes(renamed.data)
    output, status = run(image, '2\nr\nl\nq\n')
    assert 'alpha moved' in output and 'RENAMED.DAT - Tang Nano 20K' in status
    # Replacing the same filename with a new release allocates another pair.
    replaced = FatImage(image.read_bytes())
    updated = make_story(4096, 'alpha', 3)
    for i, sector in enumerate(replaced.sectors('RENAMED.DAT')):
        replaced.data[sector*512:(sector+1)*512] = updated[i*512:(i+1)*512]
    image.write_bytes(replaced.data)
    baseline = image.read_bytes()
    output, _ = run(image, '2\nr\ns\nq\n')
    assert 'restorefailed' in output
    unchanged_except(baseline, image.read_bytes(), set(pool[1024:1536]))
    print('PASS startup menu/editing, story switching, save-slot isolation, rename continuity and new-release separation')

    # FAT directory/copy order must not determine display order or selection.
    image_for(image,[('ZULU.DAT',make_story(name='zulu',release=4)),
                     ('BETA.DAT',beta),('ALPHA.DAT',alpha)])
    expected_menu='V3 stories:\n1. ALPHA.DAT\n2. BETA.DAT\n3. ZULU.DAT\n'
    for choice,name in ((1,'alpha'),(2,'beta'),(3,'zulu')):
        output,_=run(image,f'{choice}\ns\nq\n')
        assert expected_menu in output and f'{name} ready' in output
    # A different directory order must still find each story's existing slot.
    saved=FatImage(image.read_bytes()).file_bytes('SAVES.BIN')
    image.write_bytes(make_image([('BETA.DAT',beta),('ALPHA.DAT',alpha),
                                  ('ZULU.DAT',make_story(name='zulu',release=4)),
                                  ('SAVES.BIN',saved)],16,8,False))
    for choice in (1,2,3):
        output,_=run(image,f'{choice}\nr\nq\n')
        assert expected_menu in output and 'restorefailed' not in output
    print('PASS alphabetical menu independent of copy order, matching story selection and save ownership after directory reordering')

    invalid = []
    def bad(label, offset, fmt, value, reason):
        broken = bytearray(alpha)
        struct.pack_into(fmt, broken, offset, value)
        invalid.append((label, bytes(broken), reason))
    bad('wrong version', 0, 'B', 5, 'requires Z-machine V3')
    bad('no dynamic RAM', 14, '>H', 32, 'memory layout')
    bad('PC outside file', 6, '>H', 60000, 'memory layout')
    bad('globals outside RAM', 12, '>H', 2000, 'memory layout')
    bad('invalid declared size', 26, '>H', 30000, 'declared length')
    invalid += [('too small', bytes(63), 'size must'), ('too large', bytes(1048577), 'padded file exceeds')]
    for label, broken, reason in invalid:
        image_for(image, [('BAD.DAT', broken)])
        baseline = image.read_bytes()
        output, _ = run(image, expected=2)
        assert reason in output, (label, output)
        assert image.read_bytes() == baseline
        image_for(image, [('BAD.DAT', broken), ('GOOD.DAT', alpha)])
        output, _ = run(image, 'q\n')
        assert 'Skipping BAD.DAT' in output and 'alpha ready' in output and 'Select story number' not in output
    # Very old V3 headers may omit length/checksum; actual file length is used.
    old = bytearray(alpha)
    struct.pack_into('>HH', old, 26, 0, 0)
    image_for(image, [('OLD.DAT', old)])
    assert 'alpha ready' in run(image, 'q\n')[0]
    image_for(image, [('CLOCK.DAT', make_story(clock=True))])
    assert 'Time: 13:07' in run(image, 'q\n')[1]
    print('PASS unsupported versions/layouts/sizes reject clearly, mixed directories skip incompatible stories, old headers and clock status')

    # No source trimming: accept physical padding but execute only logical bytes.
    for dynamic in (12289, 16384, 32768, 49152, 65534, 65535):
        large=make_story(131070, dynamic=dynamic)
        padded=large+b'\x1a'+b'^'*24529
        validate_story(padded)
        image_for(image, [('LARGE.DAT', padded)])
        output,_=run(image, 's\nn\nr\nl\nq\n')
        assert output.count('saved')==2 and 'alpha home' in output and 'memoryfailed' not in output, output
        output,_=run(image, 'r\nl\nq\n')
        assert 'alpha home' in output and 'memoryfailed' not in output, output
        layout=FatImage(image.read_bytes())
        assert layout.file_bytes('LARGE.DAT')==padded
        # Removing irrelevant padding preserves ownership of the saved snapshot.
        entry=layout.file_entry('LARGE.DAT')
        pool=layout.file_bytes('SAVES.BIN')
        image.write_bytes(make_image([('LARGE.DAT',large),('SAVES.BIN',pool)],16,8,False))
        assert 'restorefailed' not in run(image,'r\nl\nq\n')[0]
    print('PASS padded V3 files, 12..64 KiB writable memory, last writable byte, full-state restore/reset and padding-independent identity')

    # An old header with no declared length cannot justify an oversized image.
    oversized=bytearray(make_story(131072));struct.pack_into('>H',oversized,26,0)
    oversized+=b'padding'
    image_for(image,[('OVERSIZE.DAT',oversized)])
    assert 'declared length' in run(image,expected=2)[0]
    # The previous 512 KiB pool is left untouched and cannot authorize writes.
    image.write_bytes(make_image([('ALPHA.DAT',alpha),('SAVES.BIN',bytes(524288))],16,8,False))
    baseline=image.read_bytes()
    assert 'savefailed' in run(image,'s\nq\n')[0] and image.read_bytes()==baseline

    image_for(image,[('MAXIMUM.DAT',make_story(131070,dynamic=65535))])
    run(image,'s\ns\nq\n')
    baseline=image.read_bytes()
    payload=struct.unpack_from('<I',FatImage(baseline).file_bytes('SAVES.BIN'),8)[0]
    save_writes=(payload+511)//512+1
    for cut in range(save_writes):
        image.write_bytes(baseline)
        result=subprocess.run([ROOT/'impl/zork-host'],input='r\nn\ns\n',text=True,capture_output=True,
                              env=dict(os.environ,ZORK_SD_IMAGE=str(image),ZORK_CUT_AFTER_WRITES=str(cut)))
        assert result.returncode==99,(cut,result.stdout,result.stderr)
        recovered,_=run(image,'r\nl\nq\n')
        assert 'alpha home' in recovered and 'memoryfailed' not in recovered and 'restorefailed' not in recovered
        FatImage(image.read_bytes()).assert_only_saves_changed(baseline)
    image.write_bytes(baseline)
    run(image,'r\nn\ns\nq\n')
    assert 'alpha moved' in run(image,'r\nl\nq\n')[0]
    print(f'PASS all {save_writes} maximum-memory snapshot interruption boundaries, including the last dynamic byte')

    image_for(image, [('ALPHA.DAT', alpha)])
    full = FatImage(image.read_bytes())
    pool = full.sectors('SAVES.BIN')
    for slot in range(SAVE_SLOTS):
        full.data[pool[slot*512]*512:pool[slot*512]*512+8] = b'occupied'
    image.write_bytes(full.data)
    output, _ = run(image, 's\nq\n')
    assert 'Save pool full' in output and 'savefailed' in output
    assert image.read_bytes() == full.data
    # A restored known slot remains usable even when no blank slots remain.
    image_for(image, [('ALPHA.DAT', alpha)])
    run(image, 's\nn\ns\nq\n')
    owned = FatImage(image.read_bytes())
    pool = owned.sectors('SAVES.BIN')
    for slot in range(1, SAVE_SLOTS):
        owned.data[pool[slot*512]*512:pool[slot*512]*512+8] = b'occupied'
    image.write_bytes(owned.data)
    assert 'alpha moved' in run(image, 'r\nl\nq\n')[0]
    for kind in ('mixed', 'duplicate'):
        broken = FatImage(owned.data)
        target = pool[256 if kind=='mixed' else 512]*512
        source = pool[0]*512
        broken.data[target:target+512] = broken.data[source:source+512]
        if kind == 'mixed':
            broken.data[target+16] ^= 0x80
        image.write_bytes(broken.data)
        assert 'Saves disabled' in run(image, 's\nq\n')[0]
        assert image.read_bytes() == broken.data
    print('PASS full pool preserves unknown slots, existing owners retain restore access, mixed/duplicate ownership disables writes')

    many = [(f'GAME{i:02}.DAT', make_story(4096, 'alpha', i+1)) for i in range(SAVE_SLOTS)]
    for fat in (16,32):
        image.write_bytes(make_image(list(reversed(many))+[('SAVES.BIN',bytes(POOL_SIZE))],fat,8 if fat==16 else 64,False))
        baseline=image.read_bytes()
        for choice in range(1,SAVE_SLOTS+1):
            output,_=run(image,f'{choice}\nn\ns\nq\n')
            assert f'{choice}. GAME{choice-1:02}.DAT' in output and f'Starting GAME{choice-1:02}.DAT' in output
            assert 'savefailed' not in output and 'Saves disabled' not in output
        FatImage(image.read_bytes()).assert_only_saves_changed(baseline)
        for choice in range(1,SAVE_SLOTS+1):
            output,_=run(image,f'{choice}\nr\nl\nq\n')
            assert 'alpha moved' in output and 'restorefailed' not in output
        # Multi-digit editing, empty/zero/out-of-range/overflow input and arrows.
        output,_=run(image,'0\n21\n999\n\n1x\n19\x7f0\nq\n')
        assert output.count('Choose a compatible story number.')==5 and 'Starting GAME09.DAT' in output
        assert 'Starting GAME18.DAT' in run(image,'\x1b[A19\nq\n')[0]
    image_for(image, many+[('EXTRA.DAT', alpha)])
    assert 'Too many DAT files (maximum 20)' in run(image, expected=2)[0]
    print('PASS FAT16/FAT32 20-story sorted menu, multi-digit editing, every save slot and fresh-process restore, discovery limit')

    # Older ZMV5 pools retain their eight slots; expanding a copy keeps all bytes.
    image.write_bytes(make_image([('ALPHA.DAT',alpha),('SAVES.BIN',bytes(2097152))],16,8,False))
    assert 'savefailed' not in run(image,'n\ns\nq\n')[0]
    old_pool=FatImage(image.read_bytes()).file_bytes('SAVES.BIN')
    old=temp/'old-saves.bin';expanded=temp/'expanded-saves.bin'
    old.write_bytes(old_pool)
    args=[sys.executable,ROOT/'scripts/make_sd.py','--expand-saves',old,'--output',expanded]
    subprocess.run(args,check=True,capture_output=True)
    assert old.read_bytes()==old_pool and expanded.read_bytes()==old_pool+bytes(POOL_SIZE-len(old_pool))
    assert subprocess.run(args,capture_output=True).returncode!=0
    image.write_bytes(make_image([('ALPHA.DAT',alpha),('SAVES.BIN',expanded.read_bytes())],16,8,False))
    output,_=run(image,'r\nl\nq\n')
    assert 'alpha moved' in output and 'restorefailed' not in output
    print('PASS legacy 2 MiB saves, lossless expansion into a new file and overwrite refusal')

    # The fixtures are genuine V3 programs, checked by an independent interpreter.
    frotz = Path('/tmp/zork-tools/usr/games/dfrotz')
    if frotz.exists():
        source = temp/'alpha.dat'
        source.write_bytes(make_story(65538))
        reference = subprocess.run([frotz, '-q', '-m', '-p', '-w', '100', source],
                                   input='n\nl\nq\n', text=True, capture_output=True, check=True)
        assert 'alpha ready' in reference.stdout and 'tail data' in reference.stdout
        assert reference.stdout.count('alpha moved') == 2
        print('PASS independent Frotz execution of the original V3 fixture')

    # Add only the missing pool to an existing card directory; never touch old saves/stories.
    stage = temp/'existing'
    (stage/'ZORK').mkdir(parents=True)
    (stage/'ZORK/ALPHA.DAT').write_bytes(alpha)
    (stage/'ZORK/SAVEA.BIN').write_bytes(b'old save')
    args = [sys.executable, ROOT/'scripts/make_sd.py', '--directory', stage, '--prepare-saves']
    subprocess.run(args, check=True, capture_output=True)
    assert (stage/'ZORK/SAVES.BIN').read_bytes() == bytes(POOL_SIZE)
    assert (stage/'ZORK/SAVEA.BIN').read_bytes() == b'old save'
    assert (stage/'ZORK/ALPHA.DAT').read_bytes() == alpha
    assert subprocess.run(args, capture_output=True).returncode != 0
    # New image CLI also accepts multiple V3 stories without fixed identities.
    first, second = temp/'alpha.dat', temp/'beta.dat'
    first.write_bytes(alpha);second.write_bytes(beta)
    new_image = temp/'multi.img'
    subprocess.run([sys.executable, ROOT/'scripts/make_sd.py', '--story', first,
                    '--story', second, '--output', new_image, '--fat', '16', '--size-mib', '8'],
                   check=True, capture_output=True)
    assert 'beta ready' in run(new_image, '2\nq\n')[0]
    cli_image=temp/'twenty.img'
    cli_args=[sys.executable, ROOT/'scripts/make_sd.py', '--output', cli_image, '--fat', '16', '--size-mib', '8']
    for name,data in many:
        source=temp/name
        source.write_bytes(data)
        cli_args.extend(['--story',source])
    subprocess.run(cli_args,check=True,capture_output=True)
    assert 'Starting GAME18.DAT' in run(cli_image,'19\nq\n')[0]
    assert len(FatImage(cli_image.read_bytes()).file_bytes('SAVES.BIN'))==POOL_SIZE
    print('PASS one-time save preparation preserves existing files and 20-story CLI preparation')
