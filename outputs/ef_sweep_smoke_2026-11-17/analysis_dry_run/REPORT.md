# Phase H, Amendment 13: `ef_search` Sweep Analysis Report

- **Input results:** `C:/Users/ASUS/Documents/GitHub/BSC_Research_Route_Threshold_Huristic/outputs/ef_sweep_smoke_2026-11-17/results.jsonl` (`279` rows)
- **Input EXPLAIN:** `C:/Users/ASUS/Documents/GitHub/BSC_Research_Route_Threshold_Huristic/outputs/ef_sweep_smoke_2026-11-17/explain_results.jsonl` (`117` rows)
- **Primary thresholds:** `T_hm = 0.07119177617441379` (sensitivity `0.1`), `T_edgar = 0.3786921696945195`

> **WARNING (SMOKE DRY RUN):** Input is a smoke subset (`n_vectors < 20` per cell); numbers below are for pipeline verification only and must NOT be interpreted.

## 1. Confirmatory Hypotheses (Exact Two-Sided McNemar, Holm Step-Down α = 0.05)

| Hypothesis | n_cells | pass@40 | pass@400 | n_01 (gain) | n_10 (loss) | p_value | Holm rank | Holm thr | Rejected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hm_default_hnsw | 6 | 0 | 0 | 0 | 0 | 1.000000 | 1 | 0.012500 | False |
| hm_always_iterative | 6 | 0 | 0 | 0 | 0 | 1.000000 | 2 | 0.016667 | False |
| edgar_cal_default_hnsw | 3 | 0 | 0 | 0 | 0 | 1.000000 | 3 | 0.025000 | False |
| edgar_cal_always_iterative | 3 | 0 | 0 | 0 | 0 | 1.000000 | 4 | 0.050000 | False |

## 2. Pass-Rule Decomposition

| Dataset | Arm | ef | n_cells | n_pass | recall_only_pass | latency_only_pass |
|---|---|---|---:|---:|---:|---:|
| hm | always_exact | none | 6 | 0 | 0 | 0 |
| hm | default_hnsw | 40 | 6 | 0 | 0 | 0 |
| hm | default_hnsw | 100 | 6 | 0 | 0 | 0 |
| hm | default_hnsw | 200 | 6 | 0 | 0 | 0 |
| hm | default_hnsw | 400 | 6 | 0 | 0 | 0 |
| hm | always_iterative | 40 | 6 | 0 | 0 | 0 |
| hm | always_iterative | 100 | 6 | 0 | 0 | 0 |
| hm | always_iterative | 200 | 6 | 0 | 0 | 0 |
| hm | always_iterative | 400 | 6 | 0 | 0 | 0 |
| edgar_cal | always_exact | none | 3 | 0 | 0 | 0 |
| edgar_cal | default_hnsw | 40 | 3 | 0 | 0 | 0 |
| edgar_cal | default_hnsw | 100 | 3 | 0 | 0 | 0 |
| edgar_cal | default_hnsw | 200 | 3 | 0 | 0 | 0 |
| edgar_cal | default_hnsw | 400 | 3 | 0 | 0 | 0 |
| edgar_cal | always_iterative | 40 | 3 | 0 | 0 | 0 |
| edgar_cal | always_iterative | 100 | 3 | 0 | 0 | 0 |
| edgar_cal | always_iterative | 200 | 3 | 0 | 0 | 0 |
| edgar_cal | always_iterative | 400 | 3 | 0 | 0 | 0 |

## 3. Operating-Region Subsets (`selectivity >= T`)

| Dataset | Subset | T | Arm | ef | n_cells | n_pass | recall_only | latency_only |
|---|---|---:|---|---|---:|---:|---:|---:|
| hm | primary_T_hm | 0.071192 | always_exact | none | 4 | 0 | 0 | 0 |
| hm | primary_T_hm | 0.071192 | default_hnsw | 40 | 4 | 0 | 0 | 0 |
| hm | primary_T_hm | 0.071192 | default_hnsw | 100 | 4 | 0 | 0 | 0 |
| hm | primary_T_hm | 0.071192 | default_hnsw | 200 | 4 | 0 | 0 | 0 |
| hm | primary_T_hm | 0.071192 | default_hnsw | 400 | 4 | 0 | 0 | 0 |
| hm | primary_T_hm | 0.071192 | always_iterative | 40 | 4 | 0 | 0 | 0 |
| hm | primary_T_hm | 0.071192 | always_iterative | 100 | 4 | 0 | 0 | 0 |
| hm | primary_T_hm | 0.071192 | always_iterative | 200 | 4 | 0 | 0 | 0 |
| hm | primary_T_hm | 0.071192 | always_iterative | 400 | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | always_exact | none | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | default_hnsw | 40 | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | default_hnsw | 100 | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | default_hnsw | 200 | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | default_hnsw | 400 | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | always_iterative | 40 | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | always_iterative | 100 | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | always_iterative | 200 | 4 | 0 | 0 | 0 |
| hm | sensitivity_0_1 | 0.100000 | always_iterative | 400 | 4 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | always_exact | none | 1 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | default_hnsw | 40 | 1 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | default_hnsw | 100 | 1 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | default_hnsw | 200 | 1 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | default_hnsw | 400 | 1 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | always_iterative | 40 | 1 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | always_iterative | 100 | 1 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | always_iterative | 200 | 1 | 0 | 0 | 0 |
| edgar_cal | primary_T_edgar | 0.378692 | always_iterative | 400 | 1 | 0 | 0 | 0 |

## 4. `default_hnsw` Cliff Table (`s_pass(ef)` vs `k / ef`)

*Caveat: Mandarapu & Kunkunuru (`arXiv:2606.16341v1`) assumes no attribute-vector correlation; the observed cliff may shift on the scrambled H&M tables and EDGAR.*

| Dataset | Table | ef | k/ef | s_pass(ef) | s_pass / (k/ef) |
|---|---|---:|---:|---:|---:|
| hm | hm_clothes_0 | 40 | 0.2500 | None | None |
| hm | hm_clothes_0 | 100 | 0.1000 | None | None |
| hm | hm_clothes_0 | 200 | 0.0500 | None | None |
| hm | hm_clothes_0 | 400 | 0.0250 | None | None |
| hm | hm_clothes_100 | 40 | 0.2500 | None | None |
| hm | hm_clothes_100 | 100 | 0.1000 | None | None |
| hm | hm_clothes_100 | 200 | 0.0500 | None | None |
| hm | hm_clothes_100 | 400 | 0.0250 | None | None |
| edgar_cal | edgar_chunks | 40 | 0.3750 | None | None |
| edgar_cal | edgar_chunks | 100 | 0.1500 | None | None |
| edgar_cal | edgar_chunks | 200 | 0.0750 | None | None |
| edgar_cal | edgar_chunks | 400 | 0.0375 | None | None |

## 5. Plan Verification (`EXPLAIN (ANALYZE, BUFFERS)`)
- Total EXPLAIN rows: `117`; `seq_scan_flagged`: `0`.
