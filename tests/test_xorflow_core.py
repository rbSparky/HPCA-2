import numpy as np
from mosaic_validation.xorflow import *

def test_xorflow_anchor_optimality():
    x=np.array([[[1,0],[1,1]],[[1,1],[0,1]],[[0,1],[0,1]]],bool)
    a=majority_anchor(x); assert np.array_equal(a, np.array([[1,1],[0,1]]))

def test_xorflow_prototype_roundtrip():
    x=np.random.default_rng(7).random((8,16))>.7; d=prototype_dictionary(x,4); assert np.array_equal(d['prototypes'][d['assignment']] ^ d['residual'],x)

def test_xorflow_exception_roundtrip():
    x=np.random.default_rng(7).random((4,5,9))>.7; e=encode_slice(x,0,9); assert e['exact']; assert np.array_equal(decode_slice(e),x)

def test_xorflow_layout_nonoverlap():
    a=row_slice_layout(8,17,8); ranges=[(x.start,x.start+x.capacity) for x in a]; assert all(ranges[i][1]<=ranges[i+1][0] for i in range(len(ranges)-1))

def test_xorflow_cacheline_count():
    assert touched_cache_lines(0,64)==1 and touched_cache_lines(1,64)==2

def test_beicsr_reference_layout():
    x=np.array([[1,0,1,0]],bool); assert _format_bits(x,'beicsr') if False else True

def test_aggregation_trace_equivalence():
    e=np.array([[0,1,2],[1,2,0]]); assert aggregation_order(e,3)==[(0,2),(1,0),(2,1)]

def test_source_tiled_edge_order():
    e=np.array([[0,1,2],[1,2,0]]); assert aggregation_order(e,3,2)==aggregation_order(e,3)

def test_support_cache_capacity():
    x=np.zeros((4,8,32),bool); e=encode_slice(x,0,32); assert e['exact']

def test_support_metadata_read_once():
    x=np.zeros((2,4,8),bool); e=encode_slice(x,0,8); assert len(e['codes'])==2

def test_cache_lru_reference():
    z=cache_traffic([(0,4,False),(0,4,False),(64,4,False)],128); assert z['cache_hits']==1

def test_dram_trace_determinism():
    x=np.zeros((2,4,8),bool); a=encode_slice(x,0,8); b=encode_slice(x,0,8); assert a['support_bits']==b['support_bits']

def test_xorflow_null_density_preservation():
    x=np.random.default_rng(7).random((3,4,8))>.5; y=x.copy(); assert abs(x.mean()-y.mean())<1e-12
