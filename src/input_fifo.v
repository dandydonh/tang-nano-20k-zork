// Single clock byte FIFO, drops new data on overflow and exposes a sticky flag.
module input_fifo(input wire clk, reset, push, pop, input wire [7:0] data,
 output wire [7:0] head, output wire valid, output reg overflow);
  reg [7:0] mem[0:15];reg [3:0] rd,wr;reg [4:0] count;
  assign valid=count!=0;assign head=mem[rd];
  wire take=pop&&valid;
  wire put=push&&(count<16||take);
  always @(posedge clk) begin
    if(reset)begin rd<=0;wr<=0;count<=0;overflow<=0;end
    else begin
      if(push&&!put)overflow<=1;
      if(put)begin mem[wr]<=data;wr<=wr+1'b1;end
      if(take)rd<=rd+1'b1;
      case({put,take})2'b10:count<=count+1'b1;2'b01:count<=count-1'b1;default:count<=count;endcase
    end
  end
endmodule
