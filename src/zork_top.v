module zork_top (
    input wire clk_27mhz,
    input wire reset_button,
    output wire hdmi_clk_p,
    output wire hdmi_clk_n,
    output wire [2:0] hdmi_data_p,
    output wire [2:0] hdmi_data_n,
    input wire uart_rx, ps2_clk, ps2_data, sd_miso,
`ifdef ZORK_USB_HOST
    input wire companion_cs_n, companion_sck, companion_mosi,
    output wire companion_miso,
`endif
    output wire uart_tx, sd_clk, sd_mosi, sd_cs,
    output wire led_n,
    // Gowin reserves these names for the SDRAM inside the GW2AR package.
    output wire O_sdram_clk,O_sdram_cke,O_sdram_cs_n,
    output wire O_sdram_ras_n,O_sdram_cas_n,O_sdram_wen_n,
    output wire [10:0] O_sdram_addr,output wire [1:0] O_sdram_ba,
    output wire [3:0] O_sdram_dqm,inout wire [31:0] IO_sdram_dq
);
  wire system_reset;
`ifdef ZORK_USB_HOST
  wire companion_active,transport_reset,serial_enabled,serial_selected;
  wire selection_done,mode_conflict,selection_led_n;
  startup_mode mode_selector(.clk(clk_27mhz),.button(reset_button),
    .companion_active(companion_active),.transport_reset(transport_reset),
    .game_reset(system_reset),.serial_enabled(serial_enabled),
    .serial_selected(serial_selected),.selection_done(selection_done),
    .mode_conflict(mode_conflict),.selection_led_n(selection_led_n));
`else
  assign system_reset=reset_button;
`endif
  wire serial_clk, pixel_clk, locked;
  // 27 / 4 * 55 = 371.25 MHz; DDR serialization = 742.5 Mb/s.
  rPLL #(.FCLKIN("27"), .IDIV_SEL(3), .FBDIV_SEL(54),
         .ODIV_SEL(2), .DEVICE("GW2AR-18C")) pll (
    .CLKIN(clk_27mhz), .CLKOUT(serial_clk), .LOCK(locked),
    .RESET(reset_button), .RESET_P(1'b0), .CLKFB(1'b0),
    .FBDSEL(6'd0), .IDSEL(6'd0), .ODSEL(6'd0),
    .PSDA(4'd0), .DUTYDA(4'd0), .FDLY(4'd0)
  );
  // Keep board-clock selection state out of the fast HDMI reset network.
  // S1 may reset this PLL while the selector continues on clk_27mhz.
  wire clock_ready = locked && !reset_button;
  CLKDIV #(.DIV_MODE("5"), .GSREN("false")) pixel_divider (
    .HCLKIN(serial_clk), .CLKOUT(pixel_clk),
    .RESETN(clock_ready), .CALIB(1'b1)
  );
  // Assert reset asynchronously; release after four stable pixel clocks.
  reg [3:0] reset_pipe;
  always @(posedge pixel_clk or negedge clock_ready) begin
    if (!clock_ready) reset_pipe <= 4'b1111;
    else reset_pipe <= {reset_pipe[2:0], 1'b0};
  end
  wire reset = reset_pipe[3];
  reg [15:0] power_reset=16'hffff;
  always @(posedge clk_27mhz)begin
    if(system_reset)power_reset<=16'hffff;
    else power_reset<={power_reset[14:0],1'b0};
  end
  wire cpu_reset=power_reset[15];
  wire trap;
`ifdef ZORK_USB_HOST
  assign led_n = (!selection_done||mode_conflict)?selection_led_n:(!clock_ready||trap);
`else
  assign led_n = !clock_ready || trap;
`endif
  wire [23:0] rgb;
  wire de, hs, vs;
  wire [11:0] text_addr;wire [7:0] text_data,text_read;wire text_write;
  wire game_uart_rx, game_uart_tx;
`ifdef ZORK_USB_HOST
  wire [7:0] usb_key_data;
  wire usb_key_strobe;
  wire companion_reply;
  companion_keyboard usb_keyboard(.clk(clk_27mhz),.reset(transport_reset),
    .spi_cs_n(companion_cs_n),.spi_sck(companion_sck),.spi_mosi(companion_mosi),
    .spi_miso(companion_reply),.host_active(companion_active),
    .key_data(usb_key_data),.key_strobe(usb_key_strobe));
  // Leave the BL616-facing reply pin passive until USB is selected. Serial
  // mode must not advertise a Companion core or drive its SPI input. Continue
  // observing keyboard payloads so conflicting input can block UART and
  // blink the LED without suppressing HDMI. Game resets preserve transport.
  assign companion_miso=(selection_done&&!serial_selected)?companion_reply:1'bz;
  assign game_uart_rx=serial_enabled?uart_rx:1'b1;
  // In PC mode CS can be idle-low/undefined: it is unrelated to UART. Only
  // the selected mode and detected role guard may gate serial transmission.
  assign uart_tx=serial_enabled?game_uart_tx:1'b1;
`else
  assign game_uart_rx=uart_rx;
  assign uart_tx=game_uart_tx;
`endif
  zork_soc soc(.clk(clk_27mhz),.reset(cpu_reset),.uart_rx(game_uart_rx),.uart_tx(game_uart_tx),
`ifdef ZORK_USB_HOST
    .usb_key_data(usb_key_data),
    .input_mode_status({mode_conflict,companion_active,serial_selected,1'b1}),
    .usb_key_strobe(usb_key_strobe&&selection_done&&!serial_selected),
`endif
    .ps2_clk(ps2_clk),.ps2_data(ps2_data),.sd_miso(sd_miso),.sd_clk(sd_clk),
    .sd_mosi(sd_mosi),.sd_cs(sd_cs),.trap(trap),.text_addr(text_addr),
    .text_data(text_data),.text_write(text_write),.text_read(text_read),
    .O_sdram_clk(O_sdram_clk),.O_sdram_cke(O_sdram_cke),.O_sdram_cs_n(O_sdram_cs_n),
    .O_sdram_ras_n(O_sdram_ras_n),.O_sdram_cas_n(O_sdram_cas_n),
    .O_sdram_wen_n(O_sdram_wen_n),.O_sdram_addr(O_sdram_addr),
    .O_sdram_ba(O_sdram_ba),.O_sdram_dqm(O_sdram_dqm),.IO_sdram_dq(IO_sdram_dq));
  text_video video (.pixel_clk(pixel_clk), .reset(reset),.cpu_clk(clk_27mhz),
    .cpu_addr(text_addr),.cpu_data(text_data),.cpu_write(text_write),.cpu_read(text_read),
    .rgb(rgb), .de(de), .hsync(hs), .vsync(vs));
  wire [9:0] tmds [0:2];
  tmds_encoder blue (.clk(pixel_clk), .reset(reset), .data(rgb[7:0]),
    .de(de), .control({vs, hs}), .symbol(tmds[0]));
  tmds_encoder green (.clk(pixel_clk), .reset(reset), .data(rgb[15:8]),
    .de(de), .control(2'b00), .symbol(tmds[1]));
  tmds_encoder red (.clk(pixel_clk), .reset(reset), .data(rgb[23:16]),
    .de(de), .control(2'b00), .symbol(tmds[2]));
  wire [3:0] serial;
  genvar lane;
  generate for (lane = 0; lane < 3; lane = lane + 1) begin: lanes
    OSER10 serializer (.Q(serial[lane]), .D0(tmds[lane][0]),
      .D1(tmds[lane][1]), .D2(tmds[lane][2]), .D3(tmds[lane][3]),
      .D4(tmds[lane][4]), .D5(tmds[lane][5]), .D6(tmds[lane][6]),
      .D7(tmds[lane][7]), .D8(tmds[lane][8]), .D9(tmds[lane][9]),
      .PCLK(pixel_clk), .FCLK(serial_clk), .RESET(!clock_ready));
    TLVDS_OBUF output_buffer (.I(serial[lane]),
      .O(hdmi_data_p[lane]), .OB(hdmi_data_n[lane]));
  end endgenerate
  OSER10 clock_serializer (.Q(serial[3]),
    .D0(1'b1), .D1(1'b1), .D2(1'b1), .D3(1'b1), .D4(1'b1),
    .D5(1'b0), .D6(1'b0), .D7(1'b0), .D8(1'b0), .D9(1'b0),
    .PCLK(pixel_clk), .FCLK(serial_clk), .RESET(!clock_ready));
  TLVDS_OBUF clock_buffer (.I(serial[3]), .O(hdmi_clk_p), .OB(hdmi_clk_n));
endmodule
