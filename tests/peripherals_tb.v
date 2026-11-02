`timescale 1ns/1ps
module peripherals_tb;
 reg clk=0,reset=1;always #5 clk=~clk;
 reg start=0;reg [7:0] tx_data=0;reg [7:0] divider=0;
 wire sck,mosi,busy;wire [7:0] rx_data;
 spi_byte spi(.clk(clk),.reset(reset),.start(start),.tx_data(tx_data),.divider(divider),
   .miso(mosi),.sck(sck),.mosi(mosi),.busy(busy),.rx_data(rx_data));
 reg kclk=1,kdata=1;wire [7:0] key;wire key_ready;
 ps2_receiver ps(.clk(clk),.reset(reset),.ps2_clk(kclk),.ps2_data(kdata),.data(key),.strobe(key_ready));
 integer received=0;reg [7:0] last_key;
 always @(posedge clk)if(key_ready)begin received=received+1;last_key=key;end
 task psframe(input [7:0] c,input bad);
 reg [10:0] frame;integer i;begin
   frame={1'b1,(~^c)^bad,c,1'b0};
   for(i=0;i<11;i=i+1)begin kdata=frame[i];repeat(20)@(negedge clk);kclk=0;repeat(20)@(negedge clk);kclk=1;end
   kdata=1;repeat(30)@(negedge clk);
 end endtask
 wire utx,ubusy;wire [7:0] urx;wire uready;reg ustart=0;reg [7:0] udata;
 uart #(.DIV(16)) uart_loop(.clk(clk),.reset(reset),.rx(utx),.tx(utx),.rx_data(urx),.rx_strobe(uready),
   .tx_data(udata),.tx_start(ustart),.tx_busy(ubusy));
 integer ucount=0;reg [7:0] ulast;
 always @(posedge clk)if(uready)begin ucount=ucount+1;ulast=urx;end
 integer i,d;
 initial begin
   repeat(4)@(negedge clk);reset=0;
   for(d=0;d<4;d=d+1)for(i=0;i<256;i=i+1)begin
     @(negedge clk);divider=d;tx_data=i;start=1;
     @(negedge clk);start=0;wait(!busy);@(negedge clk);
     if(rx_data!==i[7:0]||sck!==0)$fatal(1,"SPI failed %d divider%d got%h",i,d,rx_data);
   end
   psframe(8'h1c,0);if(received!=1||last_key!=8'h1c)$fatal(1,"PS/2 receive failed");
   psframe(8'h55,1);if(received!=1)$fatal(1,"PS/2 accepted bad parity");
   psframe(8'hf0,0);psframe(8'h1c,0);if(received!=3)$fatal(1,"PS/2 break sequence");
   // Incomplete frame times out, then recovers.
   kdata=0;repeat(20)@(negedge clk);kclk=0;repeat(20)@(negedge clk);kclk=1;kdata=1;
   repeat(270050)@(negedge clk);psframe(8'h5a,0);if(received!=4||last_key!=8'h5a)$fatal(1,"PS/2 timeout recovery");
   for(i=0;i<256;i=i+1)begin
     @(negedge clk);udata=i;ustart=1;@(negedge clk);ustart=0;
     wait(!ubusy);repeat(20)@(negedge clk);
     if(ucount!=i+1||ulast!==i[7:0])$fatal(1,"UART byte %d count%d got%h",i,ucount,ulast);
   end
   $display("PASS SPI 1024 byte transfers, UART 256 bytes, PS/2 parity/break/timeout");$finish;
 end
 initial begin #100000000;$fatal(1,"peripheral test timeout");end
endmodule
