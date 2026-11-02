#!/usr/bin/env python3
import os
from pathlib import Path
import struct
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
def run(image,commands):
    env=dict(os.environ,ZORK_SD_IMAGE=str(image))
    p=subprocess.run([root/'impl/zork-host'],input=commands,text=True,capture_output=True,env=env,check=True)
    assert 'CORE ERROR' not in p.stdout,p.stdout
    return p.stdout
with tempfile.TemporaryDirectory(prefix='zork-test-') as d:
    image=Path(d)/'card.img'
    subprocess.run(['python3',root/'scripts/make_sd.py','--output',image],check=True,capture_output=True)
    # Recall submits only on Enter; Down restores a draft. CSI parameters and
    # unsupported navigation keys must never leak into the game's parser.
    history=run(image,'look\n\x1b[A\n\x1bOA\nopen mailbox\x1b[A\x1b[B\n'
                'lookx\x7f\x1b[C\x1b[D\x1b[3~\n\x1b[1;5A\n')
    assert history.count('West of House')==6,history
    assert 'Opening the small mailbox reveals a leaflet.' in history,history
    assert "I don't know the word" not in history and 'beg your pardon' not in history,history
    assert '\x1b' not in history,history
    boot=run(image,'look\nopen mailbox\nread leaflet\ninventory\nxyzzyxyz\nsave\n')
    assert 'West of House' in boot
    assert 'Opening the small mailbox reveals a leaflet.' in boot
    assert 'A leaflet' in boot and "I don't know the word" in boot
    original=image.read_bytes()
    # New process models power cycling: restore inventory, room and parser state.
    restored=run(image,'restore\ninventory\nnorth\nsave\n')
    assert 'A leaflet' in restored and 'North of House' in restored
    assert restored.count('Ok.')==2,restored
    second=image.read_bytes()
    assert second[:256*512]==original[:256*512], 'story modified by SAVE'
    assert second[384*512:]==original[384*512:], 'write outside save banks'
    assert b'ZMV3' in second[256*512:256*512+4]
    assert b'ZMV3' in second[320*512:320*512+4]
    # Corrupt newest bank payload: restore must fall back to the previous snapshot.
    bad=bytearray(second);bad[321*512+123]^=128;image.write_bytes(bad)
    recovered=run(image,'restore\nlook\ninventory\n')
    assert recovered.count('West of House')==2 and 'A leaflet' in recovered,recovered
    # Corrupt both snapshots: report failure while preserving live game state.
    bad[257*512+123]^=128;image.write_bytes(bad)
    failed=run(image,'north\nrestore\nlook\n')
    assert 'Failed.' in failed and failed.count('North of House')==2,failed
    image.write_bytes(bytes(bad[:256*512])+bytes(128*512)+bytes(bad[384*512:]))
    commands='n\ne\nopen window\nenter window\nw\ntake lamp\ntake sword\nmove rug\nopen trapdoor\nturn on lamp\ndown\nlook\ninventory\nup\ne\nopen sack\ntake lunch\ntake bottle\nscore\n$verify\nquit\ny\n'
    walk=run(image,commands)
    for expected in ['Kitchen','Living Room','Cellar','A brass lantern','A sword','Your score is']:
        assert expected in walk,(expected,walk)
    (root/'impl/host-walkthrough.txt').write_text(walk)
    (root/'impl/host-transcript.txt').write_text(boot+restored+recovered+failed)
    # Optional independent interpreter comparison for deterministic initial moves.
    ref=os.environ.get('DFROTZ','/tmp/zork-tools/usr/games/dfrotz')
    if Path(ref).exists():
        short='look\nopen mailbox\nread leaflet\ninventory\nn\ne\nopen window\nenter window\nw\ntake lamp\ntake sword\n'
        ours=run(image,short)
        theirs=subprocess.run([ref,'-q','-m','-p','-w','200','-Z','3',str(root/'zork1.dat')],input=short,text=True,capture_output=True).stdout
        for phrase in ['West of House','Opening the small mailbox reveals a leaflet.', 'WELCOME TO ZORK!', 'You are carrying:', 'North of House', 'Behind House', 'Kitchen', 'Living Room']:
            assert phrase in ours and phrase in theirs,phrase
        (root/'impl/frotz-reference.txt').write_text(theirs)
print('PASS command history/escape keys, story gameplay, independent Frotz comparison, power-cycle restore, alternating saves, corruption fallback, write bounds')
