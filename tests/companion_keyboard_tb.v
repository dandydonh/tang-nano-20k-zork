`timescale 1ns/1ps
module companion_keyboard_tb;
  reg clk=0, reset=0, cs=1, sck=0, mosi=0;
  wire miso, strobe;
  wire [7:0] data;
  always #18.5185 clk=~clk;
  companion_keyboard dut(.clk(clk),.reset(reset),.spi_cs_n(cs),
    .spi_sck(sck),.spi_mosi(mosi),.spi_miso(miso),
    .key_data(data),.key_strobe(strobe));
  reg [7:0] expected[0:511];
  integer sent=0, seen=0, i;
  reg last_strobe=0;
  real half_period=18.75; // 26.667 MHz, asynchronous to 27 MHz CPU
  always @(posedge clk) begin
    #1;
    if (!reset) begin
      if (strobe) begin
        if (last_strobe) $fatal(1,"strobe lasted more than one cycle");
        if (seen >= sent || data !== expected[seen])
          $fatal(1,"byte %0d got %02x expected %02x",seen,data,expected[seen]);
        seen=seen+1;
      end
    end
    last_strobe=strobe;
  end
  task start_packet;
    begin cs=0; #7; end
  endtask
  task end_packet;
    begin #1; cs=1; #151; end
  endtask
  task transfer(input [7:0] tx, output [7:0] rx);
    integer b;
    begin
      for(b=7;b>=0;b=b-1) begin
        sck=1; mosi=tx[b]; #(half_period);
        rx[b]=miso; sck=0; #(half_period);
      end
    end
  endtask
  reg [7:0] reply;
  reg [71:0] legacy_config = "<config/>";
  integer probe, c;
  task put(input [7:0] tx);
    begin transfer(tx,reply); end
  endtask
  task key_byte(input [7:0] tx);
    begin expected[sent]=tx; sent=sent+1; put(tx); end
  endtask
  task header(input [7:0] t, input [7:0] c);
    begin start_packet; put(t); put(c); put(8'h68); put(8'he0); end
  endtask
  initial begin
    #1; reset=1; #122; reset=0; #57;
    if (miso !== 1'bz) $fatal(1,"MISO not tri-stated while deselected");
    start_packet; put(0); put(0); put(0);
    put(0); if(reply !== 8'h5c) $fatal(1,"bad status signature first byte: %02x",reply);
    put(0); if(reply !== 8'h42) $fatal(1,"bad status signature second byte");
    put(0); if(reply !== 0) $fatal(1,"bad core id"); end_packet;
    // Actual Companion config-probe ordering: target, command, dummy, string.
    // Read twice to verify CS restarts the response, then test a keyboard packet.
    for(probe=0;probe<2;probe=probe+1) begin
      start_packet; put(0); put(8); put(0);
      for(c=0;c<9;c=c+1) begin
        put(0);
        if(reply !== legacy_config[71-c*8 -: 8])
          $fatal(1,"config probe %0d byte %0d: %02x",probe,c,reply);
      end
      put(0); if(reply !== 0) $fatal(1,"config not terminated");
      put(0); if(reply !== 0) $fatal(1,"config read past terminator");
      end_packet;
    end
    header(1,1); key_byte(8'h1c); end_packet; // 'a' press
    header(1,1); key_byte(8'hf0); key_byte(8'h1c); end_packet;
    header(1,1); key_byte(8'he0); key_byte(8'hf0); key_byte(8'h11); end_packet;
    // All byte values, continuous at maximum expected rate.
    header(1,1);
    for(i=0;i<256;i=i+1) key_byte((i*73)&255);
    end_packet;
    // Metadata, unrelated commands and partial packets must never emit keys.
    header(1,2); put(8'h1c); put(8'hf0); end_packet;
    header(3,1); put(8'h1c); end_packet;
    start_packet; put(1); put(1); put(8'h1c); end_packet;
    start_packet; put(1); sck=1; #19; sck=0; #19; end_packet;
    half_period=125; header(1,1); key_byte(8'h5a); end_packet;
    #200;
    if(seen != sent) $fatal(1,"lost bytes: %0d / %0d",seen,sent);
    // Reset without SCK cannot invent a key.
    reset=1; #100; reset=0; #200;
    header(1,1); key_byte(8'h66); end_packet;
    #200;
    if(seen != sent) $fatal(1,"post-reset byte lost");
    $display("PASS Companion SPI: %0d bytes, status, metadata filtering, fast CDC, abort/reset",seen);
    $finish;
  end
  initial begin #1000000; $fatal(1,"timeout"); end
endmodule
