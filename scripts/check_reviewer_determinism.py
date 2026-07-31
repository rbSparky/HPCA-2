#!/usr/bin/env python3
"""Run the frozen finalization twice and record principal hash equality."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3"
FILES = (
    "RESULT_MANIFEST.csv",
    "report/paper_summary.csv",
    "schedule/system_cycles.csv",
    "schedule/overlap_breakdown.csv",
    "encoder/stream_equivalence.csv",
    "quality/paired_quality.csv",
    "decoder/decoder_cluster_openroad_summary.json",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def snapshot() -> dict[str, str]:
    return {rel: sha(V3 / rel) for rel in FILES}


def main() -> None:
    subprocess.run(["/home/rishabh/miniconda/envs/taugat_pyg/bin/python", "scripts/finalize_reviewer_spec.py"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    first = snapshot()
    subprocess.run(["/home/rishabh/miniconda/envs/taugat_pyg/bin/python", "scripts/finalize_reviewer_spec.py"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    second = snapshot()
    same = first == second
    lines = ["# Reviewer-spec deterministic rerun", "", "Two no-training finalization runs were executed against the frozen cached traces.", "", "| Artifact | Run A SHA-256 | Run B SHA-256 |", "|---|---|---|"]
    for rel in FILES:
        lines.append(f"| `{rel}` | `{first[rel]}` | `{second[rel]}` |")
    lines += ["", f"Result: **{'PASS' if same else 'FAIL'}** — all listed principal hashes {'match' if same else 'do not match'} exactly.", "Report timestamps are intentionally excluded from the principal hash set."]
    (V3 / "report" / "DETERMINISTIC_RERUN.md").write_text("\n".join(lines) + "\n")
    print("PASS" if same else "FAIL")
    raise SystemExit(0 if same else 1)


if __name__ == "__main__":
    main()
