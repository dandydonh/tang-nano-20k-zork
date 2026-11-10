`timescale 1ns/1ps
// Peripheral/MMIO integration: the CPU bus is driven by this testbench.
module input_queues_tb;
  reg clk=0,reset=0,rx=1,kclk=1,kdata=1;
  always #5 clk=~clk;
  reg cs=1,sck=0,mosi=0;
  wire miso,key_strobe;wire [7:0] key_data;
  wire tx;
  companion_keyboard companion(.clk(clk),.reset(reset),.spi_cs_n(cs),
    .spi_sck(sck),.spi_mosi(mosi),.spi_miso(miso),
    .key_data(key_data),.key_strobe(key_strobe));
  zork_soc dut(.clk(clk),.reset(reset),.uart_rx(rx),.uart_tx(tx),
    .ps2_clk(kclk),.ps2_data(kdata),.usb_key_data(key_data),.usb_key_strobe(key_strobe),
    .input_mode_status(4'b0011),
    .sd_miso(1'b1),.text_read(8'b0));
  reg request=0;reg [31:0] address=0,data=0;reg [3:0] mask=0;
  initial begin
    force dut.valid=request;force dut.addr=address;
    force dut.wdata=data;force dut.wstrb=mask;
  end
  task read_input(input [7:0] offset,input bit expected_valid,input [7:0] expected);
    reg [31:0] result;
    begin
      @(negedge clk);address=32'h20000000+offset;request=1;
      @(negedge clk);if(!dut.ready)$fatal(1,"MMIO response missing");
      result=dut.rdata;request=0;
      if(result[8]!==expected_valid || ((expected_valid||offset==32)&&result[7:0]!==expected))
        $fatal(1,"queue %0d got %h expected valid=%b data=%h",offset,result,expected_valid,expected);
      if(result[9])$fatal(1,"unexpected FIFO overflow");
      @(negedge clk);
    end
  endtask
  task ps2_byte(input [7:0] c);
    reg [10:0] frame;integer b;
    begin
      frame={1'b1,~^c,c,1'b0};
      for(b=0;b<11;b=b+1)begin
        kdata=frame[b];repeat(500)@(negedge clk);kclk=0;
        repeat(500)@(negedge clk);kclk=1;
      end
      kdata=1;repeat(500)@(negedge clk);
    end
  endtask
  task spi_byte(input [7:0] c);
    integer b;
    begin
      for(b=7;b>=0;b=b-1)begin
        mosi=c[b];sck=1;repeat(5)@(negedge clk);
        sck=0;repeat(5)@(negedge clk);
      end
    end
  endtask
  task usb_byte(input [7:0] c);
    begin
      cs=0;repeat(5)@(negedge clk);
      spi_byte(1);spi_byte(1);spi_byte(0);spi_byte(0);spi_byte(c);
      cs=1;repeat(5)@(negedge clk);
    end
  endtask
  task uart_byte(input [7:0] c);
    integer b;
    begin
      rx=0;repeat(234)@(negedge clk);
      for(b=0;b<8;b=b+1)begin rx=c[b];repeat(234)@(negedge clk);end
      rx=1;repeat(234)@(negedge clk);
    end
  endtask
  integer b;reg [7:0] received;
  initial begin
    #1;reset=1;
    repeat(20)@(negedge clk);reset=0;repeat(10)@(negedge clk);
    fork
      begin ps2_byte(8'he0);ps2_byte(8'h75);end
      begin usb_byte(8'hf0);usb_byte(8'h1c);usb_byte(8'h32);end
      uart_byte("Z");
    join
    read_input(16,1,8'he0);read_input(28,1,8'hf0);
    read_input(0,1,"Z");read_input(16,1,8'h75);
    read_input(28,1,8'h1c);read_input(28,1,8'h32);
    read_input(0,0,0);read_input(16,0,0);read_input(28,0,0);
    read_input(32,0,3);
    // Serial output still traverses the UART transmitter.
    fork
      begin
        @(negedge clk);address=32'h20000014;data=8'ha6;mask=1;request=1;
        @(negedge clk);request=0;mask=0;
      end
      begin
        @(negedge tx);repeat(351)@(negedge clk);
        for(b=0;b<8;b=b+1)begin received[b]=tx;repeat(234)@(negedge clk);end
        if(received!==8'ha6||tx!==1)$fatal(1,"UART TX mismatch %h",received);
      end
    join
    // Reset must clear both keyboard FIFOs and the UART FIFO.
    usb_byte(8'h12);@(negedge clk);reset=1;repeat(5)@(negedge clk);reset=0;
    read_input(0,0,0);read_input(16,0,0);read_input(28,0,0);
    $display("PASS combined RTL queues: concurrent PS/2 wire, Companion SPI, UART RX/TX, independent MMIO pops and reset");
    $finish;
  end
  initial begin #10000000;$fatal(1,"input queue test timeout");end
endmodule
