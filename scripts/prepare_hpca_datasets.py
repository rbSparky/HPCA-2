#!/usr/bin/env python3
"""Download/verify only the HPCA-suite public datasets with a manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from mosaic_validation.datasets import load_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("artifacts_hpca_xorflow/datasets.json"))
    parser.add_argument("--datasets", nargs="+", default=["Flickr", "Reddit", "Yelp"])
    args = parser.parse_args()
    existing = json.loads(args.output.read_text()) if args.output.exists() else []
    by_name = {str(row["dataset"]): row for row in existing}
    for name in args.datasets:
        data, features, classes = load_dataset(name, args.root)
        row = {
            "dataset": name,
            "nodes": int(data.num_nodes),
            "edges": int(data.edge_index.shape[1]),
            "features": features,
            "classes": classes,
            "multilabel": bool(data.y.ndim > 1),
        }
        by_name[name] = row
        print(row, flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps([by_name[name] for name in sorted(by_name)], indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
