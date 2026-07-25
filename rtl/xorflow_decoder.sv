// One 64-bit XORFLOW tile-decoder lane.
//
// Dense words apply 64 XOR toggles directly. Fixed-ID words contain four
// 14-bit event IDs. Gap words contain eight 8-bit nonnegative gaps and use a
// parallel-prefix adder to reconstruct eight 14-bit event IDs. Stream headers,
// counts, and support-cache arbitration are outside this combinational lane.
module xorflow_decoder_lane (
    input  wire [63:0] in_word,
    input  wire [1:0]  mode,       // 0=dense, 1=fixed IDs, 2=8-bit gaps
    input  wire [13:0] base_id,
    input  wire [3:0]  input_event_count,
    output wire [63:0] dense_mask,
    output wire [111:0] event_ids, // 8 packed 14-bit IDs
    output wire [7:0] event_valid
`ifdef FORMAL
    , output wire formal_dense_ok
    , output wire formal_nondense_ok
    , output wire formal_gap0_ok
    , output wire formal_gap7_ok
`endif
);
    wire [13:0] gap_s0 [0:7];
    wire [13:0] gap_s1 [0:7];
    wire [13:0] gap_s2 [0:7];
    wire [13:0] gap_s3 [0:7];
    genvar gap_lane;

    // A three-stage inclusive scan. This is intentionally structural: the
    // longest dependency is log2(8), rather than an eight-adder serial chain.
    generate
        for (gap_lane = 0; gap_lane < 8; gap_lane = gap_lane + 1) begin: prefix_scan
            assign gap_s0[gap_lane] = {6'b0, in_word[gap_lane*8 +: 8]};
            if (gap_lane >= 1)
                assign gap_s1[gap_lane] = gap_s0[gap_lane] + gap_s0[gap_lane-1];
            else
                assign gap_s1[gap_lane] = gap_s0[gap_lane];
            if (gap_lane >= 2)
                assign gap_s2[gap_lane] = gap_s1[gap_lane] + gap_s1[gap_lane-2];
            else
                assign gap_s2[gap_lane] = gap_s1[gap_lane];
            if (gap_lane >= 4)
                assign gap_s3[gap_lane] = gap_s2[gap_lane] + gap_s2[gap_lane-4];
            else
                assign gap_s3[gap_lane] = gap_s2[gap_lane];
            if (gap_lane < 4) begin: fixed_id_lane
                assign event_ids[gap_lane*14 +: 14] =
                    (mode == 2'd1) ? in_word[gap_lane*14 +: 14] :
                    (mode == 2'd2) ? base_id + gap_s3[gap_lane] : 14'b0;
            end else begin: gap_only_lane
                assign event_ids[gap_lane*14 +: 14] =
                    (mode == 2'd2) ? base_id + gap_s3[gap_lane] : 14'b0;
            end
            assign event_valid[gap_lane] =
                ((mode == 2'd1) && (gap_lane < 4)
                 && (gap_lane < input_event_count))
                || ((mode == 2'd2) && (gap_lane < input_event_count));
        end
    endgenerate

    assign dense_mask = (mode == 2'd0) ? in_word : 64'b0;

`ifdef FORMAL
    assign formal_dense_ok = (mode != 2'd0) || (dense_mask == in_word);
    assign formal_nondense_ok = (mode == 2'd0) || (dense_mask == 64'b0);
    assign formal_gap0_ok = (mode != 2'd2) ||
        (event_ids[13:0] == base_id + {6'b0, in_word[7:0]});
    assign formal_gap7_ok = (mode != 2'd2) ||
        (event_ids[111:98] == base_id + gap_s3[7]);
`endif
endmodule


// Thirty-two independent lanes match a 256-byte/cycle HBM interface.
module xorflow_decoder_bank (
    input  wire [2047:0] in_words,
    input  wire [63:0] modes,
    input  wire [447:0] base_ids,
    input  wire [127:0] event_counts,
    output wire [2047:0] dense_masks,
    output wire [3583:0] event_ids,
    output wire [255:0] event_valid
);
    genvar lane;
    generate
        for (lane = 0; lane < 32; lane = lane + 1) begin: lanes
            xorflow_decoder_lane decoder (
                .in_word(in_words[lane*64 +: 64]),
                .mode(modes[lane*2 +: 2]),
                .base_id(base_ids[lane*14 +: 14]),
                .input_event_count(event_counts[lane*4 +: 4]),
                .dense_mask(dense_masks[lane*64 +: 64]),
                .event_ids(event_ids[lane*112 +: 112]),
                .event_valid(event_valid[lane*8 +: 8])
            );
        end
    endgenerate
endmodule
