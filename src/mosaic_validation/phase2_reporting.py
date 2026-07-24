"""Phase-2 plots and report."""

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


def _save(fig, root, name):
    fig.tight_layout(); fig.savefig(root/f"{name}.png",dpi=150); fig.savefig(root/f"{name}.pdf"); plt.close(fig)


def plots(enc,modes,entropy,replay,segments,nulls,cal,root):
    for name,col in (("encoder_metadata_comparison","metadata_ratio_to_full_bitmap"),("encoder_byte_comparison","byte_ratio_to_independent")):
        fig,ax=plt.subplots(figsize=(8,4)); enc.groupby(["config_id","representation"])[col].median().unstack().plot.bar(ax=ax); _save(fig,root,name)
    fig,ax=plt.subplots(figsize=(8,4)); modes.groupby("config_id")[["fraction_full_core","fraction_lane_anchor","fraction_independent_sparse"]].mean().plot.bar(stacked=True,ax=ax); _save(fig,root,"anchor_mode_breakdown")
    fig,ax=plt.subplots(figsize=(6,4)); ax.scatter(modes.anchor_nnz_capture,modes.padding_fraction); ax.set(xlabel="capture",ylabel="padding"); _save(fig,root,"anchor_capture_vs_padding")
    fig,ax=plt.subplots(figsize=(6,4)); ax.scatter(entropy.event_density,entropy.coding_overhead_ratio); ax.set(xlabel="event density",ylabel="coding overhead"); _save(fig,root,"entropy_coding_efficiency")
    fig,ax=plt.subplots(figsize=(7,4)); replay[~replay.config_id.str.startswith("synthetic")].pivot(index="config_id",columns="W",values="replay_amplification").plot.bar(ax=ax); _save(fig,root,"chain_replay_vs_window")
    fig,ax=plt.subplots(figsize=(7,4)); segments.query("representation=='MOSAIC_ANCHOR' and eta==0.05 and rebuild_cost_fraction==0.01").set_index("config_id").mean_segment_length.plot.bar(ax=ax); _save(fig,root,"adaptive_segment_lengths")
    fig,ax=plt.subplots(figsize=(8,4)); nulls.pivot(index="config_id",columns="control_type",values="analytical_proxy_speedup_rho1_25").plot.bar(ax=ax); _save(fig,root,"real_vs_null_anchor")
    fig,ax=plt.subplots(figsize=(7,4)); cal.groupby("config_id")[["hybrid_speedup_vs_dense_combination"]].median().plot.bar(ax=ax); _save(fig,root,"analytical_vs_scalesim_hybrid")


def markdown(df):
    x=df.fillna("").astype(str); return "\n".join(["| "+" | ".join(x.columns)+" |","| "+" | ".join("---" for _ in x.columns)+" |",*["| "+" | ".join(r)+" |" for r in x.itertuples(index=False,name=None)]])


def report(root,decision,wall,summary,gates):
    indexed = summary.set_index("config_id")
    cora = indexed.loc["cora_gcnii16"]
    pubmed = indexed.loc["pubmed_gcnii16"]
    deep = indexed.loc["cora_deepres28_w128"]
    text=f"""# MOSAIC-Anchor Phase-2 results

## Executive decision

`{decision}`

Cached-trace wall-clock: {wall:.1f} seconds. No model was retrained.

## Gates

{markdown(gates)}

## Principal summary

{markdown(summary)}

## Interpretation discipline

This phase reports exact representation bytes, analytical compute proxies,
SCALE-Sim regular-path cycles, and a hybrid combination-path estimate. The
hybrid is **not** a measured end-to-end accelerator speedup. No full graph
aggregation or memory-system measurement is available yet.

CHAIN-GAP is an optimistic reference. Its deployability is limited by replay or
the N×F support-state lifetime. MOSAIC-Anchor is independently decodable from a
persistent anchor and one layer-local exception stream.

## Strongest results

The strongest positive result is the valid sparse deep target: analytical
anchor proxies are {deep.anchor_proxy_speedup_rho1_25:.3f} at rho=1.25 and
{deep.anchor_proxy_speedup_rho1_50:.3f} at rho=1.50, with exact independent
decoding. Principal Cora/PubMed byte ratios versus independently decodable R0
are {cora.anchor_byte_ratio:.3f}/{pubmed.anchor_byte_ratio:.3f}, and their
analytical rho=1.25 proxies are
{cora.anchor_proxy_speedup_rho1_25:.3f}/{pubmed.anchor_proxy_speedup_rho1_25:.3f}.

The strongest negative result is calibration: hybrid combination-path estimates
are only {cora.anchor_hybrid_combination_speedup:.3f} for Cora,
{pubmed.anchor_hybrid_combination_speedup:.3f} for PubMed, and
{deep.anchor_hybrid_combination_speedup:.3f} for the valid deep target. Anchor
feature coverage leaves GEMM K close to dense, then residual/decode work erases
the analytical slot-model advantage. CHAIN-GAP also increases metadata relative
to Delta-v1 and has principal replay amplification above 1.45×; it should remain
an upper-bound reference, not a deployable design.

## Phase-3 conclusion

Phase-3 accelerator implementation is **not yet justified**. Evidence supports
continued depthwise-anchor encoding work—not a spatial-only pivot—because G4,
G5, G6, and G7 pass and Anchor improves Phase-0 bytes. The next iteration must
reduce effective GEMM K or explicitly exploit lane masks in the regular path,
then repeat calibration before aggregation/memory-system implementation.

Phase-3 must still model event-decoder bandwidth, lane imbalance, anchor-hole
padding, layer barriers, aggregation dominance, weight-panel changes, and the
complete memory system.
"""
    (root/"PHASE2_RESULTS.md").write_text(text)
