# HPCA XORFLOW Consolidated Host Results

All values below are modeled aggregation+combination host estimates, not measured end-to-end accelerator speedups.

| Configuration | Run | Pairs | Host speedup (geomean) | Serialized-memory speedup | Mean traffic reduction | Mean support ratio | FP8 quality |
|---|---|---:|---:|---:|---:|---:|---:|
| ogbn_arxiv_deepres8_w128_s17 | arxiv_bw128 | 2 | 1.233× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_bw512 | 2 | 1.029× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_cache1m | 2 | 1.208× | 1.248× | 20.5% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_cache256 | 2 | 1.210× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_decoder16 | 2 | 1.201× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_decoder8 | 2 | 1.184× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres16_w128_s7 | arxiv_depth16 | 2 | 1.159× | 1.186× | 16.4% | 0.675 | 0.6821 |
| ogbn_arxiv_deepres4_w128_s7 | arxiv_depth4_repaired | 2 | 1.129× | 1.150× | 13.9% | 0.845 | 0.6847 |
| ogbn_arxiv_gin8_w128_s7 | arxiv_gin8 | 2 | 0.988× | 0.984× | -1.2% | 0.187 | 0.0016 |
| ogbn_arxiv_gin8_residual_w128_s7 | arxiv_gin8_residual | 2 | 1.271× | 1.341× | 25.7% | 0.663 | 0.3869 |
| ogbn_arxiv_graphsage8_w128_s7 | arxiv_graphsage8 | 2 | 1.173× | 1.217× | 18.0% | 0.638 | 0.4153 |
| ogbn_arxiv_graphsage8_residual_w128_s7 | arxiv_graphsage8_residual | 2 | 1.523× | 1.665× | 41.1% | 0.770 | 0.5658 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_order_o1 | 2 | 1.210× | 1.248× | 20.5% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s7 | arxiv_s7 | 2 | 1.244× | 1.290× | 23.2% | 0.675 | 0.6870 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_single_buffer | 2 | 1.112× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_slice256 | 2 | 1.144× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_slice64 | 2 | 0.975× | 0.973× | -2.1% | 0.623 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_slice96 | 2 | 1.180× | 1.193× | 16.9% | 0.627 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_support32k | 2 | 1.210× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_support64k | 2 | 1.210× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_support8k | 2 | 1.210× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_tile256 | 2 | 1.210× | 1.248× | 20.5% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s17 | arxiv_tile64 | 2 | 1.209× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w256_s7 | arxiv_width256 | 2 | 1.427× | 1.471× | 32.9% | 0.653 | 0.6919 |
| ogbn_arxiv_deepres8_w64_s7 | arxiv_width64 | 2 | 0.978× | 0.972× | -2.2% | 0.654 | 0.6797 |
| chameleon_gcnii16 | boundary_chameleon | 2 | 1.000× | 0.955× | -3.2% | 0.424 |  |
| cora_gcnii16 | boundary_cora | 2 | 1.028× | 1.062× | 8.1% | 0.455 |  |
| pubmed_gcnii16 | boundary_pubmed | 2 | 1.028× | 1.048× | 6.0% | 0.363 |  |
| citeseer_deepres8_w128_s7 | citeseer | 2 | 1.132× | 1.257× | 24.9% | 0.777 | 0.6370 |
| flickr_deepres8_w128_s7 | flickr_cache1m | 2 | 1.052× | 1.063× | 6.6% | 0.380 | 0.4723 |
| flickr_deepres8_w128_s7 | flickr_cache256 | 2 | 1.053× | 1.062× | 6.4% | 0.380 | 0.4723 |
| flickr_deepres8_w128_s7 | flickr_order_o1 | 2 | 1.052× | 1.062× | 6.5% | 0.380 | 0.4723 |
| flickr_deepres8_w128_s7 | flickr_slice64 | 2 | 0.983× | 0.981× | -1.4% | 0.328 | 0.4723 |
| ogbn_arxiv_deepres8_w128_s17 | primary_arxiv_s17 | 2 | 1.210× | 1.247× | 20.4% | 0.693 | 0.6828 |
| ogbn_arxiv_deepres8_w128_s27 | primary_arxiv_s27 | 2 | 1.253× | 1.300× | 23.8% | 0.691 | 0.6866 |
| flickr_deepres8_w128_s7 | primary_flickr | 2 | 1.052× | 1.063× | 6.5% | 0.380 | 0.4723 |
| reddit_deepres8_w128_s7_native | primary_reddit | 2 | 1.691× | 1.696× | 40.9% | 0.634 | 0.9534 |
| yelp_deepres8_w128_s7_balanced_fallback | primary_yelp_borderline | 2 | 1.076× | 1.084× | 8.1% | 0.484 |  |
| reddit_deepres8_w128_s7_native | reddit_cache1m | 2 | 1.748× | 1.754× | 42.9% | 0.634 | 0.9534 |
| reddit_deepres8_w128_s7_native | reddit_cache256 | 2 | 1.659× | 1.664× | 39.8% | 0.634 | 0.9534 |
| reddit_deepres8_w128_s7_native | reddit_order_o1 | 2 | 1.591× | 1.596× | 37.3% | 0.634 | 0.9534 |
| reddit_deepres8_w128_s7_native | reddit_slice256 | 2 | 1.677× | 1.696× | 40.9% | 0.634 | 0.9534 |
| reddit_deepres8_w128_s7_native | reddit_slice64 | 2 | 0.999× | 0.999× | -0.1% | 0.572 | 0.9534 |
| reddit_deepres8_w128_s7_native | reddit_slice96 | 2 | 1.058× | 1.058× | 5.5% | 0.575 | 0.9534 |
| reddit_deepres8_w128_s7_native | reddit_support64k | 2 | 1.691× | 1.696× | 40.9% | 0.634 | 0.9534 |
| reddit_deepres8_w128_s7_native | reddit_tile64 | 2 | 1.691× | 1.696× | 40.9% | 0.634 | 0.9534 |
| yelp_deepres8_w128_s7_balanced_fallback | yelp_cache1m | 2 | 1.073× | 1.080× | 7.8% | 0.484 |  |
| yelp_deepres8_w128_s7_balanced_fallback | yelp_cache256 | 2 | 1.079× | 1.087× | 8.3% | 0.484 |  |
| yelp_deepres8_w128_s7_balanced_fallback | yelp_order_o1 | 2 | 1.076× | 1.084× | 8.1% | 0.484 |  |
| yelp_deepres8_w128_s7_balanced_fallback | yelp_slice64 | 2 | 0.988× | 0.987× | -1.0% | 0.434 |  |

Machine-readable table: `PAPER_SUITE_HOST_SUMMARY.csv`.
