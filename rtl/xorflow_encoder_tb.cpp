#include "Vxorflow_encoder_pipelined.h"
#include "verilated.h"

#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>

static void tick(Vxorflow_encoder_pipelined* dut) {
    dut->clk = 0; dut->eval();
    dut->clk = 1; dut->eval();
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: encoder_tb stream.bin\n";
        return 2;
    }
    std::ifstream in(argv[1], std::ios::binary);
    if (!in) { std::cerr << "cannot open stream\n"; return 2; }
    std::vector<uint64_t> words;
    uint64_t word;
    while (in.read(reinterpret_cast<char*>(&word), sizeof(word))) words.push_back(word);
    if (words.empty()) { std::cerr << "empty stream\n"; return 2; }

    Verilated::traceEverOn(false);
    auto* dut = new Vxorflow_encoder_pipelined;
    dut->rst_n = 0; dut->in_valid = 0; dut->out_ready = 1;
    dut->candidate_beicsr_bytes = 256;
    dut->candidate_a0_bytes = 192;
    dut->candidate_a2_bytes = 128;
    dut->candidate_delta_bytes = 160;
    tick(dut); tick(dut);
    dut->rst_n = 1;

    size_t sent = 0, received = 0;
    uint64_t cycles = 0;
    while (received < words.size() && cycles < words.size() * 8 + 32) {
        const bool can_send = sent < words.size() && dut->in_ready;
        dut->in_valid = can_send ? 1 : 0;
        if (can_send) {
            dut->in_word = words[sent];
            dut->in_last = (sent + 1 == words.size());
        }
        tick(dut);
        if (can_send) ++sent;
        if (dut->out_valid) {
            if (received >= words.size() || dut->out_word != words[received]) {
                std::cerr << "word mismatch at " << received << "\n";
                delete dut; return 1;
            }
            if (dut->out_last != (received + 1 == words.size())) {
                std::cerr << "last mismatch at " << received << "\n";
                delete dut; return 1;
            }
            ++received;
        }
        ++cycles;
    }
    dut->in_valid = 0;
    while (received < words.size() && cycles < words.size() * 8 + 64) {
        tick(dut);
        if (dut->out_valid) {
            if (dut->out_word != words[received] || dut->out_last != (received + 1 == words.size())) {
                std::cerr << "drain mismatch at " << received << "\n";
                delete dut; return 1;
            }
            ++received;
        }
        ++cycles;
    }
    const bool ok = sent == words.size() && received == words.size();
    std::cout << "sent=" << sent << " received=" << received << " cycles=" << cycles
              << " input_words=" << dut->input_words << " output_words=" << dut->output_words
              << " status=" << (ok ? "PASS" : "FAIL") << "\n";
    delete dut;
    return ok ? 0 : 1;
}
