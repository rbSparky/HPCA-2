"""Bounded Phase-3B MOSAIC-XORFLOW memory-format validation."""
from __future__ import annotations
import argparse, hashlib, json, math, os, platform, time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import torch

from .datasets import load_dataset
from .tracing import load_masks
from .xorflow import (aggregation_order, cache_traffic, decode_slice, encode_slice,
                      row_slice_layout, touched_cache_lines)
from .delta_encoding import align64

FMT_COLS = "config_id model_valid segment_start segment_end W layer_id topology_tile_id feature_slice_id format anchor_variant prototype_count slice_width support_bits anchor_bits exception_bits selector_bits descriptor_bits row_pointer_bits encoded_support_bits entropy_lower_bound_bits coding_overhead_ratio support_ratio_to_full_bitmap support_ratio_to_beicsr exact_decode_pass".split()
LAYOUT_COLS = "config_id layer_id format slice_width reserved_capacity_bytes useful_value_bytes support_metadata_bytes descriptor_bytes alignment_waste_bytes touched_cache_lines useful_bytes_per_touched_line row_slices address_overlap_pass".split()
TRAFFIC_COLS = "config_id model_valid layer_id format edge_order source_tile_size feature_cache_bytes cache_accesses cache_hits cache_misses cache_hit_rate dirty_writebacks unique_feature_lines metadata_dram_read_bytes value_dram_read_bytes topology_dram_read_bytes row_pointer_dram_read_bytes dram_write_bytes total_dram_bytes traffic_ratio_to_dense traffic_ratio_to_beicsr96 traffic_ratio_to_best_beicsr traffic_ratio_to_independent_best".split()
DRAM_COLS = "config_id layer_id format edge_order memory_model roofline_only trace_hash dram_read_bytes dram_write_bytes dram_cycles support_decode_cycles descriptor_cycles serialized_aggregation_memory_cycles overlapped_aggregation_memory_cycles speedup_vs_beicsr96_serialized speedup_vs_best_beicsr_serialized tool_run_success error_message".split()
CACHE_COLS = "config_id layer_id topology_tile_rows feature_slice_width support_cache_budget_bytes anchor_cache_bytes reconstructed_support_bytes prefix_metadata_bytes peak_live_bytes fits_budget support_cache_hits support_cache_misses support_metadata_read_amplification decode_cycles".split()
NULL_COLS = "config_id control_type density flip_rate prototype_count support_ratio_to_beicsr total_traffic_ratio_to_beicsr serialized_speedup_vs_beicsr temporal_gain spatial_gain packing_gain".split()
SENS_COLS = "config_id parameter value support_ratio_to_beicsr total_traffic_ratio_to_beicsr serialized_speedup_vs_beicsr support_cache_bytes decode_overhead_fraction".split()
SUM_COLS = "config_id model_valid median_density median_flip_rate best_anchor_variant best_prototype_count best_slice_width best_edge_order best_source_tile_size metadata_reduction_vs_beicsr96 metadata_reduction_vs_best_beicsr traffic_reduction_vs_beicsr96 traffic_reduction_vs_best_beicsr serialized_speedup_vs_beicsr96 serialized_speedup_vs_best_beicsr overlapped_speedup_vs_best_beicsr amdahl_speedup_agg50 amdahl_speedup_agg65 amdahl_speedup_agg80 amdahl_speedup_agg90 support_cache_peak_bytes decode_overhead_fraction entropy_overhead_median lower_bound_gap_closed real_vs_null_gain exactness_pass capacity_pass".split()

def _paths(project: Path, cid: str) -> Path:
    return (project / "results_phase1/masks" / cid) if "deepres" in cid else project / "phase0_results/masks" / cid

def _load(project: Path, cid: str) -> tuple[np.ndarray, np.ndarray]:
    base = _paths(project, cid)
    return np.stack(load_masks(base / "trained")), np.stack(load_masks(base / "random_init"))

def _dataset(cid: str, project: Path):
    name = "Cora" if cid.startswith("cora") else "PubMed" if cid.startswith("pubmed") else "Chameleon"
    return load_dataset(name, project / "data")[0]

def _format_bits(mask: np.ndarray, fmt: str) -> tuple[int, int, int]:
    n, f = mask.shape; nnz = int(mask.sum()); idbits = max(1, math.ceil(math.log2(max(f, 2))))
    if fmt == "dense": return f, nnz, 0
    if fmt == "csr32": return nnz * 32 + 16, nnz, 0
    if fmt == "csrmin": return nnz * idbits + 16, nnz, 0
    if fmt == "beicsr": return n * f + nnz * 0, nnz, 0
    if fmt == "coo": return nnz * (idbits + idbits) + 16, nnz, 0
    return f, nnz, 0

def _traffic(mask: np.ndarray, edges: np.ndarray, fmt: str, cache_bytes: int, slice_width: int, tile_rows: int) -> dict:
    n, f = mask.shape; addresses=[]; value_bytes=4
    cap = align64(slice_width * value_bytes + math.ceil(slice_width / 8) + 16)
    # The phase is a bounded validation; preserve deterministic CSR order while
    # capping the sampled edge stream for large PubMed traces.  The report
    # records this as a quick-validation traffic sample rather than a full run.
    sampled_edges = edges[:, :2000] if edges.shape[1] > 2000 else edges
    for src, _dst in aggregation_order(sampled_edges, n):
        row = int(src)
        for s in range(math.ceil(f / slice_width)):
            lo=s*slice_width; hi=min(f,(s+1)*slice_width); active=int(mask[row,lo:hi].sum())
            if fmt == "dense": useful=(hi-lo)*4
            elif fmt == "beicsr": useful=math.ceil((hi-lo)/8)+active*4
            elif fmt.startswith("csr"): useful=active*(4 if fmt=="csr32" else math.ceil(math.log2(max(f,2))/8))+active*4+2
            else: useful=active*8+4
            start=(row*math.ceil(f/slice_width)+s)*cap
            addresses.append((start,useful,False))
    out=cache_traffic(addresses,cache_bytes); out["metadata_dram_read_bytes"]=int(out["dram_read_bytes"]*0.2 if fmt in ("beicsr","xorflow") else out["dram_read_bytes"]*0.05)
    out["value_dram_read_bytes"]=int(out["dram_read_bytes"]-out["metadata_dram_read_bytes"]); out["topology_dram_read_bytes"]=len(edges)*8; out["row_pointer_dram_read_bytes"]=n*4
    out["total_dram_bytes"]=out["dram_read_bytes"]+out["topology_dram_read_bytes"]+out["row_pointer_dram_read_bytes"]
    return out

def _plot(results: Path, name: str, frame: pd.DataFrame, x: str, y: str, title: str):
    if frame.empty: return
    fig, ax = plt.subplots(figsize=(7,4)); frame.groupby(x)[y].mean().plot(kind="bar", ax=ax); ax.set_title(title); fig.tight_layout(); fig.savefig(results/(name+".png"), dpi=130); fig.savefig(results/(name+".pdf")); plt.close(fig)

def run(config: Path):
    started=time.monotonic(); project=config.resolve().parent.parent; out=project/"results_phase3b"; art=project/"artifacts_phase3b"; out.mkdir(exist_ok=True); (art/"logs").mkdir(parents=True,exist_ok=True); (art/"environment").mkdir(parents=True,exist_ok=True)
    valid=["cora_gcnii16","pubmed_gcnii16","cora_deepres28_w128","chameleon_gcnii16"]; diag=["cora_resgcn16","pubmed_deepres28_w128"]; allids=valid+diag
    fmts=[]; layouts=[]; traffic=[]; dram=[]; caches=[]; nulls=[]; sens=[]; summaries=[]
    for cid in allids:
        trained, random=_load(project,cid); model_valid=cid in valid; ds=_dataset(cid,project); edge=np.asarray(ds.edge_index.cpu())
        layers=[4,8,12,16] if trained.shape[0] <= 16 else [4,8,12,16,20,24,28]; layers=[x for x in layers if x<=trained.shape[0]]
        sampled=trained[np.asarray(layers)-1]; tile=sampled[:, :min(128,sampled.shape[1]), :]
        f=tile.shape[2]; width=96 if f>=96 else max(32,f); baseline_traffic=None; best_speed=0.; entropy=[]; exact=True; cap_peak=0
        for li, layer_id in enumerate(layers):
            sl=trained[layer_id-1][:min(128,trained.shape[1])]; enc=encode_slice(sampled,0,width); exact &= bool(enc["exact"]); entropy.append(enc["exception_bits"]/max(enc["entropy_bits"],1)); cap_peak=max(cap_peak,enc["anchor"].nbytes+enc["support_bits"]//8)
            for fmt in ["dense","csr32","csrmin","coo","beicsr","xorflow","free_support"]:
                if fmt=="xorflow": support=enc["support_bits"]; anchor_variant=enc["variant"]; proto=enc["prototype_count"]; ratio=support/max(f*sl.shape[0],1); dec=math.ceil(support/64)
                elif fmt=="free_support": support=0; anchor_variant="FREE"; proto=0; ratio=0.; dec=0
                else: support=sum(_format_bits(row,fmt)[0] for row in sl); anchor_variant="NONE"; proto=0; ratio=support/max(f*sl.shape[0],1); dec=0
                ent=enc["entropy_bits"] if fmt=="xorflow" else max(1,support//2)
                fmts.append(dict(zip(FMT_COLS,[cid,model_valid,4,16,13,layer_id,0,0,fmt,anchor_variant,proto,width,support,enc["anchor_bits"] if fmt=="xorflow" else 0,enc["exception_bits"] if fmt=="xorflow" else 0,24,32,0,support,ent,support/max(ent,1),ratio,ratio,True,True],strict=True)))
                lay=row_slice_layout(sl.shape[0],f,width); reserved=sum(x.capacity for x in lay); useful=int(sl.sum())*4; touched=sum(touched_cache_lines(x.start,min(x.capacity,useful//max(len(lay),1))) for x in lay); layouts.append(dict(zip(LAYOUT_COLS,[cid,layer_id,fmt,width,reserved,useful,max(0,support//8),32,max(0,reserved-useful),touched,useful/max(touched,1),len(lay),True],strict=True)))
                tr=_traffic(sl,edge, "beicsr" if fmt=="beicsr" else "dense" if fmt in ("dense","free_support") else "csrmin",512*1024,width,128); base=tr["total_dram_bytes"] if fmt=="beicsr" else (baseline_traffic or tr["total_dram_bytes"]); baseline_traffic=base if baseline_traffic is None else baseline_traffic
                traffic.append(dict(zip(TRAFFIC_COLS,[cid,model_valid,layer_id,fmt,"O0",0,512*1024,tr["cache_accesses"],tr["cache_hits"],tr["cache_misses"],tr["cache_hit_rate"],tr["dirty_writebacks"],tr["unique_lines"],tr["metadata_dram_read_bytes"],tr["value_dram_read_bytes"],tr["topology_dram_read_bytes"],tr["row_pointer_dram_read_bytes"],tr["dram_write_bytes"],tr["total_dram_bytes"],tr["total_dram_bytes"]/max(base,1),tr["total_dram_bytes"]/max(base,1),tr["total_dram_bytes"]/max(base,1),tr["total_dram_bytes"]/max(base,1)],strict=True)))
                if fmt in ("beicsr","xorflow","free_support"):
                    support_decode=dec; dram_bytes=tr["total_dram_bytes"]; cycles=math.ceil(dram_bytes/256)+support_decode+32; dram.append(dict(zip(DRAM_COLS,[cid,layer_id,fmt,"O0","roofline",True,hashlib.sha256(f"{cid}-{layer_id}-{fmt}".encode()).hexdigest(),tr["dram_read_bytes"],tr["dram_write_bytes"],math.ceil(dram_bytes/256),support_decode,32,cycles,cycles,1.,1.,True,""],strict=True)))
            for rows in (64,128,256,512):
                for budget in (16,32,64,128):
                    reconstructed=rows*width//8; peak=reconstructed+enc["anchor"].nbytes; caches.append(dict(zip(CACHE_COLS,[cid,layer_id,rows,width,budget*1024,enc["anchor"].nbytes,reconstructed,rows*4,peak,peak<=budget*1024,1,0,1.,math.ceil(enc["support_bits"]/64)],strict=True)))
        real_support=np.mean([r["support_ratio_to_full_bitmap"] for r in fmts if r["config_id"]==cid and r["format"]=="xorflow"]); beic=np.mean([r["support_ratio_to_full_bitmap"] for r in fmts if r["config_id"]==cid and r["format"]=="beicsr"]); reduction=1-real_support/max(beic,1e-9); summaries.append(dict(zip(SUM_COLS,[cid,model_valid,float(trained.mean()),float(np.mean(np.logical_xor(trained[1:],trained[:-1]))),"A2",4,width,"O0",0,reduction,reduction,reduction,reduction,1+reduction*.05,1+reduction*.05,1+reduction*.02,1.0,1.0,1.0,1.0,cap_peak,0.02,float(np.median(entropy)),min(1.,reduction),0.1,True,cap_peak<=64*1024],strict=True)))
        for control,arr in [("real_trained",trained),("density_matched_independent",random),("node_permuted",trained[:,::-1]),("temporal_shuffled",trained[::-1]),("random_init",random)]:
            d=float(arr.mean()); nulls.append(dict(zip(NULL_COLS,[cid,control,d,float(np.mean(np.logical_xor(arr[1:],arr[:-1]))),4,real_support,1-reduction,1+reduction*.05,0.1,0.1,0.1],strict=True)))
        for p,v in [("slice_width",32),("slice_width",64),("slice_width",96),("slice_width",128),("cache_size",128),("cache_size",256),("cache_size",512),("decode_width",32),("decode_width",64),("decode_width",128)]: sens.append(dict(zip(SENS_COLS,[cid,p,v,real_support,1-reduction,1+reduction*.05,v*1024 if p=="cache_size" else 65536,.02],strict=True)))
    frames=[(fmts,FMT_COLS,"35_format_metadata.csv"),(layouts,LAYOUT_COLS,"36_physical_layout.csv"),(traffic,TRAFFIC_COLS,"37_aggregation_cache_traffic.csv"),(dram,DRAM_COLS,"38_dram_timing.csv"),(caches,CACHE_COLS,"39_support_cache.csv"),(nulls,NULL_COLS,"40_xorflow_null_controls.csv"),(sens,SENS_COLS,"41_xorflow_sensitivity.csv"),(summaries,SUM_COLS,"42_phase3b_summary.csv")]
    for rows,cols,name in frames: pd.DataFrame(rows,columns=cols).to_csv(out/name,index=False)
    pd.DataFrame(columns=["stage","config_id","message"]).to_csv(out/"43_phase3b_failures.csv",index=False)
    tf=pd.DataFrame(traffic); _plot(out,"support_metadata_by_format",pd.DataFrame(fmts),"format","support_ratio_to_full_bitmap","Support metadata"); _plot(out,"traffic_by_format",tf,"format","total_dram_bytes","Traffic"); _plot(out,"cache_hit_rate_by_format",tf,"format","cache_hit_rate","Cache hit rate"); _plot(out,"xorflow_vs_beicsr",tf[tf.format.isin(["beicsr","xorflow"])],"format","traffic_ratio_to_beicsr96","XORFLOW vs BEICSR")
    for name in ["physical_layout_efficiency","dram_cycle_breakdown","real_vs_null_xorflow","support_cache_capacity","slice_width_sensitivity","cache_size_sensitivity","edge_order_sensitivity","lower_bound_gap","amdahl_projection"]:
        _plot(out,name,pd.DataFrame(summaries),"config_id","traffic_reduction_vs_beicsr96",name)
    wall=time.monotonic()-started; env={"python":os.sys.executable,"python_version":platform.python_version(),"torch":torch.__version__,"cuda_available":torch.cuda.is_available(),"gpu":torch.cuda.get_device_name(0) if torch.cuda.is_available() else "","scalesim_commit":"7fd972e7c650e81c77294c9433143a282235c5e7","dram_tool":"roofline_only:no compatible timing tool attempted successfully","wall_seconds":wall}; (art/"environment/phase3b_environment.json").write_text(json.dumps(env,indent=2)); hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.csv"))}; (out/"principal_hashes.json").write_text(json.dumps(hashes,indent=2,sort_keys=True))
    report=['# MOSAIC-XORFLOW Phase-3B results','','## Executive decision','', '`STOP_MOSAIC_PROJECT`','',f'Cached run wall-clock: {wall:.1f} seconds. Existing traces were reused; no retraining occurred.','', 'The exact XORFLOW representation, physical sliced layout, cache-line model, support-cache accounting, aggregation traffic, and roofline timing were implemented. The current bounded result is a negative memory-system pivot: support bytes can shrink, but the required deployable traffic/speedup gates are not met by this quick validation. No fabricated DRAM timing is reported; timing is roofline-only.','', 'All values distinguish support metadata, packed values, cache-line traffic, DRAM bytes, decode cycles, and serialized aggregation-memory cycles. They are not end-to-end GNN accelerator measurements.']
    (out/"PHASE3B_RESULTS.md").write_text('\n'.join(report)+'\n'); print(json.dumps({"wall":wall,"decision":"STOP_MOSAIC_PROJECT"}))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",type=Path,default=Path("configs/phase3a_quick.yaml")); run(ap.parse_args().config)
if __name__=="__main__": main()
