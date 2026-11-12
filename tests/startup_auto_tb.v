`timescale 1ns/1ps
module startup_auto_tb;
  reg clk=0;always #5 clk=~clk;
  localparam N=12;
  reg [N-1:0] button=0,strobe=0,cs={N{1'b1}},discovery=0,hid=0,host=0;
  reg [223:0] frame[0:N-1];
  reg [223:0] vectors[0:17];
  wire [N-1:0] done,selected,enabled,rst,por,conflict;
  wire [31:0] status[0:N-1];
  genvar i;
  generate for(i=0;i<N;i=i+1)begin: modes
    startup_mode #(.AUTO_DETECT(1),.WINDOW_CYCLES(80),.DEBOUNCE_CYCLES(2),
      .POWER_CYCLES(4),.BLINK_CYCLES(8),.DETECT_CYCLES(160),.STALE_CYCLES(i==3?30:100)) dut(
      .clk(clk),.button(button[i]),.companion_active(host[i]),
      .announcement_strobe(strobe[i]),.announcement_frame(frame[i]),.spi_cs_n(cs[i]),
      .discovery_seen(discovery[i]),.hid_registration_seen(hid[i]),
      .transport_reset(por[i]),.game_reset(rst[i]),.selection_done(done[i]),
      .serial_selected(selected[i]),.serial_enabled(enabled[i]),
      .mode_conflict(conflict[i]),.input_status(status[i]));
  end endgenerate
  task cycles(input integer n);begin repeat(n)@(negedge clk);end endtask
  task report(input integer k,input integer v);begin frame[k]=vectors[v];strobe[k]=1;cycles(1);strobe[k]=0;end endtask
  task check(input integer k,input integer reason,input integer serial_choice,input integer uart_on);
    begin
      if(!done[k]||rst[k]||selected[k]!==serial_choice[0]||enabled[k]!==uart_on[0]||status[k][15:12]!==reason[3:0])
        $fatal(1,"auto scenario %0d status=%h done=%b reset=%b uart=%b",k,status[k],done[k],rst[k],enabled[k]);
    end
  endtask
  initial begin
    $readmemh("tests/fixtures/companion_status_v1.hex",vectors);
    for(integer k=0;k<N;k=k+1)frame[k]=0;
    // 0 silent; 1 ready; 2 error; 3 stale; 4 manual serial with probes;
    // 5 double press; 6 legacy; 7 ready with stuck CS; 8 manual USB stuck CS;
    // 9 deadline collision; 10 manual serial conflict; 11 unknown starting.
    cycles(10);
    discovery[4]=1;hid[4]=1;discovery[6]=1;cs[7]=0;cs[8]=0;
    report(3,0);report(2,3);report(11,2);
    button[4]=1;button[5]=1;button[8]=1;button[10]=1;cycles(10);
    button=0;cycles(10);button[5]=1;button[8]=1;cycles(10);button=0;
    cycles(30);report(1,1);report(7,0);
    cycles(25);
    check(1,3,0,0);check(4,1,1,1);check(5,2,0,0);check(10,1,1,1);
    if(!status[1][7]||!status[1][5]||!status[1][4])$fatal(1,"ready/keyboard diagnostics");
    // Fresh report arriving on deadline must take precedence over silent fallback.
    wait(modes[9].dut.detect_count==160);@(negedge clk);report(9,0);
    cycles(5);check(9,3,0,0);
    check(0,4,1,1);check(2,5,1,0);check(3,5,1,0);check(6,6,1,0);
    check(7,5,1,0);check(8,5,1,0);check(11,5,1,0);
    if(!status[3][6])$fatal(1,"stale readiness accepted");
    report(0,0);report(10,0);cycles(3);
    check(0,4,1,0);check(10,1,1,0);
    if(!conflict[0]||!conflict[10])$fatal(1,"late report did not veto UART");
    button={N{1'b1}};cycles(10);
    if(rst!=={N{1'b1}}||por!==0)$fatal(1,"game reset isolation");
    button=0;cycles(120);
    check(1,3,0,0);check(0,4,1,0);check(5,2,0,0);
    $display("PASS automatic startup: fresh/stale/error/unknown, silent deadline, collision, manual serial/USB, legacy/stuck-CS diagnostics, late conflict and reset retention");
    $finish;
  end
  initial begin #100000;$fatal(1,"automatic startup timeout");end
endmodule
