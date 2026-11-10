// S1 selects serial during a post-configuration window; otherwise use USB.
// This block runs from the board oscillator, independent of PLL/game reset.
// Registers initialize only on FPGA configuration, never on a game reset.
module startup_mode #(
  parameter WINDOW_CYCLES=54000000, // two seconds at 27 MHz
  parameter DEBOUNCE_CYCLES=270000, // ten milliseconds
  parameter BLINK_CYCLES=6750000,
  parameter POWER_CYCLES=16
)(
  input wire clk,button,companion_active,
  output reg transport_reset=0,
  output wire game_reset,serial_enabled,
  output reg serial_selected=0,
  output reg selection_done=0,
  output wire mode_conflict,
  output wire selection_led_n
);
  localparam WINDOW_BITS=$clog2(WINDOW_CYCLES+1);
  localparam DEBOUNCE_BITS=$clog2(DEBOUNCE_CYCLES+1);
  localparam BLINK_BITS=$clog2(BLINK_CYCLES+1);
  localparam POWER_BITS=$clog2(POWER_CYCLES+1);
  reg [POWER_BITS-1:0] power_count=0;
  reg [WINDOW_BITS-1:0] window_count=0;
  reg [DEBOUNCE_BITS-1:0] debounce_count=0;
  reg [BLINK_BITS-1:0] blink_count=0;
  reg blink=0,button_level=0;
  (* ASYNC_REG = "TRUE" *) reg [1:0] button_sync=0;
  // Keyboard payload traffic blocks UART until reconfiguration, but must
  // not hide HDMI diagnostics or disable independent physical PS/2 input.
  assign mode_conflict=selection_done&&serial_selected&&companion_active;
  assign serial_enabled=selection_done&&serial_selected&&!companion_active;
  assign game_reset=transport_reset||!selection_done||button_level;
  assign selection_led_n=blink;
  always @(posedge clk) begin
    button_sync<={button_sync[0],button};
    // Explicit assertion edge also initializes SPI-domain registers when
    // SCK is stopped; do not rely on simulation's time-zero reset ordering.
    if(power_count<POWER_CYCLES)begin
      transport_reset<=1;power_count<=power_count+1'b1;
    end else transport_reset<=0;
    if(button_sync[1]==button_level)debounce_count<=0;
    else if(debounce_count==DEBOUNCE_CYCLES-1)begin
      button_level<=button_sync[1];debounce_count<=0;
    end else debounce_count<=debounce_count+1'b1;
    if(blink_count==BLINK_CYCLES-1)begin blink_count<=0;blink<=!blink;end
    else blink_count<=blink_count+1'b1;
    if(!transport_reset&&!selection_done)begin
      if(button_level)serial_selected<=1;
      if(window_count<WINDOW_CYCLES)window_count<=window_count+1'b1;
      // Do not start the game while the selection press is still held, or
      // while its release is being synchronized/debounced.
      else if(!button_level&&!button_sync[1])selection_done<=1;
    end
  end
endmodule
