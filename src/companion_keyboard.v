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
  // Passive status observations; these never select a mode or veto UART.
  output reg discovery_seen,
  output reg hid_registration_seen,
  output reg announcement_seen,
  output reg announcement_strobe,
  output reg [223:0] announcement_frame,
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

  // Private draft announcement: 7e 01 "ZKCP" 01 1c, then status fields
  // and CRC-16/CCITT-FALSE (big-endian CRC, over the first 26 bytes).
  // This is not an upstream allocation. Initial receiver accepts Companion
  // reports only; Partner reporting requires an agreed ownership protocol.
  function [15:0] status_crc_byte;
    input [15:0] crc;
    input [7:0] data;
    reg [15:0] value;
    integer bit_index;
    begin
      value=crc^{data,8'b0};
      for(bit_index=0;bit_index<8;bit_index=bit_index+1)
        value=value[15]?(value<<1)^16'h1021:value<<1;
      status_crc_byte=value;
    end
  endfunction
  function status_frame_valid;
    input [223:0] frame;
    input [15:0] crc;
    reg [7:0] role,stage,flags;
    reg keyboard_present;
    begin
      role=frame[151:144];stage=frame[143:136];flags=frame[135:128];
      keyboard_present=frame[63:48]!=0;
      status_frame_valid=
        frame[223:208]==16'h7e01&&frame[207:176]==32'h5a4b4350&&
        frame[175:160]==16'h011c&&frame[159:152]==1&&
        role<=1&&stage<=3&&flags[7:4]==0&&
        flags[0]==(role==1)&&(!flags[1]||role==1)&&
        flags[3]==keyboard_present&&(!keyboard_present||flags[1])&&
        (stage!=1||(role==1&&flags[2:0]==3'b111))&&
        frame[31:16]==0&&frame[15:0]==crc;
    end
  endfunction

  reg [223:0] status_shift;
  reg [15:0] status_crc;
  reg discovery_complete,hid_complete,announcement_complete;
  reg transaction_toggle;
  // Do not clear the bundled status at CS deassertion: the board-clock
  // receiver must still be able to sample the finished transaction when
  // SCK stops. Clear completion on EVERY further bit, so a trailing partial
  // byte or extra byte invalidates the candidate before CS ends the frame.
  always @(negedge spi_sck or posedge reset) begin
    if(reset)begin
      status_shift<=0;status_crc<=16'hffff;
      discovery_complete<=0;hid_complete<=0;announcement_complete<=0;
      transaction_toggle<=0;
    end else if(!spi_cs_n)begin
      discovery_complete<=0;hid_complete<=0;announcement_complete<=0;
      if(byte_count==0&&bit_count==0)transaction_toggle<=!transaction_toggle;
      if(bit_count==7)begin
        if(byte_count==0)begin
          status_shift<={216'b0,received};
          status_crc<=status_crc_byte(16'hffff,received);
        end else begin
          if(byte_count<28)status_shift<={status_shift[215:0],received};
          if(byte_count<26)status_crc<=status_crc_byte(status_crc,received);
        end
        if(byte_count==6&&status_shift[47:0]==0&&received==0)
          discovery_complete<=1;
        if(byte_count==4&&status_shift[31:0]==32'h01000000&&received==0)
          hid_complete<=1;
        if(byte_count==27)
          announcement_complete<=status_frame_valid({status_shift[215:0],received},status_crc);
      end
    end
  end

  (* ASYNC_REG = "TRUE" *) reg [1:0] status_cs_sync,status_transaction_sync;
  reg status_cs_previous,status_transaction_seen;
  // Bundled-data CDC contract: after any transaction whose observations
  // must be delivered, CS stays high with no SCK for >=8 board clocks.
  // Custom status sender holds the SPI mutex through >=1 us idle before AND
  // after an announcement (27 MHz board clock). This leaves data/completion stable
  // until the synchronized CS rising event is consumed. No CS-derived clock
  // or oversampling of SPI data is used. Legacy probe observations are only
  // guaranteed with the same gap; keyboard delivery uses its existing CDC.
  always @(posedge clk or posedge reset)begin
    if(reset)begin
      status_cs_sync<=2'b11;status_cs_previous<=1;
      status_transaction_sync<=0;status_transaction_seen<=0;
      discovery_seen<=0;hid_registration_seen<=0;announcement_seen<=0;
      announcement_strobe<=0;announcement_frame<=0;
    end else begin
      status_cs_sync<={status_cs_sync[0],spi_cs_n};
      status_transaction_sync<={status_transaction_sync[0],transaction_toggle};
      status_cs_previous<=status_cs_sync[1];
      announcement_strobe<=0;
      // Settle the token during the pre-frame idle as well: a previously
      // unobserved runt CS pulse must not alias the next real transaction.
      if(status_cs_sync[1])status_transaction_seen<=status_transaction_sync[1];
      if(status_cs_sync[1]&&!status_cs_previous&&
         status_transaction_sync[1]!=status_transaction_seen)begin
        if(discovery_complete)discovery_seen<=1;
        if(hid_complete)hid_registration_seen<=1;
        if(announcement_complete)begin
          announcement_frame<=status_shift;
          announcement_seen<=1;
          announcement_strobe<=1;
        end
      end
    end
  end
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
