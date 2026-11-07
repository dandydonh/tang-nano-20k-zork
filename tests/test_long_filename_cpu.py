#!/usr/bin/env python3
"""Run real firmware with a VFAT menu stored in SDRAM, including reset."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from v3_fixture import make_story

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='zork-lfn-cpu-') as directory:
    work = Path(directory)
    (work/'assets').mkdir()
    (work/'impl').mkdir()
    (work/'assets/firmware.hex').write_bytes((ROOT/'assets/firmware.hex').read_bytes())
    image = work/'card.img'
    with image.open('wb') as stream:
        stream.truncate(16*1024*1024)
    subprocess.run(['mkfs.fat', '-F', '16', str(image)], check=True, capture_output=True)
    subprocess.run(['mmd', '-i', str(image), '::/ZORK'], check=True)
    longest = 'Adventure 00 '+('x'*239)+'.z3'
    assert len(longest) == 255
    for index in range(20, -1, -1):
        name = longest if index == 0 else f'Adventure {index:02}.z3'
        source = work/name
        source.write_bytes(make_story(name='alpha' if index == 0 else 'omega' if index == 19 else 'beta', release=900+index))
        subprocess.run(['mcopy', '-i', str(image), str(source), '::/ZORK/'], check=True)
    (work/'impl/test-menu.hex').write_text(''.join(f'{value:02x}\n' for value in image.read_bytes()))
    (work/'impl/test-menu-save-sectors.hex').write_text('ffffffff\n'*1024)
    bench = (ROOT/'tests/soc_tb.v').read_text().split(' initial begin\n   $display')[0]
    bench = bench.replace('module soc_tb;', 'module long_filename_soc_tb;')
    bench += '''
 initial begin
   repeat(20)@(negedge clk);reset=0;
   wait(menus==1);repeat(2000)@(negedge clk);uart_line("20");
   wait(prompts==1);wait(status_updates==1);repeat(2000)@(negedge clk);
   reset=1;repeat(20)@(negedge clk);reset=0;
   wait(menus==2);repeat(2000)@(negedge clk);uart_line("1");
   wait(prompts==2);wait(status_updates==2);repeat(2000)@(negedge clk);
   if(card.writes!=0)$fatal(1,"menu wrote to the card");
   $display("\\nPASS long filename CPU: SDRAM menu, pagination, selection and reset, %0d cycles",cycles);
   $finish;
 end
endmodule
'''
    (work/'long_filename_soc_tb.v').write_text(bench)
    verilator = os.environ.get('VERILATOR') or shutil.which('verilator') or '/tmp/zork-tools/usr/bin/verilator'
    env = dict(os.environ)
    if not shutil.which('verilator') and 'VERILATOR_ROOT' not in env:
        env['VERILATOR_ROOT'] = '/tmp/zork-tools/usr/share/verilator'
    sources = ['tests/sd_spi_model.v', 'tests/sdram_model.v', 'src/sdram_controller.v',
               'src/zork_soc.v', 'src/uart.v', 'src/ps2_receiver.v', 'src/input_fifo.v',
               'src/spi_byte.v', 'third_party/picorv32.v']
    with (ROOT/'impl/long-filename-cpu-build.log').open('w') as log:
        subprocess.run([verilator, '--binary', '--timing', '-j', '2', '-Wno-fatal',
                        '-CFLAGS', '-O3', '--top-module', 'long_filename_soc_tb',
                        '--Mdir', str(work/'obj'), str(work/'long_filename_soc_tb.v'),
                        *[str(ROOT/source) for source in sources]], env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    log = ROOT/'impl/long-filename-cpu.log'
    with log.open('w') as output:
        subprocess.run([work/'obj/Vlong_filename_soc_tb', '+menu'], cwd=work,
                       stdout=output, stderr=subprocess.STDOUT, check=True, timeout=600)
    text = log.read_text()
    clean = text.replace('\n', '').replace('\r', '')
    assert 'PASS long filename CPU:' in text and 'CORE ERROR' not in text
    assert 'more omitted' not in text
    assert text.count('Page 1/2') == 2
    assert 'Starting Adventure 19.z3' in clean and 'omega ready' in text
    assert 'Starting '+longest in clean and 'alpha ready' in text
    assert '~1.' not in text and '21. Adventure 20' not in text
    print(next(line for line in text.splitlines() if line.startswith('PASS long filename CPU:')))
