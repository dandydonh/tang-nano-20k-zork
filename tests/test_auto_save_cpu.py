#!/usr/bin/env python3
"""Actual CPU: first SAVE allocates FAT file; cancel and reset/restore checks."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import sys
from sd_image_fixture import make_image
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='zork-auto-cpu-') as directory:
    work = Path(directory)
    (work/'assets').mkdir()
    (work/'impl').mkdir()
    (work/'assets/firmware.hex').write_bytes((ROOT/'assets/firmware.hex').read_bytes())
    image = work/'card.img'
    original=make_image([('ALPHA.Z3',make_story())],16,8,False)
    image.write_bytes(original)
    trace=work/'writes.log'
    env=dict(os.environ,ZORK_SD_IMAGE=str(image),ZORK_WRITE_LOG=str(trace))
    result=subprocess.run([ROOT/'impl/zork-host'],input='n\ns\n5\nq\n',text=True,capture_output=True,env=env,check=True)
    assert 'saved' in result.stdout
    writes=list(map(int,trace.read_text().splitlines()))
    assert len(writes)<100, "first SAVE regressed to whole-file initialization"
    sectors=sorted(set(writes))
    assert len(sectors)<=4096 and max(sectors)<32768
    (work/'impl/test-wrap.hex').write_text(''.join(f'{value:02x}\n' for value in original.ljust(16*1024*1024,b'\0')))
    (work/'impl/test-wrap-save-sectors.hex').write_text(''.join(f'{value:08x}\n' for value in sectors))
    bench = (ROOT/'tests/soc_tb.v').read_text().split(' initial begin\n   $display')[0]
    bench = bench.replace('module soc_tb;', 'module auto_save_soc_tb;')
    bench = bench.replace("cycles==1000000000", "cycles==2000000000")
    bench += '''
 initial begin
   repeat(20)@(negedge clk);reset=0;
   wait(prompts==1);wait(status_updates==1);repeat(2000)@(negedge clk);
   if(card.writes!=0)$fatal(1,"playing claimed an owner");
   uart_line("s");wait(slot_menus==1);repeat(2000)@(negedge clk);uart_line("0");
   wait(prompts==2);wait(status_updates==2);repeat(2000)@(negedge clk);
   if(card.writes!=0)$fatal(1,"cancel allocated a sidecar");
   uart_line("n");wait(prompts==3);wait(status_updates==3);repeat(2000)@(negedge clk);
   uart_line("s");wait(slot_menus==2);repeat(2000)@(negedge clk);uart_line("5");
   wait(prompts==4);wait(status_updates==4);repeat(2000)@(negedge clk);
   if(card.writes!=23)$fatal(1,"owner/snapshot commit coverage %0d",card.writes);
   reset=1;repeat(20)@(negedge clk);reset=0;
   wait(prompts==5);wait(status_updates==5);repeat(2000)@(negedge clk);
   uart_line("r");wait(slot_menus==3);repeat(2000)@(negedge clk);uart_line("5");
   wait(prompts==6);wait(status_updates==6);repeat(2000)@(negedge clk);
   uart_line("l");wait(prompts==7);wait(status_updates==7);repeat(2000)@(negedge clk);
   if(card.writes!=23)$fatal(1,"restore wrote metadata/data");
   $display("\\nPASS automatic save CPU: new FAT16 sidecar, lazy creation, fifth-position save/reset/restore, %0d cycles / %0d reads / %0d writes",cycles,card.reads,card.writes);
   $finish;
 end
endmodule
'''
    bench=bench.replace("card.writes!=23",f"card.writes!={len(writes)}")
    (work/'auto_save_soc_tb.v').write_text(bench)
    verilator = os.environ.get('VERILATOR') or shutil.which('verilator') or '/tmp/zork-tools/usr/bin/verilator'
    env = dict(os.environ)
    if not shutil.which('verilator') and 'VERILATOR_ROOT' not in env:
        env['VERILATOR_ROOT'] = '/tmp/zork-tools/usr/share/verilator'
    sources = ['tests/sd_spi_model.v', 'tests/sdram_model.v', 'src/sdram_controller.v',
               'src/zork_soc.v', 'src/uart.v', 'src/ps2_receiver.v', 'src/input_fifo.v',
               'src/spi_byte.v', 'third_party/picorv32.v']
    with (ROOT/'impl/auto-save-cpu-build.log').open('w') as log:
        subprocess.run([verilator, '--binary', '--timing', '-j', '2', '-Wno-fatal',
                        '-CFLAGS', '-O3', '--top-module', 'auto_save_soc_tb',
                        '--Mdir', str(work/'obj'), str(work/'auto_save_soc_tb.v'),
                        *[str(ROOT/source) for source in sources]], env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    log = ROOT/'impl/auto-save-cpu.log'
    with log.open('w') as output:
        subprocess.run([work/'obj/Vauto_save_soc_tb', '+wrap', '+autosave'], cwd=work,
                       stdout=output, stderr=subprocess.STDOUT, check=True, timeout=1800)
    text = log.read_text()
    assert 'PASS automatic save CPU:' in text and 'CORE ERROR' not in text
    assert text.count('alpha moved') == 2 and text.count('saved\n') == 2, text
    print(next(line for line in text.splitlines() if line.startswith('PASS automatic save CPU:')))
