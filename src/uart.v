module uart #(parameter DIV=234)(input wire clk,reset,rx,
 output reg [7:0] rx_data,output reg rx_strobe,
 input wire [7:0] tx_data,input wire tx_start,output wire tx_busy,output wire tx);
  reg [2:0] sync_rx;reg [11:0] rx_timer,tx_timer;
  reg [3:0] rx_bit,tx_count;reg [7:0] rx_shift;reg [9:0] tx_shift;
  assign tx_busy=tx_count!=0;assign tx=tx_count?tx_shift[0]:1'b1;
  always @(posedge clk)begin
    sync_rx<={sync_rx[1:0],rx};rx_strobe<=0;
    if(reset)begin sync_rx<=7;rx_bit<=0;rx_timer<=0;tx_count<=0;tx_timer<=0;tx_shift<=1023;end
    else begin
      if(!rx_bit)begin if(!sync_rx[2])begin rx_bit<=1;rx_timer<=DIV/2-1;end end
      else if(rx_timer)rx_timer<=rx_timer-1'b1;
      else begin
        rx_timer<=DIV-1;
        if(rx_bit==1)begin if(sync_rx[2])rx_bit<=0;else rx_bit<=2;end
        else if(rx_bit<10)begin rx_shift<={sync_rx[2],rx_shift[7:1]};rx_bit<=rx_bit+1'b1;end
        else begin rx_bit<=0;if(sync_rx[2])begin rx_data<=rx_shift;rx_strobe<=1;end end
      end
      if(!tx_count)begin if(tx_start)begin tx_shift<={1'b1,tx_data,1'b0};tx_count<=10;tx_timer<=DIV-1;end end
      else if(tx_timer)tx_timer<=tx_timer-1'b1;
      else begin tx_shift<={1'b1,tx_shift[9:1]};tx_count<=tx_count-1'b1;tx_timer<=DIV-1;end
    end
  end
endmodule
