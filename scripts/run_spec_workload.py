#!/usr/bin/env python3
"""Run the reviewer-spec serializer and causal replay for one cached workload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from xorflow.online_replay import derive_finite_retention, replay_trace
from xorflow.serializer_validation import validate_trace
from mosaic_validation.graph_order import symmetrized_edges_and_rcm
from mosaic_validation.hpca_xorflow_cli import _case


WORKLOADS = {
    "ogbn_arxiv_deepres8_w128_s7": ("OGBN-Arxiv", 7, 2_315_598),
    "ogbn_arxiv_deepres8_w128_s17": ("OGBN-Arxiv", 17, 2_315_598),
    "ogbn_arxiv_deepres8_w128_s27": ("OGBN-Arxiv", 27, 2_315_598),
    "reddit_deepres8_w128_s7_native": ("Reddit", 7, 114_615_892),
    "reddit_deepres8_w128_s17_native": ("Reddit", 17, 114_615_892),
    "reddit_deepres8_w128_s27_native": ("Reddit", 27, 114_615_892),
    "flickr_deepres8_w128_s7": ("Flickr", 7, 899_756),
    "flickr_deepres8_w128_s17": ("Flickr", 17, 899_756),
    "flickr_deepres8_w128_s27": ("Flickr", 27, 899_756),
    "yelp_deepres8_w128_s7_balanced_fallback": ("Yelp", 7, 13_954_819),
    "citeseer_deepres8_w128_s7": ("CiteSeer", 7, 0),
    "pubmed_gin8_w128_s7_overnight": ("PubMed", 7, 0),
    "pubmed_graphsage8_w128_s7_overnight": ("PubMed", 7, 0),
    "flickr_gin8_w128_s7_overnight": ("Flickr", 7, 0),
    "flickr_graphsage8_w128_s7_overnight": ("Flickr", 7, 0),
    "ogbn_arxiv_deepres4_w128_s7": ("OGBN-Arxiv", 7, 0),
    "ogbn_arxiv_deepres16_w128_s7": ("OGBN-Arxiv", 7, 0),
    "ogbn_arxiv_deepres24_w128_s7": ("OGBN-Arxiv", 7, 0),
    "ogbn_arxiv_deepres32_w128_s7": ("OGBN-Arxiv", 7, 0),
    "reddit_deepres12_w128_s7_native": ("Reddit", 7, 114_615_892),
    "reddit_deepres16_w128_s7_native": ("Reddit", 7, 114_615_892),
    "yelp_deepres12_w128_s7_balanced_fallback": ("Yelp", 7, 13_954_819),
    "yelp_deepres16_w128_s7_balanced_fallback": ("Yelp", 7, 13_954_819),
    "flickr_deepres16_w128_s7": ("Flickr", 7, 899_756),
    "ogbn_arxiv_deepres8_w64_s7": ("OGBN-Arxiv", 7, 0),
    "ogbn_arxiv_deepres8_w256_s7": ("OGBN-Arxiv", 7, 0),
    "ogbn_arxiv_gin8_w128_s7": ("OGBN-Arxiv", 7, 0),
    "ogbn_arxiv_graphsage8_w128_s7": ("OGBN-Arxiv", 7, 0),
    "ogbn_arxiv_gin8_residual_w128_s7": ("OGBN-Arxiv", 7, 0),
    "ogbn_arxiv_graphsage8_residual_w128_s7": ("OGBN-Arxiv", 7, 0),
    "chameleon_gcnii16": ("Chameleon", 7, 0),
    "cora_deepres28_w128": ("Cora", 7, 0),
    "pubmed_gcnii16": ("PubMed", 7, 0),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config-id", choices=tuple(WORKLOADS), required=True)
    parser.add_argument("--output", type=Path, default=Path("results_hpca_xorflow/reviewer_spec"))
    parser.add_argument("--skip-serializer", action="store_true")
    parser.add_argument("--policy", choices=("both", "REREAD", "FINITE_RETENTION"), default="both")
    args = parser.parse_args()
    project = args.project.resolve()
    output = (project / args.output).resolve() if not args.output.is_absolute() else args.output
    dataset, seed, edges = WORKLOADS[args.config_id]
    trace = project / "artifacts_hpca_xorflow" / "workloads" / args.config_id / "fp8_supports.npz"
    if not trace.exists():
        trace = project / "artifacts_final8" / "masks" / f"{args.config_id}_fp8_supports.npz"
    if not trace.exists():
        raise FileNotFoundError(trace)
    output.mkdir(parents=True, exist_ok=True)
    _, data, _ = _case(project, args.config_id)
    _, node_order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    edges = int(data.edge_index.shape[1])
    if not args.skip_serializer:
        validate_trace(
            trace, output / "serializer" / f"roundtrip_{args.config_id}.csv",
            source_name=args.config_id,
        )
    summaries = []
    if args.policy in {"both", "REREAD"}:
        summaries.append(replay_trace(
            trace_path=trace, output=output / "online_replay", run_id=args.config_id,
            dataset=dataset, model="deepres_v2", seed=seed, slice_width=128,
            tile_rows=128, anchor_policy="REREAD", retention_bytes=16 * 1024,
            edge_count=edges, node_order=node_order,
        ))
    if args.policy == "both":
        summaries.append(derive_finite_retention(output=output / "online_replay", run_id=args.config_id, retention_bytes=16 * 1024))
    elif args.policy == "FINITE_RETENTION":
        # A single exact REREAD stream is the policy-independent source.
        replay_trace(
            trace_path=trace, output=output / "online_replay", run_id=args.config_id,
            dataset=dataset, model="deepres_v2", seed=seed, slice_width=128,
            tile_rows=128, anchor_policy="REREAD", retention_bytes=16 * 1024,
            edge_count=edges, node_order=node_order,
        )
        summaries.append(derive_finite_retention(output=output / "online_replay", run_id=args.config_id, retention_bytes=16 * 1024))
    print(json.dumps(summaries, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
