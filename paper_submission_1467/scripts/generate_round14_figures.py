from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
FIG=ROOT/'figures'; FIG.mkdir(exist_ok=True)
NEW=ROOT/'results_used/review5_final2'
OLD=ROOT/'results_used'

plt.rcParams.update({
    'font.size':8,'axes.titlesize':9,'axes.labelsize':8,
    'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':6.7,
    'pdf.fonttype':42,'ps.fonttype':42,
})
DARK='#202020'; GRAY='#777777'; LIGHT='#dddddd'; WHITE='#ffffff'
COL={'Flickr':'#4C78A8','Arxiv':'#59A14F','Reddit':'#F28E2B','Yelp':'#B07AA1'}
HATCH={'Flickr':'///','Arxiv':'xx','Reddit':'..','Yelp':'\\\\'}

def save(fig,name):
    fig.savefig(FIG/f'{name}.pdf',bbox_inches='tight')
    fig.savefig(FIG/f'{name}.png',dpi=320,bbox_inches='tight')
    plt.close(fig)

# Final primary evidence: exact bytes plus architecture-faithful timing.
df=pd.read_csv(NEW/'results/primary_combined.csv')
labels=['F7','F17','F27','A7','A17','A27','R7','R17','R27','Y7']
x=np.arange(len(df))
colors=[COL[d] for d in df.dataset_norm]
hatches=[HATCH[d] for d in df.dataset_norm]
fig,axs=plt.subplots(1,3,figsize=(7.25,2.25),gridspec_kw={'wspace':0.32})
for ax,vals,title,ylabel,ylim,mean,fmt in [
    (axs[0],df.support_reduction_pct,'(a) Serialized support','Reduction (%)',(0,64),df.support_reduction_pct.mean(),'{:.1f}% mean'),
    (axs[1],df.physical_traffic_reduction_pct,'(b) Complete physical traffic','Reduction (%)',(-4,24),df.physical_traffic_reduction_pct.mean(),'{:.1f}% mean'),
    (axs[2],df.speedup,'(c) Final subsystem timing','Speedup ($\\times$)',(0.95,1.31),float(np.exp(np.log(df.speedup).mean())),'{:.3f}$\\times$ GM'),
]:
    bars=ax.bar(x,vals,color=colors,edgecolor=DARK,linewidth=.5)
    for b,h in zip(bars,hatches): b.set_hatch(h)
    base=0 if ax is not axs[2] else 1
    ax.axhline(base,color=GRAY,linestyle='--',linewidth=.8)
    ax.axhline(mean,color=DARK,linestyle='-.',linewidth=.85,label=fmt.format(mean))
    ax.set_xticks(x,labels,rotation=32,ha='right'); ax.set_ylim(*ylim); ax.set_ylabel(ylabel); ax.set_title(title)
    ax.grid(axis='y',color=LIGHT,linewidth=.35,zorder=0)
    ax.legend(frameon=False,loc='best')
# Direct labels on regressions.
for i,v in enumerate(df.speedup):
    if v<1:
        axs[2].text(i,v+.004,f'{v:.3f}',ha='center',va='bottom',fontsize=5.8)
fig.tight_layout(pad=.45)
save(fig,'fig4_final_results')

# Online/lifecycle and validation evidence.
life=pd.read_csv(NEW/'results/anchor_lifecycle_summary.csv')
cap=life.groupby('capacity_bytes',as_index=False).agg(
    delta_targets=('delta_targets','sum'), hits=('resident_decoded','sum'),
    reread_bytes=('consumer_anchor_read_bytes','sum'))
cap['hit_rate']=100*cap.hits/cap.delta_targets
cap['label']=cap.capacity_bytes.map({16384:'16 KiB',262144:'256 KiB',1048576:'1 MiB',4194304:'4 MiB'})
mem=pd.read_csv(NEW/'results/heldout_absolute_memory_validation.csv')
mem_all=pd.read_csv(NEW/'results/complete_external_memory_validation.csv')
cy=pd.read_csv(NEW/'results/final_unified_primary_cycles.csv')
primary_ids=set(df.run_id)
primary_sched=cy[cy.run_id.isin(primary_ids)]
fig,axs=plt.subplots(1,2,figsize=(7.25,2.30),gridspec_kw={'wspace':0.32})
# capacity
xx=np.arange(len(cap))
b=axs[0].bar(xx,cap.hit_rate,color=['#bab0ac','#9ecae9','#4c78a8','#59a14f'],edgecolor=DARK,linewidth=.5)
for bar,h in zip(b,['//','///','xx','..']): bar.set_hatch(h)
axs[0].set_xticks(xx,cap.label,rotation=18); axs[0].set_ylabel('Consumer anchor hits (%)'); axs[0].set_ylim(0,88); axs[0].set_title('(a) Bounded anchor state'); axs[0].grid(axis='y',color=LIGHT,lw=.35)
ax2=axs[0].twinx(); ax2.plot(xx,cap.reread_bytes/2**20,color=DARK,marker='D',markerfacecolor=WHITE,linewidth=1.2,linestyle='--',label='Rereads (MiB)'); ax2.set_ylim(0,160); ax2.tick_params(labelsize=6.3); ax2.legend(frameon=False,loc='upper right')
# Cross-workload retained-stream validation plus the independent held-out point.
labels_all=['Arxiv','Flickr','Reddit','Yelp']
vals_all=[float(mem_all.loc[mem_all.case.str.startswith(x.lower()),'completion_error_percent'].iloc[0]) for x in labels_all]
xx=np.arange(len(labels_all))
b=axs[1].bar(xx,vals_all,color=[COL[x] for x in labels_all],edgecolor=DARK,linewidth=.5)
for bar,h in zip(b,[HATCH[x] for x in labels_all]): bar.set_hatch(h)
heldout=float(mem.loc[mem.case.eq('flickr_s17'),'absolute_error_percent'].iloc[0])
axs[1].scatter([1],[heldout],marker='D',s=34,facecolor=WHITE,edgecolor=DARK,
               linewidth=.9,zorder=4,label='Flickr-17 held out')
axs[1].axhline(5,color=DARK,linestyle='--',linewidth=.9,label='5% tolerance')
for i,v in enumerate(vals_all): axs[1].text(i,v+.10,f'{v:.3f}%',ha='center',va='bottom',fontsize=6.4)
axs[1].set_xticks(xx,labels_all); axs[1].set_ylim(0,5.6)
axs[1].set_ylabel('Completion-time error (%)')
axs[1].set_title('(b) External memory validation')
axs[1].grid(axis='y',color=LIGHT,lw=.35); axs[1].legend(frameon=False,loc='upper right')
fig.tight_layout(pad=.45)
save(fig,'fig8_final_validation')

# Depth sensitivity under one authoritative consumer-complete scheduler.
# D8 anchors come from the final ten-checkpoint primary table, Arxiv D16 comes
# from its final unified schedule, and D12+ points come from the independently
# trained depth-extension table.
depth=pd.read_csv(ROOT/'results_used/depth_extension/depth_extension_summary.csv')
def primary_speed(run_id):
    return float(df.loc[df.run_id.eq(run_id),'speedup'].iloc[0])
arxiv16=pd.read_csv(NEW/'results/schedule_detail/ogbn_arxiv_deepres16_w128_s7/causal_event_schedule.csv')
arxiv16_speed=float(arxiv16.loc[arxiv16.variant.eq('XORFLOW_ONLINE'),'speedup_vs_selected_baseline'].iloc[0])
series={
    'Arxiv': [(8,primary_speed('ogbn_arxiv_deepres8_w128_s7')),(16,arxiv16_speed)],
    'Reddit': [(8,primary_speed('reddit_deepres8_w128_s7_native'))],
    'Flickr': [(8,primary_speed('flickr_deepres8_w128_s7'))],
    'Yelp': [(8,primary_speed('yelp_deepres8_w128_s7_balanced_fallback'))],
}
for row in depth.itertuples(index=False):
    series[row.dataset].append((int(row.depth),float(row.consumer_complete_speedup)))
fig,ax=plt.subplots(figsize=(7.2,4.4))
for name,values in series.items():
    values=sorted(values)
    ax.plot([x for x,_ in values],[y for _,y in values],marker='o',linewidth=2,label=name)
ax.axhline(1.0,color=DARK,linewidth=1,linestyle='--')
ax.set(xlabel='Model depth (layers)',ylabel='Consumer-complete subsystem speedup vs BEICSR',xticks=[8,12,16,24,32])
ax.grid(alpha=.25); ax.legend(frameon=False,ncol=2); fig.tight_layout()
save(fig,'fig_depth_scaling_consumer_complete')
print('round14 figures generated')
