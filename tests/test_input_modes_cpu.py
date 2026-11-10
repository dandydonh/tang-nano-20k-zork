#!/usr/bin/env python3
"""Actual CPU: S1 selection plus UART/physical PS2/Companion input and reset.

The selector and SoC run together with top-equivalent input gating. Separate
mode_routing_tb checks the actual top connections; no BL616 USB engine is modeled.
All card data lives in an isolated simulation directory.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from sd_image_fixture import make_image
from unicode_fixture import Program

ROOT = Path(__file__).resolve().parents[1]
work = ROOT / 'impl/input-modes-cpu'
(work / 'assets').mkdir(parents=True, exist_ok=True)
(work / 'impl').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'assets/firmware.hex', work / 'assets/firmware.hex')
p = Program()
p.data = p.data[:16384]
struct.pack_into('>H', p.data, 26, len(p.data) // 4)
for _ in range(4):
    p.char(62).op('var', 22, 1, result=20).text(' key ').number(('v', 20)).nl()
p.text('done').char(62)
# Fourteen entries force a paged menu at the fallback 18-row terminal size.
# Verify the diagnostic label survives the menu's console_clear on each boot.
original = make_image([(f'INPUT{i:02}.Z5', p.story()) for i in range(14)], 16, 8, False)
(work / 'impl/test-wrap.hex').write_text(''.join(f'{c:02x}\n' for c in original.ljust(16*1024*1024, b'\0')))
(work / 'impl/test-wrap-save-sectors.hex').write_text('ffffffff\n' * 4096)
bench = (ROOT / 'tests/soc_tb.v').read_text().split(' initial begin\n   $display')[0]
bench = bench.replace('module soc_tb;', 'module input_modes_soc_tb;')
bench = bench.replace(' wire tx,sck,mosi,cs,miso,trap,tw;', '''
 reg mode_button=0;
 wire transport_reset,startup_reset,serial_enabled,serial_selected,selection_done,host_active;
 startup_mode #(.WINDOW_CYCLES(2000),.DEBOUNCE_CYCLES(4),.BLINK_CYCLES(100)) selector(
   .clk(clk),.button(mode_button),.companion_active(host_active),
   .transport_reset(transport_reset),.game_reset(startup_reset),
   .serial_enabled(serial_enabled),.serial_selected(serial_selected),.selection_done(selection_done));
 wire soc_reset=reset||startup_reset;
 wire tx,sck,mosi,cs,miso,trap,tw;''')
bench = bench.replace('companion_keyboard usb_keyboard(.clk(clk),.reset(reset)',
                      'companion_keyboard usb_keyboard(.clk(clk),.reset(transport_reset)')
bench = bench.replace('.key_data(usb_data),.key_strobe(usb_strobe)',
                      '.host_active(host_active),.key_data(usb_data),.key_strobe(usb_strobe)')
bench = bench.replace('zork_soc dut(.clk(clk),.reset(reset),.uart_rx(rx)',
                      "zork_soc dut(.clk(clk),.reset(soc_reset),.uart_rx(serial_enabled?rx:1'b1)")
bench = bench.replace('.usb_key_data(usb_data),.usb_key_strobe(usb_strobe)',
                      '.usb_key_data(usb_data),.usb_key_strobe(usb_strobe&&selection_done&&!serial_selected)')
bench = bench.replace(".input_mode_status(4'b0001)",
                      ".input_mode_status({1'b0,host_active,serial_selected,1'b1})")
bench = bench.replace('.clk(sdram_clk),.reset(reset)', '.clk(sdram_clk),.reset(soc_reset)')
bench += '''
 integer handled_menus=0;
 initial forever begin
   wait(menus>handled_menus);repeat(100000)@(negedge clk);
   if(text[0]!=(8'h80|"I")||text[7]!=(8'h80|(serial_selected?"s":"U")))
     $fatal(1,"latched input label lost at paged menu redraw");
   if(serial_selected)begin send_uart("1");send_uart(13);end
   else begin
     send_ps2(8'h16);send_ps2(8'hf0);send_ps2(8'h16);
     send_ps2(8'h5a);send_ps2(8'hf0);send_ps2(8'h5a);
   end
   handled_menus=handled_menus+1;
 end
 integer round,base;
 initial begin
   repeat(30)@(negedge clk);
   if($test$plusargs("serial_mode"))begin
     mode_button=1;repeat(50)@(negedge clk);mode_button=0;
   end
   wait(selection_done);repeat(20)@(negedge clk);reset=0;
   for(round=0;round<2;round=round+1)begin
     base=round*5;
     wait(prompts==base+1);repeat(2000)@(negedge clk);
     if(serial_selected)begin
       // Physically inject unwanted USB packets: input gating must discard
       // them. Mask host detection in this scenario only, modeling a PC-mode
       // Partner with no Companion while exercising the USB FIFO gate.
       force host_active=0;
       send_key(8'h1a);send_uart(8'hc3);send_uart(8'ha9);
     end else begin
       send_uart("z"); // BL616 debug input must be ignored.
       send_ps2(8'he0);send_key(8'h1c);
     end
     wait(prompts==base+2);repeat(2000)@(negedge clk);
     if(serial_selected)send_ps2(8'h1c);else send_ps2(8'h75);
     wait(prompts==base+3);repeat(2000)@(negedge clk);
     if(serial_selected)send_uart("b");
     else begin send_ps2(8'h12);send_key(8'h32);end
     wait(prompts==base+4);repeat(2000)@(negedge clk);
     if(serial_selected)send_ps2(8'h12);
     send_ps2(8'h21); // C: USB keyboard must not share physical Shift state.
     wait(prompts==base+5);repeat(2000)@(negedge clk);
     if(card.writes!=0)$fatal(1,"unexpected card write");
     if(round==0)begin
       mode_button=1;repeat(20)@(negedge clk);mode_button=0;
       wait(!soc_reset);repeat(20)@(negedge clk);
       if(serial_selected!=$test$plusargs("serial_mode"))$fatal(1,"mode lost across S1 reset");
     end
   end
   $display("\\nPASS S1 input-mode actual CPU: two boots, retained selection, isolated inputs, physical PS2 and no card writes; %0d cycles",cycles);
   $finish;
 end
endmodule
'''
(work / 'input_modes_soc_tb.v').write_text(bench)
verilator = os.environ.get('VERILATOR') or shutil.which('verilator') or '/tmp/zork-tools/usr/bin/verilator'
sources = ['tests/sd_spi_model.v', 'tests/sdram_model.v', 'src/sdram_controller.v',
           'src/zork_soc.v', 'src/uart.v', 'src/ps2_receiver.v', 'src/input_fifo.v',
           'src/spi_byte.v', 'src/startup_mode.v', 'src/companion_keyboard.v',
           'third_party/picorv32.v']
with (work / 'build.log').open('w') as log:
    subprocess.run([verilator, '--binary', '--timing', '-j', '2', '-Wno-fatal',
                    '-CFLAGS', '-O3', '-DZORK_USB_HOST', '--top-module', 'input_modes_soc_tb',
                    '--Mdir', str(work / 'obj'), str(work / 'input_modes_soc_tb.v'),
                    *[str(ROOT / s) for s in sources]], stdout=log, stderr=subprocess.STDOUT,
                   check=True, timeout=300)
for name, args, expected in [('usb', [], [97, 129, 98, 67]),
                              ('serial', ['+serial_mode'], [170, 97, 98, 67])]:
    log_path = work / f'{name}.log'
    with log_path.open('w') as log:
        subprocess.run([work / 'obj/Vinput_modes_soc_tb', '+wrap', *args], cwd=work,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    output = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', log_path.read_text())
    actual = list(map(int, re.findall(r' key (\d+)', output)))
    assert actual == expected * 2, (name, actual, output)
    assert 'PASS S1 input-mode actual CPU:' in output and 'CORE ERROR' not in output
    label = 'serial terminal' if name == 'serial' else 'USB keyboard'
    assert output.count(f'Input: {label} + PS/2') == 2, output
    print(name + ': ' + next(line for line in output.splitlines() if line.startswith('PASS S1')))
(work / 'SOURCE_SHA256SUMS').write_text(''.join(
    f'{hashlib.sha256((ROOT / s).read_bytes()).hexdigest()}  {s}\n'
    for s in [*sources, 'assets/firmware.hex', 'tests/test_input_modes_cpu.py', 'tests/soc_tb.v']))
