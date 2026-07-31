#include "Vxorflow_decoder_cluster8_debug.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>

static void tick(Vxorflow_decoder_cluster8_debug* d) { d->clk=0; d->eval(); d->clk=1; d->eval(); }

int main() {
  auto* d = new Vxorflow_decoder_cluster8_debug;
  d->rst_n=0; d->in_valid=0; d->modes=0; d->event_counts=0;
  for (int i=0;i<16;i++) d->in_words[i]=0;
  for (int i=0;i<4;i++) d->base_ids[i]=0;
  tick(d); tick(d); d->rst_n=1;
  uint64_t words[8] = {0x0123456789abcdefULL,0xfedcba9876543210ULL,0x55aa55aa55aa55aaULL,0xaa55aa55aa55aa55ULL,1,2,4,8};
  for (int i=0;i<8;i++) { d->in_words[2*i] = (uint32_t)words[i]; d->in_words[2*i+1] = (uint32_t)(words[i] >> 32); }
  d->in_valid=0xff; d->modes=0; d->event_counts=0;
  tick(d);
  d->in_valid=0;
  tick(d);
  bool ok=true;
  for (int i=0;i<8;i++) {
    uint64_t got=(uint64_t)d->dense_masks[2*i] | ((uint64_t)d->dense_masks[2*i+1] << 32);
    if (got != words[i]) ok=false;
  }
  std::cout << "status=" << (ok ? "PASS" : "FAIL") << " bank_conflicts=" << d->bank_conflicts
            << " same_word_collisions=" << d->same_word_collisions
            << " support_cache_valid=" << (int)d->support_cache_valid << "\n";
  delete d; return ok ? 0 : 1;
}
