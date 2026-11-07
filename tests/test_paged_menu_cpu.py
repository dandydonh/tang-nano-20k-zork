#!/usr/bin/env python3
"""Actual CPU: 1000-entry FAT32 pages, PS/2 four digits, indexed SAVE/RESTORE."""
from pathlib import Path
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from indexed_pool_helpers import sparse_card, pool_lba
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import dir_entry

with tempfile.TemporaryDirectory(prefix='zork-menu-cpu-') as directory:
    work = Path(directory)
    (work/'assets').mkdir()
    (work/'impl').mkdir()
    (work/'assets/firmware.hex').write_bytes((ROOT/'assets/firmware.hex').read_bytes())
    image = work/'card.img'
    first, middle, last = make_story(name='first'), make_story(name='middle', release=2), make_story(name='last', release=1000)
    layout = sparse_card(image, first+middle*998+last, positions=1, spc=8, directory_clusters=8)
    # Split the contiguous fixture payload into 1000 independently allocated
    # story files, with the save pool following the final directory entry.
    with image.open('r+b') as stream:
        for copy in range(2):
            stream.seek((layout['fat_lba']+copy*layout['fat_sectors'])*512)
            fat = bytearray(stream.read(layout['fat_sectors']*512))
            for index in range(1000):
                struct.pack_into('<I', fat, (layout['story_cluster']+index)*4, 0x0fffffff)
            stream.seek((layout['fat_lba']+copy*layout['fat_sectors'])*512)
            stream.write(fat)
        directory_bytes = dir_entry('.', 3, directory=True)+dir_entry('..', 0, directory=True)
        # Reverse copy order exercises the max-heap sort on real SDRAM.
        for index in range(999, -1, -1):
            directory_bytes += dir_entry(f'G{index:04}.Z3', layout['story_cluster']+index, 4096)
        directory_bytes += dir_entry('SAVES.BIN', layout['chain'][0], layout['size'])
        stream.seek(layout['directory_lba']*512)
        stream.write(directory_bytes+bytes(32768-len(directory_bytes)))
    subprocess.run(['fsck.fat', '-n', str(image)], check=True, capture_output=True)
    with image.open('rb') as stream:
        prefix = stream.read(16*1024*1024)
    (work/'impl/test-menu.hex').write_text(''.join(f'{value:02x}\n' for value in prefix))
    allowed = [pool_lba(layout, 2), pool_lba(layout, 65)]
    allowed += [pool_lba(layout, 128+index) for index in range(512)]
    assert max(allowed) < 32768
    (work/'impl/test-menu-save-sectors.hex').write_text(''.join(f'{value:08x}\n' for value in allowed))
    bench = (ROOT/'tests/soc_tb.v').read_text().split(' initial begin\n   $display')[0]
    bench = bench.replace('module soc_tb;', 'module paged_menu_soc_tb;')
    bench += '''
 initial begin
   repeat(20)@(negedge clk);reset=0;
   wait(menus==1);repeat(2000)@(negedge clk);uart_line("N");
   wait(menus==2);repeat(2000)@(negedge clk);uart_line("P");
   wait(menus==3);repeat(2000)@(negedge clk);
   send_key(8'h16);send_key(8'h45);send_key(8'h45);send_key(8'h45);send_key(8'h5a);
   wait(prompts==1);wait(status_updates==1);repeat(2000)@(negedge clk);
   if(card.writes!=0)$fatal(1,"menu/playing wrote the card");
   uart_line("n");wait(prompts==2);wait(status_updates==2);repeat(2000)@(negedge clk);
   uart_line("s");wait(prompts==3);wait(status_updates==3);repeat(2000)@(negedge clk);
   uart_line("r");wait(prompts==4);wait(status_updates==4);repeat(2000)@(negedge clk);
   uart_line("l");wait(prompts==5);wait(status_updates==5);repeat(2000)@(negedge clk);
   if(card.writes!=23)$fatal(1,"indexed owner/snapshot commit coverage %0d",card.writes);
   $display("\\nPASS paged menu CPU: 1000 stories, UART N/P, PS2 choice 1000, indexed save/restore, %0d cycles / %0d reads / %0d writes",cycles,card.reads,card.writes);
   $finish;
 end
endmodule
'''
    (work/'paged_menu_soc_tb.v').write_text(bench)
    verilator = os.environ.get('VERILATOR') or shutil.which('verilator') or '/tmp/zork-tools/usr/bin/verilator'
    env = dict(os.environ)
    if not shutil.which('verilator') and 'VERILATOR_ROOT' not in env:
        env['VERILATOR_ROOT'] = '/tmp/zork-tools/usr/share/verilator'
    sources = ['tests/sd_spi_model.v', 'tests/sdram_model.v', 'src/sdram_controller.v',
               'src/zork_soc.v', 'src/uart.v', 'src/ps2_receiver.v', 'src/input_fifo.v',
               'src/spi_byte.v', 'third_party/picorv32.v']
    with (ROOT/'impl/paged-menu-cpu-build.log').open('w') as log:
        subprocess.run([verilator, '--binary', '--timing', '-j', '2', '-Wno-fatal',
                        '-CFLAGS', '-O3', '--top-module', 'paged_menu_soc_tb',
                        '--Mdir', str(work/'obj'), str(work/'paged_menu_soc_tb.v'),
                        *[str(ROOT/source) for source in sources]], env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    log = ROOT/'impl/paged-menu-cpu.log'
    with log.open('w') as output:
        subprocess.run([work/'obj/Vpaged_menu_soc_tb', '+menu'], cwd=work,
                       stdout=output, stderr=subprocess.STDOUT, check=True, timeout=900)
    text = log.read_text()
    assert 'PASS paged menu CPU:' in text and 'CORE ERROR' not in text and 'memoryfailed' not in text
    assert text.count('Page 1/84 (stories 1-12 of 1000)') == 2
    assert 'Page 2/84 (stories 13-24 of 1000)' in text
    assert 'Starting G0999.Z3' in text and 'last ready' in text
    assert text.count('last moved') == 2 and text.count('saved\n') == 2
    print(next(line for line in text.splitlines() if line.startswith('PASS paged menu CPU:')))
