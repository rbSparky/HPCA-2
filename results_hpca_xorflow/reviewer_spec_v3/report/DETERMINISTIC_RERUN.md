# Reviewer-spec deterministic rerun

Two no-training finalization runs were executed against the frozen cached traces.

| Artifact | Run A SHA-256 | Run B SHA-256 |
|---|---|---|
| `RESULT_MANIFEST.csv` | `076d15856179852aee9e03c8fd956cd126e1cf3494200a08637a97538146cca7` | `076d15856179852aee9e03c8fd956cd126e1cf3494200a08637a97538146cca7` |
| `report/paper_summary.csv` | `dffa1bec8a5ce4d2169f1519d98f9b1fdfd607179cd3ea522408f328a6b5a7ab` | `dffa1bec8a5ce4d2169f1519d98f9b1fdfd607179cd3ea522408f328a6b5a7ab` |
| `schedule/system_cycles.csv` | `1a619b4b9045087e9f3113d1d54fba8ac01d7553b5f80a19fe957e577402587f` | `1a619b4b9045087e9f3113d1d54fba8ac01d7553b5f80a19fe957e577402587f` |
| `schedule/overlap_breakdown.csv` | `75fd5c946a07a4be60205bc36b9f96a52794865cac5129ed05056de98f973d7b` | `75fd5c946a07a4be60205bc36b9f96a52794865cac5129ed05056de98f973d7b` |
| `encoder/stream_equivalence.csv` | `151bf83ddcaa96313f522d2c2caf2a7cb5cd624593670134efa6d655de5eade0` | `151bf83ddcaa96313f522d2c2caf2a7cb5cd624593670134efa6d655de5eade0` |
| `quality/paired_quality.csv` | `27e72b9b1dcd8ee46a6ba483140a9ff024882ae92e03dc9777afebe4501f0523` | `27e72b9b1dcd8ee46a6ba483140a9ff024882ae92e03dc9777afebe4501f0523` |
| `decoder/decoder_cluster_openroad_summary.json` | `9512a46c116e845c836148a8fe650e65a68e2a0f41dd3895f4b2835783b869e7` | `9512a46c116e845c836148a8fe650e65a68e2a0f41dd3895f4b2835783b869e7` |

Result: **PASS** — all listed principal hashes match exactly.
Report timestamps are intentionally excluded from the principal hash set.
