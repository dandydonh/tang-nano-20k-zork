`timescale 1ns/1ps
module video_tb;
 reg clk=0,cpu_clk=0,reset=1;always #5 clk=~clk;always #7 cpu_clk=~cpu_clk;
 reg [11:0] addr=0;reg [7:0] data=0;reg write=0;wire [7:0] read_data;
 wire [23:0] rgb;wire de,hs,vs;
 text_video dut(.pixel_clk(clk),.reset(reset),.cpu_clk(cpu_clk),.cpu_addr(addr),.cpu_data(data),
   .cpu_write(write),.cpu_read(read_data),.rgb(rgb),.de(de),.hsync(hs),.vsync(vs));
 task put(input [11:0] a,input [7:0] d);begin
   @(negedge cpu_clk);addr=a;data=d;write=1;@(negedge cpu_clk);write=0;
   @(negedge cpu_clk);if(read_data!==d)$fatal(1,"CPU text readback");
 end endtask
 integer x=0,y=0,frame=0,active=0,checked=0;reg [23:0] expected;
 reg [7:0] ch;reg [11:0] g;integer cx,cy,i;
 reg prev_de=0,prev_hs=0,prev_vs=0;reg [23:0] prev_rgb;
 initial begin
   // Exercise every ASCII glyph, inverse glyph, cell and edge across the frame.
   for(i=0;i<2560;i=i+1)put(i,i&255);
   put(0,8'hc1);put(1,8'h42);put(80,8'h43);put(2559,8'h5a);
   repeat(4)@(negedge clk);reset=0;
   // After reset release, de_pipe/glyph have one-cycle delay relative to x counter.
   @(negedge clk);
   for(frame=0;frame<2;frame=frame+1)begin
     active=0;
     for(y=0;y<750;y=y+1)for(x=0;x<1650;x=x+1)begin
       if(x<1280&&y<720)active=active+1;
       expected=24'h101810;
       if(x>=160&&x<1120&&y>=40&&y<680)begin
         cx=(x-160)/12;cy=(y-40)/20;ch=dut.text[cy*80+cx];g=dut.font[(ch&127)*32+(y-40)%20];
         if(((g>>(11-(x-160)%12))&1) ^ (ch>>7))expected=24'hc8e8c8;
       end
       @(negedge clk);
       if(de!==(x<1280&&y<720)||hs!==(x>=1390&&x<1430)||vs!==(y>=725&&y<730))$fatal(1,"video sync at %d,%d",x,y);
       if(rgb!==expected)$fatal(1,"glyph mismatch at %d,%d got %h want %h",x,y,rgb,expected);
       prev_de=x<1280&&y<720;prev_hs=x>=1390&&x<1430;prev_vs=y>=725&&y<730;prev_rgb=expected;checked=checked+1;
     end
     if(active!=921600)$fatal(1,"active count");
   end
   $display("PASS two 720p scans, every glyph pixel, inverse status, text CPU read/write");$finish;
 end
endmodule
