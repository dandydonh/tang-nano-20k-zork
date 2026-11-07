#!/usr/bin/env python3
"""Exercise real UART size replies and a live resize on the actual processor."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story

ROOT=Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image,project_files
firmware=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'assets/firmware.hex'
intro=' '.join(['a lengthy paragraph must remain complete when the terminal does not wrap automatically']*36)
with tempfile.TemporaryDirectory(prefix='zork-dynamic-cpu-') as directory:
    work=Path(directory)
    (work/'assets').mkdir();(work/'impl').mkdir()
    (work/'assets/firmware.hex').write_bytes(firmware.read_bytes())
    layout=FatImage(make_image(project_files(make_story(size=16384,intro=intro,input_size=120)),16,16,False))
    sectors=layout.sectors('SAVES.BIN')[:512]
    (work/'impl/test-wrap-save-sectors.hex').write_text(''.join(f'{v:08x}\n' for v in sectors))
    (work/'impl/test-wrap.hex').write_text(''.join(f'{v:02x}\n' for v in layout.data[:16*1024*1024]))
    bench=(ROOT/'tests/soc_tb.v').read_text().split(' initial begin\n   $display')[0]
    bench=bench.replace('module soc_tb;', 'module terminal_soc_tb;')
    bench=bench.replace(' integer cycles=', ''' integer size_requests=0,size_responses=0,size_position=0;
 string size_query="\\033[6n";
 bit narrow=0;
 integer cycles=''')
    needle='       if(dut.wdata[7:0]==more_prompt[more_position])begin'
    bench=bench.replace(needle,'''       if(dut.wdata[7:0]==size_query[size_position])begin
         size_position=size_position+1;
         if(size_position==size_query.len())begin size_requests=size_requests+1;size_position=0;end
       end else size_position=dut.wdata[7:0]==size_query[0]?1:0;
'''+needle)
    bench+='''
 initial begin : reply_sizes
   string reply;
   forever begin
     wait(size_requests>size_responses);repeat(2000)@(negedge clk);
     reply=narrow?"\\033[18;100R":"\\033[35;149R";
     for(integer i=0;i<reply.len();i=i+1)send_uart(reply[i]);
     size_responses=size_responses+1;
   end
 end
 initial begin
   repeat(20)@(negedge clk);reset=0;
   wait(prompts==1);wait(status_updates==1);repeat(2000)@(negedge clk);
   if(more_requests!=0)$fatal(1,"35-row terminal paged too early");
   // Resize at the open prompt; the following command boundary detects it.
   narrow=1;uart_line("look");
   wait(prompts==2);wait(status_updates==2);repeat(2000)@(negedge clk);
   uart_line("look");wait(prompts==3);wait(status_updates==3);repeat(2000)@(negedge clk);
   if(size_responses<4)$fatal(1,"command-boundary probes missing");
   reset=1;repeat(20)@(negedge clk);reset=0;
   wait(prompts==4);wait(status_updates==4);repeat(2000)@(negedge clk);
   if(more_requests<2)$fatal(1,"18-row startup did not page");
   uart_line("look");wait(prompts==5);wait(status_updates==5);repeat(2000)@(negedge clk);
   $display("\\nPASS dynamic CPU: 149x35 to 100x18, %0d size replies, %0d page pauses",size_responses,more_requests);
   $finish;
 end
endmodule
'''
    (work/'terminal_soc_tb.v').write_text(bench)
    verilator=shutil.which('verilator') or '/tmp/zork-tools/usr/bin/verilator'
    env=dict(os.environ)
    if not shutil.which('verilator'):env['VERILATOR_ROOT']='/tmp/zork-tools/usr/share/verilator'
    sources=['tests/sd_spi_model.v','tests/sdram_model.v','src/sdram_controller.v','src/zork_soc.v','src/uart.v','src/ps2_receiver.v','src/input_fifo.v','src/spi_byte.v','third_party/picorv32.v']
    with (ROOT/'impl/dynamic-cpu-build.log').open('w') as log:
        subprocess.run([verilator,'--binary','--timing','-j','2','-Wno-fatal','-CFLAGS','-O3','--top-module','terminal_soc_tb','--Mdir',str(work/'obj'),str(work/'terminal_soc_tb.v'),*[str(ROOT/s) for s in sources]],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    log=ROOT/'impl/dynamic-cpu.log'
    with log.open('w') as output:
        subprocess.run([work/'obj/Vterminal_soc_tb','+wrap'],cwd=work,stdout=output,stderr=subprocess.STDOUT,check=True,timeout=900)
    data=log.read_bytes().decode()
    assert 'PASS dynamic CPU:' in data and 'CORE ERROR' not in data,data[-1000:]
    init='\x1b[0m\x1b[37;49m\x1b[2J\x1b[2;r\x1b[2;1H'
    boots=data.split(init)[1:];assert len(boots)==2
    for boot,width in zip(boots,(149,100)):
        clean=re.sub(r'\x1b7.*?\x1b8','',boot,flags=re.S)
        clean=re.sub(r'\x1b\[0m\[MORE\]\x08{6}(?:(?:\x1b\[[07]m)?.){6}\x08{6}','',clean)
        assert intro in ' '.join(clean.split()),'intro text lost or size reply leaked into narrative'
        lines=clean[:clean.index('>')].split('\r\n')
        assert max(map(len,lines))<=width-1
        assert max(map(len,lines))>width-12
    assert data.count('alpha home')==3,'commands corrupted by size replies'
print('PASS actual CPU dynamic terminal: 149x35, live resize to 100x18, full intro at both widths, command probes, paging, reset and independent HDMI margin')
