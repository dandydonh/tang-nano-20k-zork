#!/usr/bin/env python3
"""Run the actual CPU with an original long-output story and real UART paging."""
from pathlib import Path
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from make_sd import make_image,project_files
firmware=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'assets/firmware.hex'
with tempfile.TemporaryDirectory(prefix='zork-paging-cpu-') as directory:
    work=Path(directory)
    (work/'assets').mkdir()
    (work/'impl').mkdir()
    (work/'assets/firmware.hex').write_bytes(firmware.read_bytes())
    intro=' '.join(['a lengthy paragraph must remain complete when the terminal does not wrap automatically']*12)
    layout=FatImage(make_image(project_files(make_story(intro=intro,input_size=120,stream_check=True)),16,16,False))
    layout.fragment('ZORK1.DAT',11000,stride=2)
    layout.fragment('SAVES.BIN',12000,stride=2)
    sectors=layout.sectors('SAVES.BIN')[:512]
    assert max(sectors)<32768
    (work/'impl/test-wrap-save-sectors.hex').write_text(''.join(f'{v:08x}\n' for v in sectors))
    (work/'impl/test-wrap.hex').write_text(''.join(f'{v:02x}\n' for v in layout.data[:16*1024*1024]))
    log=ROOT/'impl/paging-cpu.log'
    with log.open('w') as output:
        subprocess.run([ROOT/'impl/verilator-soc/Vsoc_tb','+wrap'],cwd=work,stdout=output,stderr=subprocess.STDOUT,check=True,timeout=900)
    data=log.read_text()
    assert data.count('[MORE]')>=2, 'paging must occur on both startup and reset'
    subprocess.run([sys.executable,ROOT/'tests/test_output.py','--cpu-log',log],cwd=ROOT,check=True)
print('PASS actual CPU paging: long introduction, UART acknowledgement, wrapped input editing, saves and reset with retained card')
