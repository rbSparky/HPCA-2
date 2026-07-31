#include "Vxorflow_decoder_cluster8_debug.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>

static void tick(Vxorflow_decoder_cluster8_debug* d, VerilatedVcdC* trace, vluint64_t& time) {
  d->clk=0; d->eval(); if (trace) trace->dump(time++);
  d->clk=1; d->eval(); if (trace) trace->dump(time++);
}

int main(int argc, char** argv) {
  std::string vcd_path;
  std::string stream_path;
  for (int i = 1; i < argc; ++i) {
    if (std::string(argv[i]) == "--vcd" && i + 1 < argc) vcd_path = argv[++i];
    else if (std::string(argv[i]) == "--stream" && i + 1 < argc) stream_path = argv[++i];
  }
  auto* d = new Vxorflow_decoder_cluster8_debug;
  VerilatedVcdC* trace = nullptr;
  vluint64_t time = 0;
  if (!vcd_path.empty()) {
    Verilated::traceEverOn(true);
    trace = new VerilatedVcdC;
    d->trace(trace, 99);
    trace->open(vcd_path.c_str());
  }
  d->rst_n=0; d->in_valid=0; d->modes=0; d->event_counts=0;
  for (int i=0;i<16;i++) d->in_words[i]=0;
  for (int i=0;i<4;i++) d->base_ids[i]=0;
  tick(d, trace, time); tick(d, trace, time); d->rst_n=1;
  uint64_t words[8] = {0x0123456789abcdefULL,0xfedcba9876543210ULL,0x55aa55aa55aa55aaULL,0xaa55aa55aa55aa55ULL,1,2,4,8};
  if (!stream_path.empty()) {
    std::ifstream in(stream_path, std::ios::binary);
    uint64_t w = 0; int n = 0;
    while (n < 8 && in.read(reinterpret_cast<char*>(&w), sizeof(w))) words[n++] = w;
  }
  for (int i=0;i<8;i++) { d->in_words[2*i] = (uint32_t)words[i]; d->in_words[2*i+1] = (uint32_t)(words[i] >> 32); }
  d->in_valid=0xff; d->modes=0; d->event_counts=0;
  tick(d, trace, time);
  d->in_valid=0;
  tick(d, trace, time);
  bool ok=true;
  for (int i=0;i<8;i++) {
    uint64_t got=(uint64_t)d->dense_masks[2*i] | ((uint64_t)d->dense_masks[2*i+1] << 32);
    if (got != words[i]) ok=false;
  }
  std::cout << "status=" << (ok ? "PASS" : "FAIL") << " bank_conflicts=" << d->bank_conflicts
            << " same_word_collisions=" << d->same_word_collisions
            << " support_cache_valid=" << (int)d->support_cache_valid << "\n";
  if (trace) { trace->dump(time++); trace->close(); delete trace; }
  delete d; return ok ? 0 : 1;
}
