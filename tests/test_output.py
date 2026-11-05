#!/usr/bin/env python3
"""Explicit wrapping must preserve text with host terminal autowrap disabled."""
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
subprocess.run(['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror','-Ifirmware',
                'firmware/output.c','tests/output_tb.c','-o','impl/output-test'],cwd=ROOT,check=True)

def output(text,mode='story'):
    result=subprocess.run([ROOT/'impl/output-test',mode],input=text.encode(),capture_output=True,check=True)
    data=result.stdout.decode()
    assert '\n' not in data.replace('\r\n',''), 'bare LF'
    return data

def render(data,width=80,wrap=False):
    screen=[list('STATUS'.ljust(width))]+[[' ']*width for _ in range(100)]
    row,col,pos=1,0,0
    clipped=0
    while pos<len(data):
        query='\x1b7\x1b[999;999H\x1b[6n\x1b8'
        if data.startswith(query,pos):
            pos+=len(query);continue
        control=re.match(r'\x1b\[(\d+)([ACm])',data[pos:])
        if control:
            n=int(control[1])
            if control[2]=='A':row-=n
            elif control[2]=='C':col=min(width-1,col+n)
            pos+=len(control[0]);continue
        c=data[pos];pos+=1
        if c=='\r':col=0
        elif c=='\n':row+=1
        elif c=='\b':col=max(0,col-1)
        else:
            assert c!='\x1b'
            if col==width and wrap:row+=1;col=0
            if col<width:screen[row][col]=c
            else:clipped+=1
            col+=1
        assert row>=1, 'input editing overwrote the status row'
    return [''.join(line).rstrip() for line in screen],row,col,clipped

paragraph=' '.join(f'word{i:03}' for i in range(240))
data=output(paragraph)
assert data.split()==paragraph.split()
assert max(map(len,data.split('\r\n')))<=79
for width in (80,100,132,180):
    for wrap in (False,True):
        screen,_,_,clipped=render(data,width,wrap)
        assert clipped==0 and ' '.join(screen[1:]).split()==paragraph.split()
        assert screen[0]=='STATUS'

for length in (78,79,80,158,159,237):
    word='x'*length
    data=output('prefix '+word+' suffix')
    assert ''.join(data.split())=='prefix'+word+'suffix'
    assert all(len(line)<=79 for line in data.split('\r\n'))
assert output('a'*79+'\nnext')=='a'*79+'\r\nnext'
assert output('a'*79+' next')=='a'*79+'\r\nnext'
assert output('one\n\ntwo\n')=='one\r\n\r\ntwo\r\n'
assert output('  indented text')=='  indented text'
assert output('unfinished prompt>')=='unfinished prompt>'
raw=output('x'*200,'raw')
assert raw.replace('\r\n','')=='x'*200
assert all(len(line)<=79 for line in raw.split('\r\n'))

# Exercise the editor's erase-space-backspace sequence across a wrapped line,
# as used by both Backspace and replacing a recalled command with its draft.
for width in (80,100,180):
    data=output('x'*119+'\b'*119+'look','edit')
    screen,row,col,clipped=render(data,width)
    assert clipped==0 and row==1 and col==11
    assert screen[1]=='Input> look' and not any(screen[2:]) and screen[0]=='STATUS'
print('PASS word wrapping: no lost/clipped text with autowrap off/on at 80/100/132/180 columns, long words, newlines, prompt flush and input erase across wraps')

if len(sys.argv)>1:
    assert sys.argv[1]=='--cpu-log'
    stream=Path(sys.argv[2]).read_bytes().decode()
    assert 'PASS soc boot' in stream and 'CORE ERROR' not in stream and 'memoryfailed' not in stream
    assert stream.count('saved')==3
    assert stream.count('stream counts\r\n6 6 13 13 ')==2, 'CPU memory stream table contents'
    assert 'hidden screen' not in stream and 'outer' not in stream and 'inner' not in stream
    init='\x1b[0m\x1b[37;49m\x1b[2J\x1b[2;r\x1b[2;1H'
    uart=stream[stream.index(init):stream.index('\nPASS serial attributes')]
    boots=uart.split(init)[1:]
    assert len(boots)==2
    intro=' '.join(['a lengthy paragraph must remain complete when the terminal does not wrap automatically']*6)
    for boot in boots:
        clean=re.sub(r'\x1b7.*?\x1b8','',boot,flags=re.S)
        narrative=re.sub(r'\x1b\[0m\[MORE\]\x08{6}(?:(?:\x1b\[[07]m)?.){6}\x08{6}','',clean)
        assert intro in ' '.join(narrative.split()), 'paragraph words missing/split in CPU output'
        assert 'alpha ready' in clean and 'tail data' in clean
        for width in (80,100,132,180):
            for wrap in (False,True):
                screen,_,_,clipped=render(clean,width,wrap)
                assert clipped==0,(width,wrap)
                assert screen[0]=='STATUS'
    print('PASS actual CPU UART: complete long paragraphs, no clipping at 80/100/132/180 columns with autowrap off/on, wrapped input erase, save/restore and reset')
