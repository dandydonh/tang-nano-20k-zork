`timescale 1ns/1ps
// Receiver frame validation and asynchronous SPI publication regression.
module companion_status_tb;
  reg clk=0,reset=0,cs=1,sck=0,mosi=0;
  always #18.5185 clk=~clk;
  wire discovery,hid,announced,update,host,key_strobe;
  wire [223:0] frame;
  wire [7:0] key;
  companion_keyboard dut(.clk(clk),.reset(reset),.spi_cs_n(cs),
    .spi_sck(sck),.spi_mosi(mosi),.discovery_seen(discovery),
    .hid_registration_seen(hid),.announcement_seen(announced),
    .announcement_strobe(update),.announcement_frame(frame),
    .host_active(host),.key_data(key),.key_strobe(key_strobe));
  reg [223:0] vectors[0:17];
  integer updates=0,keys=0,index,before_count;
  reg previous_update=0;
  always @(posedge clk)begin
    #1;
    if(!reset)begin
      if(update)begin
        if(previous_update)$fatal(1,"announcement strobe longer than one cycle");
        updates=updates+1;
      end
      if(key_strobe)begin
        if(key!==8'h1c)$fatal(1,"unexpected keyboard data");
        keys=keys+1;
      end
    end
    previous_update=update;
  end
  task put(input [7:0] value);
    integer bit_index;
    begin
      for(bit_index=7;bit_index>=0;bit_index=bit_index-1)begin
        sck=1;mosi=value[bit_index];#18.75;sck=0;#18.75;
      end
    end
  endtask
  task start_packet;begin cs=0;#7;end endtask
  task end_packet;begin #1;cs=1;#1000;end endtask
  task send_frame(input [223:0] value,input integer bytes);
    integer byte_index;
    begin
      for(byte_index=0;byte_index<bytes;byte_index=byte_index+1)
        put(value[223-byte_index*8 -: 8]);
    end
  endtask
  task configure_reset;
    begin
      cs=1;sck=0;reset=1;#151;reset=0;#1000;
      if(discovery||hid||announced||update||host)
        $fatal(1,"configuration reset did not clear observations");
    end
  endtask
  initial begin
    $readmemh("tests/fixtures/companion_status_v1.hex",vectors);
    configure_reset;
    // Complete probes are diagnostic observations, never keyboard activity.
    start_packet;repeat(7)put(0);end_packet;
    if(!discovery||hid||host)$fatal(1,"discovery classification");
    start_packet;put(1);repeat(4)put(0);end_packet;
    if(!hid||host||updates||keys)$fatal(1,"HID registration changed guard/data");
    // Valid frames publish only AFTER CS ends, even with SCK stopped.
    for(index=0;index<4;index=index+1)begin
      before_count=updates;
      start_packet;send_frame(vectors[index],28);#500;
      if(updates!=before_count)$fatal(1,"published before transaction end");
      end_packet;
      if(updates!=before_count+1||frame!==vectors[index]||!announced||host||keys)
        $fatal(1,"valid announcement %0d not isolated/published",index);
    end
    before_count=updates;
    start_packet;#500;end_packet;
    if(updates!=before_count)$fatal(1,"empty transaction republished last valid frame");
    // Every rejected frame except bad CRC has an independently correct CRC.
    for(index=4;index<18;index=index+1)begin
      before_count=updates;
      start_packet;send_frame(vectors[index],28);end_packet;
      if(updates!=before_count||frame!==vectors[3]||host||keys)
        $fatal(1,"invalid frame %0d accepted or refreshed status",index);
    end
    before_count=updates;
    start_packet;send_frame(vectors[0],27);end_packet;
    start_packet;send_frame(vectors[0],28);put(0);end_packet;
    start_packet;send_frame(vectors[0],28);
    sck=1;mosi=0;#18.75;sck=0;#18.75;end_packet;
    // Empty CS pulses must not republish a previous candidate.
    start_packet;end_packet;
    if(updates!=before_count||host||keys)$fatal(1,"truncated/overlong/partial/empty accepted");
    // Back-to-back reports use the required 1 us idle while bus ownership is held.
    start_packet;send_frame(vectors[0],28);end_packet;
    start_packet;send_frame(vectors[1],28);end_packet;
    if(updates!=before_count+2||frame!==vectors[1])$fatal(1,"repeated reports lost");
    // A runt transaction may evade the CS synchronizer. Pre-frame idle must
    // settle its token so it cannot alias a later complete announcement.
    before_count=updates;
    cs=0;#1;sck=1;#1;sck=0;#1;cs=1;#1000;
    start_packet;send_frame(vectors[0],28);end_packet;
    if(updates!=before_count+1)$fatal(1,"runt transaction hid next announcement");
    // Actual payload retains the legacy sticky guard independently of status.
    start_packet;put(1);put(1);put(4);put(4);put(8'h1c);end_packet;
    if(!host||keys!=1)$fatal(1,"legacy payload guard/delivery changed");
    start_packet;send_frame(vectors[2],28);end_packet;
    if(!host||keys!=1)$fatal(1,"status cleared payload guard or emitted key");
    // Reset with no SPI clock cannot invent a report; old status cannot survive it.
    before_count=updates;configure_reset;
    start_packet;send_frame(vectors[0],14);
    reset=1;#151;reset=0;end_packet;
    if(updates!=before_count||announced||host)$fatal(1,"reset-mid-frame publication");
    start_packet;send_frame(vectors[0],28);end_packet;
    if(updates!=before_count+1||frame!==vectors[0])$fatal(1,"post-reset recovery");
    $display("PASS passive status isolation, frame validation, CS completion, repeated CDC, payload guard and reset");
    $finish;
  end
  initial begin #1000000;$fatal(1,"status test timeout");end
endmodule
