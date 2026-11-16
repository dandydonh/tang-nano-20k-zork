// FPGA-Companion keyboard transport, SPI mode 1 (sample on falling edge).
// Protocol reference: FPGA-Companion 000fd039d793151822f08f1974df589fcba26d0b,
// src/ps2helper.c. Packet: target=1, command=1, legacy key, USB usage,
// then PS/2 set-2 bytes. No USB engine or SD access lives in this module.
//
// SCK may approach clk's frequency: receive in SCK domain, never oversample.
// The bundled byte remains stable until the next completed keyboard byte.
// Require at least four clk periods between emitted bytes, including across
// CS boundaries (27 MHz clk supports the BL616's ~26.67 MHz SPI comfortably).
// Reset must assert to both domains; it does not require SCK to be running.
module companion_keyboard (
  input wire clk, reset,
  input wire spi_cs_n, spi_sck, spi_mosi,
  output wire spi_miso,
  output wire host_active,
  output reg [7:0] key_data,
  output reg key_strobe
);
  reg [2:0] bit_count;
  reg [15:0] byte_count;
  reg [7:0] shift_in, target, command;
  wire [7:0] received = {shift_in[6:0], spi_mosi};

  always @(negedge spi_sck or posedge spi_cs_n or posedge reset) begin
    if (reset || spi_cs_n) begin
      bit_count <= 0;
      byte_count <= 0;
      shift_in <= 0;
      target <= 0;
      command <= 0;
    end else begin
      shift_in <= received;
      bit_count <= bit_count + 1'b1;
      if (bit_count == 7) begin
        if (byte_count == 0) target <= received;
        if (byte_count == 1) command <= received;
        if (byte_count != 16'hffff) byte_count <= byte_count + 1'b1;
      end
    end
  end

  reg [7:0] held_data;
  reg byte_toggle;
  reg host_seen;
  // A discovery/config request does not establish USB keyboard activity:
  // Companion sends status probes even when the FPGA never replies. Latch
  // only after receiving a keyboard payload, beyond its four-byte header.
  // CS boundaries and game resets preserve this configuration-time latch.
  always @(negedge spi_sck or posedge reset) begin
    if(reset)host_seen<=0;
    else if(!spi_cs_n&&bit_count==7&&byte_count>=4&&
      target==1&&command==1)host_seen<=1;
  end
  (* ASYNC_REG = "TRUE" *) reg [1:0] host_sync;
  always @(posedge clk or posedge reset) begin
    if(reset)host_sync<=0;
    else host_sync<={host_sync[0],host_seen};
  end
  assign host_active=host_sync[1];
  // CS resets the parser, but MUST NOT reset the mailbox toggle or data:
  // the last byte can still be crossing to clk after CS has deasserted.
  always @(negedge spi_sck or posedge reset) begin
    if (reset) begin
      held_data <= 0;
      byte_toggle <= 0;
    end else if (!spi_cs_n && bit_count == 7 &&
                 byte_count >= 4 && target == 1 && command == 1) begin
      held_data <= received;
      byte_toggle <= !byte_toggle;
    end
  end

  (* ASYNC_REG = "TRUE" *) reg [1:0] toggle_sync;
  reg toggle_seen;
  always @(posedge clk or posedge reset) begin
    if (reset) begin
      toggle_sync <= 0;
      toggle_seen <= 0;
      key_data <= 0;
      key_strobe <= 0;
    end else begin
      toggle_sync <= {toggle_sync[0], byte_toggle};
      toggle_seen <= toggle_sync[1];
      key_strobe <= toggle_sync[1] != toggle_seen;
      if (toggle_sync[1] != toggle_seen) key_data <= held_data;
    end
  end

  reg [7:0] reply;
  always @* begin
    // Unimplemented targets return zero. In particular, SDC status is never
    // "card ready"; no Companion command can reach Zork's physical SD bus.
    reply = 0;
    if (target == 0 && command == 0) begin
      if (byte_count == 3) reply = 8'h5c;
      if (byte_count == 4) reply = 8'h42;
    end
    if (target == 1 && command == 0 && byte_count == 3) reply = 1;
    // Companion v1.4.33's unsupported-config (zero first byte) path returns
    // without ending SPI, leaving its mutex held and blocking keyboard sends.
    // A short XML reply takes its explicit len<100 legacy fallback instead:
    // the transaction ends and no menu/config is installed. Keep the reply
    // NUL-terminated, including repeated reads and clocks beyond its end.
    if (target == 0 && command == 8) begin
      case (byte_count)
        3: reply = "<";
        4: reply = "c";
        5: reply = "o";
        6: reply = "n";
        7: reply = "f";
        8: reply = "i";
        9: reply = "g";
        10: reply = "/";
        11: reply = ">";
        default: reply = 0;
      endcase
    end
  end

  reg miso_bit;
  // Launch on rising edge, giving the master half a SPI cycle of setup.
  always @(posedge spi_sck or posedge spi_cs_n or posedge reset) begin
    if (reset || spi_cs_n) miso_bit <= 0;
    else miso_bit <= reply[7-bit_count];
  end
  assign spi_miso = spi_cs_n ? 1'bz : miso_bit;
endmodule
