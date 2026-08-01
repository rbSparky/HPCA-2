#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from mosaic_validation.hpca_ramulator import run_pair


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--pair-start-layer", type=int, default=4)
    parser.add_argument("--keep-trace", action="store_true")
    parser.add_argument("--artifact-dir", type=Path,
                        help="isolated timing-artifact directory")
    parser.add_argument("--results", type=Path,
                        help="isolated CSV path; defaults to the legacy aggregate")
    args = parser.parse_args()
    project = Path.cwd()
    artifact_dir = args.artifact_dir or project / "artifacts_hpca_xorflow/ramulator"
    if not artifact_dir.is_absolute():
        artifact_dir = project / artifact_dir
    output = run_pair(project, config_id=args.config_id, pair_start_layer=args.pair_start_layer, artifact_dir=artifact_dir, keep_trace=args.keep_trace)
    results = args.results or project / "results_hpca_xorflow/03_ramulator_pairs.csv"
    if not results.is_absolute():
        results = project / results
    results.parent.mkdir(parents=True, exist_ok=True)
    if results.exists():
        combined = pd.concat([pd.read_csv(results), output], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["config_id", "pair_start_layer", "format"], keep="last"
        )
    else:
        combined = output
    combined.to_csv(results, index=False)
    print(output.to_string(index=False))


if __name__ == "__main__":
    main()
