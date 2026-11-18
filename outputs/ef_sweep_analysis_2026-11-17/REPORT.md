# Phase H, Amendment 13: `ef_search` Sweep Analysis Report

- **Input results:** `C:/Users/ASUS/Documents/GitHub/BSC_Research_Route_Threshold_Huristic/outputs/ef_sweep_main_2026-11-17/results.jsonl` (`15480` rows)
- **Input EXPLAIN:** `C:/Users/ASUS/Documents/GitHub/BSC_Research_Route_Threshold_Huristic/outputs/ef_sweep_main_2026-11-17/explain_results.jsonl` (`2142` rows)
- **Primary thresholds:** `T_hm = 0.07119177617441379` (sensitivity `0.1`), `T_edgar = 0.3786921696945195`

## 1. Confirmatory Hypotheses (Exact Two-Sided McNemar, Holm Step-Down α = 0.05)

| Hypothesis | n_cells | pass@40 | pass@400 | n_01 (gain) | n_10 (loss) | p_value | Holm rank | Holm thr | Rejected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hm_default_hnsw | 65 | 11 | 44 | 33 | 0 | 0.000000 | 1 | 0.012500 | True |
| hm_always_iterative | 65 | 54 | 54 | 0 | 0 | 1.000000 | 4 | 0.050000 | False |
| edgar_cal_default_hnsw | 13 | 0 | 8 | 8 | 0 | 0.007812 | 2 | 0.016667 | True |
| edgar_cal_always_iterative | 13 | 4 | 11 | 7 | 0 | 0.015625 | 3 | 0.025000 | True |

## 2. Pass-Rule Decomposition

| Dataset | Arm | ef | n_cells | n_pass | recall_only_pass | latency_only_pass |
|---|---|---|---:|---:|---:|---:|
| hm | always_exact | none | 65 | 25 | 65 | 25 |
| hm | default_hnsw | 40 | 65 | 11 | 11 | 65 |
| hm | default_hnsw | 100 | 65 | 33 | 33 | 65 |
| hm | default_hnsw | 200 | 65 | 39 | 39 | 65 |
| hm | default_hnsw | 400 | 65 | 44 | 44 | 65 |
| hm | always_iterative | 40 | 65 | 54 | 54 | 65 |
| hm | always_iterative | 100 | 65 | 54 | 54 | 65 |
| hm | always_iterative | 200 | 65 | 54 | 54 | 65 |
| hm | always_iterative | 400 | 65 | 54 | 54 | 65 |
| edgar_cal | always_exact | none | 13 | 13 | 13 | 13 |
| edgar_cal | default_hnsw | 40 | 13 | 0 | 0 | 13 |
| edgar_cal | default_hnsw | 100 | 13 | 0 | 0 | 13 |
| edgar_cal | default_hnsw | 200 | 13 | 8 | 8 | 13 |
| edgar_cal | default_hnsw | 400 | 13 | 8 | 8 | 13 |
| edgar_cal | always_iterative | 40 | 13 | 4 | 4 | 13 |
| edgar_cal | always_iterative | 100 | 13 | 9 | 9 | 13 |
| edgar_cal | always_iterative | 200 | 13 | 11 | 11 | 13 |
| edgar_cal | always_iterative | 400 | 13 | 11 | 11 | 13 |

## 3. Operating-Region Subsets (`selectivity >= T`)

| Dataset | Subset | T | Arm | ef | n_cells | n_pass | recall_only | latency_only |
|---|---|---:|---|---|---:|---:|---:|---:|
| hm | primary_T_hm | 0.071192 | always_exact | none | 45 | 5 | 45 | 5 |
| hm | primary_T_hm | 0.071192 | default_hnsw | 40 | 45 | 11 | 11 | 45 |
| hm | primary_T_hm | 0.071192 | default_hnsw | 100 | 45 | 33 | 33 | 45 |
| hm | primary_T_hm | 0.071192 | default_hnsw | 200 | 45 | 39 | 39 | 45 |
| hm | primary_T_hm | 0.071192 | default_hnsw | 400 | 45 | 42 | 42 | 45 |
| hm | primary_T_hm | 0.071192 | always_iterative | 40 | 45 | 45 | 45 | 45 |
| hm | primary_T_hm | 0.071192 | always_iterative | 100 | 45 | 45 | 45 | 45 |
| hm | primary_T_hm | 0.071192 | always_iterative | 200 | 45 | 45 | 45 | 45 |
| hm | primary_T_hm | 0.071192 | always_iterative | 400 | 45 | 45 | 45 | 45 |
| hm | sensitivity_0_1 | 0.100000 | always_exact | none | 45 | 5 | 45 | 5 |
| hm | sensitivity_0_1 | 0.100000 | default_hnsw | 40 | 45 | 11 | 11 | 45 |
| hm | sensitivity_0_1 | 0.100000 | default_hnsw | 100 | 45 | 33 | 33 | 45 |
| hm | sensitivity_0_1 | 0.100000 | default_hnsw | 200 | 45 | 39 | 39 | 45 |
| hm | sensitivity_0_1 | 0.100000 | default_hnsw | 400 | 45 | 42 | 42 | 45 |
| hm | sensitivity_0_1 | 0.100000 | always_iterative | 40 | 45 | 45 | 45 | 45 |
| hm | sensitivity_0_1 | 0.100000 | always_iterative | 100 | 45 | 45 | 45 | 45 |
| hm | sensitivity_0_1 | 0.100000 | always_iterative | 200 | 45 | 45 | 45 | 45 |
| hm | sensitivity_0_1 | 0.100000 | always_iterative | 400 | 45 | 45 | 45 | 45 |
| edgar_cal | primary_T_edgar | 0.378692 | always_exact | none | 2 | 2 | 2 | 2 |
| edgar_cal | primary_T_edgar | 0.378692 | default_hnsw | 40 | 2 | 0 | 0 | 2 |
| edgar_cal | primary_T_edgar | 0.378692 | default_hnsw | 100 | 2 | 0 | 0 | 2 |
| edgar_cal | primary_T_edgar | 0.378692 | default_hnsw | 200 | 2 | 2 | 2 | 2 |
| edgar_cal | primary_T_edgar | 0.378692 | default_hnsw | 400 | 2 | 2 | 2 | 2 |
| edgar_cal | primary_T_edgar | 0.378692 | always_iterative | 40 | 2 | 1 | 1 | 2 |
| edgar_cal | primary_T_edgar | 0.378692 | always_iterative | 100 | 2 | 2 | 2 | 2 |
| edgar_cal | primary_T_edgar | 0.378692 | always_iterative | 200 | 2 | 2 | 2 | 2 |
| edgar_cal | primary_T_edgar | 0.378692 | always_iterative | 400 | 2 | 2 | 2 | 2 |

## 4. `default_hnsw` Cliff Table (`s_pass(ef)` vs `k / ef`)

*Caveat: Mandarapu & Kunkunuru (`arXiv:2606.16341v1`) assumes no attribute-vector correlation; the observed cliff may shift on the scrambled H&M tables and EDGAR.*

| Dataset | Table | ef | k/ef | s_pass(ef) | s_pass / (k/ef) |
|---|---|---:|---:|---:|---:|
| hm | hm_clothes_0 | 40 | 0.2500 | 0.298592 | 1.194 |
| hm | hm_clothes_0 | 100 | 0.1000 | 0.203758 | 2.038 |
| hm | hm_clothes_0 | 200 | 0.0500 | 0.106089 | 2.122 |
| hm | hm_clothes_0 | 400 | 0.0250 | 0.047774 | 1.911 |
| hm | hm_clothes_100 | 40 | 0.2500 | None | None |
| hm | hm_clothes_100 | 100 | 0.1000 | None | None |
| hm | hm_clothes_100 | 200 | 0.0500 | None | None |
| hm | hm_clothes_100 | 400 | 0.0250 | 0.230942 | 9.238 |
| hm | hm_clothes_25 | 40 | 0.2500 | 0.329010 | 1.316 |
| hm | hm_clothes_25 | 100 | 0.1000 | 0.203758 | 2.038 |
| hm | hm_clothes_25 | 200 | 0.0500 | 0.106089 | 2.122 |
| hm | hm_clothes_25 | 400 | 0.0250 | 0.047774 | 1.911 |
| hm | hm_clothes_50 | 40 | 0.2500 | 0.329010 | 1.316 |
| hm | hm_clothes_50 | 100 | 0.1000 | 0.203758 | 2.038 |
| hm | hm_clothes_50 | 200 | 0.0500 | 0.106089 | 2.122 |
| hm | hm_clothes_50 | 400 | 0.0250 | 0.106089 | 4.244 |
| hm | hm_clothes_75 | 40 | 0.2500 | None | None |
| hm | hm_clothes_75 | 100 | 0.1000 | 0.230942 | 2.309 |
| hm | hm_clothes_75 | 200 | 0.0500 | 0.203758 | 4.075 |
| hm | hm_clothes_75 | 400 | 0.0250 | 0.106089 | 4.244 |
| edgar_cal | edgar_chunks | 40 | 0.3750 | None | None |
| edgar_cal | edgar_chunks | 100 | 0.1500 | None | None |
| edgar_cal | edgar_chunks | 200 | 0.0750 | 0.203742 | 2.717 |
| edgar_cal | edgar_chunks | 400 | 0.0375 | 0.203742 | 5.433 |

## 5. Plan Verification (`EXPLAIN (ANALYZE, BUFFERS)`)
- Total EXPLAIN rows: `2142`; `seq_scan_flagged`: `0`.
