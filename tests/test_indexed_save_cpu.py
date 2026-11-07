#!/usr/bin/env python3
"""Actual CPU: default GiB indexed pool, ownership commit and reset restore."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from indexed_pool_helpers import sparse_card, pool_lba
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='zork-index-cpu-') as directory:
    work = Path(directory)
    (work/'assets').mkdir()
    (work/'impl').mkdir()
    (work/'assets/firmware.hex').write_bytes((ROOT/'assets/firmware.hex').read_bytes())
    image = work/'card.img'
    layout = sparse_card(image, make_story())
    # FAT + metadata + selected owner's five positions fit in the SPI model's
    # 16 MiB backing even though the advertised pool is 1.22 GiB.
    with image.open('rb') as stream:
        prefix = stream.read(16*1024*1024)
    (work/'impl/test-wrap.hex').write_text(''.join(f'{value:02x}\n' for value in prefix))
    start = 128+4*512
    sectors = [pool_lba(layout, 2), pool_lba(layout, 2+63)]
    sectors += [pool_lba(layout, start+i) for i in range(512)]
    assert max(sectors) < 32768
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
   if(card.writes!=23)$fatal(1,"owner/snapshot commit coverage %0d",card.writes);
   reset=1;repeat(20)@(negedge clk);reset=0;
   wait(prompts==4);wait(status_updates==4);repeat(2000)@(negedge clk);
   uart_line("r");wait(slot_menus==2);repeat(2000)@(negedge clk);uart_line("5");
   wait(prompts==5);wait(status_updates==5);repeat(2000)@(negedge clk);
   uart_line("l");wait(prompts==6);wait(status_updates==6);repeat(2000)@(negedge clk);
   if(card.writes!=23)$fatal(1,"restore wrote metadata/data");
   $display("\\nPASS indexed save CPU: 1000x5 pool, deferred owner claim, fifth-position save/reset/restore, %0d cycles / %0d reads / %0d writes",cycles,card.reads,card.writes);
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
        subprocess.run([work/'obj/Vindexed_save_soc_tb', '+wrap'], cwd=work,
                       stdout=output, stderr=subprocess.STDOUT, check=True, timeout=900)
    text = log.read_text()
    assert 'PASS indexed save CPU:' in text and 'CORE ERROR' not in text
    assert text.count('alpha moved') == 2 and text.count('saved\n') == 2, text
    print(next(line for line in text.splitlines() if line.startswith('PASS indexed save CPU:')))
