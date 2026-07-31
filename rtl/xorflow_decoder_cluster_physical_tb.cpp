#include "Vxorflow_decoder_cluster8_pipelined.h"
#include "verilated_vcd_c.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

static void tick(Vxorflow_decoder_cluster8_pipelined* d, VerilatedVcdC* trace, vluint64_t& t) {
  d->clk = 0; d->eval(); if (trace) trace->dump(t++);
  d->clk = 1; d->eval(); if (trace) trace->dump(t++);
}

int main(int argc, char** argv) {
  std::string vcd;
  std::string stream;
  for (int i = 1; i < argc; ++i) {
    if (std::string(argv[i]) == "--vcd" && i + 1 < argc) vcd = argv[++i];
    else if (std::string(argv[i]) == "--stream" && i + 1 < argc) stream = argv[++i];
  }
  auto* d = new Vxorflow_decoder_cluster8_pipelined;
  VerilatedVcdC* trace = nullptr; vluint64_t t = 0;
  if (!vcd.empty()) {
    Verilated::traceEverOn(true); trace = new VerilatedVcdC; d->trace(trace, 99); trace->open(vcd.c_str());
  }
  d->rst_n = 0; d->in_valid = 0; d->modes = 0; d->event_counts = 0;
  for (int i = 0; i < 16; ++i) d->in_words[i] = 0;
  for (int i = 0; i < 4; ++i) d->base_ids[i] = 0;
  tick(d, trace, t); tick(d, trace, t); d->rst_n = 1;
  std::vector<uint64_t> words = {0x0123456789abcdefULL, 0xfedcba9876543210ULL,
                                 0x55aa55aa55aa55aaULL, 0xaa55aa55aa55aa55ULL, 1, 2, 4, 8};
  if (!stream.empty()) {
    std::ifstream in(stream, std::ios::binary); uint64_t w = 0; words.clear();
    while (in.read(reinterpret_cast<char*>(&w), sizeof(w)) && words.size() < 4096) words.push_back(w);
    if (words.empty()) words.push_back(0);
  }
  for (size_t base = 0; base < words.size(); base += 8) {
    d->in_valid = 0;
    for (size_t lane = 0; lane < 8; ++lane) {
      size_t idx = base + lane; uint64_t w = idx < words.size() ? words[idx] : 0;
      d->in_words[2*lane] = (uint32_t)w; d->in_words[2*lane+1] = (uint32_t)(w >> 32);
      if (idx < words.size()) d->in_valid |= (1u << lane);
    }
    tick(d, trace, t); d->in_valid = 0; tick(d, trace, t);
  }
  bool ok = d->support_cache_valid;
  std::cout << "status=" << (ok ? "PASS" : "FAIL") << " bank_conflicts=" << d->bank_conflicts
            << " same_word_collisions=" << d->same_word_collisions << "\n";
  if (trace) { trace->dump(t++); trace->close(); delete trace; }
  delete d; return ok ? 0 : 1;
}
