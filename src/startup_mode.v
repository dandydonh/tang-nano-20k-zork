// Configuration-time input selection; game resets retain all selection state.
module startup_mode #(
  parameter WINDOW_CYCLES=54000000,
  parameter DEBOUNCE_CYCLES=270000,
  parameter BLINK_CYCLES=6750000,
  parameter POWER_CYCLES=16,
  parameter AUTO_DETECT=0, // Legacy test/profile compatibility; board top enables it.
  parameter DETECT_CYCLES=270000000, // Draft 10 s bound, not measured hardware evidence.
  parameter STALE_CYCLES=27000000 // Draft 1 s status age; no runtime mode switching.
)(
  input wire clk,button,companion_active,
  input wire announcement_strobe,
  input wire [223:0] announcement_frame,
  input wire spi_cs_n,
  input wire discovery_seen,hid_registration_seen,
  output reg transport_reset=0,
  output wire game_reset,serial_enabled,
  output reg serial_selected=0,
  output reg selection_done=0,
  output wire mode_conflict,
  output wire selection_led_n,
  output wire [31:0] input_status
);
  localparam WINDOW_BITS=$clog2(WINDOW_CYCLES+1);
  localparam DEBOUNCE_BITS=$clog2(DEBOUNCE_CYCLES+1);
  localparam BLINK_BITS=$clog2(BLINK_CYCLES+1);
  localparam POWER_BITS=$clog2(POWER_CYCLES+1);
  localparam DETECT_BITS=$clog2(DETECT_CYCLES+1);
  localparam AGE_BITS=$clog2(STALE_CYCLES+1);
  reg [POWER_BITS-1:0] power_count=0;
  reg [WINDOW_BITS-1:0] window_count=0;
  reg [DEBOUNCE_BITS-1:0] debounce_count=0;
  reg [BLINK_BITS-1:0] blink_count=0;
  reg [DETECT_BITS-1:0] detect_count=0;
  reg [AGE_BITS-1:0] status_age=STALE_CYCLES;
  reg blink=0,button_level=0,button_previous=0;
  reg [1:0] manual_choice=0; // 0:auto, 1:serial, 2:manual USB (two presses).
  reg observed=0,reported_ready=0,keyboard_present=0;
  reg [3:0] reason=0;
  (* ASYNC_REG = "TRUE" *) reg [1:0] button_sync=0,cs_sync=2'b11;
  wire stale=observed&&status_age==STALE_CYCLES;
  wire ready=observed&&reported_ready&&!stale;
  // A valid Companion report proves its execution even if USB role is still
  // unknown. Conservatively block serial into its IRQ input. The original
  // payload guard remains independent and sticky; neither blocks the CPU.
  wire uart_blocked=companion_active||(AUTO_DETECT&&(observed||reason==5||reason==6));
  assign mode_conflict=selection_done&&serial_selected&&uart_blocked;
  assign serial_enabled=selection_done&&serial_selected&&!uart_blocked;
  assign game_reset=transport_reset||!selection_done||button_level;
  assign selection_led_n=blink;
  // Preserve REG32 bits0..3. Additional status and reason are diagnostics.
  assign input_status={16'b0,reason,2'b0,
    (AUTO_DETECT?hid_registration_seen:1'b0),
    (AUTO_DETECT?discovery_seen:1'b0),keyboard_present,stale,ready,observed,
    mode_conflict,companion_active,serial_selected,1'b1};
  always @(posedge clk)begin
    button_sync<={button_sync[0],button};
    cs_sync<={cs_sync[0],spi_cs_n};
    button_previous<=button_level;
    if(power_count<POWER_CYCLES)begin
      transport_reset<=1;power_count<=power_count+1'b1;
    end else transport_reset<=0;
    if(button_sync[1]==button_level)debounce_count<=0;
    else if(debounce_count==DEBOUNCE_CYCLES-1)begin
      button_level<=button_sync[1];debounce_count<=0;
    end else debounce_count<=debounce_count+1'b1;
    if(blink_count==BLINK_CYCLES-1)begin blink_count<=0;blink<=!blink;end
    else blink_count<=blink_count+1'b1;
    if(AUTO_DETECT)begin
      if(status_age<STALE_CYCLES)status_age<=status_age+1'b1;
      if(announcement_strobe)begin
        observed<=1;status_age<=0;
        reported_ready<=announcement_frame[151:144]==1&&
          announcement_frame[143:136]==1&&announcement_frame[130:128]==3'b111;
        keyboard_present<=announcement_frame[131];
      end
    end
    if(!transport_reset&&!selection_done)begin
      if(window_count<WINDOW_CYCLES)begin
        window_count<=window_count+1'b1;
        if(button_level&&!button_previous)begin
          if(manual_choice==0)manual_choice<=1;
          else if(AUTO_DETECT)manual_choice<=2;
        end
      end
      if(detect_count<DETECT_CYCLES)detect_count<=detect_count+1'b1;
      if(!AUTO_DETECT)begin
        if(button_level)serial_selected<=1;
        if(window_count==WINDOW_CYCLES&&!button_level&&!button_sync[1])selection_done<=1;
      end else if(window_count==WINDOW_CYCLES&&!button_level&&!button_sync[1])begin
        if(manual_choice==1)begin
          serial_selected<=1;selection_done<=1;reason<=1;
        end else if(manual_choice==2)begin
          // Only enable replies at an idle transaction boundary.
          if(cs_sync[1]&&spi_cs_n)begin serial_selected<=0;selection_done<=1;reason<=2;end
          else if(detect_count==DETECT_CYCLES)begin serial_selected<=1;selection_done<=1;reason<=5;end
        end else if(ready&&!announcement_strobe)begin
          if(cs_sync[1]&&spi_cs_n)begin serial_selected<=0;selection_done<=1;reason<=3;end
          else if(detect_count==DETECT_CYCLES)begin serial_selected<=1;selection_done<=1;reason<=5;end
        end else if(detect_count==DETECT_CYCLES&&!announcement_strobe)begin
          serial_selected<=1;selection_done<=1;
          if(observed)reason<=5;
          else if(discovery_seen||hid_registration_seen)reason<=6;
          else reason<=4;
        end
      end
    end
  end
endmodule
