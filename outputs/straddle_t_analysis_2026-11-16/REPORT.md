# Phase G Amendment 12 — Straddle-T Analysis Report

## 1. Parameters
- Bootstrap seed: `20261115`
- Bootstrap resamples (`B`): `10000`
- Band pass rule: `n_invalid == 0`, `mean(recall_at_15) >= 0.90`, `median(latency_median_ms) <= 500.0 ms`
- Family-wise error rate control: Holm step-down across 5 hypotheses (`alpha = 0.05`)

## 2. Confirmatory Hypotheses (`hypotheses.csv`)

| Hypothesis | Group | Manifest | Arm | Component Bands | Point Est. | Raw p (Q-Cluster) | Raw p (F-Cluster) | Holm Adj. p | Decision |
|---|---|---|---|---|---|---|---|---|---|
| H1a | R | edgar_pairs_primary_T_edgar.csv | router | far_below,near_below | True | 0.000100 | 0.000100 | 0.000500 | **supported** |
| H1b | N | edgar_pairs_primary_T_edgar.csv | router | above_T(near_above+far_above) | False | 0.987201 | 0.992901 | 0.987201 | **not_supported** |
| H3 | R | edgar_pairs_primary_T_edgar.csv | default_hnsw | far_below,near_below | True | 0.000600 | 0.005000 | 0.002400 | **supported** |
| H5a | N | finqa_pairs_primary_T_hm.csv | router_hmT | far_below,near_below,near_above,far_above | True | 0.306869 | 0.310869 | 0.920608 | **not_supported** |
| H5b | R | edgar_pairs_secondary_T_hm.csv | router_hmT | far_below,near_above,far_above | True | 0.385161 | 0.340166 | 0.920608 | **not_supported** |

## 3. Generated Output Files
- `band_table.csv`
- `group_table.csv`
- `hypotheses.csv`
- `secondary_tables.csv`
- `descriptive_tables.csv`
- `REPORT.md`
