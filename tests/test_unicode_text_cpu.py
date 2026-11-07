#!/usr/bin/env python3
"""Actual CPU: custom V5 Unicode keys/text/streams and saved parser state."""
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from fat_helpers import FatImage
from sd_image_fixture import make_image, POOL_SIZE
from unicode_fixture import Program, CUSTOM

ROOT = Path(__file__).resolve().parents[1]
p = Program(table=CUSTOM)
p.data = p.data[:16384]
struct.pack_into('>H', p.data, 26, len(p.data) // 4)
p.text('unicode vfive ').op('ext', 11, 0x754c).nl().char(62)
p.op('var', 22, 1, result=20).op('two', 1, ('v', 20), ord('r')).branch('restore')
p.text('character ').number(('v', 20)).nl().char(62).read().values(0x701, 4)
p.op('var', 19, 3, 0xb00).op('ext', 11, 0x100).op('ext', 11, 0xe9).char(155)
p.op('var', 19, -3).values(0xb00, 1, word=True).values(0xb02, 3)
p.op('ext', 0, result=20).op('two', 1, ('v', 20), 2).branch('resumed')
p.text('saved').nl().char(62).op('var', 22, 1, result=20).jump('done')
p.label('restore').op('ext', 1, result=20).text('restore failed').jump('done')
p.label('resumed').text('restored unicode ').char(155).nl().values(0x701, 4)
p.char(62).op('var', 22, 1, result=20).label('done')

with tempfile.TemporaryDirectory(prefix='zork-unicode-v5-cpu-') as directory:
    work = Path(directory)
    (work / 'assets').mkdir()
    (work / 'impl').mkdir()
    shutil.copy2(ROOT / 'assets/firmware.hex', work / 'assets/firmware.hex')
    original = make_image([('UNICODE.Z5', p.story()), ('SAVES.BIN', bytes(POOL_SIZE))], 16, 8, False)
    forbidden = FatImage(original).sectors('SAVES.BIN')
    image, trace = work / 'card.img', work / 'writes.log'
    image.write_bytes(original)
    ps2_unicode=bool(os.environ.get('ZORK_TEST_PS2_UNICODE'))
    env=dict(os.environ,ZORK_SD_IMAGE=str(image),ZORK_WRITE_LOG=str(trace))
    commands='ĀĀΩ界\n5\nq'
    if ps2_unicode:
        from ps2_fixture import hex_entry,text as ps2_text
        keys=work/'keys.bin';keys.write_bytes(hex_entry('0100')+hex_entry('0100')+hex_entry('03a9')+hex_entry('754c')+ps2_text('\n'))
        env['ZORK_PS2_SCANS']=str(keys);commands='5\nq'
    native = subprocess.run([ROOT / 'impl/zork-host'], input=commands, text=True,
                            capture_output=True, check=True,
                            env=env)
    assert 'character 155' in native.stdout and 'saved\n' in native.stdout, native.stdout
    writes = list(map(int, trace.read_text().splitlines()))
    sectors = sorted(set(writes))
    assert len(writes) < 100 and max(sectors) < 32768
    (work / 'impl/test-wrap.hex').write_text(''.join(f'{c:02x}\n' for c in original.ljust(16*1024*1024, b'\0')))
    (work / 'impl/test-wrap-save-sectors.hex').write_text(''.join(f'{s:08x}\n' for s in sectors))
    bench = (ROOT / 'tests/soc_tb.v').read_text().split(' initial begin\n   $display')[0]
    bench = bench.replace('module soc_tb;', 'module unicode_text_soc_tb;')
    bench += '''
 initial begin
   repeat(20)@(negedge clk);reset=0;
   wait(prompts==1);repeat(2000)@(negedge clk);
   READ_CHAR_INPUT
   wait(prompts==2);repeat(2000)@(negedge clk);
   LINE_INPUT
   wait(slot_menus==1);repeat(2000)@(negedge clk);uart_line("5");
   wait(prompts==3);repeat(2000)@(negedge clk);
   if(card.writes!=EXPECTED_WRITES)$fatal(1,"Unicode save commit coverage %0d",card.writes);
   reset=1;repeat(20)@(negedge clk);reset=0;
   wait(prompts==4);repeat(2000)@(negedge clk);send_uart("r");
   wait(slot_menus==2);repeat(2000)@(negedge clk);uart_line("5");
   wait(prompts==5);repeat(2000)@(negedge clk);
   if(card.writes!=EXPECTED_WRITES)$fatal(1,"Unicode restore wrote data");
   $display("\\nPASS Unicode V5 CPU: custom read_char/AREAD, UTF-8, memory stream, save/reset/restore, %0d cycles / %0d reads / %0d writes",cycles,card.reads,card.writes);
   $finish;
 end
endmodule
'''.replace('EXPECTED_WRITES', str(len(writes)))
    if ps2_unicode:
        def send(scans):return ''.join(f"send_key(8'h{c:02x});" for c in scans)
        char_input=send(hex_entry('0100'))
        line_input=send(hex_entry('0100')+hex_entry('03a9')+hex_entry('754c')+ps2_text('\n'))
        bench=bench.replace('send_uart("r");',send(ps2_text('r')))
        # AREAD probes UART size after displaying its prompt. Let the existing
        # bounded probe finish before injecting a burst of raw PS/2 frames into
        # the 16-byte hardware FIFO (a human enters these keys much more slowly).
        bench=bench.replace('wait(prompts==2);repeat(2000)', 'wait(prompts==2);repeat(10000000)')
    else:
        char_input="send_uart(8'hc4);send_uart(8'h80);"
        line_input="send_uart(8'hc4);send_uart(8'h80);send_uart(8'hce);send_uart(8'ha9);send_uart(8'he7);send_uart(8'h95);send_uart(8'h8c);send_uart(13);"
    bench=bench.replace('READ_CHAR_INPUT',char_input).replace('LINE_INPUT',line_input)
    (work / 'unicode_text_soc_tb.v').write_text(bench)
    verilator = os.environ.get('VERILATOR') or shutil.which('verilator') or '/tmp/zork-tools/usr/bin/verilator'
    sources = ['tests/sd_spi_model.v', 'tests/sdram_model.v', 'src/sdram_controller.v',
               'src/zork_soc.v', 'src/uart.v', 'src/ps2_receiver.v', 'src/input_fifo.v',
               'src/spi_byte.v', 'third_party/picorv32.v']
    with (ROOT / 'impl/unicode-text-v5-cpu-build.log').open('w') as log:
        subprocess.run([verilator, '--binary', '--timing', '-j', '2', '-Wno-fatal', '-CFLAGS', '-O3',
                        '--top-module', 'unicode_text_soc_tb', '--Mdir', str(work / 'obj'),
                        str(work / 'unicode_text_soc_tb.v'), *[str(ROOT / s) for s in sources]],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    log = ROOT / 'impl/unicode-text-v5-cpu.log'
    with log.open('w') as output:
        subprocess.run([work / 'obj/Vunicode_text_soc_tb', '+wrap', '+autosave',
                        f'+forbidden_first={min(forbidden)}', f'+forbidden_last={max(forbidden)}'],
                       cwd=work, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=1800)
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', log.read_text())
    assert 'PASS Unicode V5 CPU:' in text and 'CORE ERROR' not in text and 'restore failed' not in text
    assert text.count('unicode vfive 界') == 2 and 'character 155' in text, text
    assert text.count('values 3 156 158 159 ') == 2 and 'restored unicode Ā' in text, text
    assert 'values 3 ' in text and 'values 155 63 155 ' in text, text
    print(next(line for line in text.splitlines() if line.startswith('PASS Unicode V5 CPU:')))
    if ps2_unicode:
        print('PASS actual PS/2 V5 CPU: hex U+0100 read_char, Greek/CJK AREAD, ASCII after reset and saved Unicode parser bytes')
