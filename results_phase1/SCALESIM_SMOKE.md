# SCALE-Sim dense GEMM smoke test

This callability smoke test does not evaluate MOSAIC.

Command: `/home/rishabh/HPCA2/mosaic_delta_phase1/.scalesim-python -m mosaic_validation.scalesim_smoke_runner -c /home/rishabh/HPCA2/mosaic_delta_phase1/results_phase1/scalesim_32x32_ws.cfg -t /home/rishabh/HPCA2/mosaic_delta_phase1/results_phase1/scalesim_cora_hidden.csv -l /home/rishabh/HPCA2/mosaic_delta_phase1/third_party/SCALE-Sim/layouts/conv_nets/test.csv -p /home/rishabh/HPCA2/mosaic_delta_phase1/results_phase1/scalesim_reports`

Exit code: `0`

```text
====================================================
******************* SCALE SIM **********************
====================================================
Array Size: 	32x32
SRAM IFMAP (kB): 	256
SRAM Filter (kB): 	256
SRAM OFMAP (kB): 	256
Dataflow: 	Weight Stationary
topology file path: 	/home/rishabh/HPCA2/mosaic_delta_phase1/results_phase1/scalesim_cora_hidden.csv
layout file path: 	/home/rishabh/HPCA2/mosaic_delta_phase1/third_party/SCALE-Sim/layouts/conv_nets/test.csv
Working in ESTIMATE BANDWIDTH mode.
====================================================

Running Layer 0
Total cycles: 26920
Compute cycles: 11207
Stall cycles: 0
Overall utilization: 96.65%
Mapping efficiency: 100.00%
Average IFMAP SRAM BW: 30.929 words/cycle
Average Filter SRAM BW: 0.365 words/cycle
Average OFMAP SRAM BW: 30.929 words/cycle
Average IFMAP DRAM BW: 16.051 words/cycle
Average Filter DRAM BW: 7.802 words/cycle
Average OFMAP DRAM BW: 36.185 words/cycle
************ SCALE SIM Run Complete ****************


  0%|          | 0/11208 [00:00<?, ?it/s]
  9%|▊         | 962/11208 [00:00<00:01, 9608.49it/s]
 17%|█▋        | 1923/11208 [00:00<00:01, 7768.97it/s]
 24%|██▍       | 2722/11208 [00:00<00:01, 6138.03it/s]
 30%|███       | 3372/11208 [00:00<00:01, 5617.35it/s]
 35%|███▌      | 3954/11208 [00:00<00:01, 5231.64it/s]
 40%|████      | 4488/11208 [00:00<00:01, 5056.32it/s]
 48%|████▊     | 5405/11208 [00:00<00:00, 6177.27it/s]
 55%|█████▌    | 6197/11208 [00:00<00:00, 6665.10it/s]
 61%|██████▏   | 6888/11208 [00:01<00:00, 6422.30it/s]
 67%|██████▋   | 7548/11208 [00:01<00:00, 5780.76it/s]
 73%|███████▎  | 8147/11208 [00:01<00:00, 5291.37it/s]
 78%|███████▊  | 8695/11208 [00:01<00:00, 5048.07it/s]
 85%|████████▌ | 9561/11208 [00:01<00:00, 5971.59it/s]
 91%|█████████▏| 10244/11208 [00:01<00:00, 6200.57it/s]
 97%|█████████▋| 10885/11208 [00:01<00:00, 6143.93it/s]
100%|██████████| 11208/11208 [00:01<00:00, 5976.99it/s]

```
