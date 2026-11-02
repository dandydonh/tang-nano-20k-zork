`timescale 1ns/1ps
module tmds_encoder_tb;
  reg clk = 0, reset = 0, de = 0;
  reg [7:0] data;
  reg [1:0] control = 0;
  wire [9:0] symbol;
  tmds_encoder dut (.clk(clk), .reset(reset), .data(data), .de(de),
    .control(control), .symbol(symbol));
  integer n, bit_index, ones, running_balance = 0;
  reg previous_de = 0;
  reg [7:0] previous_data = 0, decoded, q;
  reg [1:0] previous_control = 0;
  reg [9:0] expected_control;
  initial begin
    #1 reset = 1;
    #4 clk = 1;
    #5 clk = 0;
    reset = 0;
    for (n = 0; n < 100001; n = n + 1) begin
      data = n < 65536 ? n % 256 : $random;
      de = n % 263 < 256;
      control = (n / 263) % 4;
      #5 clk = 1;
      #1;
      if (!previous_de) begin
        case (previous_control)
          0: expected_control = 10'b1101010100;
          1: expected_control = 10'b0010101011;
          2: expected_control = 10'b0101010100;
          3: expected_control = 10'b1010101011;
        endcase
        if (symbol !== expected_control) $fatal(1, "Incorrect control symbol");
        running_balance = 0;
      end else begin
        q = symbol[9] ? ~symbol[7:0] : symbol[7:0];
        decoded[0] = q[0];
        for (bit_index = 1; bit_index < 8; bit_index = bit_index + 1)
          decoded[bit_index] = q[bit_index] ^ q[bit_index-1] ^ !symbol[8];
        if (decoded !== previous_data)
          $fatal(1, "TMDS decode failed at %0d: symbol=%b decoded=%h expected=%h", n, symbol, decoded, previous_data);
        ones = 0;
        for (bit_index = 0; bit_index < 10; bit_index = bit_index + 1)
          ones = ones + symbol[bit_index];
        running_balance = running_balance + 2 * ones - 10;
        if (running_balance < -8 || running_balance > 8)
          $fatal(1, "TMDS running disparity out of bounds: %0d", running_balance);
        if (running_balance != $signed(dut.disparity))
          $fatal(1, "TMDS disparity accumulator mismatch");
      end
      previous_de = de;
      previous_data = data;
      previous_control = control;
      #4 clk = 0;
    end
    $display("PASS: 100000 TMDS symbols, data decoding, control codes and DC balance");
    $finish;
  end
endmodule
