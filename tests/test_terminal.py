#!/usr/bin/env python3
"""Render actual CPU UART output and check fixed status, scrolling and cursor."""
from pathlib import Path
import re

init = '\x1b[0m\x1b[37;49m\x1b[2J\x1b[2;r\x1b[2;1H'
title = 'ZORK1.DAT - Tang Nano 20K'
status = re.compile(r'\x1b7\x1b\[1;1H\x1b\[2K' + re.escape(title) +
                    r'\x1b\[999C\x1b\[(\d+)D(Score: (-?\d+) +Moves: (\d+))\x1b8')

for logfile in ('impl/soc-verilator.log', 'impl/soc-sdsc.log', 'impl/soc-fat32.log', 'impl/soc-menu.log'):
    # read_bytes preserves the actual UART CR/LF bytes.
    stream = Path(logfile).read_bytes().decode()
    frames = status.findall(stream)
    assert len(frames) == 10, (logfile, frames)
    clean = status.sub('', stream).replace(init, '')
    assert title not in clean, 'duplicate standalone startup title'
    assert '\x1b' not in clean, 'unexpected/incomplete serial control sequence'
    values = [(int(score), int(moves)) for _, _, score, moves in frames]
    assert values[:3] == [(0, 0), (0, 1), (0, 2)], values
    assert values[4][1] > values[3][1], values  # NORTH advances moves.
    assert values[5] == values[3], values  # RESTORE restores saved moves.
    assert values[7] == (0, 0) and values[8] == values[3], values

    # Model two terminal heights, including a gray palette-black theme.
    for height, width in ((24, 80), (32, 80), (24, 100), (32, 132)):
        screen = [[' '] * width for _ in range(height)]
        row = col = top = 0
        bottom = height - 1
        background = 'gray'
        reverse = True
        saved = None
        updates = scrolls = boots = 0
        expected_status = None
        data = stream[stream.index(init):]
        pos = 0
        while pos < len(data):
            if data.startswith('\x1b7', pos):
                saved = (row, col)
                assert row >= 1, 'input cursor overlaps status'
                pos += 2
                continue
            if data.startswith('\x1b8', pos):
                assert saved is not None
                distance, counters, _, _ = frames[updates]
                assert int(distance) == len(counters)
                expected_status = title + ' ' * (width-len(title)-len(counters)-1) + counters
                assert ''.join(screen[0]).rstrip() == expected_status
                row, col = saved
                saved = None
                updates += 1
                pos += 2
                continue
            control = re.match(r'\x1b\[([0-9;]*)([mJHKrCD])', data[pos:])
            if control:
                args, command = control.groups()
                params = [int(p) if p else 0 for p in args.split(';')]
                if command == 'm':
                    for p in params:
                        if p == 0: background = 'black'; reverse = False
                        elif p == 40: background = 'gray'
                        elif p == 49: background = 'black'
                elif command == 'J':
                    assert args == '2' and background == 'black' and not reverse
                    screen = [[' '] * width for _ in range(height)]
                    expected_status = None
                    boots += 1
                elif command == 'H':
                    row = (params[0] or 1) - 1
                    col = ((params[1] if len(params) > 1 else 1) or 1) - 1
                elif command == 'C': col = min(width-1, col+(params[0] or 1))
                elif command == 'D': col = max(0, col-(params[0] or 1))
                elif command == 'K':
                    assert args == '2'
                    screen[row] = [' '] * width
                elif command == 'r':
                    top = (params[0] or 1) - 1
                    bottom = ((params[1] if len(params) > 1 else 0) or height) - 1
                    row = col = 0
                    assert top == 1 and bottom == height - 1
                pos += len(control[0])
                continue
            c = data[pos]
            assert c != '\x1b', repr(data[pos:pos+20])
            if c == '\r': col = 0
            elif c == '\b': col = max(0, col - 1)
            elif c == '\n':
                if row == bottom:
                    screen[top:bottom+1] = screen[top+1:bottom+1] + [[' '] * width]
                    scrolls += 1
                    if expected_status is not None:
                        assert ''.join(screen[0]).rstrip() == expected_status
                else: row = min(height-1, row+1)
            elif c >= ' ':
                if col == width:
                    col = 0
                    if row == bottom:
                        screen[top:bottom+1] = screen[top+1:bottom+1] + [[' '] * width]
                        scrolls += 1
                    else: row += 1
                screen[row][col] = c
                col += 1
            pos += 1
        assert updates == 10 and boots == 2 and scrolls > 0
print('PASS CPU serial status: score/moves, restore/reset, fixed row, scrolling, cursor, single title, right alignment at 80/100/132 columns, black background at 24/32 rows')
