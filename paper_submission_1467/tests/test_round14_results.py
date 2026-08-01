import csv, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'results_used/review5_final2/results'

def rows(path):
    with open(path,newline='') as f: return list(csv.DictReader(f))

def gmean(xs): return math.exp(sum(math.log(x) for x in xs)/len(xs))

def test_primary_aggregates():
    d=rows(R/'primary_combined.csv')
    assert len(d)==10
    speed=[float(x['speedup']) for x in d]
    assert abs(gmean(speed)-1.08258225037)<1e-9
    assert sum(x>=1 for x in speed)==8
    assert abs(max(speed)-1.27924675673)<1e-9
    assert abs(sum(float(x['support_reduction_pct']) for x in d)/10-37.050646)<1e-5
    assert abs(sum(float(x['physical_traffic_reduction_pct']) for x in d)/10-7.939687)<1e-5

def test_dataset_balanced_and_flickr_disclosure():
    d=rows(R/'primary_combined.csv')
    groups={}
    for x in d: groups.setdefault(x['dataset_norm'],[]).append(float(x['speedup']))
    balanced=gmean([gmean(v) for v in groups.values()])
    assert abs(balanced-1.07644752228)<1e-9
    f={x['seed']:float(x['speedup']) for x in d if x['dataset_norm']=='Flickr'}
    assert abs(f['17']-0.996049)<1e-6
    assert abs(f['27']-0.974768)<1e-6

def test_heldout_memory_and_scalesim():
    d=rows(R/'heldout_absolute_memory_validation.csv')
    held=[x for x in d if x['role']=='HELD_OUT_VALIDATION'][0]
    assert held['same_case_external_used_for_prediction']=='False'
    assert float(held['absolute_error_percent'])<0.5
    cache=json.load(open(R/'scalesim_shape_cache.json'))
    if isinstance(cache, dict) and 'entries' not in cache:
        entries=list(cache.values())
    else:
        entries=cache.get('entries',cache if isinstance(cache,list) else [])
        if isinstance(entries,dict): entries=list(entries.values())
    assert len(entries)==7
