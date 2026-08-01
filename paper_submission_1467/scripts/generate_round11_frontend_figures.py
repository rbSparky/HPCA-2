#!/usr/bin/env python3
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT=Path(__file__).resolve().parents[1]
TAB=ROOT/'results_used'/'appendix'/'tables'
FIG=ROOT/'figures'; SFIG=ROOT/'supplement'/'figures'
BLUE='#0072B2'; SKY='#56B4E9'; ORANGE='#E69F00'; GREEN='#009E73'; PURPLE='#CC79A7'; GRAY='#6B6B6B'; DARK='#202020'; RED=DARK; WHITE='#FFFFFF'; LIGHT='#D9D9D9'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.2,'axes.labelsize':8.2,'axes.titlesize':8.8,'xtick.labelsize':7.1,'ytick.labelsize':7.1,'legend.fontsize':6.5,'pdf.fonttype':42,'ps.fonttype':42,'axes.linewidth':.8})

def save(fig,path):
    fig.savefig(path.with_suffix('.pdf'),bbox_inches='tight',pad_inches=.025)
    fig.savefig(path.with_suffix('.png'),dpi=360,bbox_inches='tight',pad_inches=.025)
    plt.close(fig)

# Main Fig. 1: direct learned-structure controls only.
a2=pd.read_csv(TAB/'A2_learned_structure_controls.csv')
primary_ids=['flickr_deepres8_w128_s7','flickr_deepres8_w128_s17','flickr_deepres8_w128_s27','ogbn_arxiv_deepres8_w128_s7','ogbn_arxiv_deepres8_w128_s17','ogbn_arxiv_deepres8_w128_s27','reddit_deepres8_w128_s7_native','reddit_deepres8_w128_s17_native','reddit_deepres8_w128_s27_native','yelp_deepres8_w128_s7_balanced_fallback']
controls=['real_adjacent','nonadjacent_l_plus_2','row_permutation','feature_permutation','exact_count_independent']
labels=['Adjacent','Layer +2','Rows permuted','Features permuted','Independent']
colors=[GREEN,SKY,PURPLE,ORANGE,GRAY]; hatches=['///','..','xx','\\','++']; markers=['o','s','^','D','P']
p=a2[a2.run_id.isin(primary_ids)]
fig,axs=plt.subplots(1,2,figsize=(7.15,2.35))
for ax,metric,ylabel,ylim,title in [(axs[0],'jaccard','Support Jaccard',(0,1.03),'(a) Learned support alignment'),(axs[1],'exception_density','XOR exception density',(0,.56),'(b) Correspondence suppresses events')]:
    vals=[]
    for i,c in enumerate(controls):
        v=p[p.control_type==c][metric].to_numpy(); vals.append(np.median(v)); jit=np.linspace(-.08,.08,len(v))
        ax.scatter(np.full(len(v),i)+jit,v,s=18,facecolor=WHITE,edgecolor=colors[i],lw=.8,marker=markers[i],zorder=3)
    bars=ax.bar(np.arange(len(controls)),vals,color=colors,edgecolor=DARK,lw=.5,hatch=hatches,alpha=.78,zorder=2)
    ax.set_xticks(np.arange(len(controls)),labels,rotation=25,ha='right'); ax.set_ylabel(ylabel); ax.set_ylim(*ylim); ax.grid(axis='y',color=LIGHT,lw=.4); ax.set_title(title)
    off=.019 if metric=='jaccard' else .012
    for b,v in zip(bars,vals): ax.text(b.get_x()+b.get_width()/2,v+off,f'{v:.3f}',ha='center',fontsize=6.6,fontweight='bold')
fig.tight_layout(pad=.35); save(fig,FIG/'fig1_opportunity_scaling')

# Main Fig. 7: conservative implementation scope.
a8=pd.read_csv(TAB/'A8_decoder_banking.csv')
fig=plt.figure(figsize=(7.15,2.35)); gs=fig.add_gridspec(1,3,width_ratios=[1.18,1.02,1.10],wspace=.40)
ax=fig.add_subplot(gs[0,0]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis('off'); ax.text(0,.99,'(a) Producer RTL scope',ha='left',va='top',fontweight='bold')
steps=[('32 x 64-bit tile capture','#E8F1FA',BLUE),('Majority + XOR front end','#E8F1FA',BLUE),('Dense / ID / Gap8 stream RTL','#FFF2DC',ORANGE),('Finite serialized interface','#E8F7F2',GREEN)]
ys=[.76,.56,.36,.16]
for i,((txt,fc,ec),y) in enumerate(zip(steps,ys)):
    ax.add_patch(FancyBboxPatch((.06,y),.88,.13,boxstyle='round,pad=.01',facecolor=fc,edgecolor=ec,lw=1)); ax.text(.5,y+.065,txt,ha='center',va='center',fontsize=6.65)
    if i<3: ax.add_patch(FancyArrowPatch((.5,y-.002),(.5,ys[i+1]+.135),arrowstyle='-|>',mutation_scale=8,lw=.9,color=GRAY))
ax.text(.5,.035,'1,055 mapped cells; 24/24 streams exact',ha='center',va='bottom',color=DARK,fontweight='bold',fontsize=5.55)
ax=fig.add_subplot(gs[0,1]); banks=a8.banks.to_numpy(); thr=a8.encoded_bits_per_cycle.to_numpy(); conf=a8.bank_conflicts.to_numpy()
ax.bar(range(3),thr,color=[ORANGE,SKY,GREEN],edgecolor=DARK,lw=.55,hatch=['///','xx','..']); ax.axhline(2048,color=RED,ls='--',lw=1,label='2,048 nominal'); ax.set_xticks(range(3),[str(x) for x in banks]); ax.set_xlabel('Support-cache banks'); ax.set_ylabel('Encoded bits/cycle'); ax.set_ylim(0,2200); ax.grid(axis='y',color=LIGHT,lw=.4); ax.set_title('(b) Bank-aware 32-lane model')
for i,v in enumerate(thr): ax.text(i,v+55,f'{v:,.0f}',ha='center',fontsize=6.4,fontweight='bold')
ax2=ax.twinx(); ax2.plot(range(3),conf/conf[0]*100,color=PURPLE,marker='D',mfc=WHITE,ls='-.',lw=1.5); ax2.set_ylim(0,112); ax2.set_ylabel('Conflicts vs. 8 banks (%)'); ax2.text(2,conf[-1]/conf[0]*100+5,'2.9%',ha='center',color=PURPLE,fontsize=6.3,fontweight='bold')
ax=fig.add_subplot(gs[0,2]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis('off'); ax.text(0,.99,'(c) Routed 8-lane cluster',ha='left',va='top',fontweight='bold')
rows=[('Timing','1.0 ns target; +0.565 ns slack',BLUE,'#E8F1FA'),('Route','0 DRC errors; 13.881 mm wire',GREEN,'#E8F7F2'),('Die','0.0682 mm$^2$; 11% utilization',ORANGE,'#FFF2DC'),('Cells','0.001795 mm$^2$ standard cells',PURPLE,'#F7EAF3')]
for (lab,val,ec,fc),y in zip(rows,[.76,.56,.36,.16]):
    ax.add_patch(FancyBboxPatch((.03,y),.94,.15,boxstyle='round,pad=.01',facecolor=fc,edgecolor=ec,lw=1))
    ax.text(.08,y+.105,lab,ha='left',va='center',fontweight='bold',color=ec,fontsize=6.9)
    ax.text(.08,y+.043,val,ha='left',va='center',fontsize=6.05)
ax.text(.5,.035,'OpenROAD/ORFS, Nangate45',ha='center',va='bottom',color=GRAY,fontsize=5.9)
save(fig,FIG/'fig7_implementation_validation')

print('Generated structure and implementation figures')
