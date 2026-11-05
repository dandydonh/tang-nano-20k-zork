#!/usr/bin/env python3
"""Render V5 serial control bytes and validate the visible game-owned screen."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
from v5_fixture import make_story
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from make_sd import make_image,project_files


def render(data):
    cells=[[' ']*80 for _ in range(32)]
    inverse=[[False]*80 for _ in range(32)]
    row=col=top=0
    bottom=31
    style=False
    saved=None
    pos=0
    while pos<len(data):
        query='\x1b7\x1b[999;999H\x1b[6n\x1b8'
        if data.startswith(query,pos):
            pos+=len(query)
            continue
        if data.startswith('\x1b7',pos):
            saved=(row,col,style);pos+=2;continue
        if data.startswith('\x1b8',pos):
            assert saved is not None
            row,col,style=saved;pos+=2;continue
        # The CPU fixture resets/finishes shortly after a prompt, which can
        # interrupt a size probe. A new ESC cancels the unfinished CSI, as on
        # a terminal; an unfinished final CSI has no visible effect.
        interrupted=re.match(r'\x1b\[[0-9;]*(?=\x1b|$)',data[pos:])
        if interrupted:
            pos+=len(interrupted[0]);continue
        control=re.match(r'\x1b\[([0-9;]*)([mHKrJ])',data[pos:])
        if control:
            args,cmd=control.groups()
            params=[int(p) if p else 0 for p in args.split(';')]
            if cmd=='H':row=(params[0] or 1)-1;col=((params[1] if len(params)>1 else 1) or 1)-1
            elif cmd=='K':
                assert params[0]==2
                cells[row]=[' ']*80;inverse[row]=[False]*80
            elif cmd=='J':
                assert params[0]==2
                cells=[[' ']*80 for _ in range(32)]
                inverse=[[False]*80 for _ in range(32)]
            elif cmd=='r':
                top=(params[0] or 1)-1;bottom=((params[1] if len(params)>1 else 0) or 32)-1
                row=col=0
            elif cmd=='m':
                for p in params:
                    if p==0:style=False
                    elif p==7:style=True
            assert 0<=row<32 and 0<=col<80,(row,col,control[0])
            pos+=len(control[0]);continue
        c=data[pos];pos+=1
        assert c!='\x1b',repr(data[pos-1:pos+20])
        if c=='\r':col=0
        elif c=='\n':
            if row==bottom:
                cells[top:bottom+1]=cells[top+1:bottom+1]+[[' ']*80]
                inverse[top:bottom+1]=inverse[top+1:bottom+1]+[[False]*80]
            else:row=min(31,row+1)
        elif c=='\b':col=max(0,col-1)
        elif ord(c)>=32:
            assert col<80,'output requires terminal autowrap'
            cells[row][col]=c;inverse[row][col]=style;col+=1
    return [''.join(line).rstrip() for line in cells],inverse


if len(sys.argv)>1:
    data=Path(sys.argv[1]).read_bytes().decode()
    # Testbench diagnostics after the final UART byte are not terminal output.
    data=data[data.index('\x1b'):data.index('\nPASS V5 CPU')]
    screen,styles=render(data)
    assert screen[0][1:13]=='upper screen',screen
    assert styles[0][1] and any('>' in line for line in screen[2:]),screen
    print('PASS actual V5 CPU UART: inverse upper text survives lower scrolling and reset restore')
    sys.exit(0)

cases=[('original',make_story(),'n\nl\n')]
for name,commands in (('hitchhik','turn on light\nlook\ni\n'),
                      ('beyondzo','begin\n\n\n\n\n\nlook\ni\n')):
    path=ROOT/'inspect_files'/f'{name}.dat'
    if path.is_file():cases.append((name,path.read_bytes(),commands))
with tempfile.TemporaryDirectory(prefix='zork-display-') as d:
    image=Path(d)/'card.img'
    for name,story,commands in cases:
        image.write_bytes(make_image(project_files(story),16,8,False))
        result=subprocess.run([ROOT/'impl/zork-host'],input=commands,text=True,capture_output=True,
                              env=dict(os.environ,ZORK_SD_IMAGE=str(image),ZORK_SCREEN='1'),timeout=30,check=True)
        screen,styles=render(result.stdout)
        if name=='original':
            assert screen[0][1:13]=='upper screen' and styles[0][1],screen
            assert any('9' in line for line in screen[2:]),screen
        elif name=='hitchhik':
            assert 'Bedroom, in the bed' in screen[0] and 'Score:' in screen[0] and 'Moves:' in screen[0],screen
            assert any('no tea' in line for line in screen[1:]),screen
        else:
            assert 'Hilltop' in screen[0] and 'EN:16' in screen[1],screen
            assert any("You're wearing a pack." in line for line in screen),screen
            assert any('+---' in line for line in screen),screen
            assert not any('???' in line for line in screen),screen
        print(f'PASS rendered V5 UART screen: {name}')
