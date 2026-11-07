#!/usr/bin/env python3
"""Optional exact-story counter comparison; private game data stays untracked."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image, project_files

story = ROOT / 'inspect_files/planetfa.dat'
if not story.is_file():
    print('SKIP Planetfall counter comparison (private file unavailable)')
    sys.exit(0)
data = story.read_bytes()
if (int.from_bytes(data[2:4], 'big'), data[18:24], data[28:30]) != (37, b'851003', b'\x02\xd6'):
    print('SKIP Planetfall counter comparison (requires release 37 / 851003)')
    sys.exit(0)

commands = 'l\ni\nl\ni\nscore\nread chronometer\nwait\nscore\n'
with tempfile.TemporaryDirectory(prefix='planetfall-counter-') as directory:
    image = Path(directory) / 'card.img'
    image.write_bytes(make_image(project_files(data, 'PLANETFA.DAT'), 16, 8, False))
    ours = subprocess.run([ROOT / 'impl/zork-host'], input=commands, text=True,
                          capture_output=True, check=True, timeout=30,
                          env=dict(os.environ, ZORK_SD_IMAGE=str(image)))
    frames = [tuple(map(int, match)) for match in
              re.findall(r'Score: (-?\d+) +Moves: (\d+)', ours.stderr)]
    assert len(frames) == 9, ours.stderr
    assert all(score == 0 for score, _ in frames), frames
    values = [time for _, time in frames]
    # This release charges 9 for LOOK, 18 for INVENTORY, 7 for reading the
    # chronometer and 40 for WAIT. SCORE consumes no time.
    changes = [b - a for a, b in zip(values, values[1:])]
    assert changes == [9, 18, 9, 18, 0, 7, 40, 0], changes
    reported = list(map(int, re.findall(r'local day-cycle\) is (\d+)', ours.stdout)))
    assert reported == [values[4], values[7]], (reported, values)
    assert f'the current time is {values[5]}.' in ours.stdout
    assert 'CORE ERROR' not in ours.stdout
    assert story.read_bytes() == data
    logs = ROOT / 'impl/inspect-validation'
    logs.mkdir(exist_ok=True)
    (logs / 'planetfall-counters.txt').write_text(ours.stdout + '\nSTATUS:\n' + ours.stderr)

    reference = os.environ.get('DFROTZ') or shutil.which('dfrotz')
    if not reference and Path('/usr/games/dfrotz').is_file():
        reference = '/usr/games/dfrotz'
    if reference:
        theirs = subprocess.run([reference, '-q', '-m', '-p', '-w', '80', '-s', '1',
                                 '-Z', '3', str(story)], input=commands, text=True,
                                capture_output=True, check=True, timeout=30)
        other = [tuple(map(int, match)) for match in
                 re.findall(r'Score: (-?\d+) +Moves: (\d+)', theirs.stdout)]
        # Frotz suppresses unchanged status frames. Compare changed values
        # relative to startup because the two interpreters use different RNGs.
        changed = [value for i, value in enumerate(values) if not i or value != values[i-1]]
        assert [value - other[0][1] for _, value in other] == [value - changed[0] for value in changed], other
        assert all(score == 0 for score, _ in other), other
        (logs / 'planetfall-counters-frotz.txt').write_text(theirs.stdout + theirs.stderr)
        print('PASS Planetfall release 37: counter deltas match independent Frotz')
    else:
        print('SKIP independent Planetfall comparison (dfrotz unavailable)')
print('PASS Planetfall: LOOK +9, INVENTORY +18, SCORE unchanged; status agrees with story clock')
