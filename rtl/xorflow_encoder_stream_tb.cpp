#include "Vxorflow_encoder_stream_engine.h"
#include "verilated_vcd_c.h"
#include <cstdint>
#include <iostream>
#include <string>

static void tick(Vxorflow_encoder_stream_engine* d, VerilatedVcdC* trace, vluint64_t& time) {
  d->clk = 0; d->eval(); if (trace) trace->dump(time++);
  d->clk = 1; d->eval(); if (trace) trace->dump(time++);
}

int main(int argc, char** argv) {
  std::string vcd_path;
  for (int i = 1; i < argc; ++i)
    if (std::string(argv[i]) == "--vcd" && i + 1 < argc) vcd_path = argv[++i];
  auto* d = new Vxorflow_encoder_stream_engine;
  VerilatedVcdC* trace = nullptr; vluint64_t time = 0;
  if (!vcd_path.empty()) {
    Verilated::traceEverOn(true); trace = new VerilatedVcdC; d->trace(trace, 99); trace->open(vcd_path.c_str());
  }
  d->rst_n = 0; d->in_valid = 0; d->out_ready = 1;
  tick(d, trace, time); tick(d, trace, time); d->rst_n = 1;
  for (unsigned row = 0; row < 32; ++row) {
    d->row_id = row;
    d->support_word = row == 0 ? ((1ULL << 1) | (1ULL << 3)) : 0ULL;
    d->anchor_word = 0;
    d->in_last = row == 31;
    d->descriptor_offset_bytes = 64;
    d->in_valid = 1;
    tick(d, trace, time);
    if (!d->in_ready && row != 31) {
      std::cerr << "input_not_ready row=" << row << " stateful stream stalled\n";
      return 2;
    }
  }
  d->in_valid = 0;
  bool seen = false;
  uint64_t first = 0;
  for (int cycle = 0; cycle < 2200 && !seen; ++cycle) {
    tick(d, trace, time);
    if (d->out_valid) { seen = true; first = d->out_word; }
  }
  bool ok = seen && d->selected_kind == 2 && d->event_count == 2 && d->stream_bits == 32;
  ok = ok && d->descriptor_offset == 64 && d->out_last;
  ok = ok && ((first & 0xffffULL) == 2);
  ok = ok && (((first >> 16) & 0x7ffULL) == 1);
  ok = ok && (((first >> 27) & 0xfULL) == 0); // one-bit gap width header
  ok = ok && (((first >> 31) & 0x1ULL) == 1); // ID 3 - ID 1 - 1
  std::cout << "status=" << (ok ? "PASS" : "FAIL")
            << " events=" << d->event_count
            << " bits=" << d->stream_bits
            << " format=" << (unsigned)d->selected_kind
            << " discovered=" << d->discovered_events << "\n";
  if (trace) { trace->dump(time++); trace->close(); delete trace; }
  delete d;
  return ok ? 0 : 1;
}
