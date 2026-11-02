// SPI mode 0. Start only while idle. Divider is half-period minus one.
module spi_byte(input wire clk,reset,start,input wire [7:0] tx_data,
 input wire [7:0] divider,input wire miso,
 output reg sck,output wire mosi,output reg busy,output reg [7:0] rx_data);
  reg [7:0] tx_shift,rx_shift,timer;reg [3:0] bits;
  assign mosi=busy?tx_shift[7]:1'b1;
  always @(posedge clk)begin
    if(reset)begin sck<=0;busy<=0;rx_data<=255;timer<=0;bits<=0;tx_shift<=255;rx_shift<=0;end
    else if(!busy)begin
      sck<=0;
      if(start)begin tx_shift<=tx_data;rx_shift<=0;bits<=0;busy<=1;timer<=divider;end
    end else if(timer)timer<=timer-1'b1;
    else begin
      timer<=divider;sck<=!sck;
      if(!sck)rx_shift<={rx_shift[6:0],miso};
      else begin
        tx_shift<={tx_shift[6:0],1'b1};
        if(bits==7)begin busy<=0;rx_data<=rx_shift;end
        else bits<=bits+1'b1;
      end
    end
  end
endmodule
