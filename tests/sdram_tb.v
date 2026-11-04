`timescale 1ns/1ps
module sdram_tb;
  reg clk=0,reset=1,request=0;
  always #5 clk=~clk;
  reg [22:0] address=0;
  reg [31:0] wdata=0;
  reg [3:0] mask=0;
  wire [31:0] rdata,dq;
  wire done,initialized,sclk,cke,cs,ras,cas,we;
  wire [10:0] a;wire [1:0] ba;wire [3:0] dqm;
  sdram_controller dut(.clk(clk),.reset(reset),.request(request),.address(address),
    .write_data(wdata),.write_mask(mask),.read_data(rdata),.done(done),.initialized(initialized),
    .O_sdram_clk(sclk),.O_sdram_cke(cke),.O_sdram_cs_n(cs),.O_sdram_ras_n(ras),
    .O_sdram_cas_n(cas),.O_sdram_wen_n(we),.O_sdram_addr(a),.O_sdram_ba(ba),
    .O_sdram_dqm(dqm),.IO_sdram_dq(dq));
  sdram_model model(.clk(sclk),.reset(reset),.cke(cke),.cs_n(cs),.ras_n(ras),
    .cas_n(cas),.we_n(we),.address(a),.bank(ba),.mask(dqm),.data(dq));
  task access(input [22:0] location,input [31:0] value,input [3:0] lanes);
    begin
      @(negedge clk);address=location;wdata=value;mask=lanes;request=1;
      do @(negedge clk);while(!done);
      request=0;repeat(2)@(negedge clk);
    end
  endtask
  task check(input [22:0] location,input [31:0] value);
    begin access(location,0,0);if(rdata!==value)$fatal(1,"SDRAM %h: got %h expected %h",location,rdata,value);end
  endtask
  integer bitno,lane,i,old_refresh,old_writes;reg [31:0] expected;
  initial begin
    repeat(4)@(negedge clk);reset=0;
    // A pending bus request must wait for the complete power-up sequence.
    access(0,32'h12345678,15);
    if(!initialized||model.cycles<5400)$fatal(1,"SDRAM accepted access before initialization");
    check(0,32'h12345678);
    for(bitno=0;bitno<32;bitno=bitno+1)begin
      access(0,32'b1<<bitno,15);check(0,32'b1<<bitno);
      access(0,~(32'b1<<bitno),15);check(0,~(32'b1<<bitno));
    end
    expected=32'h11223344;access(0,expected,15);
    for(lane=0;lane<4;lane=lane+1)begin
      access(lane,32'ha5a5a5a5,1<<lane);expected[lane*8+:8]=8'ha5;check(0,expected);
    end
    access(0,32'hcafebabe,15);
    for(bitno=2;bitno<23;bitno=bitno+1)access(1<<bitno,32'h31415926^bitno,15);
    access(23'h7ffffc,32'h89abcdef,15);
    check(0,32'hcafebabe);check(23'h7ffffc,32'h89abcdef);
    for(bitno=2;bitno<23;bitno=bitno+1)check(1<<bitno,32'h31415926^bitno);
    // Keep requests coming across refresh deadlines; no refresh starvation.
    for(i=0;i<1000;i=i+1)begin access(23'h20000+i*4,i,15);check(23'h20000+i*4,i);end
    old_refresh=model.refreshes;
    repeat(20000)@(negedge clk);
    if(model.refreshes-old_refresh<45)$fatal(1,"SDRAM did not refresh while idle");
    check(23'h20000+999*4,999);
    // Holding a request after completion must not issue it a second time.
    @(negedge clk);address=0;wdata=32'h55667788;mask=15;request=1;old_writes=model.writes;
    repeat(1500)@(negedge clk);
    if(model.writes!=old_writes+1)$fatal(1,"duplicate SDRAM transaction");
    request=0;repeat(2)@(negedge clk);check(0,32'h55667788);
    reset=1;repeat(4)@(negedge clk);reset=0;
    access(0,32'hdeadbeef,15);check(0,32'hdeadbeef);
    // Reset can interrupt an in-flight request; the next boot reinitializes
    // SDRAM and reloads memory rather than depending on the interrupted write.
    @(negedge clk);address=23'h400;wdata=32'hf00dcafe;mask=15;request=1;
    repeat(2)@(negedge clk);reset=1;request=0;
    repeat(4)@(negedge clk);reset=0;
    access(23'h400,32'hfeed1234,15);check(23'h400,32'hfeed1234);
    $display("PASS SDRAM init, CAS/timing, all data/address bits, byte lanes, refresh under load/idle, request handshake and reset");
    $finish;
  end
  initial begin repeat(100000)@(negedge clk);$fatal(1,"SDRAM test timeout");end
endmodule
