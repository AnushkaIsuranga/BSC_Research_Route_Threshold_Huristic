# Second held-out results (policy_v2, selectivity 0.23-0.45), 2026-10-12

Computed by `src/phase_c_analysis/holdout2_analysis.py` from `outputs/phase_a_holdout2/results.jsonl` (1,500 rows). Protocol: `PHASE_A_HOLDOUT2_PROTOCOL.md` (tag `phase-a-holdout2-frozen-2026-10-12`). SLAs: mean recall@10 >= 0.90 and median latency <= 500 ms. A cell with any invalid vector counts as not passing.

Run: seed 20261017, table order ['hm_clothes_100', 'hm_clothes_75', 'hm_clothes_25', 'hm_clothes_0', 'hm_clothes_50'], commit `c01f2da`, started 2026-10-12T10:51:46.056885+00:00.

## Hypotheses

- **H10 (primary) policy_v2 passes all 25 cells: HOLDS** (25/25).
- **H11 per filter (P1 fails >= 1 of its 5 cells):**
  - h2a (0.2304) [exploratory]: FAILS, 0/5 cells fail; P1 routes {'hm_clothes_0': 'forced-exact', 'hm_clothes_25': 'forced-exact', 'hm_clothes_50': 'forced-exact', 'hm_clothes_75': 'forced-exact', 'hm_clothes_100': 'forced-exact'}; failing: none
  - h2b (0.2563) [exploratory]: HOLDS, 1/5 cells fail; P1 routes {'hm_clothes_0': 'forced-exact', 'hm_clothes_25': 'forced-exact', 'hm_clothes_50': 'forced-exact', 'hm_clothes_75': 'forced-exact', 'hm_clothes_100': 'forced-exact'}; failing: hm_clothes_75 (forced-exact): latency 523 ms
  - h2c (0.3262): HOLDS, 4/5 cells fail; P1 routes {'hm_clothes_0': 'forced-hnsw', 'hm_clothes_25': 'forced-exact', 'hm_clothes_50': 'forced-hnsw', 'hm_clothes_75': 'forced-hnsw', 'hm_clothes_100': 'forced-hnsw'}; failing: hm_clothes_25 (forced-exact): latency 615 ms; hm_clothes_50 (forced-hnsw): recall 0.885; hm_clothes_75 (forced-hnsw): recall 0.775; hm_clothes_100 (forced-hnsw): recall 0.660
  - h2d (0.3767): HOLDS, 5/5 cells fail; P1 routes {'hm_clothes_0': 'forced-exact', 'hm_clothes_25': 'forced-exact', 'hm_clothes_50': 'forced-exact', 'hm_clothes_75': 'forced-exact', 'hm_clothes_100': 'forced-hnsw'}; failing: hm_clothes_0 (forced-exact): latency 698 ms; hm_clothes_25 (forced-exact): latency 686 ms; hm_clothes_50 (forced-exact): latency 698 ms; hm_clothes_75 (forced-exact): latency 785 ms; hm_clothes_100 (forced-hnsw): recall 0.630
  - h2e (0.4464): HOLDS, 5/5 cells fail; P1 routes {'hm_clothes_0': 'forced-exact', 'hm_clothes_25': 'forced-exact', 'hm_clothes_50': 'forced-exact', 'hm_clothes_75': 'forced-exact', 'hm_clothes_100': 'forced-hnsw'}; failing: hm_clothes_0 (forced-exact): latency 814 ms; hm_clothes_25 (forced-exact): latency 828 ms; hm_clothes_50 (forced-exact): latency 811 ms; hm_clothes_75 (forced-exact): latency 846 ms; hm_clothes_100 (forced-hnsw): recall 0.730
- **H12 P4 fails latency in all 15 cells with s >= 0.30: HOLDS** (15/15 fail).
  - Exploratory (s < 0.30, no pass/fail claim): hm_clothes_0 x h2a: 454.7 ms (passes latency); hm_clothes_0 x h2b: 490.7 ms (passes latency); hm_clothes_25 x h2a: 437.4 ms (passes latency); hm_clothes_25 x h2b: 478.4 ms (passes latency); hm_clothes_50 x h2a: 435.7 ms (passes latency); hm_clothes_50 x h2b: 485.8 ms (passes latency); hm_clothes_75 x h2a: 447.2 ms (passes latency); hm_clothes_75 x h2b: 523.4 ms (fails latency); hm_clothes_100 x h2a: 466.0 ms (passes latency); hm_clothes_100 x h2b: 483.9 ms (passes latency)

## Policy pass counts

| policy | cells passed of 25 | of the 15 confirmatory cells (h2c-h2e) |
|---|---|---|
| P1 v1 matrix (policy.py + phase_a_v1/thresholds.json) | 10/25 | 1/15 |
| P4 always forced-exact | 9/25 | 0/15 |
| P5 always forced-hnsw | 7/25 | 7/15 |
| P6 always iterative-relaxed | 25/25 | 15/15 |
| policy_v2 (forced-exact if s < 0.1 else iterative-relaxed) | 25/25 | 15/15 |

## Per-cell results (all policies' arms; mean recall@10, median latency ms)

**h2a** (s = 0.23038) - exploratory

| table | forced-exact | forced-hnsw | iterative-relaxed | policy_v2 | P1 arm / pass |
|---|---|---|---|---|---|
| hm_clothes_0 | 1.000 / 454.7 | 0.800 / 0.9 | 0.980 / 1.3 | pass (iterative-relaxed) | forced-exact: pass |
| hm_clothes_25 | 1.000 / 437.4 | 0.795 / 0.8 | 0.970 / 0.8 | pass (iterative-relaxed) | forced-exact: pass |
| hm_clothes_50 | 1.000 / 435.7 | 0.815 / 0.8 | 0.985 / 1.0 | pass (iterative-relaxed) | forced-exact: pass |
| hm_clothes_75 | 1.000 / 447.2 | 0.660 / 0.8 | 0.975 / 1.4 | pass (iterative-relaxed) | forced-exact: pass |
| hm_clothes_100 | 1.000 / 466.0 | 0.560 / 0.8 | 0.960 / 1.7 | pass (iterative-relaxed) | forced-exact: pass |

**h2b** (s = 0.25625) - exploratory

| table | forced-exact | forced-hnsw | iterative-relaxed | policy_v2 | P1 arm / pass |
|---|---|---|---|---|---|
| hm_clothes_0 | 1.000 / 490.7 | 0.830 / 0.8 | 0.985 / 1.0 | pass (iterative-relaxed) | forced-exact: pass |
| hm_clothes_25 | 1.000 / 478.4 | 0.790 / 0.7 | 1.000 / 1.1 | pass (iterative-relaxed) | forced-exact: pass |
| hm_clothes_50 | 1.000 / 485.8 | 0.735 / 0.8 | 0.995 / 1.2 | pass (iterative-relaxed) | forced-exact: pass |
| hm_clothes_75 | 1.000 / 523.4 | 0.410 / 0.8 | 0.975 / 1.6 | pass (iterative-relaxed) | forced-exact: FAIL latency 523 ms |
| hm_clothes_100 | 1.000 / 483.9 | 0.300 / 0.7 | 0.975 / 2.3 | pass (iterative-relaxed) | forced-exact: pass |

**h2c** (s = 0.32620)

| table | forced-exact | forced-hnsw | iterative-relaxed | policy_v2 | P1 arm / pass |
|---|---|---|---|---|---|
| hm_clothes_0 | 1.000 / 613.6 | 0.950 / 0.9 | 0.970 / 0.9 | pass (iterative-relaxed) | forced-hnsw: pass |
| hm_clothes_25 | 1.000 / 615.5 | 0.880 / 0.8 | 0.995 / 1.0 | pass (iterative-relaxed) | forced-exact: FAIL latency 615 ms |
| hm_clothes_50 | 1.000 / 605.7 | 0.885 / 0.8 | 0.990 / 0.9 | pass (iterative-relaxed) | forced-hnsw: FAIL recall 0.885 |
| hm_clothes_75 | 1.000 / 611.3 | 0.775 / 0.8 | 0.985 / 1.0 | pass (iterative-relaxed) | forced-hnsw: FAIL recall 0.775 |
| hm_clothes_100 | 1.000 / 612.8 | 0.660 / 0.7 | 0.985 / 1.1 | pass (iterative-relaxed) | forced-hnsw: FAIL recall 0.660 |

**h2d** (s = 0.37669)

| table | forced-exact | forced-hnsw | iterative-relaxed | policy_v2 | P1 arm / pass |
|---|---|---|---|---|---|
| hm_clothes_0 | 1.000 / 697.9 | 0.975 / 0.8 | 0.985 / 0.8 | pass (iterative-relaxed) | forced-exact: FAIL latency 698 ms |
| hm_clothes_25 | 1.000 / 685.5 | 0.960 / 0.8 | 0.990 / 0.8 | pass (iterative-relaxed) | forced-exact: FAIL latency 686 ms |
| hm_clothes_50 | 1.000 / 698.3 | 0.925 / 0.8 | 0.980 / 0.9 | pass (iterative-relaxed) | forced-exact: FAIL latency 698 ms |
| hm_clothes_75 | 1.000 / 784.9 | 0.775 / 0.9 | 0.990 / 1.2 | pass (iterative-relaxed) | forced-exact: FAIL latency 785 ms |
| hm_clothes_100 | 1.000 / 696.7 | 0.630 / 0.7 | 0.980 / 0.9 | pass (iterative-relaxed) | forced-hnsw: FAIL recall 0.630 |

**h2e** (s = 0.44642)

| table | forced-exact | forced-hnsw | iterative-relaxed | policy_v2 | P1 arm / pass |
|---|---|---|---|---|---|
| hm_clothes_0 | 1.000 / 813.6 | 0.985 / 0.8 | 0.985 / 0.8 | pass (iterative-relaxed) | forced-exact: FAIL latency 814 ms |
| hm_clothes_25 | 1.000 / 828.3 | 0.975 / 0.9 | 0.980 / 0.9 | pass (iterative-relaxed) | forced-exact: FAIL latency 828 ms |
| hm_clothes_50 | 1.000 / 810.9 | 0.955 / 0.7 | 0.985 / 0.8 | pass (iterative-relaxed) | forced-exact: FAIL latency 811 ms |
| hm_clothes_75 | 1.000 / 846.1 | 0.850 / 0.9 | 0.990 / 0.9 | pass (iterative-relaxed) | forced-exact: FAIL latency 846 ms |
| hm_clothes_100 | 1.000 / 837.4 | 0.730 / 0.8 | 0.980 / 0.9 | pass (iterative-relaxed) | forced-hnsw: FAIL recall 0.730 |

## Host load

run_start 10:51:42Z cpu% [30, 15, 12]; table_start_warmup 10:51:50Z cpu% [39, 18, 21]; table_start_warmup 11:01:50Z cpu% [18, 28, 17]; table_start_warmup 11:12:12Z cpu% [65, 31, 27]; table_start_warmup 11:21:48Z cpu% [3, 5, 8]; table_start_warmup 11:31:41Z cpu% [12, 11, 8]; run_end 11:41:17Z cpu% [5, 6, 2]
