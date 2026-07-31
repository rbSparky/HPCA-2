#include "Vxorflow_encoder_tile_engine.h"
#include "verilated_vcd_c.h"
#include <cstdint>
#include <iostream>
#include <string>

static void tick(Vxorflow_encoder_tile_engine* d, VerilatedVcdC* trace, vluint64_t& time) {
  d->clk = 0; d->eval(); if (trace) trace->dump(time++);
  d->clk = 1; d->eval(); if (trace) trace->dump(time++);
}

int main(int argc, char** argv) {
  std::string vcd_path;
  for (int i = 1; i < argc; ++i)
    if (std::string(argv[i]) == "--vcd" && i + 1 < argc) vcd_path = argv[++i];
  auto* d = new Vxorflow_encoder_tile_engine;
  VerilatedVcdC* trace = nullptr;
  vluint64_t time = 0;
  if (!vcd_path.empty()) {
    Verilated::traceEverOn(true);
    trace = new VerilatedVcdC;
    d->trace(trace, 99);
    trace->open(vcd_path.c_str());
  }
  d->rst_n = 0; d->in_valid = 0; d->out_ready = 1;
  tick(d, trace, time); tick(d, trace, time); d->rst_n = 1;
  d->support_word = (1ULL<<1) | (1ULL<<3) | (1ULL<<7);
  d->anchor_word = 0; d->row_id = 0; d->in_last = 1;
  d->candidate_a0_bytes = 100; d->candidate_a2_bytes = 100; d->candidate_delta_bytes = 100;
  d->in_valid = 1; tick(d, trace, time); d->in_valid = 0;
  bool ok = d->out_valid && d->xor_mask == d->support_word && d->event_count == 3;
  ok = ok && d->majority_mask == 0; // one-row tile: no strict majority bit
  // Three six-bit IDs are packed in ascending bit order: 1, 3, 7.
  const uint32_t low_ids = d->packed_event_ids[0];
  ok = ok && ((low_ids & 0x3f) == 1);
  ok = ok && (((low_ids >> 6) & 0x3f) == 3);
  ok = ok && (((low_ids >> 12) & 0x3f) == 7);
  std::cout << "status=" << (ok ? "PASS" : "FAIL")
            << " events=" << (unsigned)d->event_count
            << " selected_kind=" << (unsigned)d->selected_kind
            << " selected_bytes=" << d->selected_bytes << "\n";
  if (trace) { trace->dump(time++); trace->close(); delete trace; }
  delete d;
  return ok ? 0 : 1;
}
