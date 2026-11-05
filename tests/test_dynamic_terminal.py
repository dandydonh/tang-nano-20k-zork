#!/usr/bin/env python3
"""Render real board output with independently sized UART and HDMI sinks."""
from pathlib import Path
import subprocess
from test_output import render

ROOT=Path(__file__).resolve().parents[1]
words=[f'word{i:03}' for i in range(200)]
for width in (20,60,80,100,149,180,300):
    for mode in ('story','edit','long'):
        data=subprocess.check_output([ROOT/'impl/paging-test',str(width),'35',mode]).decode()
        for wrap in (False,True):
            screen,row,col,clipped=render(data,width,wrap)
            assert not clipped,(width,mode)
            if mode=='story':
                assert ' '.join(screen[1:]).split()==words,width
                assert max(map(len,data.split('\r\n')))<=width-1
                if width>80:assert max(map(len,data.split('\r\n')))>79,width
            elif mode=='long':
                assert ''.join(screen[1:]).replace(' ','')=='x'*500
                assert max(map(len,data.split('\r\n')))==width-1
            else:
                assert row==1 and col==11 and screen[1]=='Input> look',(width,row,col)
                assert not any(screen[2:]),width
print('PASS dynamic board UART: 20/60/80/100/149/180/300 columns, independent HDMI margin, full words, autowrap off/on and wrapped input erase')
