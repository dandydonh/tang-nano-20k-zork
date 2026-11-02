// DVI TMDS, one component per pixel, LSB transmitted first.
module tmds_encoder (
    input wire clk,
    input wire reset,
    input wire [7:0] data,
    input wire de,
    input wire [1:0] control,
    output reg [9:0] symbol
);
  integer i;
  reg [3:0] ones_data, ones_q;
  reg [8:0] q_comb, q;
  reg signed [5:0] disparity;
  reg signed [5:0] balance_comb, balance;
  reg de_pipe;
  reg [1:0] control_pipe;
  reg use_xnor;
  always @* begin
    ones_data = 0;
    for (i = 0; i < 8; i = i + 1) ones_data = ones_data + data[i];
    use_xnor = (ones_data > 4) || (ones_data == 4 && !data[0]);
    q_comb[0] = data[0];
    for (i = 1; i < 8; i = i + 1)
      q_comb[i] = q_comb[i-1] ^ data[i] ^ use_xnor;
    q_comb[8] = !use_xnor;
    ones_q = 0;
    for (i = 0; i < 8; i = i + 1) ones_q = ones_q + q_comb[i];
    balance_comb = $signed({1'b0, ones_q, 1'b0}) - 6'sd8;
  end
  // Separate transition minimization from running disparity correction.
  always @(posedge clk or posedge reset) begin
    if (reset) begin
      q <= 0;
      balance <= 0;
      de_pipe <= 0;
      control_pipe <= 0;
    end else begin
      q <= q_comb;
      balance <= balance_comb;
      de_pipe <= de;
      control_pipe <= control;
    end
  end
  always @(posedge clk or posedge reset) begin
    if (reset) begin
      symbol <= 10'b1101010100;
      disparity <= 0;
    end else if (!de_pipe) begin
      disparity <= 0;
      case (control_pipe)
        2'b00: symbol <= 10'b1101010100;
        2'b01: symbol <= 10'b0010101011;
        2'b10: symbol <= 10'b0101010100;
        2'b11: symbol <= 10'b1010101011;
      endcase
    end else if (disparity == 0 || balance == 0) begin
      symbol <= {~q[8], q[8], q[8] ? q[7:0] : ~q[7:0]};
      disparity <= disparity + (q[8] ? balance : -balance);
    end else if ((disparity > 0 && balance > 0) || (disparity < 0 && balance < 0)) begin
      symbol <= {1'b1, q[8], ~q[7:0]};
      disparity <= disparity - balance + (q[8] ? 6'sd2 : 6'sd0);
    end else begin
      symbol <= {1'b0, q[8], q[7:0]};
      disparity <= disparity + balance - (q[8] ? 6'sd0 : 6'sd2);
    end
  end
endmodule
