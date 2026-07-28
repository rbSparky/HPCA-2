module xorflow_decoder_lane_top (
  input wire clk,
  input wire [63:0] in_word,
  input wire [1:0] mode,
  input wire [13:0] base_id,
  input wire [3:0] input_event_count,
  output reg [63:0] dense_mask,
  output reg [111:0] event_ids,
  output reg [7:0] event_valid
);
  wire [63:0] dense_mask_w; wire [111:0] event_ids_w; wire [7:0] event_valid_w;
  xorflow_decoder_lane u_lane (.in_word(in_word), .mode(mode), .base_id(base_id),
    .input_event_count(input_event_count), .dense_mask(dense_mask_w),
    .event_ids(event_ids_w), .event_valid(event_valid_w));
  always @(posedge clk) begin
    dense_mask <= dense_mask_w; event_ids <= event_ids_w; event_valid <= event_valid_w;
  end
endmodule
