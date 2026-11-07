#!/usr/bin/env python3
"""Actual CPU: indexed sidecar with ignored shared pool and reset restore."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from sd_image_fixture import make_image, project_files, POOL_SIZE
from fat_helpers import FatImage
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='zork-index-cpu-') as directory:
    work = Path(directory)
    (work/'assets').mkdir()
    (work/'impl').mkdir()
    (work/'assets/firmware.hex').write_bytes((ROOT/'assets/firmware.hex').read_bytes())
    image = work/'card.img'
    layout=FatImage(make_image(project_files(make_story(),'ALPHA.Z3')+[('SAVES.BIN',bytes(POOL_SIZE))],16,8,False))
    (work/'impl/test-wrap.hex').write_text(''.join(f'{value:02x}\n' for value in layout.data.ljust(16*1024*1024,b'\0')))
    sectors=layout.sectors('ALPHA.SAV')[4+4*512:4+5*512]
    forbidden=layout.sectors('SAVES.BIN')
    (work/'impl/test-wrap-save-sectors.hex').write_text(''.join(f'{value:08x}\n' for value in sectors))
    bench = (ROOT/'tests/soc_tb.v').read_text().split(' initial begin\n   $display')[0]
    bench = bench.replace('module soc_tb;', 'module indexed_save_soc_tb;')
    bench += '''
 initial begin
   repeat(20)@(negedge clk);reset=0;
   wait(prompts==1);wait(status_updates==1);repeat(2000)@(negedge clk);
   if(card.writes!=0)$fatal(1,"playing claimed an owner");
   uart_line("n");wait(prompts==2);wait(status_updates==2);repeat(2000)@(negedge clk);
   uart_line("s");wait(slot_menus==1);repeat(2000)@(negedge clk);uart_line("5");
   wait(prompts==3);wait(status_updates==3);repeat(2000)@(negedge clk);
   if(card.writes!=21)$fatal(1,"owner/snapshot commit coverage %0d",card.writes);
   reset=1;repeat(20)@(negedge clk);reset=0;
   wait(prompts==4);wait(status_updates==4);repeat(2000)@(negedge clk);
   uart_line("r");wait(slot_menus==2);repeat(2000)@(negedge clk);uart_line("5");
   wait(prompts==5);wait(status_updates==5);repeat(2000)@(negedge clk);
   uart_line("l");wait(prompts==6);wait(status_updates==6);repeat(2000)@(negedge clk);
   if(card.writes!=21)$fatal(1,"restore wrote metadata/data");
   $display("\\nPASS indexed save CPU: existing indexed sidecar, ignored SAVES.BIN, fifth-position save/reset/restore, %0d cycles / %0d reads / %0d writes",cycles,card.reads,card.writes);
   $finish;
 end
endmodule
'''
    (work/'indexed_save_soc_tb.v').write_text(bench)
    verilator = os.environ.get('VERILATOR') or shutil.which('verilator') or '/tmp/zork-tools/usr/bin/verilator'
    env = dict(os.environ)
    if not shutil.which('verilator') and 'VERILATOR_ROOT' not in env:
        env['VERILATOR_ROOT'] = '/tmp/zork-tools/usr/share/verilator'
    sources = ['tests/sd_spi_model.v', 'tests/sdram_model.v', 'src/sdram_controller.v',
               'src/zork_soc.v', 'src/uart.v', 'src/ps2_receiver.v', 'src/input_fifo.v',
               'src/spi_byte.v', 'third_party/picorv32.v']
    with (ROOT/'impl/indexed-save-cpu-build.log').open('w') as log:
        subprocess.run([verilator, '--binary', '--timing', '-j', '2', '-Wno-fatal',
                        '-CFLAGS', '-O3', '--top-module', 'indexed_save_soc_tb',
                        '--Mdir', str(work/'obj'), str(work/'indexed_save_soc_tb.v'),
                        *[str(ROOT/source) for source in sources]], env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    log = ROOT/'impl/indexed-save-cpu.log'
    with log.open('w') as output:
        subprocess.run([work/'obj/Vindexed_save_soc_tb', '+wrap','+manualslots',f'+forbidden_first={min(forbidden)}',f'+forbidden_last={max(forbidden)}'], cwd=work,
                       stdout=output, stderr=subprocess.STDOUT, check=True, timeout=900)
    text = log.read_text()
    assert 'PASS indexed save CPU:' in text and 'CORE ERROR' not in text
    assert text.count('alpha moved') == 2 and text.count('saved\n') == 2, text
    print(next(line for line in text.splitlines() if line.startswith('PASS indexed save CPU:')))
