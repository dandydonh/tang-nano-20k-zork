`timescale 1ns/1ps
// Behavioral primitive stubs exercise reset/routing only, not HDMI timing.
module rPLL #(parameter FCLKIN="27",IDIV_SEL=0,FBDIV_SEL=0,ODIV_SEL=0,DEVICE="")(
 input CLKIN,RESET,RESET_P,CLKFB,input [5:0] FBDSEL,IDSEL,ODSEL,
 input [3:0] PSDA,DUTYDA,FDLY,output CLKOUT,LOCK);
 assign CLKOUT=CLKIN;assign LOCK=!RESET;
endmodule
module CLKDIV #(parameter DIV_MODE="5",GSREN="false")(
 input HCLKIN,RESETN,CALIB,output CLKOUT);
 assign CLKOUT=HCLKIN;
endmodule
module OSER10(input D0,D1,D2,D3,D4,D5,D6,D7,D8,D9,PCLK,FCLK,RESET,output Q);
 assign Q=D0;
endmodule
module TLVDS_OBUF(input I,output O,OB);assign O=I;assign OB=!I;endmodule
module mode_routing_tb;
 reg clk=0;always #5 clk=~clk;
 reg button=0,cs=1,sck=0,mosi=0,rx=1;
 wire tx,led;wire miso;
 zork_top dut(.clk_27mhz(clk),.reset_button(button),.uart_rx(rx),
   .ps2_clk(1'b1),.ps2_data(1'b1),.sd_miso(1'b1),
   .companion_cs_n(cs),.companion_sck(sck),.companion_mosi(mosi),
   .companion_miso(miso),.uart_tx(tx),.led_n(led));
 defparam dut.mode_selector.WINDOW_CYCLES=400;
 defparam dut.mode_selector.DEBOUNCE_CYCLES=4;
 defparam dut.mode_selector.DETECT_CYCLES=4000;
 defparam dut.mode_selector.STALE_CYCLES=4000;
 defparam dut.mode_selector.BLINK_CYCLES=8;
 reg [223:0] vectors[0:17];
 reg mock_tx=0;
 initial force dut.game_uart_tx=mock_tx;
 task cycles(input integer n);begin repeat(n)@(negedge clk);end endtask
 reg [7:0] spi_reply;
 task spi_byte(input [7:0] c);
   integer b;begin for(b=7;b>=0;b=b-1)begin
     mosi=c[b];sck=1;cycles(5);spi_reply[b]=miso;sck=0;cycles(5);
   end end
 endtask
 task packet(input [7:0] target,input [7:0] command);
   begin cs=0;cycles(5);spi_byte(target);spi_byte(command);cycles(5);cs=1;cycles(5);end
 endtask
 task keyboard_payload;
   begin cs=0;cycles(5);spi_byte(1);spi_byte(1);
     spi_byte(0);spi_byte(4);spi_byte(8'h1c);cs=1;cycles(10);end
 endtask
 initial begin
   $readmemh("tests/fixtures/companion_status_v1.hex",vectors);
   cycles(20);rx=0;
   if(tx!==1||dut.game_uart_rx!==1)$fatal(1,"UART exposed during selection");
   cs=0;cycles(2);
   if(miso!==1'bz)$fatal(1,"SPI reply driven before mode selection");
   cs=1;cycles(2);
   packet(0,0);
   if(dut.selection_done||dut.companion_active)$fatal(1,"startup probe latched conflict");
   if($test$plusargs("serial"))begin
     button=1;cycles(15);button=0;
     wait(dut.selection_done);cycles(20);
     if(!dut.serial_enabled||tx!==0||dut.game_uart_rx!==0)
       $fatal(1,"serial routing missing enabled=%b selected=%b active=%b tx=%b internal=%b rx=%b",dut.serial_enabled,dut.serial_selected,dut.companion_active,tx,dut.game_uart_tx,dut.game_uart_rx);
     if(dut.soc.input_mode_status!==32'h1003)$fatal(1,"serial mode status wiring");
     mock_tx=1;cycles(2);if(tx!==1)$fatal(1,"serial high");
     button=1;cycles(10);button=0;cycles(30);
     if(!dut.serial_enabled||dut.cpu_reset)$fatal(1,"serial mode reset retention");
     mock_tx=0;packet(7,9);
     if(dut.companion_active||!dut.serial_enabled)$fatal(1,"unrelated SPI falsely recognized");
     if(spi_reply!==8'hzz)$fatal(1,"serial mode drove SPI reply");
     // Discovery/config and truncated keyboard headers must not veto UART.
     repeat(3)begin packet(0,0);packet(0,8);packet(1,0);packet(1,1);end
     if(dut.companion_active||!dut.serial_enabled||dut.cpu_reset||tx!==0)
       $fatal(1,"discovery probe falsely blocked serial");
     cs=0;cycles(5);spi_byte(1);spi_byte(1);spi_byte(0);spi_byte(4);
     cs=1;cycles(10);
     if(dut.companion_active)$fatal(1,"keyboard header without payload recognized");
     // Idle-low CS is unrelated to UART.
     cs=0;cycles(2);if(tx!==0)$fatal(1,"CS incorrectly gated UART");
     if(miso!==1'bz)$fatal(1,"SPI driven in serial mode");
     cs=1;cycles(5);keyboard_payload;
     if(!dut.companion_active||dut.serial_enabled||tx!==1||dut.cpu_reset)
       $fatal(1,"keyboard conflict UART isolation/visible diagnostics");
     if(dut.soc.input_mode_status[3:0]!==4'b1111)$fatal(1,"conflict status unavailable");
     button=1;cycles(10);button=0;cycles(30);
     if(!dut.mode_conflict||dut.cpu_reset||tx!==1)
       $fatal(1,"conflict reset retention/diagnostics");
   end else begin
     cs=0;cycles(5);
     for(integer k=0;k<28;k=k+1)spi_byte(vectors[0][223-k*8 -: 8]);
     cs=1;cycles(20);
     wait(dut.selection_done);cycles(20);
     if(dut.serial_enabled||tx!==1||dut.game_uart_rx!==1)$fatal(1,"USB debug UART leaked");
     if(dut.soc.input_mode_status!==32'h3031)$fatal(1,"USB mode status wiring");
     packet(0,8);
     if(dut.companion_active)$fatal(1,"config request falsely recognized as keyboard");
     cs=0;cycles(5);spi_byte(0);spi_byte(0);spi_byte(0);spi_byte(0);
     if(spi_reply!==8'h5c)$fatal(1,"USB status signature first byte");
     spi_byte(0);
     if(spi_reply!==8'h42)$fatal(1,"USB status signature second byte");
     cs=1;cycles(5);keyboard_payload;
     if(!dut.companion_active)$fatal(1,"keyboard payload not recognized");
     button=1;cycles(10);
     if(!dut.cpu_reset||dut.transport_reset||!dut.companion_active)$fatal(1,"reset erased host state");
     button=0;cycles(30);
     if(dut.serial_enabled||dut.cpu_reset)$fatal(1,"USB reset retention");
   end
   $display("PASS top mode routing: passive SPI startup/serial, USB signature, CS-independent UART, reset retention and payload-only guard with visible diagnostics");
   $finish;
 end
 initial begin #200000;$fatal(1,"routing test timeout");end
endmodule
