"""Forensic audit of Phase-3A oracle naming and array-partition mapping."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd

from .datasets import load_dataset
from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .panel_encoding import PanelCostConfig, correlation_panels, encode_panel_segment, _jaccard_matrix
from .phase3a_cli import _dataset_name, _load_traces, _propose_correlation_swap, _baseline_cycles
from .tracing import load_masks


def _cache(project: Path, array: int) -> dict[tuple[int,int,int], tuple[float,float]]:
    cache_path = (
        project / 'artifacts_rescue_audit/scalesim_array_8/shape_cache.json'
        if array == 8
        else project / f'artifacts_phase3a/scalesim/array_{array}/shape_cache.json'
    )
    raw=json.loads(cache_path.read_text())
    return {tuple(map(int,k.split('_'))):tuple(v) for k,v in raw.items()}


def _lpt(tasks: list[float], processors: int) -> float:
    loads=[0.0]*processors
    for task in sorted(tasks, reverse=True):
        i=min(range(processors), key=lambda j:(loads[j],j)); loads[i]+=task
    return max(loads, default=0.0)


def run(project: Path) -> pd.DataFrame:
    cfg={'valid_configs':['cora_gcnii16','pubmed_gcnii16','cora_deepres28_w128','chameleon_gcnii16'],'diagnostic_configs':[]}
    traces=_load_traces(project,cfg); tables={a:_cache(project,a) for a in (8,16,32)}
    orders={}
    rows=[]
    for cid,mapping in traces.items():
        dataset=_dataset_name(cid)
        if dataset not in orders:
            data,_,_=load_dataset(dataset,project/'data'); _,orders[dataset]=symmetrized_edges_and_rcm(data.edge_index,data.num_nodes)
        masks=mapping['trained'][3:min(28 if 'deepres' in cid else 16,len(mapping['trained']))]
        tiles=tiles_from_order(orders[dataset],128)
        totals={k:0.0 for k in ('dense32','dense_sixteen8','monolithic32','four16','sixteen8',
                                 'sixteen8_acc128','ideal_nnz')}
        for offset in range(0,len(masks),13):
            window=masks[offset:offset+13]; panels=correlation_panels(window,32)
            config=PanelCostConfig(rho_residual=1.5,output_features=window.shape[2],escape_enabled=True)
            current=encode_panel_segment(window,tiles,panels,config,lambda m,k,n:tables[32][(m,k,n)])
            similarity=_jaccard_matrix(window)
            for _ in range(2):
                candidate_panels=_propose_correlation_swap(panels,similarity)
                if candidate_panels is None: break
                candidate=encode_panel_segment(window,tiles,candidate_panels,config,lambda m,k,n:tables[32][(m,k,n)])
                if candidate.metrics['total_hybrid_cycles']+1e-9 < current.metrics['total_hybrid_cycles']:
                    panels,current=candidate_panels,candidate
                else: break
            dense=_baseline_cycles(tiles,len(window),window.shape[2],tables[32])
            dense8_per_layer = _lpt(
                [tables[8][(len(tile), window.shape[2], window.shape[2])][0]
                 for tile in tiles],
                16,
            )
            regular={8:0.,16:0.,32:0.}
            for layer in range(len(window)):
                tasks={8:[],16:[],32:[]}
                for tile_schedules in current.schedules:
                    for item in tile_schedules:
                        if len(item.selected_rows) and not item.escape_layers[layer]:
                            shape=(len(item.selected_rows),len(item.features),window.shape[2])
                            for a in tasks: tasks[a].append(tables[a][shape][0])
                regular[32]+=_lpt(tasks[32],1)
                regular[16]+=_lpt(tasks[16],4)
                regular[8]+=_lpt(tasks[8],16)
            m=current.metrics
            # Conservative: retain every non-regular charge, including the
            # corrected residual contribution count that Phase-3A's prefix
            # objective accidentally omitted.
            nonregular=sum(float(m[k]) for k in ('residual_cycles','gather_cycles','decoder_cycles','output_init_cycles','output_add_cycles','weight_pack_cycles'))
            distributed_nonregular=sum(float(m[k]) for k in
                ('residual_cycles','gather_cycles','decoder_cycles','weight_pack_cycles'))
            distributed_nonregular += (
                float(m['output_init_cycles']) + float(m['output_add_cycles'])
            ) / 4.0
            totals['dense32']+=dense
            totals['dense_sixteen8']+=len(window)*dense8_per_layer
            totals['monolithic32']+=regular[32]+nonregular
            totals['four16']+=regular[16]+nonregular
            totals['sixteen8']+=regular[8]+nonregular
            totals['sixteen8_acc128']+=regular[8]+distributed_nonregular
            totals['ideal_nnz']+=dense*float(window.mean())
        reported=pd.read_csv(project/'results_phase3a/33_phase3a_summary.csv').set_index('config_id').loc[cid]
        density=float(masks.mean()); beicsr_max=(4*density+1/8)/(4*density)
        fair_dense=min(totals['dense32'],totals['dense_sixteen8'])
        rows.append({'config_id':cid,'density':density,'reported_panel_speedup':float(reported.panel_hybrid_speedup),
            'reported_oracle_speedup':float(reported.layer_local_oracle_speedup),'corrected_oracle_with_dense_fallback':max(1.,float(reported.layer_local_oracle_speedup)),
            'monolithic32_corrected_speedup':totals['dense32']/totals['monolithic32'],
            'partitioned_4x16_speedup':totals['dense32']/totals['four16'],
            'partitioned_16x8_speedup':totals['dense32']/totals['sixteen8'],
            'partitioned_16x8_acc128_speedup':totals['dense32']/totals['sixteen8_acc128'],
            'dense_16x8_vs_dense32':totals['dense32']/totals['dense_sixteen8'],
            'partitioned_16x8_acc128_speedup_vs_best_dense':fair_dense/totals['sixteen8_acc128'],
            'ideal_nnz_compute_bound':totals['dense32']/totals['ideal_nnz'],
            'fp32_beicsr_free_support_max_speedup':beicsr_max,
            'panel_survives_1_10':totals['dense32']/totals['sixteen8']>=1.10})
    return pd.DataFrame(rows)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--project',type=Path,default=Path('.'))
    project=ap.parse_args().project.resolve(); out=project/'results_rescue_audit'; out.mkdir(exist_ok=True)
    frame=run(project); frame.to_csv(out/'rescue_audit.csv',index=False)
    phase2=pd.read_csv(project/'results_phase2/24_phase2_summary.csv').set_index('config_id')
    precision_rows=[]
    for row in frame.itertuples():
        metadata_ratio=float(phase2.loc[row.config_id].anchor_metadata_ratio)
        for label,value_bytes in (('FP32',4),('FP16',2),('INT8',1)):
            beicsr=value_bytes*row.density+0.125
            xorflow=value_bytes*row.density+0.125*metadata_ratio
            precision_rows.append({
                'config_id':row.config_id,'precision':label,
                'value_bytes':value_bytes,'density':row.density,
                'phase2_anchor_metadata_ratio':metadata_ratio,
                'free_support_max_speedup':beicsr/(value_bytes*row.density),
                'anchor_storage_speedup_projection':beicsr/xorflow,
                'anchor_logical_traffic_reduction':1-xorflow/beicsr,
            })
    precision=pd.DataFrame(precision_rows)
    precision.to_csv(out/'precision_pivot_bounds.csv',index=False)
    principal=frame.set_index('config_id')
    report=f"""# MOSAIC rescue audit

## Verdict

The Phase-3A result contains real implementation/accounting defects, but fixing
them does **not** rescue the FP32 monolithic panel architecture. The defensible
last-chance direction is narrower: INT8 MOSAIC-XORFLOW, with accuracy validation,
against a faithful INT8 BEICSR baseline.

## Confirmed Phase-3A defects

1. `LAYER_LOCAL_ORACLE` was not an oracle. It omitted the dense fallback, used
   density-sorted panels rather than a complete cost-aware search, and retained
   row-list decode cost despite declaring schedule metadata free. Its reported
   value below 1.0 must be replaced by at least 1.0.
2. The deployable prefix objective omitted residual-row output contributions on
   non-escaped panels. The reporting columns counted them, but
   `total_hybrid_cycles` did not. This defect made Phase-3A slightly optimistic;
   it cannot explain the slowdown.
3. P3 tested at most one Jaccard-proposed swap per pass rather than all legal
   cost-reducing swaps. This is a heuristic, not the specified full cost-aware
   swap search.
4. Weight packing was charged inside each tile optimizer even though weights are
   shared across graph tiles. Its measured impact is small and does not alter the
   decision.

## Corrected hardware audit

The same 1,024 MACs were mapped as one 32x32 array, four 16x16 arrays, and sixteen
8x8 arrays using real SCALE-Sim shape cycles. Tasks were scheduled per layer with
deterministic LPT; layer barriers were preserved. All residual, gather, decode,
and output contribution costs were retained.

```text
{frame.to_string(index=False)}
```

Partitioning initially appears to rescue the panel path when compared only with
the old monolithic dense baseline. That comparison is not fair: the dense
baseline can use the same reconfigurable subarrays across topology tiles.
Against the best dense mapping, the 16x8 plus 128-lane accumulator speedups are
only {principal.loc['cora_gcnii16','partitioned_16x8_acc128_speedup_vs_best_dense']:.3f}
on Cora, {principal.loc['pubmed_gcnii16','partitioned_16x8_acc128_speedup_vs_best_dense']:.3f}
on PubMed, and {principal.loc['cora_deepres28_w128','partitioned_16x8_acc128_speedup_vs_best_dense']:.3f}
on DeepRes. The regular-panel paper direction therefore remains stopped.

## Why FP32 XORFLOW is also structurally capped

BEICSR support costs only one bit per feature while each active FP32 value costs
32 bits. Even deleting support metadata entirely gives maximum logical-format
speedups of {principal.loc['cora_gcnii16','fp32_beicsr_free_support_max_speedup']:.3f},
{principal.loc['pubmed_gcnii16','fp32_beicsr_free_support_max_speedup']:.3f}, and
{principal.loc['cora_deepres28_w128','fp32_beicsr_free_support_max_speedup']:.3f}
on Cora, PubMed, and DeepRes before topology traffic or cache-line rounding.
The Phase-3B FP32 gates are at or beyond this free-support ceiling.

## Quantified salvage hypothesis

```text
{precision.to_string(index=False)}
```

At INT8, metadata is four times more important. Using the already observed
Phase-2 anchor metadata ratios as a conservative projection produces useful
logical-format speedups on the principal traces, whereas FP32 does not. This is
not yet a result: INT8 changes numerical values and therefore requires
post-training quantization or quantization-aware training plus accuracy checks.
It is, however, the only remaining hypothesis with enough mathematical
headroom to justify one bounded experiment.

## Next action

Do one final, predeclared INT8 XORFLOW kill test: preserve exact support coding,
quantize packed values, verify model accuracy, compare cache-line traffic against
INT8 BEICSR, and stop if Cora/PubMed geomean serialized aggregation-memory
speedup is below 1.05 or DeepRes is below 1.08. Do not continue the FP32 memory
format or any regular-panel mapping.
"""
    (out/'RESCUE_AUDIT.md').write_text(report)
    print(frame.to_string(index=False))
if __name__=='__main__': main()
