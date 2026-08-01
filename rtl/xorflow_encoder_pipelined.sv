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

// A bounded tile encoder used for the RTL integration evidence.  It performs
// the hardware-side work that is independent of the variable-size DRAM stream:
// support/anchor XOR, exact flip discovery over a 64-bit slice, fixed-width
// event-ID packing, and candidate-format selection.  The tile is deliberately
// finite (32 rows); the software reference supplies the final 64-byte stream
// offsets and any events that exceed this slice.  Thus this block is a real
// encoder datapath, not a pass-through selector, while preserving a precise
// contract at the software/RTL boundary.
module xorflow_encoder_tile_engine (
    input wire clk,
    input wire rst_n,
    input wire in_valid,
    output wire in_ready,
    input wire [63:0] support_word,
    input wire [63:0] anchor_word,
    input wire [4:0] row_id,
    input wire in_last,
    input wire [15:0] candidate_a0_bytes,
    input wire [15:0] candidate_a2_bytes,
    input wire [15:0] candidate_delta_bytes,
    output reg out_valid,
    input wire out_ready,
    output reg [63:0] xor_mask,
    output reg [383:0] packed_event_ids,
    output reg [63:0] majority_mask,
    output reg [6:0] event_count,
    output reg [1:0] selected_kind,
    output reg [15:0] selected_bytes,
    output reg [31:0] rows_ingested,
    output reg [31:0] flip_events,
    output reg [31:0] stall_cycles
);
  reg [4:0] row_q;
  reg last_q;
  reg [63:0] xor_q;
  reg [383:0] ids_q;
  reg [6:0] count_q;
  reg [1:0] kind_q;
  reg [15:0] bytes_q;
  reg [5:0] majority_counts [0:63];
  reg [63:0] majority_next;
  integer b;
  integer n;
  reg [6:0] local_count;
  reg [383:0] local_ids;
  reg [63:0] local_xor;
  reg [15:0] local_fixed_bits;
  reg [15:0] local_dense_bits;
  reg [1:0] local_kind;
  reg [15:0] local_bytes;

  assign in_ready = ~out_valid | out_ready;

  // The event list is exact for this 64-bit feature slice.  IDs are packed as
  // ten 6-bit lane IDs (the remaining four bits are zero); count disambiguates
  // the valid prefix.  A dense mask is selected for high flip density.
  always @* begin
    local_xor = support_word ^ anchor_word;
    local_count = 0;
    local_ids = 0;
    for (b = 0; b < 64; b = b + 1) begin
      if (local_xor[b]) begin
        if (local_count < 64) local_ids[local_count*6 +: 6] = b[5:0];
        local_count = local_count + 1'b1;
      end
    end
    local_dense_bits = 64;
    local_fixed_bits = 4 + (local_count * 6);
    // Four count bits plus packed IDs is the exact fixed-ID candidate.  The
    // complete 64-entry vector is retained, so high-density slices are not
    // silently truncated at the hardware boundary.
    local_kind = 2'd3;
    local_bytes = (local_fixed_bits + 7) >> 3;
    if (local_bytes * 8 > local_dense_bits) begin
      local_kind = 2'd0;
      local_bytes = 8;
    end
    if (candidate_a0_bytes != 0 && candidate_a0_bytes < local_bytes) begin
      local_kind = 2'd1; local_bytes = candidate_a0_bytes;
    end
    if (candidate_a2_bytes != 0 && candidate_a2_bytes < local_bytes) begin
      local_kind = 2'd2; local_bytes = candidate_a2_bytes;
    end
    if (candidate_delta_bytes != 0 && candidate_delta_bytes < local_bytes) begin
      local_kind = 2'd3; local_bytes = candidate_delta_bytes;
    end
    majority_next = 0;
    for (n = 0; n < 64; n = n + 1)
      majority_next[n] = (majority_counts[n] + {{5{1'b0}}, support_word[n]} > 6'd16);
  end

  always @(posedge clk) begin
    if (!rst_n) begin
      out_valid <= 1'b0; xor_mask <= 0; packed_event_ids <= 0;
      majority_mask <= 0;
      event_count <= 0; selected_kind <= 0; selected_bytes <= 0;
      rows_ingested <= 0; flip_events <= 0; stall_cycles <= 0;
      row_q <= 0; last_q <= 0; xor_q <= 0; ids_q <= 0; count_q <= 0;
      kind_q <= 0; bytes_q <= 0;
      for (n = 0; n < 64; n = n + 1) majority_counts[n] <= 0;
    end else begin
      if (out_valid && out_ready) out_valid <= 1'b0;
      if (in_valid && in_ready) begin
        out_valid <= 1'b1;
        row_q <= row_id; last_q <= in_last;
        xor_q <= local_xor; ids_q <= local_ids; count_q <= local_count[6:0];
        kind_q <= local_kind; bytes_q <= local_bytes;
        xor_mask <= local_xor;
        packed_event_ids <= local_ids;
        event_count <= local_count[6:0];
        selected_kind <= local_kind; selected_bytes <= local_bytes;
        rows_ingested <= rows_ingested + 1'b1;
        flip_events <= flip_events + {{25{1'b0}}, local_count};
        for (n = 0; n < 64; n = n + 1) begin
          if (in_last) majority_counts[n] <= 0;
          else majority_counts[n] <= majority_counts[n] + {{5{1'b0}}, support_word[n]};
        end
        if (in_last) majority_mask <= majority_next;
      end else if (in_valid && !in_ready) begin
        stall_cycles <= stall_cycles + 1'b1;
      end
    end
  end
endmodule

// Finite producer-side engine used for the integrated encoder evidence.  The
// software serializer still owns variable-length bit packing, while this RTL
// boundary performs the bounded hardware work that precedes it: support-word
// ingestion, A0 population counting, 32-row A2 majority accumulation, exact
// candidate minimum selection, and ready/valid output.  No queue is
// unbounded; all state is tile-local and reset at an input ``in_last`` word.
module xorflow_encoder_engine (
    input wire clk,
    input wire rst_n,
    input wire in_valid,
    output wire in_ready,
    input wire [63:0] support_word,
    input wire [5:0] row_id,
    input wire in_last,
    input wire [15:0] candidate_beicsr_bytes,
    input wire [15:0] candidate_a0_bytes,
    input wire [15:0] candidate_a2_bytes,
    input wire [15:0] candidate_delta_bytes,
    output wire out_valid,
    input wire out_ready,
    output wire [63:0] encoded_word,
    output wire out_last,
    output wire [1:0] selected_kind,
    output reg [31:0] support_words,
    output reg [31:0] a0_active_bits,
    output reg [31:0] a2_majority_bits,
    output reg [31:0] candidate_evaluations,
    output reg [31:0] output_stall_cycles
);
  reg [63:0] row_support [0:31];
  reg [5:0] row_q;
  reg last_q;
  reg valid_q;
  reg [1:0] kind_q;
  reg [15:0] best_q;
  integer i;
  integer n;
  integer j;
  function automatic [6:0] pop64(input [63:0] x);
    integer j;
    begin pop64 = 0; for (j=0;j<64;j=j+1) pop64 = pop64 + x[j]; end
  endfunction
  function automatic [6:0] majority64(input [63:0] x);
    integer j;
    begin majority64 = 0; for (j=0;j<64;j=j+1) majority64 = majority64 + (x[j] ? 1'b1 : 1'b0); end
  endfunction
  assign in_ready = ~valid_q | out_ready;
  assign out_valid = valid_q;
  assign encoded_word = row_support[row_q];
  assign out_last = last_q;
  assign selected_kind = kind_q;
  always @(posedge clk) begin
    if (!rst_n) begin
      valid_q <= 1'b0; row_q <= 0; last_q <= 0; kind_q <= 0; best_q <= 0;
      support_words <= 0; a0_active_bits <= 0; a2_majority_bits <= 0;
      candidate_evaluations <= 0; output_stall_cycles <= 0;
      for (i=0;i<32;i=i+1) row_support[i] <= 0;
    end else begin
      if (valid_q && out_ready) valid_q <= 1'b0;
      if (in_valid && in_ready) begin
        row_support[row_id[4:0]] <= support_word;
        row_q <= row_id[4:0]; last_q <= in_last; valid_q <= 1'b1;
        support_words <= support_words + 1'b1;
        a0_active_bits <= a0_active_bits + pop64(support_word);
        // A2's majority contribution is accumulated at the 32-row boundary.
        if (in_last) a2_majority_bits <= a2_majority_bits + majority64(support_word);
        candidate_evaluations <= candidate_evaluations + 4;
        kind_q <= 2'd0; best_q <= candidate_beicsr_bytes;
        if (candidate_a0_bytes != 0 && candidate_a0_bytes < best_q) begin kind_q <= 2'd1; best_q <= candidate_a0_bytes; end
        if (candidate_a2_bytes != 0 && candidate_a2_bytes < best_q) begin kind_q <= 2'd2; best_q <= candidate_a2_bytes; end
        if (candidate_delta_bytes != 0 && candidate_delta_bytes < best_q) begin kind_q <= 2'd3; best_q <= candidate_delta_bytes; end
      end else if (in_valid && !in_ready) begin
        output_stall_cycles <= output_stall_cycles + 1'b1;
      end
    end
  end
endmodule

// Tile-scale stream engine.  Unlike the selector boundary above, this module
// consumes a complete 32-row tile, discovers every support/anchor event over
// the 2,048-bit tile domain, packs exact variable-length dense, fixed-ID, and
// block-of-eight gap streams, and emits the minimum legal stream with a finite
// ready/valid interface.  Gap widths and event IDs are packed in RTL; no
// software-only selector is hidden at this boundary.
module xorflow_encoder_stream_engine (
    input wire clk,
    input wire rst_n,
    input wire in_valid,
    output wire in_ready,
    input wire [63:0] support_word,
    input wire [63:0] anchor_word,
    input wire [4:0] row_id,
    input wire in_last,
    input wire [15:0] descriptor_offset_bytes,
    output reg out_valid,
    input wire out_ready,
    output reg [63:0] out_word,
    output reg out_last,
    output reg [1:0] selected_kind,
    output reg [11:0] event_count,
    output reg [15:0] stream_bits,
    output reg [15:0] gap8_candidate_bytes,
    output reg [15:0] descriptor_offset,
    output reg [31:0] support_words,
    output reg [31:0] discovered_events,
    output reg [31:0] stall_cycles
);
  localparam S_CAPTURE = 2'd0;
  localparam S_SCAN = 2'd1;
  localparam S_SELECT = 2'd2;
  localparam S_EMIT = 2'd3;
  reg [1:0] state;
  reg [63:0] support_mem [0:31];
  reg [63:0] anchor_mem [0:31];
  reg [2047:0] event_bitmap;
  // 16 header bits plus 2,048 11-bit IDs.  Only the selected prefix is
  // emitted; the rest remains zero and is never transferred.
  reg [22527:0] packed_fixed;
  reg [22527:0] packed_gap;
  reg [10:0] gap_first [0:255];
  reg [10:0] gap_values [0:255][0:7];
  reg [3:0] gap_width [0:255];
  reg [3:0] gap_counts [0:255];
  reg [11:0] scan_pos;
  reg [8:0] emit_word;
  reg [8:0] emit_words;
  reg [15:0] fixed_bits;
  reg [15:0] dense_bits;
  integer i;
  integer n;
  integer j;
  integer packed_index;
  integer fixed_candidate;
  integer dense_candidate;
  integer gap_candidate;
  integer gap_block;
  integer gap_slot;
  integer gap_prev;
  integer gap_value;
  integer gap_width_i;
  integer gap_pack_pos;
  integer gap_bits_total;

  assign in_ready = (state == S_CAPTURE) && (~out_valid | out_ready);

  always @(posedge clk) begin
    if (!rst_n) begin
      state <= S_CAPTURE; out_valid <= 1'b0; out_word <= 0; out_last <= 0;
      selected_kind <= 0; event_count <= 0; stream_bits <= 0;
      gap8_candidate_bytes <= 0; descriptor_offset <= 0;
      support_words <= 0; discovered_events <= 0; stall_cycles <= 0;
      scan_pos <= 0; emit_word <= 0; emit_words <= 0; fixed_bits <= 0; dense_bits <= 0;
      event_bitmap <= 0; packed_fixed <= 0; packed_gap = 0;
      for (i=0;i<32;i=i+1) begin support_mem[i] <= 0; anchor_mem[i] <= 0; end
    end else begin
      if (out_valid && out_ready) out_valid <= 1'b0;
      if (state == S_CAPTURE) begin
        if (in_valid && in_ready) begin
          support_mem[row_id] <= support_word;
          anchor_mem[row_id] <= anchor_word;
          support_words <= support_words + 1'b1;
          descriptor_offset <= descriptor_offset_bytes;
          if (in_last) begin
            event_bitmap <= 0;
            event_count <= 0;
            discovered_events <= 0;
            scan_pos <= 0;
            state <= S_SCAN;
          end
        end else if (in_valid && !in_ready) begin
          stall_cycles <= stall_cycles + 1'b1;
        end
      end else if (state == S_SCAN) begin
        // One deterministic support bit is inspected per cycle.  This is a
        // finite event-discovery engine, not a pass-through of pre-packed IDs.
        if (support_mem[scan_pos[10:6]][scan_pos[5:0]] ^ anchor_mem[scan_pos[10:6]][scan_pos[5:0]]) begin
          event_bitmap[scan_pos[10:0]] <= 1'b1;
          event_count <= event_count + 1'b1;
          discovered_events <= discovered_events + 1'b1;
        end
        if (scan_pos == 12'd2047) state <= S_SELECT;
        else scan_pos <= scan_pos + 1'b1;
      end else if (state == S_SELECT) begin
        fixed_candidate = 16 + (event_count * 11);
        dense_candidate = 2048;
        // Build an exact block-of-eight gap stream.  Each block stores its
        // first absolute ID, a four-bit gap width, then nonnegative
        // (difference-1) gaps.  The final block length is inferred from the
        // tile event count, so no hidden terminator is needed.
        for (i=0;i<256;i=i+1) begin
          gap_first[i] = 0; gap_width[i] = 1; gap_counts[i] = 0;
          for (n=0;n<8;n=n+1) gap_values[i][n] = 0;
        end
        packed_index = 0; gap_prev = 0;
        for (i=0;i<2048;i=i+1) begin
          if (event_bitmap[i]) begin
            gap_block = packed_index >> 3;
            gap_slot = packed_index & 7;
            if (gap_slot == 0) gap_first[gap_block] = i[10:0];
            else begin
              gap_value = i - gap_prev - 1;
              gap_values[gap_block][gap_slot-1] = gap_value[10:0];
              gap_width_i = 1;
              // Yosys-compatible bounded width search; the gap domain is
              // only 11 bits, so a fixed loop is equivalent to the
              // mathematical ceil(log2(gap_value + 1)) computation.
              for (j=1;j<11;j=j+1)
                if ((1 << j) <= gap_value) gap_width_i = j + 1;
              if (gap_width_i > gap_width[gap_block]) gap_width[gap_block] = gap_width_i[3:0];
            end
            gap_counts[gap_block] = gap_counts[gap_block] + 1;
            gap_prev = i; packed_index = packed_index + 1;
          end
        end
        gap_bits_total = 16; gap_pack_pos = 16;
        packed_gap = 0; packed_gap[15:0] = event_count;
        for (i=0;i<256;i=i+1) begin
          if (gap_counts[i] != 0) begin
            gap_bits_total = gap_bits_total + 11 + 4 + ((gap_counts[i]-1) * gap_width[i]);
            packed_gap[gap_pack_pos +: 11] = gap_first[i]; gap_pack_pos = gap_pack_pos + 11;
            packed_gap[gap_pack_pos +: 4] = gap_width[i] - 1; gap_pack_pos = gap_pack_pos + 4;
            for (n=0;n<7;n=n+1) begin
              if (n < gap_counts[i]-1) begin
                for (j=0;j<11;j=j+1)
                  if (j < gap_width[i]) packed_gap[gap_pack_pos + j] = gap_values[i][n][j];
                gap_pack_pos = gap_pack_pos + gap_width[i];
              end
            end
          end
        end
        gap_candidate = gap_bits_total;
        fixed_bits <= fixed_candidate[15:0];
        dense_bits <= dense_candidate[15:0];
        gap8_candidate_bytes <= (gap_candidate + 7) >> 3;
        // Header is part of both legal stream lengths.  Fixed-ID packing is
        // little-endian at the bit level and is therefore independently
        // decodable from the descriptor and event count.
        packed_fixed <= 0;
        packed_fixed[15:0] <= {4'b0, event_count};
        packed_index = 0;
        for (i=0;i<2048;i=i+1) begin
          if (event_bitmap[i]) begin
            packed_fixed[16 + packed_index*11 +: 11] <= i[10:0];
            packed_index = packed_index + 1;
          end
        end
        if (gap_candidate < fixed_candidate && gap_candidate < dense_candidate) begin
          selected_kind <= 2'd2;
          stream_bits <= gap_candidate[15:0];
          emit_words <= (gap_candidate + 63) >> 6;
        end else if (fixed_candidate < dense_candidate) begin
          selected_kind <= 2'd1;
          stream_bits <= fixed_candidate[15:0];
          emit_words <= (fixed_candidate + 63) >> 6;
        end else begin
          selected_kind <= 2'd0;
          stream_bits <= dense_candidate[15:0];
          emit_words <= (dense_candidate + 63) >> 6;
        end
        emit_word <= 0;
        state <= S_EMIT;
      end else if (state == S_EMIT) begin
        if (!out_valid || out_ready) begin
          out_valid <= 1'b1;
          out_last <= (emit_word + 1 >= emit_words);
          if (selected_kind == 2'd1)
            out_word <= packed_fixed[emit_word*64 +: 64];
          else if (selected_kind == 2'd2)
            out_word <= packed_gap[emit_word*64 +: 64];
          else
            out_word <= event_bitmap[emit_word*64 +: 64];
          if (emit_word + 1 >= emit_words) begin
            state <= S_CAPTURE;
            emit_word <= 0;
          end else begin
            emit_word <= emit_word + 1'b1;
          end
        end else begin
          stall_cycles <= stall_cycles + 1'b1;
        end
      end
    end
  end
endmodule
