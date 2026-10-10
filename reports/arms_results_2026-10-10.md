# H&M three-arm danger-zone run: results — 2026-10-10

**[V]** = computed from `outputs/phase_a_arms/results.jsonl` by `src/phase_c_analysis/arm_analysis.py`. **[I]** = my interpretation. The protocol (`PHASE_A_ARMS_PROTOCOL.md`, Amendments 1 and 2) was frozen before the run; the hypotheses and the decision rule are applied exactly as written there.

Provenance [V]: run commit `a282da9`, pgvector 0.8.3, PostgreSQL 16.14, seed 20261010, k=10, ef_search=40, `jit=off`, server settings {"shared_buffers": "128MB", "work_mem": "4MB", "effective_cache_size": "4GB", "max_parallel_workers_per_gather": "2", "random_page_cost": "4"}. Result file contains one row per (table, filter, vector, arm).

## (a) Completeness

- Rows expected 6500, written **6500**, unique (table, filter, arm, vector) keys 6500, max multiplicity 1. [V]
- Rows with a non-null `error` (including statement timeouts): **0**; rows without a valid recall/latency: 0. [V]
- `plan_as_intended == false` rows: **0**. The pre-flight (`preflight.json`, 260 arm 2-5 checks) had 0 failures. [V]

| arm | rows | errors/timeouts | plan_as_intended=false | scan nodes (all rows) |
|---|---|---|---|---|
| planner-default | 1300 | 0 | 0 | Bitmap Heap Scan:900, Index Scan:400 |
| forced-exact | 1300 | 0 | 0 | Bitmap Heap Scan:1300 |
| forced-hnsw | 1300 | 0 | 0 | Index Scan:1300 |
| iterative-relaxed | 1300 | 0 | 0 | Index Scan:1300 |
| iterative-strict | 1300 | 0 | 0 | Index Scan:1300 |

- **Crash and resume.** The run stopped once when a PostgreSQL backend exited with code 2 and the server did crash recovery (container never restarted, OOMKilled=false); the script stopped itself without recording a row and was resumed (`resumes.jsonl`: resumed 2026-10-10T09:35:22Z with 5609 rows present). **891 rows were written after the resume** (row_idx >= 5609); they are flagged `post_resume` in the analysis. They fall in these (table, filter) cells: hm_clothes_50/gap1 (100), hm_clothes_50/gap2 (100), hm_clothes_50/gap3 (100), hm_clothes_50/idx1 (100), hm_clothes_50/idx2 (100), hm_clothes_50/idx3 (100), hm_clothes_50/lo1 (100), hm_clothes_50/lo4 (100), hm_clothes_50/lo5 (91). [V]
- The shared buffers were cold after crash recovery [I]; rows around the resume point may include a cold-cache effect on latency (not on recall).
- The aborted first and second starts are **excluded**: `results_aborted_frozen_arms.jsonl` (42 rows, frozen arm settings, see Amendment 2) was not read by this analysis. [V]

Cross-table spread of forced-exact median latency (ms) for the same filter, as a cache/noise indicator [V]:

| filter | selectivity | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|---|
| lo1 | 0.00012 | 0.43 | 0.44 | 0.45 | 0.46 | 0.33 |
| lo2 | 0.00085 | 2.00 | 1.90 | 1.98 | 1.98 | 2.49 |
| lo3 | 0.01054 | 26.6 | 64.4 | 24.2 | 67.6 | 24.7 |
| lo4 | 0.04777 | 284.8 | 97.9 | 154.8 | 125.5 | 113.0 |
| lo5 | 0.10609 | 283.4 | 252.6 | 316.5 | 266.9 | 262.2 |
| ctl | 0.20376 | 865.3 | 992.6 | 1080 | 547.1 | 611.2 |
| gap1 | 0.21388 | 1271 | 491.2 | 623.8 | 620.6 | 488.9 |
| gap2 | 0.23094 | 1448 | 694.2 | 760.4 | 1408 | 520.8 |
| gap3 | 0.25991 | 1943 | 640.0 | 781.3 | 1867 | 601.3 |
| gap4 | 0.29859 | 781.6 | 757.7 | 6567 | 1383 | 644.2 |
| idx1 | 0.32901 | 885.9 | 751.5 | 2261 | 1928 | 851.5 |
| idx2 | 0.37633 | 889.4 | 1089 | 1206 | 965.2 | 1694 |
| idx3 | 0.47050 | 3273 | 2465 | 3419 | 1131 | 1162 |

## (b) Per (table, filter, arm) summary

Columns: mean/min recall@10 over the 20 vectors; fraction of vectors with recall < 0.9; median rows returned (of 10); median latency = median of the 20 per-vector medians (each the median of 5 timed `EXPLAIN ANALYZE` runs); IQR of latency over the 20 vectors; scan node counts. Full data with more columns: `outputs/phase_a_arms/analysis/cell_summary.csv`. [V]

### Arm: planner-default

| table | filter | sel | mean rec | min rec | frac<0.9 | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|---|
| T0 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.46 | 0.09 | Bitmap Heap Scan:20 |
| T0 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 2.04 | 0.32 | Bitmap Heap Scan:20 |
| T0 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 28.2 | 4.27 | Bitmap Heap Scan:20 |
| T0 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 303.3 | 76.6 | Bitmap Heap Scan:20 |
| T0 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 273.0 | 43.3 | Bitmap Heap Scan:20 |
| T0 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 950.4 | 493.0 | Bitmap Heap Scan:20 |
| T0 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 1303 | 474.3 | Bitmap Heap Scan:20 |
| T0 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 1337 | 246.3 | Bitmap Heap Scan:20 |
| T0 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 2047 | 548.0 | Bitmap Heap Scan:20 |
| T0 | gap4 | 0.29859 | 0.930 | 0.60 | 0.20 | 10 | 1.30 | 0.35 | Index Scan:20 |
| T0 | idx1 | 0.32901 | 0.965 | 0.70 | 0.10 | 10 | 1.22 | 0.22 | Index Scan:20 |
| T0 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 1.20 | 0.24 | Index Scan:20 |
| T0 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1.22 | 0.24 | Index Scan:20 |
| T25 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.44 | 0.06 | Bitmap Heap Scan:20 |
| T25 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 1.97 | 0.30 | Bitmap Heap Scan:20 |
| T25 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 56.4 | 18.2 | Bitmap Heap Scan:20 |
| T25 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 99.3 | 8.24 | Bitmap Heap Scan:20 |
| T25 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 254.4 | 12.0 | Bitmap Heap Scan:20 |
| T25 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 1072 | 336.9 | Bitmap Heap Scan:20 |
| T25 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 481.3 | 41.5 | Bitmap Heap Scan:20 |
| T25 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 683.2 | 358.6 | Bitmap Heap Scan:20 |
| T25 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 608.5 | 73.4 | Bitmap Heap Scan:20 |
| T25 | gap4 | 0.29859 | 0.880 | 0.50 | 0.30 | 10 | 1.22 | 0.32 | Index Scan:20 |
| T25 | idx1 | 0.32901 | 0.945 | 0.50 | 0.10 | 10 | 1.06 | 0.35 | Index Scan:20 |
| T25 | idx2 | 0.37633 | 0.985 | 0.90 | 0.00 | 10 | 1.26 | 0.31 | Index Scan:20 |
| T25 | idx3 | 0.47050 | 0.995 | 0.90 | 0.00 | 10 | 1.25 | 0.15 | Index Scan:20 |
| T50 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.45 | 0.03 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 1.99 | 0.35 | Bitmap Heap Scan:20 |
| T50 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 23.5 | 3.16 | Bitmap Heap Scan:20 |
| T50 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 153.9 | 40.3 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 322.3 | 64.2 | Bitmap Heap Scan:20 (post-resume rows 19) |
| T50 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 890.5 | 1208 | Bitmap Heap Scan:20 |
| T50 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 611.2 | 72.0 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 726.3 | 121.9 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 767.8 | 170.4 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | gap4 | 0.29859 | 0.840 | 0.10 | 0.25 | 10 | 1.17 | 0.34 | Index Scan:20 |
| T50 | idx1 | 0.32901 | 0.955 | 0.70 | 0.15 | 10 | 1.40 | 0.34 | Index Scan:20 (post-resume rows 20) |
| T50 | idx2 | 0.37633 | 0.945 | 0.60 | 0.15 | 10 | 1.40 | 0.32 | Index Scan:20 (post-resume rows 20) |
| T50 | idx3 | 0.47050 | 0.970 | 0.60 | 0.10 | 10 | 1.41 | 0.42 | Index Scan:20 (post-resume rows 20) |
| T75 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.46 | 0.04 | Bitmap Heap Scan:20 |
| T75 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 2.01 | 0.24 | Bitmap Heap Scan:20 |
| T75 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 67.8 | 2.83 | Bitmap Heap Scan:20 |
| T75 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 124.2 | 12.3 | Bitmap Heap Scan:20 |
| T75 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 263.7 | 33.9 | Bitmap Heap Scan:20 |
| T75 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 535.6 | 39.8 | Bitmap Heap Scan:20 |
| T75 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 676.3 | 244.4 | Bitmap Heap Scan:20 |
| T75 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 1332 | 1295 | Bitmap Heap Scan:20 |
| T75 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 1809 | 1175 | Bitmap Heap Scan:20 |
| T75 | gap4 | 0.29859 | 0.800 | 0.30 | 0.50 | 8 | 1.28 | 0.18 | Index Scan:20 |
| T75 | idx1 | 0.32901 | 0.840 | 0.30 | 0.30 | 10 | 1.20 | 0.40 | Index Scan:20 |
| T75 | idx2 | 0.37633 | 0.900 | 0.30 | 0.15 | 10 | 1.23 | 0.38 | Index Scan:20 |
| T75 | idx3 | 0.47050 | 0.870 | 0.40 | 0.30 | 10 | 1.21 | 0.14 | Index Scan:20 |
| T100 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.34 | 0.06 | Bitmap Heap Scan:20 |
| T100 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 2.51 | 0.14 | Bitmap Heap Scan:20 |
| T100 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 24.0 | 3.40 | Bitmap Heap Scan:20 |
| T100 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 118.5 | 33.6 | Bitmap Heap Scan:20 |
| T100 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 264.6 | 17.8 | Bitmap Heap Scan:20 |
| T100 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 678.2 | 802.7 | Bitmap Heap Scan:20 |
| T100 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 502.3 | 61.6 | Bitmap Heap Scan:20 |
| T100 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 524.5 | 46.6 | Bitmap Heap Scan:20 |
| T100 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 597.5 | 28.5 | Bitmap Heap Scan:20 |
| T100 | gap4 | 0.29859 | 0.655 | 0.00 | 0.55 | 8 | 0.94 | 0.27 | Index Scan:20 |
| T100 | idx1 | 0.32901 | 0.715 | 0.00 | 0.45 | 10 | 1.08 | 0.25 | Index Scan:20 |
| T100 | idx2 | 0.37633 | 0.795 | 0.00 | 0.35 | 10 | 1.18 | 0.28 | Index Scan:20 |
| T100 | idx3 | 0.47050 | 0.695 | 0.00 | 0.35 | 10 | 1.08 | 0.23 | Index Scan:20 |

### Arm: forced-exact

| table | filter | sel | mean rec | min rec | frac<0.9 | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|---|
| T0 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.43 | 0.08 | Bitmap Heap Scan:20 |
| T0 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 2.00 | 0.43 | Bitmap Heap Scan:20 |
| T0 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 26.6 | 5.50 | Bitmap Heap Scan:20 |
| T0 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 284.8 | 63.6 | Bitmap Heap Scan:20 |
| T0 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 283.4 | 73.6 | Bitmap Heap Scan:20 |
| T0 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 865.3 | 201.0 | Bitmap Heap Scan:20 |
| T0 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 1271 | 380.5 | Bitmap Heap Scan:20 |
| T0 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 1448 | 289.5 | Bitmap Heap Scan:20 |
| T0 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 1943 | 551.0 | Bitmap Heap Scan:20 |
| T0 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 781.6 | 121.6 | Bitmap Heap Scan:20 |
| T0 | idx1 | 0.32901 | 1.000 | 1.00 | 0.00 | 10 | 885.9 | 1716 | Bitmap Heap Scan:20 |
| T0 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 889.4 | 90.9 | Bitmap Heap Scan:20 |
| T0 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 3273 | 780.3 | Bitmap Heap Scan:20 |
| T25 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.44 | 0.04 | Bitmap Heap Scan:20 |
| T25 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 1.90 | 0.14 | Bitmap Heap Scan:20 |
| T25 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 64.4 | 11.2 | Bitmap Heap Scan:20 |
| T25 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 97.9 | 5.78 | Bitmap Heap Scan:20 |
| T25 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 252.6 | 12.5 | Bitmap Heap Scan:20 |
| T25 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 992.6 | 289.2 | Bitmap Heap Scan:20 |
| T25 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 491.2 | 51.3 | Bitmap Heap Scan:20 |
| T25 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 694.2 | 207.1 | Bitmap Heap Scan:20 |
| T25 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 640.0 | 85.2 | Bitmap Heap Scan:20 |
| T25 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 757.7 | 163.8 | Bitmap Heap Scan:20 |
| T25 | idx1 | 0.32901 | 1.000 | 1.00 | 0.00 | 10 | 751.5 | 155.1 | Bitmap Heap Scan:20 |
| T25 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 1089 | 201.0 | Bitmap Heap Scan:20 |
| T25 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 2465 | 709.2 | Bitmap Heap Scan:20 |
| T50 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.45 | 0.04 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 1.98 | 0.22 | Bitmap Heap Scan:20 |
| T50 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 24.2 | 2.97 | Bitmap Heap Scan:20 |
| T50 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 154.8 | 26.5 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 316.5 | 85.5 | Bitmap Heap Scan:20 (post-resume rows 18) |
| T50 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 1080 | 594.4 | Bitmap Heap Scan:20 |
| T50 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 623.8 | 62.2 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 760.4 | 193.8 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 781.3 | 100.8 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 6567 | 7846 | Bitmap Heap Scan:20 |
| T50 | idx1 | 0.32901 | 1.000 | 1.00 | 0.00 | 10 | 2261 | 968.6 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 1206 | 124.2 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T50 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 3419 | 1189 | Bitmap Heap Scan:20 (post-resume rows 20) |
| T75 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.46 | 0.04 | Bitmap Heap Scan:20 |
| T75 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 1.98 | 0.22 | Bitmap Heap Scan:20 |
| T75 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 67.6 | 2.00 | Bitmap Heap Scan:20 |
| T75 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 125.5 | 18.5 | Bitmap Heap Scan:20 |
| T75 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 266.9 | 38.7 | Bitmap Heap Scan:20 |
| T75 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 547.1 | 102.9 | Bitmap Heap Scan:20 |
| T75 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 620.6 | 202.7 | Bitmap Heap Scan:20 |
| T75 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 1408 | 1176 | Bitmap Heap Scan:20 |
| T75 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 1867 | 1384 | Bitmap Heap Scan:20 |
| T75 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 1383 | 554.2 | Bitmap Heap Scan:20 |
| T75 | idx1 | 0.32901 | 1.000 | 1.00 | 0.00 | 10 | 1928 | 545.4 | Bitmap Heap Scan:20 |
| T75 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 965.2 | 141.0 | Bitmap Heap Scan:20 |
| T75 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1131 | 224.2 | Bitmap Heap Scan:20 |
| T100 | lo1 | 0.00012 | 1.000 | 1.00 | 0.00 | 10 | 0.33 | 0.04 | Bitmap Heap Scan:20 |
| T100 | lo2 | 0.00085 | 1.000 | 1.00 | 0.00 | 10 | 2.49 | 0.12 | Bitmap Heap Scan:20 |
| T100 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 24.7 | 3.35 | Bitmap Heap Scan:20 |
| T100 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 113.0 | 16.7 | Bitmap Heap Scan:20 |
| T100 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 262.2 | 26.2 | Bitmap Heap Scan:20 |
| T100 | ctl | 0.20376 | 1.000 | 1.00 | 0.00 | 10 | 611.2 | 694.9 | Bitmap Heap Scan:20 |
| T100 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 488.9 | 50.3 | Bitmap Heap Scan:20 |
| T100 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 520.8 | 44.6 | Bitmap Heap Scan:20 |
| T100 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 601.3 | 55.4 | Bitmap Heap Scan:20 |
| T100 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 644.2 | 39.4 | Bitmap Heap Scan:20 |
| T100 | idx1 | 0.32901 | 1.000 | 1.00 | 0.00 | 10 | 851.5 | 75.4 | Bitmap Heap Scan:20 |
| T100 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 1694 | 671.7 | Bitmap Heap Scan:20 |
| T100 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1162 | 400.0 | Bitmap Heap Scan:20 |

### Arm: forced-hnsw

| table | filter | sel | mean rec | min rec | frac<0.9 | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|---|
| T0 | lo1 | 0.00012 | 0.000 | 0.00 | 1.00 | 0 | 0.97 | 0.41 | Index Scan:20 |
| T0 | lo2 | 0.00085 | 0.000 | 0.00 | 1.00 | 0 | 0.91 | 0.24 | Index Scan:20 |
| T0 | lo3 | 0.01054 | 0.040 | 0.00 | 1.00 | 0 | 1.14 | 0.35 | Index Scan:20 |
| T0 | lo4 | 0.04777 | 0.150 | 0.00 | 1.00 | 2 | 1.07 | 0.27 | Index Scan:20 |
| T0 | lo5 | 0.10609 | 0.410 | 0.10 | 1.00 | 4 | 1.13 | 0.33 | Index Scan:20 |
| T0 | ctl | 0.20376 | 0.815 | 0.40 | 0.40 | 9 | 1.20 | 0.23 | Index Scan:20 |
| T0 | gap1 | 0.21388 | 0.820 | 0.50 | 0.40 | 9 | 1.21 | 0.20 | Index Scan:20 |
| T0 | gap2 | 0.23094 | 0.840 | 0.60 | 0.50 | 8 | 1.23 | 0.20 | Index Scan:20 |
| T0 | gap3 | 0.25991 | 0.860 | 0.40 | 0.40 | 10 | 1.22 | 0.30 | Index Scan:20 |
| T0 | gap4 | 0.29859 | 0.930 | 0.60 | 0.20 | 10 | 1.22 | 0.39 | Index Scan:20 |
| T0 | idx1 | 0.32901 | 0.965 | 0.70 | 0.10 | 10 | 1.20 | 0.28 | Index Scan:20 |
| T0 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 1.13 | 0.22 | Index Scan:20 |
| T0 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1.21 | 0.28 | Index Scan:20 |
| T25 | lo1 | 0.00012 | 0.000 | 0.00 | 1.00 | 0 | 0.92 | 0.28 | Index Scan:20 |
| T25 | lo2 | 0.00085 | 0.010 | 0.00 | 1.00 | 0 | 0.84 | 0.28 | Index Scan:20 |
| T25 | lo3 | 0.01054 | 0.030 | 0.00 | 1.00 | 0 | 0.98 | 0.23 | Index Scan:20 |
| T25 | lo4 | 0.04777 | 0.200 | 0.00 | 0.95 | 2 | 0.84 | 0.18 | Index Scan:20 |
| T25 | lo5 | 0.10609 | 0.410 | 0.00 | 0.80 | 3 | 0.91 | 0.23 | Index Scan:20 |
| T25 | ctl | 0.20376 | 0.720 | 0.30 | 0.55 | 8 | 1.17 | 0.25 | Index Scan:20 |
| T25 | gap1 | 0.21388 | 0.690 | 0.20 | 0.65 | 6 | 0.98 | 0.24 | Index Scan:20 |
| T25 | gap2 | 0.23094 | 0.825 | 0.50 | 0.50 | 8 | 1.26 | 0.23 | Index Scan:20 |
| T25 | gap3 | 0.25991 | 0.895 | 0.50 | 0.25 | 10 | 1.05 | 0.19 | Index Scan:20 |
| T25 | gap4 | 0.29859 | 0.880 | 0.50 | 0.30 | 10 | 1.03 | 0.33 | Index Scan:20 |
| T25 | idx1 | 0.32901 | 0.945 | 0.50 | 0.10 | 10 | 1.06 | 0.32 | Index Scan:20 |
| T25 | idx2 | 0.37633 | 0.985 | 0.90 | 0.00 | 10 | 1.22 | 0.28 | Index Scan:20 |
| T25 | idx3 | 0.47050 | 0.995 | 0.90 | 0.00 | 10 | 1.26 | 0.25 | Index Scan:20 |
| T50 | lo1 | 0.00012 | 0.000 | 0.00 | 1.00 | 0 | 1.12 | 0.42 | Index Scan:20 (post-resume rows 20) |
| T50 | lo2 | 0.00085 | 0.000 | 0.00 | 1.00 | 0 | 0.84 | 0.30 | Index Scan:20 |
| T50 | lo3 | 0.01054 | 0.025 | 0.00 | 1.00 | 0 | 0.96 | 0.30 | Index Scan:20 |
| T50 | lo4 | 0.04777 | 0.190 | 0.00 | 0.95 | 1 | 1.15 | 0.32 | Index Scan:20 (post-resume rows 20) |
| T50 | lo5 | 0.10609 | 0.375 | 0.00 | 0.80 | 2 | 1.22 | 0.41 | Index Scan:20 (post-resume rows 18) |
| T50 | ctl | 0.20376 | 0.600 | 0.10 | 0.75 | 6 | 0.97 | 0.23 | Index Scan:20 |
| T50 | gap1 | 0.21388 | 0.715 | 0.00 | 0.65 | 8 | 1.28 | 0.34 | Index Scan:20 (post-resume rows 20) |
| T50 | gap2 | 0.23094 | 0.725 | 0.20 | 0.65 | 7 | 1.50 | 0.32 | Index Scan:20 (post-resume rows 20) |
| T50 | gap3 | 0.25991 | 0.785 | 0.30 | 0.50 | 8 | 1.34 | 0.43 | Index Scan:20 (post-resume rows 20) |
| T50 | gap4 | 0.29859 | 0.840 | 0.10 | 0.25 | 10 | 1.16 | 0.39 | Index Scan:20 |
| T50 | idx1 | 0.32901 | 0.955 | 0.70 | 0.15 | 10 | 1.35 | 0.34 | Index Scan:20 (post-resume rows 20) |
| T50 | idx2 | 0.37633 | 0.945 | 0.60 | 0.15 | 10 | 1.49 | 0.42 | Index Scan:20 (post-resume rows 20) |
| T50 | idx3 | 0.47050 | 0.970 | 0.60 | 0.10 | 10 | 1.47 | 0.26 | Index Scan:20 (post-resume rows 20) |
| T75 | lo1 | 0.00012 | 0.000 | 0.00 | 1.00 | 0 | 0.97 | 0.29 | Index Scan:20 |
| T75 | lo2 | 0.00085 | 0.010 | 0.00 | 1.00 | 0 | 0.87 | 0.17 | Index Scan:20 |
| T75 | lo3 | 0.01054 | 0.010 | 0.00 | 1.00 | 0 | 0.95 | 0.22 | Index Scan:20 |
| T75 | lo4 | 0.04777 | 0.150 | 0.00 | 0.90 | 1 | 1.05 | 0.40 | Index Scan:20 |
| T75 | lo5 | 0.10609 | 0.305 | 0.00 | 0.80 | 2 | 1.07 | 0.22 | Index Scan:20 |
| T75 | ctl | 0.20376 | 0.640 | 0.10 | 0.70 | 6 | 1.16 | 0.20 | Index Scan:20 |
| T75 | gap1 | 0.21388 | 0.620 | 0.10 | 0.55 | 5 | 1.23 | 0.27 | Index Scan:20 |
| T75 | gap2 | 0.23094 | 0.530 | 0.00 | 0.80 | 5 | 1.09 | 0.40 | Index Scan:20 |
| T75 | gap3 | 0.25991 | 0.685 | 0.30 | 0.65 | 7 | 1.10 | 0.30 | Index Scan:20 |
| T75 | gap4 | 0.29859 | 0.800 | 0.30 | 0.50 | 8 | 1.31 | 0.16 | Index Scan:20 |
| T75 | idx1 | 0.32901 | 0.840 | 0.30 | 0.30 | 10 | 1.19 | 0.31 | Index Scan:20 |
| T75 | idx2 | 0.37633 | 0.900 | 0.30 | 0.15 | 10 | 1.26 | 0.33 | Index Scan:20 |
| T75 | idx3 | 0.47050 | 0.870 | 0.40 | 0.30 | 10 | 1.15 | 0.25 | Index Scan:20 |
| T100 | lo1 | 0.00012 | 0.000 | 0.00 | 1.00 | 0 | 0.85 | 0.18 | Index Scan:20 |
| T100 | lo2 | 0.00085 | 0.000 | 0.00 | 1.00 | 0 | 0.95 | 0.26 | Index Scan:20 |
| T100 | lo3 | 0.01054 | 0.000 | 0.00 | 1.00 | 0 | 0.88 | 0.20 | Index Scan:20 |
| T100 | lo4 | 0.04777 | 0.100 | 0.00 | 0.90 | 0 | 0.95 | 0.25 | Index Scan:20 |
| T100 | lo5 | 0.10609 | 0.200 | 0.00 | 0.80 | 0 | 0.86 | 0.30 | Index Scan:20 |
| T100 | ctl | 0.20376 | 0.520 | 0.00 | 0.75 | 6 | 1.04 | 0.31 | Index Scan:20 |
| T100 | gap1 | 0.21388 | 0.435 | 0.00 | 0.65 | 2 | 1.00 | 0.15 | Index Scan:20 |
| T100 | gap2 | 0.23094 | 0.455 | 0.00 | 0.80 | 4 | 0.96 | 0.30 | Index Scan:20 |
| T100 | gap3 | 0.25991 | 0.640 | 0.00 | 0.65 | 7 | 1.01 | 0.23 | Index Scan:20 |
| T100 | gap4 | 0.29859 | 0.655 | 0.00 | 0.55 | 8 | 0.92 | 0.23 | Index Scan:20 |
| T100 | idx1 | 0.32901 | 0.715 | 0.00 | 0.45 | 10 | 1.08 | 0.39 | Index Scan:20 |
| T100 | idx2 | 0.37633 | 0.795 | 0.00 | 0.35 | 10 | 1.21 | 0.33 | Index Scan:20 |
| T100 | idx3 | 0.47050 | 0.695 | 0.00 | 0.35 | 10 | 1.07 | 0.23 | Index Scan:20 |

### Arm: iterative-relaxed

| table | filter | sel | mean rec | min rec | frac<0.9 | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|---|
| T0 | lo1 | 0.00012 | 0.210 | 0.00 | 1.00 | 2 | 216.6 | 208.8 | Index Scan:20 |
| T0 | lo2 | 0.00085 | 0.855 | 0.60 | 0.45 | 10 | 111.0 | 38.4 | Index Scan:20 |
| T0 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 10.6 | 6.41 | Index Scan:20 |
| T0 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 3.63 | 1.33 | Index Scan:20 |
| T0 | lo5 | 0.10609 | 0.995 | 0.90 | 0.00 | 10 | 2.18 | 0.59 | Index Scan:20 |
| T0 | ctl | 0.20376 | 0.995 | 0.90 | 0.00 | 10 | 1.56 | 0.40 | Index Scan:20 |
| T0 | gap1 | 0.21388 | 0.995 | 0.90 | 0.00 | 10 | 1.63 | 0.67 | Index Scan:20 |
| T0 | gap2 | 0.23094 | 0.990 | 0.90 | 0.00 | 10 | 1.65 | 0.41 | Index Scan:20 |
| T0 | gap3 | 0.25991 | 0.990 | 0.90 | 0.00 | 10 | 1.45 | 0.46 | Index Scan:20 |
| T0 | gap4 | 0.29859 | 0.985 | 0.90 | 0.00 | 10 | 1.42 | 0.34 | Index Scan:20 |
| T0 | idx1 | 0.32901 | 0.995 | 0.90 | 0.00 | 10 | 1.28 | 0.30 | Index Scan:20 |
| T0 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 1.17 | 0.22 | Index Scan:20 |
| T0 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1.29 | 0.22 | Index Scan:20 |
| T25 | lo1 | 0.00012 | 0.215 | 0.00 | 1.00 | 2 | 166.2 | 62.3 | Index Scan:20 |
| T25 | lo2 | 0.00085 | 0.925 | 0.50 | 0.20 | 10 | 103.8 | 16.5 | Index Scan:20 |
| T25 | lo3 | 0.01054 | 0.990 | 0.90 | 0.00 | 10 | 21.1 | 4.08 | Index Scan:20 |
| T25 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 3.72 | 1.02 | Index Scan:20 |
| T25 | lo5 | 0.10609 | 0.995 | 0.90 | 0.00 | 10 | 2.08 | 1.33 | Index Scan:20 |
| T25 | ctl | 0.20376 | 0.995 | 0.90 | 0.00 | 10 | 1.72 | 0.61 | Index Scan:20 |
| T25 | gap1 | 0.21388 | 0.995 | 0.90 | 0.00 | 10 | 1.53 | 0.65 | Index Scan:20 |
| T25 | gap2 | 0.23094 | 1.000 | 1.00 | 0.00 | 10 | 1.51 | 0.31 | Index Scan:20 |
| T25 | gap3 | 0.25991 | 1.000 | 1.00 | 0.00 | 10 | 1.30 | 0.50 | Index Scan:20 |
| T25 | gap4 | 0.29859 | 0.995 | 0.90 | 0.00 | 10 | 1.29 | 0.55 | Index Scan:20 |
| T25 | idx1 | 0.32901 | 0.995 | 0.90 | 0.00 | 10 | 1.27 | 0.37 | Index Scan:20 |
| T25 | idx2 | 0.37633 | 0.995 | 0.90 | 0.00 | 10 | 1.42 | 0.35 | Index Scan:20 |
| T25 | idx3 | 0.47050 | 0.995 | 0.90 | 0.00 | 10 | 1.29 | 0.17 | Index Scan:20 |
| T50 | lo1 | 0.00012 | 0.205 | 0.00 | 1.00 | 1 | 231.0 | 139.5 | Index Scan:20 (post-resume rows 20) |
| T50 | lo2 | 0.00085 | 0.865 | 0.30 | 0.25 | 10 | 125.7 | 50.3 | Index Scan:20 |
| T50 | lo3 | 0.01054 | 1.000 | 1.00 | 0.00 | 10 | 17.6 | 5.24 | Index Scan:20 |
| T50 | lo4 | 0.04777 | 0.995 | 0.90 | 0.00 | 10 | 7.18 | 3.02 | Index Scan:20 (post-resume rows 20) |
| T50 | lo5 | 0.10609 | 0.995 | 0.90 | 0.00 | 10 | 3.33 | 2.30 | Index Scan:20 (post-resume rows 18) |
| T50 | ctl | 0.20376 | 0.995 | 0.90 | 0.00 | 10 | 1.56 | 0.53 | Index Scan:20 |
| T50 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 1.86 | 1.11 | Index Scan:20 (post-resume rows 20) |
| T50 | gap2 | 0.23094 | 0.995 | 0.90 | 0.00 | 10 | 1.96 | 0.50 | Index Scan:20 (post-resume rows 20) |
| T50 | gap3 | 0.25991 | 0.990 | 0.90 | 0.00 | 10 | 1.66 | 0.69 | Index Scan:20 (post-resume rows 20) |
| T50 | gap4 | 0.29859 | 0.995 | 0.90 | 0.00 | 10 | 1.27 | 0.55 | Index Scan:20 |
| T50 | idx1 | 0.32901 | 0.995 | 0.90 | 0.00 | 10 | 1.47 | 0.32 | Index Scan:20 (post-resume rows 20) |
| T50 | idx2 | 0.37633 | 0.995 | 0.90 | 0.00 | 10 | 1.63 | 0.37 | Index Scan:20 (post-resume rows 20) |
| T50 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1.57 | 0.34 | Index Scan:20 (post-resume rows 20) |
| T75 | lo1 | 0.00012 | 0.260 | 0.00 | 0.95 | 2 | 375.1 | 48.7 | Index Scan:20 |
| T75 | lo2 | 0.00085 | 0.750 | 0.20 | 0.70 | 10 | 124.5 | 17.1 | Index Scan:20 |
| T75 | lo3 | 0.01054 | 0.965 | 0.70 | 0.15 | 10 | 61.7 | 58.4 | Index Scan:20 |
| T75 | lo4 | 0.04777 | 1.000 | 1.00 | 0.00 | 10 | 10.4 | 3.91 | Index Scan:20 |
| T75 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 5.29 | 3.43 | Index Scan:20 |
| T75 | ctl | 0.20376 | 0.995 | 0.90 | 0.00 | 10 | 1.92 | 0.97 | Index Scan:20 |
| T75 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 2.15 | 2.36 | Index Scan:20 |
| T75 | gap2 | 0.23094 | 0.995 | 0.90 | 0.00 | 10 | 1.80 | 0.70 | Index Scan:20 |
| T75 | gap3 | 0.25991 | 0.990 | 0.90 | 0.00 | 10 | 1.74 | 0.51 | Index Scan:20 |
| T75 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 1.89 | 1.01 | Index Scan:20 |
| T75 | idx1 | 0.32901 | 1.000 | 1.00 | 0.00 | 10 | 1.57 | 0.62 | Index Scan:20 |
| T75 | idx2 | 0.37633 | 0.995 | 0.90 | 0.00 | 10 | 1.31 | 0.53 | Index Scan:20 |
| T75 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1.51 | 0.78 | Index Scan:20 |
| T100 | lo1 | 0.00012 | 0.180 | 0.00 | 0.90 | 0 | 111.0 | 21.2 | Index Scan:20 |
| T100 | lo2 | 0.00085 | 0.675 | 0.10 | 0.55 | 10 | 181.2 | 64.0 | Index Scan:20 |
| T100 | lo3 | 0.01054 | 0.820 | 0.00 | 0.25 | 10 | 95.0 | 78.6 | Index Scan:20 |
| T100 | lo4 | 0.04777 | 0.420 | 0.00 | 0.75 | 10 | 123.8 | 47.5 | Index Scan:20 |
| T100 | lo5 | 0.10609 | 0.930 | 0.70 | 0.25 | 10 | 59.5 | 97.4 | Index Scan:20 |
| T100 | ctl | 0.20376 | 0.960 | 0.80 | 0.10 | 10 | 1.96 | 3.36 | Index Scan:20 |
| T100 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 2.24 | 6.52 | Index Scan:20 |
| T100 | gap2 | 0.23094 | 0.990 | 0.90 | 0.00 | 10 | 1.82 | 0.78 | Index Scan:20 |
| T100 | gap3 | 0.25991 | 0.995 | 0.90 | 0.00 | 10 | 1.52 | 0.86 | Index Scan:20 |
| T100 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 1.39 | 1.76 | Index Scan:20 |
| T100 | idx1 | 0.32901 | 0.995 | 0.90 | 0.00 | 10 | 1.29 | 1.19 | Index Scan:20 |
| T100 | idx2 | 0.37633 | 0.990 | 0.90 | 0.00 | 10 | 1.44 | 0.53 | Index Scan:20 |
| T100 | idx3 | 0.47050 | 0.995 | 0.90 | 0.00 | 10 | 1.33 | 1.07 | Index Scan:20 |

### Arm: iterative-strict

| table | filter | sel | mean rec | min rec | frac<0.9 | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|---|
| T0 | lo1 | 0.00012 | 0.210 | 0.00 | 1.00 | 2 | 197.3 | 199.1 | Index Scan:20 |
| T0 | lo2 | 0.00085 | 0.850 | 0.60 | 0.50 | 10 | 110.4 | 28.6 | Index Scan:20 |
| T0 | lo3 | 0.01054 | 0.990 | 0.80 | 0.05 | 10 | 10.6 | 6.17 | Index Scan:20 |
| T0 | lo4 | 0.04777 | 0.995 | 0.90 | 0.00 | 10 | 3.60 | 1.50 | Index Scan:20 |
| T0 | lo5 | 0.10609 | 0.980 | 0.90 | 0.00 | 10 | 2.22 | 0.99 | Index Scan:20 |
| T0 | ctl | 0.20376 | 0.995 | 0.90 | 0.00 | 10 | 1.56 | 0.39 | Index Scan:20 |
| T0 | gap1 | 0.21388 | 0.985 | 0.90 | 0.00 | 10 | 1.56 | 0.68 | Index Scan:20 |
| T0 | gap2 | 0.23094 | 0.990 | 0.90 | 0.00 | 10 | 1.60 | 0.43 | Index Scan:20 |
| T0 | gap3 | 0.25991 | 0.985 | 0.90 | 0.00 | 10 | 1.39 | 0.54 | Index Scan:20 |
| T0 | gap4 | 0.29859 | 0.980 | 0.80 | 0.05 | 10 | 1.44 | 0.41 | Index Scan:20 |
| T0 | idx1 | 0.32901 | 0.995 | 0.90 | 0.00 | 10 | 1.23 | 0.16 | Index Scan:20 |
| T0 | idx2 | 0.37633 | 1.000 | 1.00 | 0.00 | 10 | 1.14 | 0.32 | Index Scan:20 |
| T0 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1.23 | 0.20 | Index Scan:20 |
| T25 | lo1 | 0.00012 | 0.215 | 0.00 | 1.00 | 2 | 144.5 | 53.3 | Index Scan:20 |
| T25 | lo2 | 0.00085 | 0.920 | 0.50 | 0.20 | 10 | 103.8 | 14.5 | Index Scan:20 |
| T25 | lo3 | 0.01054 | 0.985 | 0.90 | 0.00 | 10 | 21.1 | 9.90 | Index Scan:20 |
| T25 | lo4 | 0.04777 | 0.995 | 0.90 | 0.00 | 10 | 3.51 | 1.59 | Index Scan:20 |
| T25 | lo5 | 0.10609 | 0.985 | 0.90 | 0.00 | 10 | 2.16 | 1.10 | Index Scan:20 |
| T25 | ctl | 0.20376 | 0.985 | 0.90 | 0.00 | 10 | 1.73 | 0.62 | Index Scan:20 |
| T25 | gap1 | 0.21388 | 0.985 | 0.90 | 0.00 | 10 | 1.50 | 0.68 | Index Scan:20 |
| T25 | gap2 | 0.23094 | 0.995 | 0.90 | 0.00 | 10 | 1.48 | 0.36 | Index Scan:20 |
| T25 | gap3 | 0.25991 | 0.995 | 0.90 | 0.00 | 10 | 1.28 | 0.49 | Index Scan:20 |
| T25 | gap4 | 0.29859 | 0.990 | 0.90 | 0.00 | 10 | 1.32 | 0.51 | Index Scan:20 |
| T25 | idx1 | 0.32901 | 0.995 | 0.90 | 0.00 | 10 | 1.17 | 0.27 | Index Scan:20 |
| T25 | idx2 | 0.37633 | 0.995 | 0.90 | 0.00 | 10 | 1.40 | 0.39 | Index Scan:20 |
| T25 | idx3 | 0.47050 | 0.995 | 0.90 | 0.00 | 10 | 1.24 | 0.31 | Index Scan:20 |
| T50 | lo1 | 0.00012 | 0.205 | 0.00 | 1.00 | 1 | 217.0 | 46.4 | Index Scan:20 (post-resume rows 20) |
| T50 | lo2 | 0.00085 | 0.850 | 0.30 | 0.30 | 10 | 125.1 | 62.7 | Index Scan:20 |
| T50 | lo3 | 0.01054 | 0.995 | 0.90 | 0.00 | 10 | 16.4 | 4.48 | Index Scan:20 |
| T50 | lo4 | 0.04777 | 0.995 | 0.90 | 0.00 | 10 | 7.53 | 4.41 | Index Scan:20 (post-resume rows 20) |
| T50 | lo5 | 0.10609 | 0.980 | 0.70 | 0.05 | 10 | 3.32 | 2.36 | Index Scan:20 (post-resume rows 18) |
| T50 | ctl | 0.20376 | 0.990 | 0.90 | 0.00 | 10 | 1.57 | 0.75 | Index Scan:20 |
| T50 | gap1 | 0.21388 | 0.995 | 0.90 | 0.00 | 10 | 1.92 | 0.82 | Index Scan:20 (post-resume rows 20) |
| T50 | gap2 | 0.23094 | 0.995 | 0.90 | 0.00 | 10 | 1.90 | 0.56 | Index Scan:20 (post-resume rows 20) |
| T50 | gap3 | 0.25991 | 0.990 | 0.90 | 0.00 | 10 | 1.73 | 0.61 | Index Scan:20 (post-resume rows 20) |
| T50 | gap4 | 0.29859 | 0.995 | 0.90 | 0.00 | 10 | 1.32 | 0.69 | Index Scan:20 |
| T50 | idx1 | 0.32901 | 0.995 | 0.90 | 0.00 | 10 | 1.56 | 0.33 | Index Scan:20 (post-resume rows 20) |
| T50 | idx2 | 0.37633 | 0.995 | 0.90 | 0.00 | 10 | 1.64 | 0.41 | Index Scan:20 (post-resume rows 20) |
| T50 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1.49 | 0.38 | Index Scan:20 (post-resume rows 20) |
| T75 | lo1 | 0.00012 | 0.260 | 0.00 | 0.95 | 2 | 378.1 | 126.7 | Index Scan:20 |
| T75 | lo2 | 0.00085 | 0.745 | 0.20 | 0.70 | 10 | 121.3 | 21.0 | Index Scan:20 |
| T75 | lo3 | 0.01054 | 0.940 | 0.60 | 0.20 | 10 | 64.9 | 67.7 | Index Scan:20 |
| T75 | lo4 | 0.04777 | 0.995 | 0.90 | 0.00 | 10 | 8.99 | 4.37 | Index Scan:20 |
| T75 | lo5 | 0.10609 | 1.000 | 1.00 | 0.00 | 10 | 4.89 | 3.44 | Index Scan:20 |
| T75 | ctl | 0.20376 | 0.990 | 0.90 | 0.00 | 10 | 1.88 | 0.78 | Index Scan:20 |
| T75 | gap1 | 0.21388 | 1.000 | 1.00 | 0.00 | 10 | 2.31 | 2.34 | Index Scan:20 |
| T75 | gap2 | 0.23094 | 0.985 | 0.90 | 0.00 | 10 | 1.88 | 0.77 | Index Scan:20 |
| T75 | gap3 | 0.25991 | 0.985 | 0.90 | 0.00 | 10 | 1.72 | 0.56 | Index Scan:20 |
| T75 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 1.70 | 1.20 | Index Scan:20 |
| T75 | idx1 | 0.32901 | 1.000 | 1.00 | 0.00 | 10 | 1.51 | 0.62 | Index Scan:20 |
| T75 | idx2 | 0.37633 | 0.990 | 0.90 | 0.00 | 10 | 1.60 | 0.49 | Index Scan:20 |
| T75 | idx3 | 0.47050 | 1.000 | 1.00 | 0.00 | 10 | 1.47 | 0.52 | Index Scan:20 |
| T100 | lo1 | 0.00012 | 0.180 | 0.00 | 0.90 | 0 | 115.4 | 32.5 | Index Scan:20 |
| T100 | lo2 | 0.00085 | 0.660 | 0.10 | 0.60 | 10 | 171.4 | 39.3 | Index Scan:20 |
| T100 | lo3 | 0.01054 | 0.800 | 0.00 | 0.30 | 10 | 92.8 | 65.5 | Index Scan:20 |
| T100 | lo4 | 0.04777 | 0.400 | 0.00 | 0.80 | 10 | 119.3 | 49.9 | Index Scan:20 |
| T100 | lo5 | 0.10609 | 0.905 | 0.70 | 0.35 | 10 | 64.8 | 98.7 | Index Scan:20 |
| T100 | ctl | 0.20376 | 0.930 | 0.50 | 0.20 | 10 | 1.76 | 3.38 | Index Scan:20 |
| T100 | gap1 | 0.21388 | 0.990 | 0.90 | 0.00 | 10 | 2.02 | 6.54 | Index Scan:20 |
| T100 | gap2 | 0.23094 | 0.985 | 0.80 | 0.05 | 10 | 1.76 | 0.76 | Index Scan:20 |
| T100 | gap3 | 0.25991 | 0.995 | 0.90 | 0.00 | 10 | 1.64 | 0.84 | Index Scan:20 |
| T100 | gap4 | 0.29859 | 1.000 | 1.00 | 0.00 | 10 | 1.45 | 1.53 | Index Scan:20 |
| T100 | idx1 | 0.32901 | 0.995 | 0.90 | 0.00 | 10 | 1.31 | 0.95 | Index Scan:20 |
| T100 | idx2 | 0.37633 | 0.985 | 0.90 | 0.00 | 10 | 1.45 | 0.53 | Index Scan:20 |
| T100 | idx3 | 0.47050 | 0.995 | 0.90 | 0.00 | 10 | 1.26 | 1.17 | Index Scan:20 |

## (c) Hypotheses H1-H6 (operationalisations as written in the protocol)

**H1 — forced-hnsw mean recall@10 < 0.90 at >=1 index-scan point on hm_clothes_75 and on hm_clothes_100: HOLDS.** [V]
- hm_clothes_75: forced-hnsw mean recall at idx1/idx2/idx3 = 0.840 / 0.900 / 0.870 → at least one < 0.90.
- hm_clothes_100: forced-hnsw mean recall at idx1/idx2/idx3 = 0.715 / 0.795 / 0.695 → at least one < 0.90.

**H2 — iterative-relaxed mean recall@10 >= 0.90 at every point on every table: FAILS over all 65 (table, filter) cells; HOLDS over the 40 cells of the 8 originally frozen filters.** [V]
Failing cells (table, filter, mean recall, valid vectors): hm_clothes_0/lo1 0.210 (n=20); hm_clothes_0/lo2 0.855 (n=20); hm_clothes_25/lo1 0.215 (n=20); hm_clothes_50/lo1 0.205 (n=20); hm_clothes_50/lo2 0.865 (n=20); hm_clothes_75/lo1 0.260 (n=20); hm_clothes_75/lo2 0.750 (n=20); hm_clothes_100/lo1 0.180 (n=20); hm_clothes_100/lo2 0.675 (n=20); hm_clothes_100/lo3 0.820 (n=20); hm_clothes_100/lo4 0.420 (n=20)
Lowest iterative-relaxed cell mean recall: 0.180. Lowest single-vector recall over all iterative-relaxed cells: 0.00.

**H3 — forced-exact median latency > 500 ms at >= 0.329 on at least one table: HOLDS** (15 of 15 (table, idx1-3) cells exceed 500 ms). [V]

| table | filter | forced-exact median ms | > 500 |
|---|---|---|---|
| hm_clothes_0 | idx1 | 885.9 | yes |
| hm_clothes_0 | idx2 | 889.4 | yes |
| hm_clothes_0 | idx3 | 3273 | yes |
| hm_clothes_25 | idx1 | 751.5 | yes |
| hm_clothes_25 | idx2 | 1089 | yes |
| hm_clothes_25 | idx3 | 2465 | yes |
| hm_clothes_50 | idx1 | 2261 | yes |
| hm_clothes_50 | idx2 | 1206 | yes |
| hm_clothes_50 | idx3 | 3419 | yes |
| hm_clothes_75 | idx1 | 1928 | yes |
| hm_clothes_75 | idx2 | 965.2 | yes |
| hm_clothes_75 | idx3 | 1131 | yes |
| hm_clothes_100 | idx1 | 851.5 | yes |
| hm_clothes_100 | idx2 | 1694 | yes |
| hm_clothes_100 | idx3 | 1162 | yes |

**H4 — iterative-relaxed median latency < forced-exact median latency at >= 0.329: HOLDS** (true in 15 of 15 cells). [V]

| table | filter | iterative-relaxed ms | forced-exact ms | IR < FE |
|---|---|---|---|---|
| hm_clothes_0 | idx1 | 1.28 | 885.9 | yes |
| hm_clothes_0 | idx2 | 1.17 | 889.4 | yes |
| hm_clothes_0 | idx3 | 1.29 | 3273 | yes |
| hm_clothes_25 | idx1 | 1.27 | 751.5 | yes |
| hm_clothes_25 | idx2 | 1.42 | 1089 | yes |
| hm_clothes_25 | idx3 | 1.29 | 2465 | yes |
| hm_clothes_50 | idx1 | 1.47 | 2261 | yes |
| hm_clothes_50 | idx2 | 1.63 | 1206 | yes |
| hm_clothes_50 | idx3 | 1.57 | 3419 | yes |
| hm_clothes_75 | idx1 | 1.57 | 1928 | yes |
| hm_clothes_75 | idx2 | 1.31 | 965.2 | yes |
| hm_clothes_75 | idx3 | 1.51 | 1131 | yes |
| hm_clothes_100 | idx1 | 1.29 | 851.5 | yes |
| hm_clothes_100 | idx2 | 1.44 | 1694 | yes |
| hm_clothes_100 | idx3 | 1.33 | 1162 | yes |

**H5 — forced-exact median latency <= 500 ms in every (table, lo1..lo3) cell: HOLDS.** [V]
Cells: hm_clothes_0/lo1 0.43 ms; hm_clothes_0/lo2 2.00 ms; hm_clothes_0/lo3 26.6 ms; hm_clothes_25/lo1 0.44 ms; hm_clothes_25/lo2 1.90 ms; hm_clothes_25/lo3 64.4 ms; hm_clothes_50/lo1 0.45 ms; hm_clothes_50/lo2 1.98 ms; hm_clothes_50/lo3 24.2 ms; hm_clothes_75/lo1 0.46 ms; hm_clothes_75/lo2 1.98 ms; hm_clothes_75/lo3 67.6 ms; hm_clothes_100/lo1 0.33 ms; hm_clothes_100/lo2 2.49 ms; hm_clothes_100/lo3 24.7 ms

**H6 — iterative-relaxed mean recall < 0.90 OR median rows_returned < 10 in at least one (table, lo1..lo2) cell: HOLDS** (9 of 10 cells). [V]

| table | filter | mean recall | median rows | min rows (any vector) | criterion met |
|---|---|---|---|---|---|
| hm_clothes_0 | lo1 | 0.210 | 2 | 0 | yes |
| hm_clothes_0 | lo2 | 0.855 | 10 | 7 | yes |
| hm_clothes_25 | lo1 | 0.215 | 2 | 0 | yes |
| hm_clothes_25 | lo2 | 0.925 | 10 | 10 | no |
| hm_clothes_50 | lo1 | 0.205 | 1 | 0 | yes |
| hm_clothes_50 | lo2 | 0.865 | 10 | 10 | yes |
| hm_clothes_75 | lo1 | 0.260 | 2 | 0 | yes |
| hm_clothes_75 | lo2 | 0.750 | 10 | 6 | yes |
| hm_clothes_100 | lo1 | 0.180 | 0 | 0 | yes |
| hm_clothes_100 | lo2 | 0.675 | 10 | 5 | yes |

| H | verdict |
|---|---|
| H1 | holds |
| H2 (65 cells / original 40) | fails / holds |
| H3 | holds |
| H4 | holds |
| H5 | holds |
| H6 | holds |

## (d) Route map (Amendment 1 decision rule)

Rule [V, from the protocol]: per (table, filter) cell, the route is the arm among forced-exact (FE), forced-hnsw (FH) and iterative-relaxed (IR) with the lowest median latency whose mean recall@10 >= 0.90 (all 20 vectors valid; ties FE, FH, IR). If none qualifies, or the chosen arm's median latency > 500 ms, the cell is "no route meets both SLAs". planner-default and iterative-strict are reported but are not candidates. Cell text: route and its median latency in ms.

| filter | selectivity | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|---|
| lo1 | 0.00012 | FE 0.43 | FE 0.44 | FE 0.45 | FE 0.46 | FE 0.33 |
| lo2 | 0.00085 | FE 2.00 | FE 1.90 | FE 1.98 | FE 1.98 | FE 2.49 |
| lo3 | 0.01054 | IR 10.6 | IR 21.1 | IR 17.6 | IR 61.7 | FE 24.7 |
| lo4 | 0.04777 | IR 3.63 | IR 3.72 | IR 7.18 | IR 10.4 | FE 113.0 |
| lo5 | 0.10609 | IR 2.18 | IR 2.08 | IR 3.33 | IR 5.29 | IR 59.5 |
| ctl | 0.20376 | IR 1.56 | IR 1.72 | IR 1.56 | IR 1.92 | IR 1.96 |
| gap1 | 0.21388 | IR 1.63 | IR 1.53 | IR 1.86 | IR 2.15 | IR 2.24 |
| gap2 | 0.23094 | IR 1.65 | IR 1.51 | IR 1.96 | IR 1.80 | IR 1.82 |
| gap3 | 0.25991 | IR 1.45 | IR 1.30 | IR 1.66 | IR 1.74 | IR 1.52 |
| gap4 | 0.29859 | FH 1.22 | IR 1.29 | IR 1.27 | IR 1.89 | IR 1.39 |
| idx1 | 0.32901 | FH 1.20 | FH 1.06 | FH 1.35 | IR 1.57 | IR 1.29 |
| idx2 | 0.37633 | FH 1.13 | FH 1.22 | FH 1.49 | FH 1.26 | IR 1.44 |
| idx3 | 0.47050 | FH 1.21 | FH 1.26 | FH 1.47 | IR 1.51 | IR 1.33 |

Route counts over the 65 cells [V]: iterative-relaxed: 42, forced-exact: 12, forced-hnsw: 11; cells with status "route": 65.

No cell is a "no route meets both SLAs" cell. [V]

## (e) Consistency check: planner-default vs Phase A v2 plan choices

Shared filters: lo1-lo5 = f_000, f_006, f_016, f_028, f_037; ctl = f_040; idx1-3 = f_041-f_043 (v2 `outputs/phase_a_v2/sweep_results.jsonl`, vectors 0-19, first row per key; v2 keys with more than one distinct strategy: 0). A match means the same first scan node. [V]

Overall: **900 of 900** (table, filter, vector) planner-default plan choices equal the v2 scan strategy.

| filter | v2 id | sel | matches | new run planner-default scan nodes per table |
|---|---|---|---|---|
| lo1 | f_000 | 0.00012 | 100/100 | T0: Bitmap Heap Scan:20; T25: Bitmap Heap Scan:20; T50: Bitmap Heap Scan:20; T75: Bitmap Heap Scan:20; T100: Bitmap Heap Scan:20 |
| lo2 | f_006 | 0.00085 | 100/100 | T0: Bitmap Heap Scan:20; T25: Bitmap Heap Scan:20; T50: Bitmap Heap Scan:20; T75: Bitmap Heap Scan:20; T100: Bitmap Heap Scan:20 |
| lo3 | f_016 | 0.01054 | 100/100 | T0: Bitmap Heap Scan:20; T25: Bitmap Heap Scan:20; T50: Bitmap Heap Scan:20; T75: Bitmap Heap Scan:20; T100: Bitmap Heap Scan:20 |
| lo4 | f_028 | 0.04777 | 100/100 | T0: Bitmap Heap Scan:20; T25: Bitmap Heap Scan:20; T50: Bitmap Heap Scan:20; T75: Bitmap Heap Scan:20; T100: Bitmap Heap Scan:20 |
| lo5 | f_037 | 0.10609 | 100/100 | T0: Bitmap Heap Scan:20; T25: Bitmap Heap Scan:20; T50: Bitmap Heap Scan:20; T75: Bitmap Heap Scan:20; T100: Bitmap Heap Scan:20 |
| ctl | f_040 | 0.20376 | 100/100 | T0: Bitmap Heap Scan:20; T25: Bitmap Heap Scan:20; T50: Bitmap Heap Scan:20; T75: Bitmap Heap Scan:20; T100: Bitmap Heap Scan:20 |
| idx1 | f_041 | 0.32901 | 100/100 | T0: Index Scan:20; T25: Index Scan:20; T50: Index Scan:20; T75: Index Scan:20; T100: Index Scan:20 |
| idx2 | f_042 | 0.37633 | 100/100 | T0: Index Scan:20; T25: Index Scan:20; T50: Index Scan:20; T75: Index Scan:20; T100: Index Scan:20 |
| idx3 | f_043 | 0.47050 | 100/100 | T0: Index Scan:20; T25: Index Scan:20; T50: Index Scan:20; T75: Index Scan:20; T100: Index Scan:20 |

## (f) Gap points 0.204-0.329

Per filter, aggregated over the 5 tables (mean of the cell mean recalls; median of the cell median latencies); planner-default plan share over 5 tables x 20 vectors = 100 queries. [V]

| filter | type | sel | planner-default plan | planner-default (recall / ms) | forced-exact (recall / ms) | forced-hnsw (recall / ms) | iterative-relaxed (recall / ms) | iterative-strict (recall / ms) |
|---|---|---|---|---|---|---|---|---|
| ctl | control (equality) | 0.20376 | 0% HNSW Index Scan / 100% other | 1.000 / 890.5 | 1.000 / 865.3 | 0.659 / 1.16 | 0.988 / 1.72 | 0.978 / 1.73 |
| gap1 | gap, equality | 0.21388 | 0% HNSW Index Scan / 100% other | 1.000 / 611.2 | 1.000 / 620.6 | 0.656 / 1.21 | 0.998 / 1.86 | 0.991 / 1.92 |
| gap2 | gap, IN list | 0.23094 | 0% HNSW Index Scan / 100% other | 1.000 / 726.3 | 1.000 / 760.4 | 0.675 / 1.23 | 0.994 / 1.80 | 0.990 / 1.76 |
| gap3 | gap, IN list | 0.25991 | 0% HNSW Index Scan / 100% other | 1.000 / 767.8 | 1.000 / 781.3 | 0.773 / 1.10 | 0.993 / 1.52 | 0.990 / 1.64 |
| gap4 | gap, IN list | 0.29859 | 100% HNSW Index Scan / 0% other | 0.821 / 1.22 | 1.000 / 781.6 | 0.821 / 1.16 | 0.995 / 1.39 | 0.993 / 1.44 |
| idx1 | index-scan point (equality) | 0.32901 | 100% HNSW Index Scan / 0% other | 0.884 / 1.20 | 1.000 / 885.9 | 0.884 / 1.19 | 0.996 / 1.29 | 0.996 / 1.31 |

Per table, planner-default share of HNSW Index Scan (of 20 vectors) and forced-hnsw mean recall [V]:

| filter | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|
| ctl | 0/20 · FH rec 0.815 | 0/20 · FH rec 0.720 | 0/20 · FH rec 0.600 | 0/20 · FH rec 0.640 | 0/20 · FH rec 0.520 |
| gap1 | 0/20 · FH rec 0.820 | 0/20 · FH rec 0.690 | 0/20 · FH rec 0.715 | 0/20 · FH rec 0.620 | 0/20 · FH rec 0.435 |
| gap2 | 0/20 · FH rec 0.840 | 0/20 · FH rec 0.825 | 0/20 · FH rec 0.725 | 0/20 · FH rec 0.530 | 0/20 · FH rec 0.455 |
| gap3 | 0/20 · FH rec 0.860 | 0/20 · FH rec 0.895 | 0/20 · FH rec 0.785 | 0/20 · FH rec 0.685 | 0/20 · FH rec 0.640 |
| gap4 | 20/20 · FH rec 0.930 | 20/20 · FH rec 0.880 | 20/20 · FH rec 0.840 | 20/20 · FH rec 0.800 | 20/20 · FH rec 0.655 |
| idx1 | 20/20 · FH rec 0.965 | 20/20 · FH rec 0.945 | 20/20 · FH rec 0.955 | 20/20 · FH rec 0.840 | 20/20 · FH rec 0.715 |

## (h) What this does NOT show

- H&M only: five categorical columns, 105,100 rows per table, halfvec(2048) cosine HNSW (m=16, ef_construction=64). Nothing here is evidence about FinQA (vector(768), L2, JSONB metadata) or about the Phase D router.
- Fixed k=10 and `hnsw.ef_search`=40; `hnsw.max_scan_tuples` at its default 20000 and `hnsw.scan_mem_multiplier`=1. Other values were not tested here.
- Single machine, single Docker PostgreSQL 16.14 / pgvector 0.8.3 instance with `shared_buffers`=128MB, `work_mem`=4MB (the Phase A defaults, deliberately unchanged); latency conclusions describe this configuration, and exact plans in particular may be faster with more memory.
- 20 query vectors (the Phase A v2 vectors) per cell; cell means over 20 vectors carry sampling uncertainty that is not quantified here, and no significance tests were run.
- Equality and IN-list filters on one column (plus the 8 originally frozen filters); no numeric ranges, no multi-column filters, no filter correlated with the query.
- Latency is the PostgreSQL `Execution Time` of `EXPLAIN ANALYZE` (median of 5 timed runs after 1 warm-up), not end-to-end application latency. The run crashed once and resumed (see (a)); rows after the resume may carry a cold-cache effect.
- `jit` was off and plans were pre-checked; arms 3-5 use `enable_sort=off` (Amendment 2). Results for those arms describe forced-HNSW plans, not what the planner would choose by itself.
- The run does not evaluate the Decision Matrix (`policy.py`); it only measures candidate routes. Any change to `policy.py` is a separate step.

## (i) Summary and interpretation (hand-written after reading sections (a)-(f); numbers are from the tables above)

**Verdicts [V].** H1, H3, H4, H5 and H6 hold; H2 fails over all 65 cells (it holds over the 40 cells of the 8 originally frozen filters). All 65 (table, filter) cells have a route that meets both SLAs (recall >= 0.90 and median latency <= 500 ms): route counts iterative-relaxed 42, forced-exact 12, forced-hnsw 11.

**What each arm does across selectivity [V].**
- *forced-exact* has recall 1.000 in every cell. Its median latency rises with selectivity: sub-ms to 2.5 ms at lo1-lo2, 24-68 ms at lo3, 98-317 ms at lo4-lo5, and 490 ms to 6.6 s from 0.204 upward; all 15 idx1-3 cells exceed 500 ms (smallest 751.5 ms, hm_clothes_25/idx1).
- *forced-hnsw* (the Phase D "post-filter" arm: forced HNSW, `iterative_scan=off`) has mean recall >= 0.90 in only **11 of 65 cells**, all at selectivity >= 0.2986 (gap4 on hm_clothes_0; idx1 on hm_clothes_0/25/50; idx2 on hm_clothes_0/25/50/75; idx3 on hm_clothes_0/25/50). In none of the 13 cells of hm_clothes_100 does it reach 0.90, and at lo1-lo2 it is at 0.00-0.01. Its latency is flat at about 1 ms.
- *iterative-relaxed* has recall >= 0.90 in 54 of 65 cells and a latency that falls from 111-375 ms (lo1-lo2) to 1-2 ms (>= 0.2). Its 11 cells below 0.90 are lo1 on all five tables (0.18-0.26), lo2 on four tables (0.675-0.865), and, on hm_clothes_100 only, lo3 (0.820) and lo4 (0.420). *iterative-strict* fails in the same 11 cells with nearly identical values.
- *planner-default* reproduces Phase A: it matches the v2 plan choice in 900 of 900 shared (table, filter, vector) queries. It uses an exact Bitmap Heap Scan up to 0.2599 (100% on all five tables) and the HNSW Index Scan from 0.2986 (100%), so its recall is 1.000 up to 0.2599 and 0.82-0.93 (mean over tables) from 0.2986.

**Gap 0.204-0.329 [V, with [I] where marked].**
- The planner's switch from exact to HNSW lies between 0.2599 (gap3) and 0.2986 (gap4) on every table; the Phase A "danger zone" start at 0.329 therefore sits above the switch.
- Below the switch, planner-default is exact (recall 1.000) but slow (611-890 ms median over tables at ctl, gap1-gap3, i.e. over the 500 ms SLA in most cells). Forced-hnsw there is fast but has recall 0.66-0.77 (mean over tables). Iterative-relaxed has recall 0.988-0.998 at 1.5-1.9 ms.
- Equality vs IN list: forced-hnsw recall averaged over tables is 0.656 at gap1 (equality) and 0.675 / 0.773 at gap2 / gap3 (IN lists); I see no difference between the filter types, but with a single equality point I cannot separate filter type from selectivity [I].

**Where the Decision Matrix's assumption breaks [I, based on the tables].** The v1 thresholds mark recall danger at 0.329-0.4705 and route that zone to `post-filter` (the forced-hnsw arm). In this run that arm is the one with the low recall, over a much wider range than the recorded zone (54 of 65 cells < 0.90, including all cells below 0.2599). In the 15 idx1-3 cells, iterative-relaxed meets both SLAs in every one, and forced-hnsw in 10 of the 15 cells at selectivity >= 0.329 (all on hm_clothes_0/25/50, plus hm_clothes_75/idx2); it fails in the other five (hm_clothes_75/idx1 and idx3, hm_clothes_100/idx1-3). This supports the audit's earlier concern (risk 2) with H&M evidence; whether it carries over to FinQA is not tested here. Choosing between forced-hnsw and iterative-relaxed in the 11 cells where the rule picked forced-hnsw rests on latency differences of 0.04-0.2 ms, which I consider within run-to-run noise [I]; iterative-relaxed has recall at least as high as forced-hnsw in every such cell.

**Where iterative scan fails [V, mechanism [I]].** At the lowest selectivities (lo1 = 13 rows, lo2 = 89 rows) iterative-relaxed returns 0-2 rows (median) at lo1 and has recall 0.18-0.26; at hm_clothes_100/lo3-lo4 it returns 10 rows at the median but with recall 0.82 / 0.42 (minimum 6 and 4 rows over vectors). iterative-strict behaves the same, so result ordering is not the cause. The pre-registered expectation (H6) was the `hnsw.max_scan_tuples = 20000` cap; the lo1 under-fill fits that, but the 10-row / low-recall cells on hm_clothes_100 are not explained by the cap alone, and the mechanism was not tested (it would need runs with a different `max_scan_tuples` and `ef_search`). The decision rule avoids these cells by choosing forced-exact there (lo1-lo2 on all tables, lo3-lo4 on hm_clothes_100), which is cheap (0.33-113 ms).

**Noise and the crash [V, interpretation [I]].** Forced-exact latency varies strongly between tables for the same filter (section (a)): for example gap4 is 6567 ms on hm_clothes_50 against 644-1383 ms on the other tables, and that cell has no post-resume rows. The 891 post-resume rows are all on hm_clothes_50 (lo1, lo4, lo5, gap1-gap3, idx1-idx3); I see no systematic cold-cache pattern there, but I cannot rule one out. No verdict or route depends on it: the smallest forced-exact value used for H3 is 751.5 ms against a 500 ms limit, the largest forced-exact value used for H5 is 67.6 ms, and the iterative-relaxed vs forced-exact gap at idx1-3 is more than two orders of magnitude.

**Files.** `outputs/phase_a_arms/analysis/cell_summary.csv` (325 rows), `route_map.csv`, `hypotheses.json`, `recall_vs_selectivity.png`, `latency_vs_selectivity.png`; script `src/phase_c_analysis/arm_analysis.py`. Sections (a)-(h) above are generated by the script; this section (i) was written by hand and appended to the generated file.
