#!/usr/bin/env python3
"""V5 character keys, maximum/preloaded input and custom alphabet checks."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import struct
from v5_fixture import make_story
from v3_fixture import zstring
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from make_sd import make_image,project_files


def program(code, change=None, commands=''):
    data=bytearray(make_story())
    data[8192:8192+len(code)]=code
    if change:change(data)
    struct.pack_into('>H',data,28,sum(data[64:262140])&65535)
    with tempfile.TemporaryDirectory(prefix='zork-v5-input-') as d:
        image=Path(d)/'card.img'
        image.write_bytes(make_image(project_files(bytes(data)),16,8,False))
        result=subprocess.run([ROOT/'impl/zork-host'],input=commands,text=True,capture_output=True,
                              env=dict(os.environ,ZORK_SD_IMAGE=str(image)),timeout=20,check=True)
        assert 'CORE ERROR' not in result.stdout,result.stdout
        return result.stdout

# read_char must consume the whole ANSI key, rather than return ESC and leak it.
code=bytes((0xf6,0x7f,1,16,0xe6,0xbf,16,0xbb))*5+b'\xba'
output=program(code,commands='\x1b[A\x1b[B\x1b[D\x1b[C\n')
assert '\n129\n130\n131\n132\n13\n' in output,output

# AREAD permits all 255 bytes, counts preloaded bytes, and never appends NUL.
code=bytes((0xe4,0x0f,0x19,0,0,0,16,       # read 0x1900,0 -> g0
            0xd0,0x1f,0x19,0,1,16,       # loadb text,1 -> g0
            0xe6,0xbf,16,0xbb,
            0xd0,0x1f,0x1a,1,0,16,       # canary at text+257
            0xe6,0xbf,16,0xbb,0xba))
def preload(data):
    data[0x1900:0x1905]=b'\xff\x03foo'
    data[0x1a01]=90
output=program(code,preload,'x'*252+'\n')
assert '\n255\n90\n' in output,output

# Decode and dictionary encoding both use the story-provided V5 alphabet.
code=bytearray((0xb2,))+zstring('alpha')+bytearray((0xbb,))
code+=bytes((0xfc,0x14,0x19,2,5,0,0x1b,0,  # encode_text 0x1902,5,0,0x1b00
             0xcf,0x1f,0x1b,0,0,16,0xe6,0xbf,16,0xbb,0xba))
def custom(data):
    struct.pack_into('>H',data,52,0x1c00)
    data[0x1c00:0x1c00+78]=b'zyxwvutsrqponmlkjihgfedcbaABCDEFGHIJKLMNOPQRSTUVWXYZ \n0123456789.,!?_#\'"/\\-:()'
    data[0x1902:0x1907]=b'alpha'
output=program(code,custom)
assert '\nzoksz\n' in output,output
# a,l,p map to Z-characters 31,20,16 in the reversed alphabet.
expected=(31<<10)|(20<<5)|16
expected=expected if expected<32768 else expected-65536
assert f'\n{expected}\n' in output,output
print('PASS V5 input: ANSI arrow keys, 255-byte preloaded AREAD, no NUL overrun, custom alphabet text/encoding')

# THROW unwinds past its own caller to the frame returned by CATCH.
code=bytes((0x88,0x80,0x10,16,0xe6,0xbf,16,0xbb,0xba))
def catches(data):
    a=bytes((2,0xb9,1,0xd9,0x2f,0x80,0x18,1,2,0xb1))
    b=bytes((1,0xdc,0x6f,55,1,0xb1))
    data[0x20040:0x20040+len(a)]=a
    data[0x20060:0x20060+len(b)]=b
output=program(code,catches)
assert '\n55\n' in output,output
print('PASS V5 CATCH/THROW: nested nonlocal return and call_2s')
