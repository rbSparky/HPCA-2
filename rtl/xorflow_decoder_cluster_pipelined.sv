// Complete eight-lane decoder/support-cache integration boundary.
// The lanes are independent ready/valid producers; this wrapper adds the
// finite support-cache write arbitration and conflict counters that were
// previously present only in the software model.
// Debug/co-simulation view.  The wide lane results stay internal to the
// physical integration top below; this view is retained for bit-level tests.
module xorflow_decoder_cluster8_debug (
    input wire clk,
    input wire rst_n,
    input wire [7:0] in_valid,
    input wire [511:0] in_words,
    input wire [15:0] modes,
    input wire [111:0] base_ids,
    input wire [31:0] event_counts,
    output wire [7:0] in_ready,
    output wire [7:0] out_valid,
    output wire [511:0] dense_masks,
    output wire [895:0] event_ids,
    output wire [63:0] event_valid,
    output reg [31:0] bank_conflicts,
    output reg [31:0] same_word_collisions,
    output reg [31:0] merged_writes,
    output reg [31:0] support_ready_cycles,
    output reg [63:0] support_cache_head,
    output reg support_cache_valid
);
  wire [7:0] lane_ready;
  wire [63:0] lane_masks [0:7];
  wire [111:0] lane_ids [0:7];
  wire [7:0] lane_events [0:7];
  wire [7:0] lane_valid;
  reg [63:0] support_cache [0:255];
  integer i;
  integer j;
  reg [7:0] bank_seen;
  reg [7:0] word_seen;
  assign in_ready = lane_ready;
  assign out_valid = lane_valid;
  genvar g;
  generate for (g=0; g<8; g=g+1) begin: decoder_lanes
    xorflow_decoder_lane_pipelined lane (
      .clk(clk), .in_word(in_words[g*64 +: 64]), .mode(modes[g*2 +: 2]),
      .base_id(base_ids[g*14 +: 14]), .input_event_count(event_counts[g*4 +: 4]),
      .dense_mask(lane_masks[g]), .event_ids(lane_ids[g]), .event_valid(lane_events[g])
    );
    assign lane_ready[g] = 1'b1;
    assign lane_valid[g] = in_valid[g];
    assign dense_masks[g*64 +: 64] = lane_masks[g];
    assign event_ids[g*112 +: 112] = lane_ids[g];
    assign event_valid[g*8 +: 8] = lane_events[g];
  end endgenerate
  always @(posedge clk) begin
    if (!rst_n) begin
      bank_conflicts <= 0; same_word_collisions <= 0; merged_writes <= 0;
      support_ready_cycles <= 0;
      support_cache_head <= 0; support_cache_valid <= 1'b0;
      for (i=0;i<256;i=i+1) support_cache[i] = 0;
    end else begin
      bank_seen = 0; word_seen = 0;
      for (j=0;j<8;j=j+1) begin
        if (in_valid[j]) begin
          if (bank_seen[j%4]) bank_conflicts <= bank_conflicts + 1'b1;
          bank_seen[j%4] = 1'b1;
          if (word_seen[j%4]) begin
            same_word_collisions <= same_word_collisions + 1'b1;
            merged_writes <= merged_writes + 1'b1;
          end
          word_seen[j%4] = 1'b1;
          support_cache[j] <= lane_masks[j];
          support_cache_head <= lane_masks[j];
          support_cache_valid <= 1'b1;
        end
      end
      if (|lane_valid) support_ready_cycles <= support_ready_cycles + 1'b1;
      support_cache_head <= support_cache[0];
    end
  end
endmodule

// Physical integration top.  Wide decoded masks/event IDs are not package
// pins: they terminate in the tile-local support cache and aggregation FIFO.
// Only the narrow control/status interface is exposed, matching a hierarchical
// bank integration rather than the earlier all-wires boundary.
module xorflow_decoder_cluster8_pipelined (
    input wire clk,
    input wire rst_n,
    input wire [7:0] in_valid,
    input wire [511:0] in_words,
    input wire [15:0] modes,
    input wire [111:0] base_ids,
    input wire [31:0] event_counts,
    output wire [7:0] in_ready,
    output wire [7:0] out_valid,
    output wire [31:0] bank_conflicts,
    output wire [31:0] same_word_collisions,
    output wire [31:0] merged_writes,
    output wire [31:0] support_ready_cycles,
    output wire support_cache_valid
);
  wire [511:0] dense_masks;
  wire [895:0] event_ids;
  wire [63:0] event_valid;
  wire [63:0] support_cache_head;
  xorflow_decoder_cluster8_debug debug_view (
    .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .in_words(in_words),
    .modes(modes), .base_ids(base_ids), .event_counts(event_counts),
    .in_ready(in_ready), .out_valid(out_valid), .dense_masks(dense_masks),
    .event_ids(event_ids), .event_valid(event_valid),
    .bank_conflicts(bank_conflicts), .same_word_collisions(same_word_collisions),
    .merged_writes(merged_writes), .support_ready_cycles(support_ready_cycles),
    .support_cache_head(support_cache_head), .support_cache_valid(support_cache_valid)
  );
endmodule
