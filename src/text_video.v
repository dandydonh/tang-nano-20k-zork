// 720p60 timing. Left-aligned 80x32 console, native 12x20 glyphs.
module text_video(input wire pixel_clk,reset,input wire cpu_clk,
 input wire [11:0] cpu_addr,input wire [7:0] cpu_data,input wire cpu_write,
 output reg [7:0] cpu_read,
 output wire [23:0] rgb,output wire de,hsync,vsync);
  reg [7:0] text[0:4095];reg [11:0] font[0:4095];
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
  wire in_console=x<960&&y>=40&&y<680;
  reg [6:0] column;
  reg [4:0] row,pixel_row;
  reg [3:0] pixel_column;
  // Counters avoid division by the non-power-of-two cell dimensions.
  always @(posedge pixel_clk)begin
    if(reset)begin column<=0;row<=0;pixel_row<=0;pixel_column<=0;end
    else begin
      if(x>=960)begin column<=0;pixel_column<=0;end
      else if(pixel_column==11)begin pixel_column<=0;column<=column+1'b1;end
      else pixel_column<=pixel_column+1'b1;
      if(x==1649)begin
        if(y<40||y>=679)begin row<=0;pixel_row<=0;end
        else if(pixel_row==19)begin pixel_row<=0;row<=row+1'b1;end
        else pixel_row<=pixel_row+1'b1;
      end
    end
  end
  wire [11:0] address=(row*12'd80)+{5'b0,column};
  reg [7:0] character;reg [11:0] glyph;
  reg [4:0] glyph_row;reg [3:0] bit0,bit1;reg inverse0;
  reg [2:0] de_pipe,hs_pipe,vs_pipe,console_pipe;
  always @(posedge pixel_clk)begin
    character<=text[address];glyph_row<=pixel_row;bit0<=pixel_column;bit1<=bit0;
    glyph<=font[{character[6:0],glyph_row}];inverse0<=character[7];
    de_pipe<={de_pipe[1:0],x<1280&&y<720};
    hs_pipe<={hs_pipe[1:0],x>=1390&&x<1430};
    vs_pipe<={vs_pipe[1:0],y>=725&&y<730};
    console_pipe<={console_pipe[1:0],in_console};
    if(reset)begin de_pipe<=0;hs_pipe<=0;vs_pipe<=0;console_pipe<=0;end
  end
  // Character and font RAM give two-cycle latency.
  wire foreground=glyph[11-bit1]^inverse0;
  assign rgb=console_pipe[1]?(foreground?24'hc8e8c8:24'h101810):24'h101810;
  assign de=de_pipe[1];assign hsync=hs_pipe[1];assign vsync=vs_pipe[1];
endmodule
