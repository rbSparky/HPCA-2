#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <random>
#include "verilated.h"
#include "Vxorflow_decoder_lane_pipelined.h"

struct Ref { uint64_t dense; std::array<uint16_t,8> ids; uint8_t valid; };
static Ref reference(uint64_t word, uint8_t mode, uint16_t base, uint8_t count) {
  Ref out{};
  if (mode == 0) out.dense = word;
  for (unsigned i=0;i<8;i++) {
    if (mode == 1 && i < 4) out.ids[i] = (word >> (14*i)) & 0x3fff;
    if (mode == 2) { uint16_t total=0; for (unsigned j=0;j<=i;j++) total += (word >> (8*j)) & 0xff; out.ids[i]=(base+total)&0x3fff; }
    if ((mode==1 && i<4 && i<count) || (mode==2 && i<count)) out.valid |= uint8_t(1u<<i);
  }
  return out;
}
static uint16_t get_id(const Vxorflow_decoder_lane_pipelined* top, unsigned i) {
  const unsigned bit = 14*i, wi = bit/32, shift = bit%32;
  uint64_t raw = top->event_ids[wi] >> shift;
  if (shift > 18) raw |= uint64_t(top->event_ids[wi+1]) << (32-shift);
  return raw & 0x3fff;
}
int main() {
  Vxorflow_decoder_lane_pipelined top; std::mt19937_64 rng(7); Ref previous{}; bool have_previous=false;
  for (int cycle=0;cycle<10000;cycle++) {
    const uint64_t word=rng(); const uint8_t mode=rng()%3; const uint16_t base=rng()&0x3fff; const uint8_t count=rng()%9;
    top.clk=0; top.in_word=word; top.mode=mode; top.base_id=base; top.input_event_count=count; top.eval();
    top.clk=1; top.eval();
    if (have_previous) {
      if (top.dense_mask != previous.dense || top.event_valid != previous.valid) { std::cerr << "scalar mismatch at cycle " << cycle << "\n"; return 1; }
      for (unsigned i=0;i<8;i++) if (get_id(&top,i)!=previous.ids[i]) { std::cerr << "id mismatch at cycle " << cycle << " lane " << i << "\n"; return 1; }
    }
    previous=reference(word,mode,base,count); have_previous=true;
  }
  std::cout << "PASS cycles=9999 seed=7 latency=1 throughput_words_per_cycle=1\n";
  return 0;
}
