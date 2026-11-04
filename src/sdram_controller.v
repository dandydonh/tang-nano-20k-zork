// GW2AR-18 integrated 8 MiB SDR SDRAM, 27 MHz controller/32-bit CPU port.
// BL=1, CAS=2, auto-precharge. Commands launch on clk's rising edge;
// the SDRAM samples them on the opposite edge, leaving half a cycle for I/O.
// At 27 MHz: tRCD/tRP >= 2 clocks, tRFC >= 4 clocks, tWR >= 2 clocks.
// Refresh has priority between transactions and continues with no CPU traffic.
module sdram_controller(
  input wire clk, reset, request,
  input wire [22:0] address,
  input wire [31:0] write_data,
  input wire [3:0] write_mask,
  output reg [31:0] read_data,
  output reg done,
  output reg initialized,
  output wire O_sdram_clk, O_sdram_cke, O_sdram_cs_n,
  output wire O_sdram_ras_n, O_sdram_cas_n, O_sdram_wen_n,
  output reg [10:0] O_sdram_addr,
  output reg [1:0] O_sdram_ba,
  output reg [3:0] O_sdram_dqm,
  inout wire [31:0] IO_sdram_dq
);
  localparam NOP=3'b111, PRECHARGE=3'b010, REFRESH=3'b001,
             MODE=3'b000, ACTIVATE=3'b011, READ=3'b101, WRITE=3'b100;
  localparam POWERUP=0, CONFIGURE=1, IDLE=2, ACCESS=3, REFRESH_WAIT=4;
  reg [2:0] state, command;
  reg [12:0] power_count;
  reg [8:0] refresh_count;
  reg [4:0] phase;
  reg armed, drive;
  reg [22:0] latched_address;
  reg [31:0] latched_data;
  reg [3:0] latched_mask;
  assign O_sdram_clk=~clk;
  assign O_sdram_cke=1'b1;
  assign O_sdram_cs_n=1'b0;
  assign {O_sdram_ras_n,O_sdram_cas_n,O_sdram_wen_n}=command;
  assign IO_sdram_dq=drive?latched_data:32'bz;
  always @(posedge clk)begin
    command<=NOP;done<=0;
    if(!request)armed<=1;
    if(initialized&&refresh_count!=511)refresh_count<=refresh_count+1'b1;
    case(state)
      POWERUP:begin
        // 200 us with stable clock before precharging all banks.
        if(power_count==5400)begin
          command<=PRECHARGE;O_sdram_addr<=11'h400;
          phase<=0;state<=CONFIGURE;
        end else power_count<=power_count+1'b1;
      end
      CONFIGURE:begin
        phase<=phase+1'b1;
        case(phase)
          2,6:command<=REFRESH;
          10:begin command<=MODE;O_sdram_ba<=0;O_sdram_addr<=11'h020;end
          13:begin initialized<=1;refresh_count<=0;state<=IDLE;end
          default:begin end
        endcase
      end
      IDLE:begin
        if(refresh_count>=384)begin
          command<=REFRESH;refresh_count<=0;phase<=0;state<=REFRESH_WAIT;
        end else if(request&&armed)begin
          armed<=0;latched_address<=address;latched_data<=write_data;
          latched_mask<=write_mask;
          O_sdram_ba<=address[22:21];O_sdram_addr<=address[20:10];
          command<=ACTIVATE;phase<=0;state<=ACCESS;
        end
      end
      ACCESS:begin
        phase<=phase+1'b1;
        case(phase)
          1:begin
            O_sdram_addr<={1'b1,2'b00,latched_address[9:2]};
            O_sdram_dqm<=latched_mask==0?4'b0000:~latched_mask;
            command<=latched_mask==0?READ:WRITE;
            drive<=latched_mask!=0;
          end
          2:drive<=0;
          // READ sampled half a clock after phase 1, CAS=2 output follows
          // phase 3's falling edge; sample at phase 4's rising edge.
          4:if(latched_mask==0)read_data<=IO_sdram_dq;
          7:begin done<=1;state<=IDLE;O_sdram_dqm<=0;end
          default:begin end
        endcase
      end
      REFRESH_WAIT:begin
        if(phase==3)state<=IDLE;else phase<=phase+1'b1;
      end
      default:state<=POWERUP;
    endcase
    if(reset)begin
      state<=POWERUP;power_count<=0;refresh_count<=0;phase<=0;
      initialized<=0;done<=0;armed<=1;drive<=0;command<=NOP;
      O_sdram_addr<=0;O_sdram_ba<=0;O_sdram_dqm<=0;read_data<=0;
    end
  end
endmodule
