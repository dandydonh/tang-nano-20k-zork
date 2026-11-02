// 720p60 timing. 80x32 console, 8x16 glyphs doubled horizontally.
module text_video(input wire pixel_clk,reset,input wire cpu_clk,
 input wire [11:0] cpu_addr,input wire [7:0] cpu_data,input wire cpu_write,
 output reg [7:0] cpu_read,
 output wire [23:0] rgb,output wire de,hsync,vsync);
  reg [7:0] text[0:4095];reg [7:0] font[0:2047];
  initial begin
    $readmemh("assets/text_blank.hex",text);
    $readmemh("assets/font.hex",font);
  end
  always @(posedge cpu_clk)begin
    if(cpu_write)text[cpu_addr]<=cpu_data;else cpu_read<=text[cpu_addr];
  end
  reg [10:0] x;reg [9:0] y;
  always @(posedge pixel_clk)begin
    if(reset)begin x<=0;y<=0;end
    else if(x==1649)begin x<=0;if(y==749)y<=0;else y<=y+1'b1;end
    else x<=x+1'b1;
  end
  wire in_console=x<1280&&y>=104&&y<616;
  wire [9:0] cy=y-104;
  wire [11:0] address=(cy[8:4]*12'd80)+{5'b0,x[10:4]};
  reg [7:0] character,glyph;
  reg [3:0] glyph_row;reg [2:0] bit0,bit1;reg inverse0;
  reg [2:0] de_pipe,hs_pipe,vs_pipe,console_pipe;
  always @(posedge pixel_clk)begin
    character<=text[address];glyph_row<=cy[3:0];bit0<=x[3:1];bit1<=bit0;
    glyph<=font[{character[6:0],glyph_row}];inverse0<=character[7];
    de_pipe<={de_pipe[1:0],x<1280&&y<720};
    hs_pipe<={hs_pipe[1:0],x>=1390&&x<1430};
    vs_pipe<={vs_pipe[1:0],y>=725&&y<730};
    console_pipe<={console_pipe[1:0],in_console};
    if(reset)begin de_pipe<=0;hs_pipe<=0;vs_pipe<=0;console_pipe<=0;end
  end
  // Character and font RAM give two-cycle latency.
  wire foreground=glyph[7-bit1]^inverse0;
  assign rgb=console_pipe[1]?(foreground?24'hc8e8c8:24'h101810):24'h101810;
  assign de=de_pipe[1];assign hsync=hs_pipe[1];assign vsync=vs_pipe[1];
endmodule
