module ps2_receiver(input wire clk, reset, ps2_clk, ps2_data,
 output reg [7:0] data, output reg strobe);
  reg [2:0] cs,ds;reg [7:0] filter;reg filtered,last;
  reg [3:0] count;reg [8:0] bits;reg [19:0] timeout_count;
  always @(posedge clk) begin
    cs<={cs[1:0],ps2_clk};ds<={ds[1:0],ps2_data};filter<={filter[6:0],cs[2]};
    if(&filter)filtered<=1;else if(~|filter)filtered<=0;
    last<=filtered;strobe<=0;
    if(reset)begin cs<=7;ds<=7;filter<=255;filtered<=1;last<=1;count<=0;timeout_count<=0;end
    else begin
      if(count)begin
        if(timeout_count==270000)begin count<=0;timeout_count<=0;end
        else timeout_count<=timeout_count+1'b1;
      end
      if(last&&!filtered)begin
        timeout_count<=0;
        if(count==0)begin if(!ds[2])count<=1;end
        else if(count<10)begin bits<={ds[2],bits[8:1]};count<=count+1'b1;end
        else begin count<=0;if(ds[2]&&(^bits))begin data<=bits[7:0];strobe<=1;end end
      end
    end
  end
endmodule
