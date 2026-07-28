// Throughput-preserving experimental lane: one prefix pipeline boundary.
// A new word may enter every cycle; decoded output latency is one extra cycle.
module xorflow_decoder_lane_pipelined (
    input wire clk,
    input wire [63:0] in_word,
    input wire [1:0] mode,
    input wire [13:0] base_id,
    input wire [3:0] input_event_count,
    output reg [63:0] dense_mask,
    output reg [111:0] event_ids,
    output reg [7:0] event_valid
);
  wire [13:0] s0 [0:7]; wire [13:0] s1 [0:7]; wire [13:0] s2 [0:7];
  reg [13:0] s2_q [0:7]; reg [63:0] word_q; reg [1:0] mode_q;
  reg [13:0] base_q; reg [3:0] count_q;
  wire [13:0] s3 [0:7];
  genvar i;
  generate for (i=0;i<8;i=i+1) begin: prefix
    assign s0[i] = {6'b0,in_word[i*8 +: 8]};
    if (i>=1) assign s1[i] = s0[i]+s0[i-1]; else assign s1[i]=s0[i];
    if (i>=2) assign s2[i] = s1[i]+s1[i-2]; else assign s2[i]=s1[i];
    if (i>=4) assign s3[i] = s2_q[i]+s2_q[i-4]; else assign s3[i]=s2_q[i];
  end endgenerate
  integer k;
  always @(posedge clk) begin
    for (k=0;k<8;k=k+1) s2_q[k] <= s2[k];
    word_q <= in_word; mode_q <= mode; base_q <= base_id; count_q <= input_event_count;
    dense_mask <= (mode_q==2'd0) ? word_q : 64'b0;
    for (k=0;k<8;k=k+1) begin
      if (mode_q==2'd1 && k<4) event_ids[k*14 +: 14] <= word_q[k*14 +: 14];
      else if (mode_q==2'd2) event_ids[k*14 +: 14] <= base_q+s3[k];
      else event_ids[k*14 +: 14] <= 14'b0;
      event_valid[k] <= ((mode_q==2'd1)&&(k<4)&&(k<count_q)) || ((mode_q==2'd2)&&(k<count_q));
    end
  end
endmodule

// Hierarchical composition used by the accelerator integration: each physical
// lane is a separately placed decoder macro. The 2,048-bit stream is an
// internal HBM-buffer interface, not a package-level pin interface.
module xorflow_decoder_bank_pipelined (
    input wire clk,
    input wire [2047:0] in_words,
    input wire [63:0] modes,
    input wire [447:0] base_ids,
    input wire [127:0] event_counts,
    output wire [2047:0] dense_masks,
    output wire [3583:0] event_ids,
    output wire [255:0] event_valid
);
  genvar lane;
  generate for (lane=0; lane<32; lane=lane+1) begin: lanes
    xorflow_decoder_lane_pipelined decoder (
      .clk(clk), .in_word(in_words[lane*64 +: 64]), .mode(modes[lane*2 +: 2]),
      .base_id(base_ids[lane*14 +: 14]), .input_event_count(event_counts[lane*4 +: 4]),
      .dense_mask(dense_masks[lane*64 +: 64]), .event_ids(event_ids[lane*112 +: 112]),
      .event_valid(event_valid[lane*8 +: 8])
    );
  end endgenerate
endmodule
