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
    args = parser.parse_args()
    project = Path.cwd()
    output = run_pair(project, config_id=args.config_id, pair_start_layer=args.pair_start_layer, artifact_dir=project / "artifacts_hpca_xorflow/ramulator", keep_trace=args.keep_trace)
    results = project / "results_hpca_xorflow/03_ramulator_pairs.csv"
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
