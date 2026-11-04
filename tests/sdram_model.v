// Independent command-level model: BL=1/CAS=2, four banks, 11 row/8 column bits.
// Timing is checked in 27 MHz clock cycles; simulation may scale wall-clock time.
module sdram_model(input wire clk,reset,cke,cs_n,ras_n,cas_n,we_n,
 input wire [10:0] address,input wire [1:0] bank,input wire [3:0] mask,
 inout wire [31:0] data);
  reg [31:0] memory[0:2097151];
  reg [10:0] rows[0:3];
  reg [3:0] active;
  integer available[0:3],activated[0:3];
  integer cycles=0,last_refresh=0,refreshes=0,reads=0,writes=0;
  integer init_refreshes=0,precharged=0,configured=0,read_delay=0;
  reg [20:0] read_address;
  reg [31:0] output_data;
  reg drive=0;
  assign data=drive?output_data:32'bz;
  integer i,lane,index;
  always @(posedge clk)begin
    cycles=cycles+1;
    drive<=0;
    if(read_delay!=0)begin
      read_delay=read_delay-1;
      if(read_delay==0)begin output_data<=memory[read_address];drive<=1;end
    end
    if(!reset&&configured&&cycles-last_refresh>421)$fatal(1,"SDRAM refresh overdue at cycle %0d",cycles);
    if(!reset&&cke&&!cs_n)case({ras_n,cas_n,we_n})
      3'b010:begin
        if(address[10])begin
          active=0;precharged=1;
          for(i=0;i<4;i=i+1)available[i]=cycles+2;
        end else begin active[bank]=0;available[bank]=cycles+2;end
      end
      3'b001:begin
        if(active!=0||!precharged)$fatal(1,"SDRAM refresh with open/uninitialized bank");
        for(i=0;i<4;i=i+1)begin
          if(cycles<available[i])$fatal(1,"SDRAM refresh before tRP/tRFC");
          available[i]=cycles+4;
        end
        last_refresh=cycles;refreshes=refreshes+1;init_refreshes=init_refreshes+1;
      end
      3'b000:begin
        if(!precharged||init_refreshes<2||address!=11'h020||bank!=0)
          $fatal(1,"SDRAM initialization/mode mismatch");
        for(i=0;i<4;i=i+1)if(cycles<available[i])$fatal(1,"SDRAM mode before tRFC");
        configured=1;last_refresh=cycles;
        for(i=0;i<4;i=i+1)available[i]=cycles+2;
      end
      3'b011:begin
        if(!configured||active[bank]||cycles<available[bank])$fatal(1,"SDRAM activate timing/state");
        rows[bank]=address;active[bank]=1;activated[bank]=cycles;
      end
      3'b100,3'b101:begin
        if(!configured||!active[bank]||cycles-activated[bank]<2||!address[10]||address[9:8]!=0)
          $fatal(1,"SDRAM column command timing/address");
        index={bank,rows[bank],address[7:0]};
        active[bank]=0;available[bank]=cycles+5;
        if(we_n)begin
          if(read_delay!=0)$fatal(1,"overlapping SDRAM read");
          read_address=index;read_delay=2;reads=reads+1;
        end else begin
          for(lane=0;lane<4;lane=lane+1)if(!mask[lane])begin
            if(^data[lane*8+:8]===1'bx)$fatal(1,"undefined SDRAM write data");
            memory[index][lane*8+:8]=data[lane*8+:8];
          end
          writes=writes+1;
        end
      end
      default:begin end
    endcase
    if(reset)begin
      active=0;precharged=0;configured=0;init_refreshes=0;read_delay=0;drive<=0;
      last_refresh=cycles;
      for(i=0;i<4;i=i+1)available[i]=0;
    end
  end
endmodule
