# policy_v2 held-out results — 2026-10-12-rerun

**[V]** = computed by `src/phase_c_analysis/holdout_analysis.py` from `outputs/phase_a_holdout_rerun/results.jsonl`. **[I]** = interpretation. Protocol: `PHASE_A_HOLDOUT_PROTOCOL.md` (frozen in `fe06e9b`); `T = 0.1` was fixed before any held-out query and is not re-tuned here.

Provenance [V]: run commit `e0f898a`, pgvector 0.8.3, PostgreSQL 16.14, seed 20261014, k=10, ef_search=40, server settings {"shared_buffers": "128MB", "work_mem": "4MB", "effective_cache_size": "4GB", "max_parallel_workers_per_gather": "2", "random_page_cost": "4"}.

## 1. Headline: H7

**H7 — policy_v2 passes both SLAs in all 25 held-out cells: HOLDS** (25 of 25 cells pass). [V]

## 2. Completeness

- Rows expected 1500, written **1500**, unique keys 1500, max multiplicity 1. [V]
- Rows with an error/timeout: **0**; rows without valid recall/latency: 0; `plan_as_intended == false`: **0**. [V]
- Resumes: 0; rows written after a resume: **0**. [V]
- Vectors: 0-based line indices 20-39 of tests.jsonl; SHA-256 of the 20 lines `8e3e384621b599dbbf532c7772fc2f218a63365cd5706af02480155834c53208`. [V]
- Machine notes recorded outside the run (kernel CPU seconds and host load at start/end): `outputs/phase_a_holdout_rerun/machine_notes.txt`:

```
START 2026-10-12T08:03:33Z | Ollama stopped, no Jupyter/python processes, host CPU 17-21% (Claude desktop app, Docker) | see host_load.json | run commit e0f898a
END 2026-10-12T08:19:13Z | 1500 rows, 0 resumes | host CPU 3-5%
```

| arm | rows | errors | plan_as_intended=false | scan nodes |
|---|---|---|---|---|
| forced-exact | 500 | 0 | 0 | Bitmap Heap Scan:500 |
| forced-hnsw | 500 | 0 | 0 | Index Scan:500 |
| iterative-relaxed | 500 | 0 | 0 | Index Scan:500 |

## 3. Per-cell results (arm x table x filter)

Mean/min recall@10 over the 20 vectors; median rows returned; median latency (median of per-vector medians), IQR; scan nodes. CSV: `outputs/phase_a_holdout_rerun/analysis/cell_summary.csv`. [V]

### Arm: forced-exact

| table | filter | sel | mean rec | min rec | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|
| T0 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 37.2 | 1.15 | Bitmap Heap Scan:20 |
| T0 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 53.7 | 1.86 | Bitmap Heap Scan:20 |
| T0 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 123.7 | 6.10 | Bitmap Heap Scan:20 |
| T0 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 280.2 | 5.98 | Bitmap Heap Scan:20 |
| T0 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 351.0 | 7.79 | Bitmap Heap Scan:20 |
| T25 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 37.1 | 1.93 | Bitmap Heap Scan:20 |
| T25 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 53.3 | 1.47 | Bitmap Heap Scan:20 |
| T25 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 122.8 | 1.86 | Bitmap Heap Scan:20 |
| T25 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 281.4 | 5.95 | Bitmap Heap Scan:20 |
| T25 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 350.0 | 6.02 | Bitmap Heap Scan:20 |
| T50 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 36.3 | 1.87 | Bitmap Heap Scan:20 |
| T50 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 52.9 | 1.50 | Bitmap Heap Scan:20 |
| T50 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 122.1 | 3.85 | Bitmap Heap Scan:20 |
| T50 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 284.6 | 7.43 | Bitmap Heap Scan:20 |
| T50 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 354.5 | 7.12 | Bitmap Heap Scan:20 |
| T75 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 36.7 | 0.68 | Bitmap Heap Scan:20 |
| T75 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 53.8 | 1.98 | Bitmap Heap Scan:20 |
| T75 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 124.4 | 2.74 | Bitmap Heap Scan:20 |
| T75 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 281.5 | 5.74 | Bitmap Heap Scan:20 |
| T75 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 352.9 | 9.32 | Bitmap Heap Scan:20 |
| T100 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 36.2 | 0.44 | Bitmap Heap Scan:20 |
| T100 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 52.9 | 1.20 | Bitmap Heap Scan:20 |
| T100 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 122.5 | 3.27 | Bitmap Heap Scan:20 |
| T100 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 280.9 | 6.89 | Bitmap Heap Scan:20 |
| T100 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 350.4 | 11.9 | Bitmap Heap Scan:20 |

### Arm: forced-hnsw

| table | filter | sel | mean rec | min rec | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|
| T0 | ho1 | 0.02013 | 0.060 | 0.00 | 0 | 0.62 | 0.14 | Index Scan:20 |
| T0 | ho2 | 0.02962 | 0.115 | 0.00 | 1 | 0.60 | 0.25 | Index Scan:20 |
| T0 | ho3 | 0.07052 | 0.255 | 0.00 | 2 | 0.55 | 0.18 | Index Scan:20 |
| T0 | ho4 | 0.14352 | 0.535 | 0.20 | 6 | 0.68 | 0.20 | Index Scan:20 |
| T0 | ho5 | 0.18029 | 0.685 | 0.40 | 7 | 0.68 | 0.19 | Index Scan:20 |
| T25 | ho1 | 0.02013 | 0.100 | 0.00 | 0 | 0.65 | 0.28 | Index Scan:20 |
| T25 | ho2 | 0.02962 | 0.065 | 0.00 | 0 | 0.54 | 0.20 | Index Scan:20 |
| T25 | ho3 | 0.07052 | 0.225 | 0.00 | 2 | 0.58 | 0.19 | Index Scan:20 |
| T25 | ho4 | 0.14352 | 0.580 | 0.20 | 5 | 0.70 | 0.22 | Index Scan:20 |
| T25 | ho5 | 0.18029 | 0.625 | 0.30 | 8 | 0.67 | 0.20 | Index Scan:20 |
| T50 | ho1 | 0.02013 | 0.070 | 0.00 | 0 | 0.59 | 0.18 | Index Scan:20 |
| T50 | ho2 | 0.02962 | 0.090 | 0.00 | 1 | 0.55 | 0.18 | Index Scan:20 |
| T50 | ho3 | 0.07052 | 0.175 | 0.00 | 2 | 0.61 | 0.09 | Index Scan:20 |
| T50 | ho4 | 0.14352 | 0.555 | 0.10 | 6 | 0.72 | 0.21 | Index Scan:20 |
| T50 | ho5 | 0.18029 | 0.575 | 0.20 | 6 | 0.68 | 0.24 | Index Scan:20 |
| T75 | ho1 | 0.02013 | 0.090 | 0.00 | 0 | 0.59 | 0.17 | Index Scan:20 |
| T75 | ho2 | 0.02962 | 0.085 | 0.00 | 1 | 0.60 | 0.09 | Index Scan:20 |
| T75 | ho3 | 0.07052 | 0.080 | 0.00 | 1 | 0.57 | 0.09 | Index Scan:20 |
| T75 | ho4 | 0.14352 | 0.530 | 0.10 | 4 | 0.69 | 0.14 | Index Scan:20 |
| T75 | ho5 | 0.18029 | 0.450 | 0.00 | 3 | 0.68 | 0.21 | Index Scan:20 |
| T100 | ho1 | 0.02013 | 0.075 | 0.00 | 0 | 0.59 | 0.24 | Index Scan:20 |
| T100 | ho2 | 0.02962 | 0.085 | 0.00 | 0 | 0.58 | 0.22 | Index Scan:20 |
| T100 | ho3 | 0.07052 | 0.025 | 0.00 | 0 | 0.57 | 0.19 | Index Scan:20 |
| T100 | ho4 | 0.14352 | 0.470 | 0.00 | 5 | 0.63 | 0.23 | Index Scan:20 |
| T100 | ho5 | 0.18029 | 0.375 | 0.00 | 2 | 0.65 | 0.23 | Index Scan:20 |

### Arm: iterative-relaxed

| table | filter | sel | mean rec | min rec | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|
| T0 | ho1 | 0.02013 | 0.995 | 0.90 | 10 | 5.08 | 2.42 | Index Scan:20 |
| T0 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 3.45 | 1.92 | Index Scan:20 |
| T0 | ho3 | 0.07052 | 0.990 | 0.90 | 10 | 1.78 | 1.13 | Index Scan:20 |
| T0 | ho4 | 0.14352 | 0.990 | 0.90 | 10 | 1.12 | 0.69 | Index Scan:20 |
| T0 | ho5 | 0.18029 | 0.980 | 0.90 | 10 | 1.13 | 0.37 | Index Scan:20 |
| T25 | ho1 | 0.02013 | 0.995 | 0.90 | 10 | 5.40 | 3.58 | Index Scan:20 |
| T25 | ho2 | 0.02962 | 0.980 | 0.80 | 10 | 4.13 | 0.91 | Index Scan:20 |
| T25 | ho3 | 0.07052 | 0.995 | 0.90 | 10 | 2.06 | 1.11 | Index Scan:20 |
| T25 | ho4 | 0.14352 | 0.995 | 0.90 | 10 | 1.18 | 0.56 | Index Scan:20 |
| T25 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 1.29 | 0.58 | Index Scan:20 |
| T50 | ho1 | 0.02013 | 0.980 | 0.80 | 10 | 7.69 | 3.89 | Index Scan:20 |
| T50 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 4.27 | 2.42 | Index Scan:20 |
| T50 | ho3 | 0.07052 | 0.995 | 0.90 | 10 | 2.89 | 1.56 | Index Scan:20 |
| T50 | ho4 | 0.14352 | 0.985 | 0.90 | 10 | 1.40 | 0.91 | Index Scan:20 |
| T50 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 1.14 | 0.52 | Index Scan:20 |
| T75 | ho1 | 0.02013 | 0.995 | 0.90 | 10 | 8.55 | 6.74 | Index Scan:20 |
| T75 | ho2 | 0.02962 | 0.985 | 0.80 | 10 | 5.00 | 2.25 | Index Scan:20 |
| T75 | ho3 | 0.07052 | 0.990 | 0.90 | 10 | 3.62 | 1.20 | Index Scan:20 |
| T75 | ho4 | 0.14352 | 0.995 | 0.90 | 10 | 1.37 | 0.72 | Index Scan:20 |
| T75 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 1.56 | 1.00 | Index Scan:20 |
| T100 | ho1 | 0.02013 | 0.895 | 0.10 | 10 | 15.8 | 64.7 | Index Scan:20 |
| T100 | ho2 | 0.02962 | 0.985 | 0.80 | 10 | 6.72 | 6.47 | Index Scan:20 |
| T100 | ho3 | 0.07052 | 0.950 | 0.50 | 10 | 7.41 | 5.03 | Index Scan:20 |
| T100 | ho4 | 0.14352 | 0.975 | 0.50 | 10 | 1.50 | 1.51 | Index Scan:20 |
| T100 | ho5 | 0.18029 | 0.980 | 0.80 | 10 | 3.24 | 2.95 | Index Scan:20 |

## 4. Policies on the 25 held-out cells

| policy | pass both SLAs | recall fail | latency fail | both | cells with invalid vectors |
|---|---|---|---|---|---|
| P1 v1 matrix (policy.py + phase_a_v1/thresholds.json) | **25** / 25 | 0 | 0 | 0 | 0 |
| P4 always forced-exact | **25** / 25 | 0 | 0 | 0 | 0 |
| P5 always forced-hnsw | **0** / 25 | 25 | 0 | 0 | 0 |
| P6 always iterative-relaxed | **24** / 25 | 1 | 0 | 0 | 0 |
| policy_v2 (forced-exact if s < 0.1 else iterative-relaxed) | **25** / 25 | 0 | 0 | 0 | 0 |

| policy | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|
| P1 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| P4 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| P5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 |
| P6 | 5/5 | 5/5 | 5/5 | 5/5 | 4/5 |
| policy_v2 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |

Route per held-out filter under each policy (policy_v2 and P1 vary only through selectivity and, for P1, the table tier) [V]:

| filter | sel | policy_v2 arm | P1 arm(s) over tables |
|---|---|---|---|
| ho1 | 0.02013 | FE | FE |
| ho2 | 0.02962 | FE | FE |
| ho3 | 0.07052 | FE | FE |
| ho4 | 0.14352 | IR | FE |
| ho5 | 0.18029 | IR | FE |

### Failing cells per policy

**P1 v1 matrix (policy.py + phase_a_v1/thresholds.json)** — 0 failing cell(s)
- none

**P4 always forced-exact** — 0 failing cell(s)
- none

**P5 always forced-hnsw** — 25 failing cell(s)
- ho1 (0.02013): T0:R(0.06/1ms), T25:R(0.10/1ms), T50:R(0.07/1ms), T75:R(0.09/1ms), T100:R(0.08/1ms)
- ho2 (0.02962): T0:R(0.12/1ms), T25:R(0.07/1ms), T50:R(0.09/1ms), T75:R(0.09/1ms), T100:R(0.09/1ms)
- ho3 (0.07052): T0:R(0.26/1ms), T25:R(0.22/1ms), T50:R(0.17/1ms), T75:R(0.08/1ms), T100:R(0.03/1ms)
- ho4 (0.14352): T0:R(0.54/1ms), T25:R(0.58/1ms), T50:R(0.56/1ms), T75:R(0.53/1ms), T100:R(0.47/1ms)
- ho5 (0.18029): T0:R(0.69/1ms), T25:R(0.63/1ms), T50:R(0.57/1ms), T75:R(0.45/1ms), T100:R(0.38/1ms)

**P6 always iterative-relaxed** — 1 failing cell(s)
- ho1 (0.02013): T100:R(0.89/16ms)

**policy_v2 (forced-exact if s < 0.1 else iterative-relaxed)** — 0 failing cell(s)
- none

## 5. Hypotheses H7-H9

**H7** policy_v2 passes all 25 held-out cells: **HOLDS** (25/25). [V]

**H8** P6 (always iterative) fails recall in >= 1 held-out cell on hm_clothes_100 at s <= 0.03: **HOLDS**. Cells covered (hm_clothes_100, s <= 0.03): ho1 (s=0.02013): iterative-relaxed mean recall 0.895; ho2 (s=0.02962): iterative-relaxed mean recall 0.985. [V]

**H9** policy_v2 passes more held-out cells than P1: **FAILS** (policy_v2 25 vs P1 25 of 25). [V]

| H | verdict |
|---|---|
| H7 | holds |
| H8 | holds |
| H9 | fails |

## 6. Combined picture (in-sample and held-out kept separate)

In-sample = the 65 cells of the three-arm run (`reports/policy_evaluation_2026-10-10.md`; P1 and policy_v2 = P8 with T = 0.1 evaluated there; policy_v2's T was fitted on these cells). Held-out = the 25 cells above, tested once with T fixed in advance. The two sets are not independent samples of one population (same tables, same vector pool), so the combined row is a convenience, not an overall estimate. [V]

| policy | in-sample | held-out | combined |
|---|---|---|---|
| P1 v1 matrix (policy.py + phase_a_v1/thresholds.json) | 29 / 65 (in-sample) | 25 / 25 (held-out) | 54 / 90 |
| P4 always forced-exact | 27 / 65 (in-sample) | 25 / 25 (held-out) | 52 / 90 |
| P5 always forced-hnsw | 11 / 65 (in-sample) | 0 / 25 (held-out) | 11 / 90 |
| P6 always iterative-relaxed | 54 / 65 (in-sample) | 24 / 25 (held-out) | 78 / 90 |
| policy_v2 (forced-exact if s < 0.1 else iterative-relaxed) | 65 / 65 (in-sample) | 25 / 25 (held-out) | 90 / 90 |

