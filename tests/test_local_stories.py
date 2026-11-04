#!/usr/bin/env python3
"""Optional native validation of privately supplied files; contains no story data."""
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from fat_helpers import FatImage

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from make_sd import make_image,POOL_SIZE,SAVE_SIZE,validate_story

source=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'inspect_files'
paths=[source/name for name in ('lurking.dat','moonmist.dat','planetfa.dat')]
if not all(p.is_file() for p in paths):
    print('SKIP optional local story validation (private files unavailable)')
    sys.exit(0)
originals={p:p.read_bytes() for p in paths}
logs=ROOT/'impl/inspect-validation'
logs.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='zork-private-') as directory:
    image=Path(directory)/'card.img'
    files=[(p.name.upper(),data) for p,data in originals.items()]+[('SAVES.BIN',bytes(POOL_SIZE))]
    image.write_bytes(make_image(files,16,8,False))
    for index,(path,data) in enumerate(originals.items()):
        validate_story(data)
        length=int.from_bytes(data[26:28],'big')*2
        assert sum(data[64:length])&65535==int.from_bytes(data[28:30],'big')
        before=image.read_bytes()
        for tag,commands,successes in [('play','look\ninventory\nsave\nlook\nrestore\nlook\n',2),
                                         ('reset','restore\nlook\n',1)]:
            result=subprocess.run([ROOT/'impl/zork-host'],input=f'{index+1}\n'+commands,text=True,
                                  capture_output=True,env=dict(os.environ,ZORK_SD_IMAGE=str(image)),timeout=30)
            assert result.returncode==0,(path,result.stdout,result.stderr)
            assert 'CORE ERROR' not in result.stdout and 'Failed.' not in result.stdout
            assert len(re.findall(r'\b(?:Ok|Okay)\.',result.stdout))==successes,(path,result.stdout)
            assert path.name.upper() in result.stderr
            assert all(len(line)<=79 for line in result.stdout.splitlines()), 'unwrapped/clipped story line'
            if data[1]&2:assert 'Time:' in result.stderr
            (logs/(path.stem+'-'+tag+'.txt')).write_text(result.stdout+'\nSTATUS:\n'+result.stderr)
        after=FatImage(image.read_bytes())
        pool=after.sectors('SAVES.BIN')
        allowed=set(pool[index*2*SAVE_SIZE//512:(index+1)*2*SAVE_SIZE//512])
        for sector in range(len(before)//512):
            if sector not in allowed:assert before[sector*512:(sector+1)*512]==after.data[sector*512:(sector+1)*512]
        header=after.file_bytes('SAVES.BIN')[index*2*SAVE_SIZE:][:512]
        magic,generation,size,checksum=struct.unpack_from('<4I',header)
        assert magic==0x35564d5a and generation==1
        assert int.from_bytes(data[14:16],'big')<size<int.from_bytes(data[14:16],'big')+16384
        payload=after.file_bytes('SAVES.BIN')[index*2*SAVE_SIZE+512:][:size]
        calculated=2166136261
        for value in payload:calculated=((calculated^value)*16777619)&0xffffffff
        assert calculated==checksum
        for p,original in originals.items():assert after.file_bytes(p.name.upper())==original
        frotz=Path('/tmp/zork-tools/usr/games/dfrotz')
        if frotz.exists():
            reference=subprocess.run([frotz,'-q','-m','-p','-w','200',str(path)],input='',
                                     text=True,capture_output=True,timeout=10)
            paragraphs=[p for p in re.split(r'\n\s*\n',reference.stdout)
                        if len(p)>120 and not re.search(r'(?:Time:|Score:).*$',p.splitlines()[0])]
            assert paragraphs, 'independent story startup missing'
            ours=' '.join((logs/(path.stem+'-play.txt')).read_text().split())
            for paragraph in paragraphs:assert ' '.join(paragraph.split()) in ours, 'story text lost during wrapping'
        print(f'PASS private {path.name}: unchanged padded V3 file, startup, commands, save/restore, reset restore, isolated slot and snapshot checksum')
for path,data in originals.items():assert path.read_bytes()==data
