`timescale 1ns/1ps
module soc_tb;
 reg clk=0,reset=1,rx=1,kclk=1,kdata=1;
 always #5 clk=~clk;
 wire tx,sck,mosi,cs,miso,trap,tw;wire [11:0] ta;wire [7:0] td;reg [7:0] tr;
 reg [7:0] text[0:4095];
 wire sdram_clk,sdram_cke,sdram_cs,sdram_ras,sdram_cas,sdram_we;
 wire [31:0] sdram_dq;wire [10:0] sdram_addr;wire [1:0] sdram_ba;wire [3:0] sdram_dqm;
 zork_soc dut(.clk(clk),.reset(reset),.uart_rx(rx),.uart_tx(tx),.ps2_clk(kclk),.ps2_data(kdata),
   .sd_miso(miso),.sd_clk(sck),.sd_mosi(mosi),.sd_cs(cs),.trap(trap),
   .text_addr(ta),.text_data(td),.text_write(tw),.text_read(tr),
   .O_sdram_clk(sdram_clk),.O_sdram_cke(sdram_cke),.O_sdram_cs_n(sdram_cs),
   .O_sdram_ras_n(sdram_ras),.O_sdram_cas_n(sdram_cas),.O_sdram_wen_n(sdram_we),
   .O_sdram_addr(sdram_addr),.O_sdram_ba(sdram_ba),.O_sdram_dqm(sdram_dqm),.IO_sdram_dq(sdram_dq));
 sdram_model memory(.clk(sdram_clk),.reset(reset),.cke(sdram_cke),.cs_n(sdram_cs),
   .ras_n(sdram_ras),.cas_n(sdram_cas),.we_n(sdram_we),.address(sdram_addr),
   .bank(sdram_ba),.mask(sdram_dqm),.data(sdram_dq));
 sd_spi_model card(.sck(sck),.cs(cs),.mosi(mosi),.miso(miso));
 integer cycles=0,prompts=0,chars=0,menus=0,menu_position=0;
 string menu_prompt="Select story number: ";
 reg [7:0] previous_serial=0;
 integer serial_newlines=0;
 string terminal_init="\033[0m\033[37;49m\033[2J\033[2;r\033[2;1H";
 integer init_position=0,terminal_initializations=0;
 integer status_updates=0,status_position=0;
 string status_prefix="\0337\033[1;1H";
 bit status_active=0;
 integer slot_menus=0,slot_position=0,confirmations=0,confirm_position=0;
 string slot_prompt="Slot number [Enter=1, 0=cancel]: ";
 string confirm_prompt="? [y/N]: ";
 string more_prompt="[MORE]";
 integer more_position=0,more_requests=0;
 always @(posedge clk)begin
   tr<=text[ta];if(tw)text[ta]<=td;
   if($test$plusargs("wrap")&&tw&&ta>=80&&ta<2560&&ta%80==79&&td!=" ")
     $fatal(1,"transcript overwrote the reserved HDMI wrap margin");
   if(reset)init_position=0;
   if(!reset)begin cycles=cycles+1;if(trap)$fatal(1,"CPU trap at %h",dut.cpu.reg_pc);
     if(dut.io_write&&dut.addr[7:0]==20&&!dut.tx_busy)begin
       if(dut.wdata[7:0]==more_prompt[more_position])begin
         more_position=more_position+1;
         if(more_position==more_prompt.len())begin more_requests=more_requests+1;more_position=0;end
       end else more_position=dut.wdata[7:0]==more_prompt[0]?1:0;
       if(init_position<terminal_init.len())begin
         if(dut.wdata[7:0]!=terminal_init[init_position])
           $fatal(1,"terminal startup attributes/clear mismatch at byte %0d",init_position);
         init_position=init_position+1;
         if(init_position==terminal_init.len())terminal_initializations=terminal_initializations+1;
       end
       if(dut.wdata[7:0]==menu_prompt[menu_position])begin
         menu_position=menu_position+1;
         if(menu_position==menu_prompt.len())begin menus=menus+1;menu_position=0;end
       end else menu_position=dut.wdata[7:0]==menu_prompt[0]?1:0;
       if(dut.wdata[7:0]==slot_prompt[slot_position])begin
         slot_position=slot_position+1;
         if(slot_position==slot_prompt.len())begin slot_menus=slot_menus+1;slot_position=0;end
       end else slot_position=dut.wdata[7:0]==slot_prompt[0]?1:0;
       if(dut.wdata[7:0]==confirm_prompt[confirm_position])begin
         confirm_position=confirm_position+1;
         if(confirm_position==confirm_prompt.len())begin confirmations=confirmations+1;confirm_position=0;end
       end else confirm_position=dut.wdata[7:0]==confirm_prompt[0]?1:0;
       if(dut.wdata[7:0]==status_prefix[status_position])begin
         status_position=status_position+1;
         if(status_position==status_prefix.len())begin status_active=1;status_position=0;end
       end else status_position=dut.wdata[7:0]==status_prefix[0]?1:0;
       if(status_active&&previous_serial==27&&dut.wdata[7:0]=="8")begin status_updates=status_updates+1;status_active=0;end
       if(dut.wdata[7:0]==10)begin
         if(previous_serial!=13)$fatal(1,"serial LF without CR causes terminal skew");
         serial_newlines=serial_newlines+1;
       end
       if(previous_serial==13&&dut.wdata[7:0]!=10)$fatal(1,"serial CR without LF");
       previous_serial=dut.wdata[7:0];
       $write("%c",dut.wdata[7:0]);$fflush();chars=chars+1;if(dut.wdata[7:0]==62)prompts=prompts+1;
     end
     // Expanded pool scans dominate the maximum-memory fixture boot/reset.
     if(cycles==1000000000)$fatal(1,"timeout pc=%h SDreads=%d",dut.cpu.reg_pc,card.reads);
   end
 end
 task send_uart(input [7:0] c);
   integer b;begin
     @(negedge clk);rx=0;repeat(234)@(negedge clk);
     for(b=0;b<8;b=b+1)begin rx=c[b];repeat(234)@(negedge clk);end
     rx=1;repeat(234)@(negedge clk);
   end
 endtask
 initial begin : acknowledge_pages
   integer handled=0;
   forever begin
     wait(more_requests>handled);repeat(2000)@(negedge clk);
     send_uart(" ");handled=handled+1;
   end
 end
 task send_key(input [7:0] c);
   reg [10:0] frame;integer b;begin
     frame={1'b1,~^c,c,1'b0};
     for(b=0;b<11;b=b+1)begin kdata=frame[b];repeat(500)@(negedge clk);kclk=0;repeat(500)@(negedge clk);kclk=1;end
     kdata=1;repeat(500)@(negedge clk);
   end
 endtask
 integer edit_index;
 task uart_line(input string line);
   integer n;begin for(n=0;n<line.len();n=n+1)send_uart(line[n]);send_uart(13);end
 endtask
 initial begin
   $display("Starting firmware/SD integration test");$fflush();
   repeat(20)@(negedge clk);reset=0;
   if($test$plusargs("v5"))begin
     wait(prompts==1);repeat(10000)@(negedge clk);
     if(text[1]!=(8'h80|"u")||text[12]!=(8'h80|"n"))$fatal(1,"V5 inverse upper window missing");
     uart_line("s");wait(prompts==2);repeat(10000)@(negedge clk);
     uart_line("n");wait(prompts==3);repeat(10000)@(negedge clk);
     if((memory.memory['h40104/4]&'hffff)!='h0900)$fatal(1,"V5 move state missing");
     uart_line("l");wait(prompts==4);repeat(10000)@(negedge clk);
     uart_line("r");wait(prompts==5);repeat(10000)@(negedge clk);
     if((memory.memory['h40104/4]&'hffff)!=0)$fatal(1,"V5 restore state missing");
     uart_line("l");wait(prompts==6);repeat(10000)@(negedge clk);
     @(negedge clk);reset=1;repeat(20)@(negedge clk);reset=0;
     wait(prompts==7);repeat(10000)@(negedge clk);
     uart_line("r");wait(prompts==8);repeat(10000)@(negedge clk);
     uart_line("l");wait(prompts==9);repeat(10000)@(negedge clk);
     if(text[1]!=(8'h80|"u")||text[12]!=(8'h80|"n"))$fatal(1,"V5 upper window lost to scrolling/restore");
     if(card.writes<2||terminal_initializations!=2)$fatal(1,"V5 persistence coverage missing");
     $display("\nPASS V5 CPU: high calls, max dynamic memory, inverse upper window, undo, save/reset/restore: %0d cycles / %0d reads / %0d writes",cycles,card.reads,card.writes);
     $finish;
   end
   if($test$plusargs("slots"))begin
     wait(prompts==1);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     uart_line("s");wait(slot_menus==1);repeat(2000)@(negedge clk);
     send_key(8'h16);send_key(8'h5a); // PS/2 slot 1: home.
     wait(prompts==2);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     uart_line("n");wait(prompts==3);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     uart_line("s");wait(slot_menus==2);repeat(2000)@(negedge clk);uart_line("2");
     wait(prompts==4);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     uart_line("r");wait(slot_menus==3);repeat(2000)@(negedge clk);
     send_key(8'h16);send_key(8'h5a);
     wait(prompts==5);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     uart_line("l");wait(prompts==6);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     uart_line("s");wait(slot_menus==4);repeat(2000)@(negedge clk);
     send_key(8'h1e);send_key(8'h5a); // Decline overwriting moved state.
     wait(confirmations==1);repeat(2000)@(negedge clk);uart_line("n");
     wait(slot_menus==5);repeat(2000)@(negedge clk);uart_line("0");
     wait(prompts==7);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     @(negedge clk);reset=1;repeat(20)@(negedge clk);reset=0;
     wait(prompts==8);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     uart_line("r");wait(slot_menus==6);repeat(2000)@(negedge clk);uart_line("2");
     wait(prompts==9);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     uart_line("l");wait(prompts==10);wait(status_updates==prompts);repeat(2000)@(negedge clk);
     if(card.writes!=42)$fatal(1,"cancel changed saved data: %0d writes",card.writes);
     if(terminal_initializations!=2)$fatal(1,"terminal reset coverage missing");
     $display("\nPASS selectable saves: UART/PS2 slots, independent states, declined overwrite/cancel, reset restore: %0d cycles / %0d reads / %0d writes",cycles,card.reads,card.writes);
     $finish;
   end
   if($test$plusargs("menu"))begin
     wait(menus==1);repeat(2000)@(negedge clk);
     send_uart("1");send_uart("9");send_uart(13); // 18 GAME entries precede ZORK1.
   end
   wait(prompts==1);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   // PS/2 types LOOK, proving receiver, FIFO, map, editor and interpreter path.
   send_key(8'h4b);send_key(8'h44);send_key(8'h44);send_key(8'h42);send_key(8'h5a);
   wait(prompts==2);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   // Recall PS/2 LOOK via extended Up; serial Down restores draft "x".
   // Erase draft, recall with SS3 Up and ignore CSI Right, then submit LOOK.
   send_uart("x");send_key(8'he0);send_key(8'h75);
   send_key(8'he0);send_key(8'hf0);send_key(8'h75);
   send_uart(27);send_uart("[");send_uart("B");send_uart(127);
   send_uart(27);send_uart("O");send_uart("A");
   send_uart(27);send_uart("[");send_uart("C");send_uart(13);
   wait(prompts==3);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   if($test$plusargs("wrap"))begin
     // Cross a physical input line and erase it back through the wrap.
     for(edit_index=0;edit_index<90;edit_index=edit_index+1)send_uart("x");
     repeat(20000)@(negedge clk);
     for(edit_index=0;edit_index<90;edit_index=edit_index+1)begin
       send_uart(127);repeat(8000)@(negedge clk);
     end
   end
   send_uart("s");send_uart("a");send_uart("v");send_uart("e");send_uart(13);
   wait(prompts==4);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   send_uart("n");send_uart(13);
   wait(prompts==5);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   send_uart("r");send_uart("e");send_uart("s");send_uart("t");send_uart("o");send_uart("r");send_uart("e");send_uart(13);
   wait(prompts==6);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   send_uart("l");send_uart("o");send_uart("o");send_uart("k");send_uart(13);
   wait(prompts==7);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   // Reset CPU and all peripherals while retaining SD contents, then restore.
   @(negedge clk);reset=1;repeat(20)@(negedge clk);reset=0;
   if($test$plusargs("menu"))begin
     wait(menus==2);repeat(2000)@(negedge clk);
     send_key(8'h16);send_key(8'h46);send_key(8'h5a); // Select ZORK1 (19) after reset.
   end
   wait(prompts==8);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   send_uart("r");send_uart("e");send_uart("s");send_uart("t");send_uart("o");send_uart("r");send_uart("e");send_uart(13);
   wait(prompts==9);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   send_uart("l");send_uart("o");send_uart("o");send_uart("k");send_uart(13);
   wait(prompts==10);wait(status_updates==prompts);repeat(2000)@(negedge clk);
   if(card.writes<2)$fatal(1,"save never wrote SD");
   if(serial_newlines<20)$fatal(1,"serial line ending coverage missing");
   if(terminal_initializations!=2)$fatal(1,"terminal must initialize at boot and reset");
   $display("\nPASS serial attributes, white on default background, clear/home at boot and reset");
   $display("\nPASS serial CRLF on %0d newlines",serial_newlines);
   $display("\nPASS soc boot, PS/2 LOOK, UART SAVE/NORTH/RESTORE/LOOK, reset/restore: %0d cycles, %0d SD reads, %0d writes",cycles,card.reads,card.writes);
   $finish;
 end
endmodule
