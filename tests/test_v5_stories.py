#!/usr/bin/env python3
"""Optional private V5 gameplay/save comparison, without embedding game bytes."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image,project_files

cases = (
    ('hitchhik', 'look\ni\nturn on light\nlook\ni\n',
     ('It is pitch black.', 'Bedroom, in the bed', 'a splitting headache', 'no tea')),
    ('beyondzo', 'begin\n\n\n\n\n\nlook\ni\nscore\n',
     ('Character Setup', 'Hilltop', "You\'re wearing a pack.", 'Level 0 Male Peasant')),
)
for name,commands,phrases in cases:
    path=ROOT/'inspect_files'/f'{name}.dat'
    if not path.is_file():
        print(f'SKIP optional V5 {name} (private file unavailable)')
        continue
    original=path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='zork-private-v5-') as directory:
        image=Path(directory)/'card.img'
        image.write_bytes(make_image(project_files(original,name.upper()+'.DAT'),16,8,False))
        def run(text):
            result=subprocess.run([ROOT/'impl/zork-host'],input=text,text=True,capture_output=True,
                                  env=dict(os.environ,ZORK_SD_IMAGE=str(image)),timeout=30)
            assert result.returncode==0 and 'CORE ERROR' not in result.stdout,(name,result.stdout)
            return result.stdout
        ours=run(commands+'save\nlook\nrestore\nlook\n')
        clean=' '.join(ours.split())
        for phrase in phrases:assert phrase in clean,(phrase,ours)
        assert ours.count('Okay.')>=2 or '[RESTORE completed.]' in ours or 'Restored' in ours,ours
        # Beyond Zork's initial restore prompt is answered before character setup.
        reset=run('restore\nlook\n')
        assert 'Bedroom' in reset if name=='hitchhik' else 'Hilltop' in reset,reset
        assert 'Failed.' not in ours and 'Failed.' not in reset
        assert path.read_bytes()==original
        logs=ROOT/'impl/inspect-validation'
        logs.mkdir(exist_ok=True)
        (logs/f'{name}-v5-play.txt').write_text(ours+'\nRESET:\n'+reset)
        ref=Path(os.environ.get('DFROTZ','/usr/games/dfrotz'))
        if ref.is_file():
            reference=subprocess.run([ref,'-q','-m','-p','-I','6','-w','79','-Z','3',str(path)],
                                     input=commands,text=True,capture_output=True,timeout=30)
            assert reference.returncode==0,(reference.stdout,reference.stderr)
            text=' '.join(reference.stdout.split())
            # Dumb Frotz omits upper window contents, so compare narrative.
            for phrase in phrases:
                if phrase not in ('Character Setup',"You're wearing a pack."):
                    assert phrase in text,(name,phrase,reference.stdout)
            (logs/f'{name}-v5-frotz.txt').write_text(reference.stdout+reference.stderr)
        print(f'PASS private V5 {name}: boot/gameplay, upper-window text, save/restore/reset, independent narrative comparison, unchanged original')
