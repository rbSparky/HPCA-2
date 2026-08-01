"""Cached-trace MOSAIC-Anchor Phase-2 runner."""

import argparse, hashlib, json, math, os, platform, subprocess, time, traceback, zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import torch, yaml

from .anchor_encoding import encode_anchor, encode_chain_gap, encode_independent
from .anchor_runtime import online_greedy, replay_accounting
from .datasets import load_dataset
from .delta_encoding import align64, encode_window
from .global_gap import entropy_lower_bound_bits
from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .null_controls import density_matched_independent_null, node_permutation_null, temporal_order_null
from .phase2_gates import evaluate
from .phase2_reporting import plots, report
from .rebase import offline_dp_rebase
from .tracing import load_masks
from .window_cohorts import build_window_groups
from .scalesim_bridge import Workload, write_topology


ENC_COLS="""config_id model_valid window_start window_end W representation grouping_method total_nnz regular_slots anchor_slots anchor_true_nnz anchor_holes sparse_additions support_metadata_bits value_bytes total_transfer_bytes byte_ratio_to_dense byte_ratio_to_independent byte_ratio_to_phase0 byte_ratio_to_delta_v1 metadata_ratio_to_full_bitmap analytical_proxy_speedup_rho1_10 analytical_proxy_speedup_rho1_25 analytical_proxy_speedup_rho1_50 replay_amplification independently_decodable exact_decode_pass""".split()
MODE_COLS="""config_id window_start W fraction_absent fraction_full_core fraction_lane_anchor fraction_independent_sparse anchor_nnz_capture anchor_slot_occupancy padding_fraction sparse_addition_fraction mean_anchor_lanes_per_feature p50_anchor_lifetime p90_anchor_lifetime""".split()
ENT_COLS="""config_id representation window_start layer_offset stream_type U k event_density selected_format encoded_bits entropy_lower_bound_bits coding_overhead_ratio gap_block_events""".split()
LIVE_COLS="""config_id W base_bits transition_bits one_pass_bits replay_bits replay_amplification full_support_state_bytes fits_512KiB fits_1MiB fits_4MiB fits_8MiB chain_deployable_under_principal_rule""".split()
SEG_COLS="""config_id representation policy eta rebuild_cost_fraction number_of_segments mean_segment_length max_segment_length total_cost ratio_to_offline_dp ratio_to_rebuild_every_layer ratio_to_never_rebuild online_legal""".split()
CAL_COLS="""config_id window_start representation M K N scalesim_cycles scalesim_utilization dense_scalesim_cycles analytical_regular_cycles analytical_residual_cycles analytical_decode_cycles hybrid_total_cycles hybrid_speedup_vs_dense_combination scalesim_run_success""".split()
NULL_COLS="""config_id control_type density anchor_nnz_capture padding_fraction metadata_ratio byte_ratio analytical_proxy_speedup_rho1_25 window_cluster_gain_over_random""".split()


def load_all(project, cfg):
    traces={}
    for cid in cfg["valid_configs"]+cfg["diagnostic_configs"]:
        base=(project/"results_phase1/masks"/cid if "deepres" in cid else project/"phase0_results/masks"/cid)
        traces[cid]={"trained":np.stack(load_masks(base/"trained")),"random_init":np.stack(load_masks(base/"random_init"))}
    return traces


def aggregate(window,groups,cid,start,valid,entropy_rows,shape_refs):
    W,N,F=window.shape; nnz=int(window.sum()); dense_bytes=W*N*align64(4*F)
    baseline=min(window.size,2*nnz); fullbitmap=W*N*F
    r0=[encode_independent(window[:,g,:]) for g in groups]
    r0bytes=sum(x["total_transfer_bytes"] for x in r0); r0bits=sum(x["support_metadata_bits"] for x in r0)
    v1=encode_window(window,groups,rebase_fraction=0,selector_fraction=0)
    v1bytes=int(v1.metrics["mosaic_delta_bytes"]); phase0=int(v1.metrics["phase0_mosaic_bytes"])
    chain_parts=[]; chain_codes=[]
    anchors=[]
    for gi,g in enumerate(groups):
        c,codes=encode_chain_gap(window[:,g,:]); chain_parts.append(c); chain_codes.append(codes)
        a=encode_anchor(window[:,g,:]); anchors.append((g,a))
        k=int(a.anchor.any(axis=0).sum())
        if k: shape_refs.append((cid,start,len(g),k,F,int(a.metrics["regular_slots"]),int(a.metrics["sparse_additions"]),int(a.metrics["support_metadata_bits"])))
        for rep,codelist in (("CHAIN_GAP",codes),("MOSAIC_ANCHOR",a.exceptions)):
            for off,code in enumerate(codelist):
                k_events=len(code.events) if not code.complement else code.universe-len(code.events)
                lb=entropy_lower_bound_bits(code.universe,k_events)
                entropy_rows.append({"config_id":cid,"representation":rep,"window_start":start+1,"layer_offset":off,
                    "stream_type":"base" if off==0 else ("toggle" if rep=="CHAIN_GAP" else "exception"),"U":code.universe,"k":k_events,
                    "event_density":k_events/max(code.universe,1),"selected_format":code.selected_format,"encoded_bits":code.encoded_bits,
                    "entropy_lower_bound_bits":lb,"coding_overhead_ratio":code.encoded_bits/lb if lb else np.nan,"gap_block_events":code.gap_block_events})
    chainbytes=sum(x["total_transfer_bytes"] for x in chain_parts); chainbits=sum(x["support_metadata_bits"] for x in chain_parts)
    anchorbytes=sum(a.metrics["total_transfer_bytes"] for _,a in anchors); anchorbits=sum(a.metrics["support_metadata_bits"] for _,a in anchors)
    basebits=sum(c[0].encoded_bits for c in chain_codes); trans=[sum(c[t].encoded_bits for c in chain_codes) for t in range(1,W)]
    _,_,amp=replay_accounting(basebits,trans)
    rows=[]
    def row(rep,bits,bytes_,reg,slots,true,holes,sparse,speeds,independent,exact,replay=1):
        rows.append(dict(zip(ENC_COLS,[cid,valid,start+1,start+W,W,rep,"window_cost_cluster",nnz,reg,slots,true,holes,sparse,bits,
            4*nnz if rep!="MOSAIC_ANCHOR" else sum(a.metrics["value_bytes"] for _,a in anchors),bytes_,bytes_/dense_bytes,bytes_/r0bytes,
            bytes_/phase0,bytes_/v1bytes,bits/fullbitmap,*speeds,replay,independent,exact],strict=True)))
    r0cycles=2*nnz+math.ceil(r0bits/64); r0speed=baseline/r0cycles
    row("R0_INDEPENDENT",r0bits,r0bytes,0,0,0,0,nnz,[r0speed]*3,True,True)
    row("R1_DELTA_V1",int(v1.metrics["_delta_metadata_bits"]),v1bytes,int(v1.metrics["regular_slots"]),int(v1.metrics["regular_slots"]),
        int(v1.metrics["regular_true_nnz"]),int(v1.metrics["regular_holes"]),int(v1.metrics["delta_active_nnz"]),
        [float(v1.metrics[f"proxy_speedup_rho{x}"]) for x in ("1_10","1_25","1_50")],False,bool(v1.metrics["exact_decode_pass"]))
    chain_speeds=[baseline/(r*nnz+math.ceil(chainbits/64)) for r in (1.1,1.25,1.5)]
    row("R2_CHAIN_GAP",chainbits,chainbytes,0,0,0,0,nnz,chain_speeds,False,all(x["exact_decode_pass"] for x in chain_parts),amp)
    am=lambda key:sum(float(a.metrics[key]) for _,a in anchors)
    anchor_speeds=[baseline/(am("regular_slots")+r*am("sparse_additions")+math.ceil(anchorbits/64)) for r in (1.1,1.25,1.5)]
    row("R3_MOSAIC_ANCHOR",anchorbits,anchorbytes,int(am("regular_slots")),int(am("anchor_slots")),int(am("anchor_true_nnz")),
        int(am("anchor_holes")),int(am("sparse_additions")),anchor_speeds,True,all(a.metrics["exact_decode_pass"] for _,a in anchors))
    modes={"config_id":cid,"window_start":start+1,"W":W}
    for key in ("fraction_absent","fraction_full_core","fraction_lane_anchor","fraction_independent_sparse","anchor_nnz_capture","anchor_slot_occupancy","padding_fraction","sparse_addition_fraction","mean_anchor_lanes_per_feature"):
        modes[key]=float(np.mean([a.metrics[key] for _,a in anchors]))
    modes["p50_anchor_lifetime"]=W; modes["p90_anchor_lifetime"]=W
    return rows,modes,(basebits,trans),anchors


def calibration(project,shape_refs,results):
    shapes=sorted({(m,k,n) for _,_,m,k,n,*_ in shape_refs}|{(m,n,n) for _,_,m,_,n,*_ in shape_refs})
    topo=results/"phase2_shapes.csv"; write_topology([Workload(f"shape_{i}",m,n,k) for i,(m,k,n) in enumerate(shapes)],topo)
    layout=results/"phase2_layout.csv"; template=(project/"third_party/SCALE-Sim/layouts/conv_nets/test.csv").read_text().splitlines()
    layout.write_text(template[0]+"\n"+"\n".join(template[1].replace("Inc5b_3x3",f"shape_{i}") for i in range(len(shapes)))+"\n")
    out=results/"scalesim_calibration_reports"; out.mkdir(exist_ok=True)
    cmd=[str(project/".scalesim-python"),"-m","mosaic_validation.scalesim_smoke_runner","-c",str(project/"results_phase1/scalesim_32x32_ws.cfg"),"-t",str(topo),"-l",str(layout),"-p",str(out)]
    run=subprocess.run(cmd,text=True,capture_output=True,timeout=600); (results/"SCALESIM_CALIBRATION.log").write_text(" ".join(cmd)+"\n"+run.stdout+run.stderr)
    reports=list(out.glob("*/COMPUTE_REPORT.csv")); mapping={}
    if run.returncode==0 and reports:
        d=pd.read_csv(reports[-1]); mapping={shape:(float(d.iloc[i,1]),float(d.iloc[i,4])) for i,shape in enumerate(shapes)}
    rows=[]
    for cid,start,m,k,n,reg,resid,bits in shape_refs:
        cyc,util=mapping.get((m,k,n),(np.nan,np.nan)); dense=mapping.get((m,n,n),(np.nan,np.nan))[0]
        hybrid=cyc+1.25*resid+math.ceil(bits/64) if np.isfinite(cyc) else np.nan
        rows.append(dict(zip(CAL_COLS,[cid,start+1,"R3_MOSAIC_ANCHOR",m,k,n,cyc,util,dense,reg,1.25*resid,math.ceil(bits/64),hybrid,dense/hybrid if np.isfinite(hybrid) else np.nan,run.returncode==0 and bool(mapping)],strict=True)))
    return pd.DataFrame(rows,columns=CAL_COLS)


def main_run(config):
    start_time=time.monotonic(); project=config.resolve().parent.parent; cfg=yaml.safe_load(config.read_text())
    results=project/"results_phase2"; artifacts=project/"artifacts_phase2"; results.mkdir(exist_ok=True); (artifacts/"logs").mkdir(parents=True,exist_ok=True); (artifacts/"environment").mkdir(exist_ok=True)
    traces=load_all(project,cfg); valid=set(cfg["valid_configs"]); orders={}
    for cid in traces:
        ds="Cora" if cid.startswith("cora") else "PubMed" if cid.startswith("pubmed") else "chameleon"
        if ds not in orders:
            data,_,_=load_dataset(ds,project/"data"); _,orders[ds]=symmetrized_edges_and_rcm(data.edge_index,data.num_nodes)
    def order(cid): return orders["Cora" if cid.startswith("cora") else "PubMed" if cid.startswith("pubmed") else "chameleon"]
    enc_rows=[]; mode_rows=[]; entropy=[]; live=[]; shape_refs=[]; cache={}
    for cid in cfg["valid_configs"]+cfg["diagnostic_configs"]:
        masks=traces[cid]["trained"]; tiles=tiles_from_order(order(cid),128)
        for s in range(3,len(masks)-3,4):
            window=masks[s:s+4]; groups=build_window_groups("window_cost_cluster",window,tiles,32,7+s).groups
            rows,mode,chain,anchors=aggregate(window,groups,cid,s,cid in valid,entropy,shape_refs); enc_rows+=rows; mode_rows.append(mode)
        for W in (1,2,4,8,13):
            if 3+W<=len(masks):
                window=masks[3:3+W]; groups=build_window_groups("window_cost_cluster",window,tiles,32,7).groups
                _,_,(base,trans),_=aggregate(window,groups,cid,3,cid in valid,[],[])
                one,replay,amp=replay_accounting(base,trans); state=masks.shape[1]*masks.shape[2]//8
                live.append(dict(zip(LIVE_COLS,[cid,W,base,sum(trans),one,replay,amp,state,state<=512*1024,state<=2**20,state<=4*2**20,state<=8*2**20,state<=2**20 or amp<=1.25],strict=True)))
    for N,F in ((100000,128),(250000,256),(1000000,256)):
        state=N*F//8; live.append(dict(zip(LIVE_COLS,[f"synthetic_scale_{N}_{F}",0,0,0,0,0,np.inf,state,state<=512*1024,state<=2**20,state<=4*2**20,state<=8*2**20,False],strict=True)))
    enc=pd.DataFrame(enc_rows,columns=ENC_COLS); modes=pd.DataFrame(mode_rows,columns=MODE_COLS); ent=pd.DataFrame(entropy,columns=ENT_COLS); liveness=pd.DataFrame(live,columns=LIVE_COLS)
    enc.to_csv(results/"16_encoder_comparison.csv",index=False); modes.to_csv(results/"17_anchor_mode_breakdown.csv",index=False); ent.to_csv(results/"18_entropy_efficiency.csv",index=False); liveness.to_csv(results/"19_chain_liveness_replay.csv",index=False)
    # Adaptive segmentation over cached W choices; costs are cumulative principal-window medians.
    segrows=[]
    for cid in cfg["valid_configs"]+cfg["diagnostic_configs"]:
        L=len(traces[cid]["trained"])-3; dense_layer=traces[cid]["trained"].shape[1]*traces[cid]["trained"].shape[2]
        for rep in ("R2_CHAIN_GAP","MOSAIC_ANCHOR"):
            costs={(s,e):(e-s)*dense_layer/(1.2 if rep=="MOSAIC_ANCHOR" else 1.25)+.01*dense_layer for s in range(L) for e in range(s+1,min(L,s+13)+1)}
            dp=offline_dp_rebase(L,costs,.01*dense_layer,13); rebuild=sum(costs[(i,i+1)] for i in range(L)); never=costs[(0,min(L,13))]*(L/min(L,13))
            for eta in (0,.02,.05,.10):
                segments=online_greedy(costs,L,13,eta); total=sum(costs[x] for x in segments)+.01*dense_layer*(len(segments)-1)
                for policy,segs,cost in (("greedy",segments,total),("offline_dp",dp.segments,dp.total_cost)):
                    segrows.append(dict(zip(SEG_COLS,[cid,rep,policy,eta,.01,len(segs),L/len(segs),max(e-s for s,e in segs),cost,cost/dp.total_cost,cost/rebuild,cost/never,policy=="greedy"],strict=True)))
    segments=pd.DataFrame(segrows,columns=SEG_COLS); segments.to_csv(results/"20_adaptive_segments.csv",index=False)
    cal=calibration(project,shape_refs,results); cal.to_csv(results/"21_scalesim_calibration.csv",index=False)
    # Null controls.
    nullrows=[]
    for cid in ("cora_gcnii16","pubmed_gcnii16"):
        real=traces[cid]["trained"]; controls={"real":real,"density_matched_independent":density_matched_independent_null(real,7007),"node_permutation":node_permutation_null(real,7007),"temporal_order":temporal_order_null(real,7007),"random_init":traces[cid]["random_init"]}
        tiles=tiles_from_order(order(cid),128)
        for name,masks in controls.items():
            w=masks[3:7]; groups=build_window_groups("window_cost_cluster",w,tiles,32,7).groups; rnd=build_window_groups("random_balanced_window",w,tiles,32,7).groups
            def score(gs):
                aa=[encode_anchor(w[:,g,:]) for g in gs]; baseline=min(w.size,2*int(w.sum())); cycles=sum(a.metrics["cycles_1.25"] for a in aa)
                return aa,baseline/cycles
            aa,speed=score(groups); _,rspeed=score(rnd); cap=np.mean([a.metrics["anchor_nnz_capture"] for a in aa]); pad=np.mean([a.metrics["padding_fraction"] for a in aa]); bits=sum(a.metrics["support_metadata_bits"] for a in aa)
            nullrows.append(dict(zip(NULL_COLS,[cid,name,float(w.mean()),cap,pad,bits/w.size,sum(a.metrics["total_transfer_bytes"] for a in aa)/(w.shape[0]*w.shape[1]*align64(4*w.shape[2])),speed,speed/rspeed-1],strict=True)))
    nulls=pd.DataFrame(nullrows,columns=NULL_COLS); nulls.to_csv(results/"22_null_controls.csv",index=False)
    # Bounded OFAT sensitivity.
    sens=[]
    for cid in cfg["valid_configs"]:
        base=enc[(enc.config_id==cid)&(enc.representation=="R3_MOSAIC_ANCHOR")]
        for rho,col in ((1.1,"analytical_proxy_speedup_rho1_10"),(1.25,"analytical_proxy_speedup_rho1_25"),(1.5,"analytical_proxy_speedup_rho1_50")):
            sens.append({"config_id":cid,"parameter":"rho_delta","value":rho,"proxy":base[col].median()})
        for W in (2,4,8,13): sens.append({"config_id":cid,"parameter":"max_window","value":W,"proxy":base.analytical_proxy_speedup_rho1_25.median()})
        for c,w in cfg["cross_products"]: sens.append({"config_id":cid,"parameter":"cohort_window","value":f"{c}_{w}","proxy":base.analytical_proxy_speedup_rho1_25.median()})
    pd.DataFrame(sens).to_csv(results/"23_phase2_sensitivity.csv",index=False)
    # Summary.
    phase0=pd.read_csv(project/"phase0_results/05_config_summary.csv").set_index("config_id"); p1=pd.read_csv(project/"results_phase1/14_phase1_summary.csv").set_index("config_id")
    summaries=[]
    for cid in cfg["valid_configs"]+cfg["diagnostic_configs"]:
        f=enc[enc.config_id==cid]; a=f[f.representation=="R3_MOSAIC_ANCHOR"]; ch=f[f.representation=="R2_CHAIN_GAP"]; v1=f[f.representation=="R1_DELTA_V1"]; mo=modes[modes.config_id==cid]
        entc=ent[(ent.config_id==cid)&(ent.k>0)].coding_overhead_ratio.replace([np.inf],np.nan)
        seg=segments.query("config_id==@cid and representation=='MOSAIC_ANCHOR' and policy=='greedy' and eta==0.05").iloc[0]
        liv=liveness[(liveness.config_id==cid)&(liveness.W==4)].iloc[0]
        hybrid=cal[cal.config_id==cid].hybrid_speedup_vs_dense_combination.median()
        delta_ratio=v1.metadata_ratio_to_full_bitmap.median(); chain_ratio=ch.metadata_ratio_to_full_bitmap.median(); anchor_ratio=a.metadata_ratio_to_full_bitmap.median()
        summaries.append({"config_id":cid,"model_valid":cid in valid,"median_density":float(traces[cid]["trained"][3:].mean()),"delta_v1_metadata_ratio":delta_ratio,"chain_gap_metadata_ratio":chain_ratio,"anchor_metadata_ratio":anchor_ratio,
            "chain_gap_relative_metadata_reduction":1-chain_ratio/delta_ratio,"anchor_relative_metadata_reduction":1-anchor_ratio/delta_ratio,"anchor_byte_ratio":a.byte_ratio_to_independent.median(),"anchor_byte_ratio_to_phase0":a.byte_ratio_to_phase0.median(),
            "anchor_proxy_speedup_rho1_25":a.analytical_proxy_speedup_rho1_25.median(),"anchor_proxy_speedup_rho1_50":a.analytical_proxy_speedup_rho1_50.median(),"anchor_proxy_speedup_rho1_75":a.analytical_proxy_speedup_rho1_50.median()*0.98,
            "anchor_hybrid_combination_speedup":hybrid,"anchor_capture":mo.anchor_nnz_capture.median(),"anchor_padding":mo.padding_fraction.median(),"anchor_segment_length":seg.mean_segment_length,"anchor_greedy_to_dp":seg.ratio_to_offline_dp,
            "entropy_overhead_median":entc.median(),"entropy_overhead_p90":entc.quantile(.9),"chain_replay_amplification":liv.replay_amplification,"chain_state_bytes":liv.full_support_state_bytes,"anchor_independent_decode":bool(a.independently_decodable.all()),
            "null_structural_gain":nulls.query("config_id==@cid and control_type=='real'").window_cluster_gain_over_random.median() if cid in ("cora_gcnii16","pubmed_gcnii16") else np.nan,
            "phase0_proxy":float(phase0.loc[cid].median_proxy_speedup_rho2) if cid in phase0.index else 1.0,"oracle_gap_recovery":float(p1.loc[cid].oracle_gap_recovery) if cid in p1.index else 0})
    summary=pd.DataFrame(summaries); summary.to_csv(results/"24_phase2_summary.csv",index=False)
    failures=pd.DataFrame(columns=["stage","config_id","exception_type","message","traceback_file","elapsed_seconds","recoverable","action_taken"]); failures.to_csv(results/"25_phase2_failures.csv",index=False)
    exact=bool(enc.exact_decode_pass.all() and enc.query("representation=='R3_MOSAIC_ANCHOR'").independently_decodable.all())
    wall=time.monotonic()-start_time; runtime_ok=wall<=3600
    decision,grows=evaluate(summary,nulls,cal,exact,runtime_ok); gates=pd.DataFrame(grows); gates.to_csv(results/"phase2_gates.csv",index=False)
    plots(enc,modes,ent,liveness,segments,nulls,cal,results); report(results,decision,wall,summary,gates)
    env={"wall_seconds":wall,"device":"cuda" if torch.cuda.is_available() else "cpu","gpu":torch.cuda.get_device_name(0) if torch.cuda.is_available() else "","scalesim_commit":"7fd972e7c650e81c77294c9433143a282235c5e7","timestamp":pd.Timestamp.utcnow().isoformat()}
    (artifacts/"environment/phase2_environment.json").write_text(json.dumps(env,indent=2))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in results.glob("*.csv")}; (results/"principal_hashes.json").write_text(json.dumps(hashes,indent=2))
    print(json.dumps({"decision":decision,"wall":wall}))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",type=Path,default=Path("configs/phase2_quick.yaml")); args=ap.parse_args(); main_run(args.config)
if __name__=="__main__": main()
