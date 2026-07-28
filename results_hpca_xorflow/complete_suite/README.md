# Consolidated HPCA XORFLOW Suite Results

This is the single result root for the paper-ready evaluation.

- `paper_suite_20260728_v1/` is the live, resumable GPU1 campaign. Its
  `CAMPAIGN.md`, `campaign_ledger.csv`, and `campaign_ledger.json` show every
  submitted task, status, log, dependency, and the deadline-aware estimate.
- `local_toolchain_20260728T221500Z/` contains the local reproducibility and
  package validation: full pytest, CUDA decoder microbenchmark, DRAMsim3 HBM2
  smoke, pipelined RTL co-simulation/synthesis, CACTI, and OpenROAD version.

Raw per-task logs are stored in the mirrored
`artifacts_hpca_xorflow/complete_suite/` hierarchy.  No result should be used
without its corresponding ledger row and artifact path.
