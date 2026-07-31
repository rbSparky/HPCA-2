#include "Vxorflow_encoder_tile_engine.h"
#include <cstdint>
#include <iostream>

static void tick(Vxorflow_encoder_tile_engine* d) {
  d->clk = 0; d->eval(); d->clk = 1; d->eval();
}

int main() {
  auto* d = new Vxorflow_encoder_tile_engine;
  d->rst_n = 0; d->in_valid = 0; d->out_ready = 1;
  tick(d); tick(d); d->rst_n = 1;
  d->support_word = (1ULL<<1) | (1ULL<<3) | (1ULL<<7);
  d->anchor_word = 0; d->row_id = 0; d->in_last = 1;
  d->candidate_a0_bytes = 100; d->candidate_a2_bytes = 100; d->candidate_delta_bytes = 100;
  d->in_valid = 1; tick(d); d->in_valid = 0;
  bool ok = d->out_valid && d->xor_mask == d->support_word && d->event_count == 3;
  ok = ok && d->majority_mask == 0; // one-row tile: no strict majority bit
  // Three six-bit IDs are packed in ascending bit order: 1, 3, 7.
  ok = ok && ((d->packed_event_ids & 0x3f) == 1);
  ok = ok && (((d->packed_event_ids >> 6) & 0x3f) == 3);
  ok = ok && (((d->packed_event_ids >> 12) & 0x3f) == 7);
  std::cout << "status=" << (ok ? "PASS" : "FAIL")
            << " events=" << (unsigned)d->event_count
            << " selected_kind=" << (unsigned)d->selected_kind
            << " selected_bytes=" << d->selected_bytes << "\n";
  delete d;
  return ok ? 0 : 1;
}
