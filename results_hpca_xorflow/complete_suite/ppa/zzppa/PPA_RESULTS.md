# XORFLOW subsystem PPA

This table reports absolute subsystem PPA only. SRAMs are CACTI macros; the routed result is one decoder lane. The 32-lane line is a labelled linear estimate, not a bank-level routed macro. Host-area and host-power percentage gates remain **UNASSESSED**.

| Component | Status | Area (mm²) | Access/cycle (ns) | Fmax (MHz) | Provenance |
|---|---|---:|---:|---:|---|
| support_cache_sram | PASS |  |  |  | `artifacts_hpca_xorflow/complete_suite/ppa/zzppa/cacti/support_cache_8192.log` |
| support_cache_sram | PASS |  |  |  | `artifacts_hpca_xorflow/complete_suite/ppa/zzppa/cacti/support_cache_16384.log` |
| support_cache_sram | PASS |  |  |  | `artifacts_hpca_xorflow/complete_suite/ppa/zzppa/cacti/support_cache_32768.log` |
| support_cache_sram | PASS |  |  |  | `artifacts_hpca_xorflow/complete_suite/ppa/zzppa/cacti/support_cache_65536.log` |
| xorflow_decoder_lane_pipelined | PASS |  |  |  | `artifacts_hpca_xorflow/complete_suite/ppa/zzppa/rtl/xorflow_decoder_lane_pipelined_synthesis.log` |
| xorflow_decoder_bank_pipelined | PASS |  |  |  | `artifacts_hpca_xorflow/complete_suite/ppa/zzppa/rtl/xorflow_decoder_bank_pipelined_synthesis.log` |
| decoder_lane_placed | TOOL_FAILURE |  | 1.0 | 1458.88 | `artifacts_hpca_xorflow/complete_suite/ppa/zzppa/openroad/6_finish.rpt` |
| decoder_32lane_linear_estimate | UNASSESSED |  | 1.0 | 1458.88 | `linear extrapolation from decoder_lane_placed; bank integration is synthesized separately` |
