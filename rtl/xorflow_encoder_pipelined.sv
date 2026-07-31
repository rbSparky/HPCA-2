// Finite ready/valid encoder boundary used to validate the software stream
// contract. Candidate lengths are produced by the exact software serializer;
// this block performs the hardware-visible minimum selector and one-word
// elastic output stage. It never drops a word under backpressure.
module xorflow_encoder_pipelined (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire [63:0] in_word,
    input  wire        in_last,
    input  wire [15:0] candidate_beicsr_bytes,
    input  wire [15:0] candidate_a0_bytes,
    input  wire [15:0] candidate_a2_bytes,
    input  wire [15:0] candidate_delta_bytes,
    output reg         out_valid,
    input  wire        out_ready,
    output reg  [63:0] out_word,
    output reg         out_last,
    output reg  [1:0]  selected_kind,
    output reg  [31:0] input_words,
    output reg  [31:0] output_words,
    output reg  [31:0] stall_cycles
);
  reg [1:0] selected_kind_next;
  reg [15:0] selected_bytes_next;
  always @* begin
    // Deterministic tie order: BEICSR, A0, A2, DELTA. Zero is not a legal
    // candidate length and therefore loses to every emitted candidate.
    selected_kind_next = 2'd0;
    selected_bytes_next = candidate_beicsr_bytes;
    if (candidate_a0_bytes != 0 && (selected_bytes_next == 0 || candidate_a0_bytes < selected_bytes_next)) begin
      selected_kind_next = 2'd1; selected_bytes_next = candidate_a0_bytes;
    end
    if (candidate_a2_bytes != 0 && (selected_bytes_next == 0 || candidate_a2_bytes < selected_bytes_next)) begin
      selected_kind_next = 2'd2; selected_bytes_next = candidate_a2_bytes;
    end
    if (candidate_delta_bytes != 0 && (selected_bytes_next == 0 || candidate_delta_bytes < selected_bytes_next)) begin
      selected_kind_next = 2'd3; selected_bytes_next = candidate_delta_bytes;
    end
  end

  assign in_ready = ~out_valid | out_ready;

  always @(posedge clk) begin
    if (!rst_n) begin
      out_valid <= 1'b0;
      out_word <= 64'b0;
      out_last <= 1'b0;
      selected_kind <= 2'b0;
      input_words <= 32'b0;
      output_words <= 32'b0;
      stall_cycles <= 32'b0;
    end else begin
      if (out_valid && out_ready) begin
        out_valid <= 1'b0;
        output_words <= output_words + 1'b1;
      end
      if (in_valid && in_ready) begin
        out_valid <= 1'b1;
        out_word <= in_word;
        out_last <= in_last;
        selected_kind <= selected_kind_next;
        input_words <= input_words + 1'b1;
      end else if (in_valid && !in_ready) begin
        stall_cycles <= stall_cycles + 1'b1;
      end
    end
  end
endmodule
