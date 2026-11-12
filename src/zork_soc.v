module zork_soc(input wire clk,reset,uart_rx,ps2_clk,ps2_data,sd_miso,
`ifdef ZORK_USB_HOST
 input wire [7:0] usb_key_data, input wire usb_key_strobe,
 input wire [31:0] input_mode_status,
`endif
 output wire uart_tx,sd_clk,sd_mosi,output reg sd_cs,
 output wire trap,
 output wire [11:0] text_addr,output wire [7:0] text_data,output wire text_write,
 input wire [7:0] text_read,
 output wire O_sdram_clk,O_sdram_cke,O_sdram_cs_n,
 output wire O_sdram_ras_n,O_sdram_cas_n,O_sdram_wen_n,
 output wire [10:0] O_sdram_addr,output wire [1:0] O_sdram_ba,
 output wire [3:0] O_sdram_dqm,inout wire [31:0] IO_sdram_dq);
  wire valid,instr;reg ready;wire [31:0] addr,wdata;reg [31:0] rdata;wire [3:0] wstrb;
  picorv32 #(.ENABLE_COUNTERS(0),.ENABLE_MUL(1),.ENABLE_DIV(1),.BARREL_SHIFTER(1),
    .PROGADDR_RESET(0),.STACKADDR(65536)) cpu (
    .clk(clk),.resetn(!reset),.trap(trap),.mem_valid(valid),.mem_instr(instr),
    .mem_ready(ready),.mem_addr(addr),.mem_wdata(wdata),.mem_wstrb(wstrb),.mem_rdata(rdata),
    .irq(32'b0),.pcpi_wr(1'b0),.pcpi_rd(32'b0),.pcpi_wait(1'b0),.pcpi_ready(1'b0));
  reg [31:0] ram[0:16383];
  initial $readmemh("assets/firmware.hex",ram);
  // Hold synchronous RAM result stable until the CPU accepts the bus response.
  wire ram_access=valid&&!ready&&addr<65536;
  reg [31:0] ram_data;
  always @(posedge clk)if(ram_access)begin
    ram_data<=ram[addr[15:2]];
    if(wstrb[0])ram[addr[15:2]][7:0]<=wdata[7:0];
    if(wstrb[1])ram[addr[15:2]][15:8]<=wdata[15:8];
    if(wstrb[2])ram[addr[15:2]][23:16]<=wdata[23:16];
    if(wstrb[3])ram[addr[15:2]][31:24]<=wdata[31:24];
  end
  wire text_access=valid&&!ready&&addr[31:16]==16'h1000;
  assign text_addr=addr[13:2];assign text_data=wdata[7:0];
  assign text_write=text_access&&wstrb[0];
  wire io_access=valid&&!ready&&addr[31:16]==16'h2000;
  wire sdram_access=valid&&!ready&&addr[31:23]==9'h060;
  wire sdram_done,sdram_initialized;wire [31:0] sdram_data;
  sdram_controller memory(.clk(clk),.reset(reset),.request(sdram_access),
    .address(addr[22:0]),.write_data(wdata),.write_mask(wstrb),
    .read_data(sdram_data),.done(sdram_done),.initialized(sdram_initialized),
    .O_sdram_clk(O_sdram_clk),.O_sdram_cke(O_sdram_cke),.O_sdram_cs_n(O_sdram_cs_n),
    .O_sdram_ras_n(O_sdram_ras_n),.O_sdram_cas_n(O_sdram_cas_n),
    .O_sdram_wen_n(O_sdram_wen_n),.O_sdram_addr(O_sdram_addr),
    .O_sdram_ba(O_sdram_ba),.O_sdram_dqm(O_sdram_dqm),.IO_sdram_dq(IO_sdram_dq));
  wire io_write=io_access&&|wstrb;
  wire [7:0] urx,pkey,ufront,pfront;wire ustrobe,pstrobe,uvalid,pvalid,uover,pover;
  wire tx_busy;
  uart serial(.clk(clk),.reset(reset),.rx(uart_rx),.tx(uart_tx),.rx_data(urx),.rx_strobe(ustrobe),
    .tx_data(wdata[7:0]),.tx_start(io_write&&addr[7:0]==20&&!tx_busy),.tx_busy(tx_busy));
`ifdef ZORK_USB_HOST
  wire [7:0] usb_front;
  wire usb_valid,usb_over;
  input_fifo usb_fifo(.clk(clk),.reset(reset),.push(usb_key_strobe),.data(usb_key_data),
    .head(usb_front),.valid(usb_valid),.overflow(usb_over),
    .pop(io_access&&!wstrb&&addr[7:0]==28));
`endif
  ps2_receiver keyboard(.clk(clk),.reset(reset),.ps2_clk(ps2_clk),.ps2_data(ps2_data),.data(pkey),.strobe(pstrobe));
  input_fifo uart_fifo(.clk(clk),.reset(reset),.push(ustrobe),.data(urx),.head(ufront),.valid(uvalid),
    .pop(io_access&&!wstrb&&addr[7:0]==0),.overflow(uover));
  input_fifo ps2_fifo(.clk(clk),.reset(reset),.push(pstrobe),.data(pkey),.head(pfront),.valid(pvalid),
    .pop(io_access&&!wstrb&&addr[7:0]==16),.overflow(pover));
  wire spi_busy;wire [7:0] spi_rx;reg [7:0] spi_div;
  spi_byte spi(.clk(clk),.reset(reset),.start(io_write&&addr[7:0]==4&&!spi_busy),
    .tx_data(wdata[7:0]),.divider(spi_div),.miso(sd_miso),.sck(sd_clk),.mosi(sd_mosi),.busy(spi_busy),.rx_data(spi_rx));
  reg [1:0] read_kind;
  // rdata is overridden by the synchronous RAM/display output during response.
  always @*begin
    case(read_kind)0:rdata=ram_data;1:rdata={24'b0,text_read};3:rdata=sdram_data;default:rdata=io_data;endcase
  end
  reg [31:0] io_data;
  always @(posedge clk)begin
    ready<=0;
    if(reset)begin ready<=0;sd_cs<=1;spi_div<=39;read_kind<=0;io_data<=0;end
    else if(valid&&!ready)begin
      if(ram_access)begin ready<=1;read_kind<=0;end
      else if(text_access)begin ready<=1;read_kind<=1;end
      else if(sdram_access)begin read_kind<=3;if(sdram_done)ready<=1;end
      else if(io_access)begin
        read_kind<=2;io_data<=0;
        case(addr[7:0])
          0:begin ready<=1;io_data<={22'b0,uover,uvalid,ufront};end
          4:begin ready<=1;io_data<={23'b0,spi_busy,spi_rx};end
          8:begin ready<=1;io_data<={31'b0,sd_cs};if(io_write)sd_cs<=wdata[0];end
          12:begin ready<=1;io_data<={24'b0,spi_div};if(io_write)spi_div<=wdata[7:0];end
          16:begin ready<=1;io_data<={22'b0,pover,pvalid,pfront};end
          20:begin if(!tx_busy)ready<=1;end
          24:begin ready<=1;io_data<={31'b0,sdram_initialized};end
`ifdef ZORK_USB_HOST
          28:begin ready<=1;io_data<={22'b0,usb_over,usb_valid,usb_front};end
          // bit0: selectable profile, bit1: serial chosen, bit2: host seen,
          // bit3: role conflict. Used to identify actual mode on HDMI.
          32:begin ready<=1;io_data<=input_mode_status;end
`endif
          default:ready<=1;
        endcase
      end
      else begin ready<=1;read_kind<=2;io_data<=0;end
    end
  end
endmodule
