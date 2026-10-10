# policy_v2 held-out results — 2026-10-10

**[V]** = computed by `src/phase_c_analysis/holdout_analysis.py` from `outputs/phase_a_holdout/results.jsonl`. **[I]** = interpretation. Protocol: `PHASE_A_HOLDOUT_PROTOCOL.md` (frozen in `fe06e9b`); `T = 0.1` was fixed before any held-out query and is not re-tuned here.

Provenance [V]: run commit `fe06e9b`, pgvector 0.8.3, PostgreSQL 16.14, seed 20261012, k=10, ef_search=40, server settings {"shared_buffers": "128MB", "work_mem": "4MB", "effective_cache_size": "4GB", "max_parallel_workers_per_gather": "2", "random_page_cost": "4"}.

## 1. Headline: H7

**H7 — policy_v2 passes both SLAs in all 25 held-out cells: FAILS** (24 of 25 cells pass). [V]

Failing cells (policy_v2):

| table | filter | sel | arm used | mean recall | median ms | valid vectors | reason |
|---|---|---|---|---|---|---|---|
| hm_clothes_25 | ho3 | 0.07052 | FE | 1.000 | 528.4 | 20 | latency |

## 2. Completeness

- Rows expected 1500, written **1500**, unique keys 1500, max multiplicity 1. [V]
- Rows with an error/timeout: **0**; rows without valid recall/latency: 0; `plan_as_intended == false`: **0**. [V]
- Resumes: 0; rows written after a resume: **0**. [V]
- Vectors: 0-based line indices 20-39 of tests.jsonl; SHA-256 of the 20 lines `8e3e384621b599dbbf532c7772fc2f218a63365cd5706af02480155834c53208`. [V]
- Machine notes recorded outside the run (kernel CPU seconds and host load at start/end): `outputs/phase_a_holdout/machine_notes.txt`:

```
START 2026-10-10T17:57:38+05:30 | ipykernel PID 41292 cumulative CPU = 24992 s | host CPU load = 100% | run PID 49260 | run commit fe06e9b
END   2026-10-10T18:29:20+05:30 | ipykernel PID 41292 cumulative CPU = 28402 s | host CPU load = 50% | last result row 2026-10-10T12:51:42Z (18:21:42 +05:30), 1500 rows, 0 resumes
```

| arm | rows | errors | plan_as_intended=false | scan nodes |
|---|---|---|---|---|
| forced-exact | 500 | 0 | 0 | Bitmap Heap Scan:500 |
| forced-hnsw | 500 | 0 | 0 | Index Scan:500 |
| iterative-relaxed | 500 | 0 | 0 | Index Scan:500 |

## 3. Per-cell results (arm x table x filter)

Mean/min recall@10 over the 20 vectors; median rows returned; median latency (median of per-vector medians), IQR; scan nodes. CSV: `outputs/phase_a_holdout/analysis/cell_summary.csv`. [V]

### Arm: forced-exact

| table | filter | sel | mean rec | min rec | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|
| T0 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 39.0 | 3.20 | Bitmap Heap Scan:20 |
| T0 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 105.4 | 13.9 | Bitmap Heap Scan:20 |
| T0 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 175.2 | 119.2 | Bitmap Heap Scan:20 |
| T0 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 572.1 | 29.6 | Bitmap Heap Scan:20 |
| T0 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 711.6 | 330.3 | Bitmap Heap Scan:20 |
| T25 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 144.4 | 11.5 | Bitmap Heap Scan:20 |
| T25 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 207.0 | 150.9 | Bitmap Heap Scan:20 |
| T25 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 528.4 | 15.8 | Bitmap Heap Scan:20 |
| T25 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 308.9 | 8.75 | Bitmap Heap Scan:20 |
| T25 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 1255 | 1109 | Bitmap Heap Scan:20 |
| T50 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 38.6 | 0.75 | Bitmap Heap Scan:20 |
| T50 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 56.4 | 3.03 | Bitmap Heap Scan:20 |
| T50 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 133.3 | 10.0 | Bitmap Heap Scan:20 |
| T50 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 308.1 | 9.86 | Bitmap Heap Scan:20 |
| T50 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 370.5 | 9.61 | Bitmap Heap Scan:20 |
| T75 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 39.8 | 2.21 | Bitmap Heap Scan:20 |
| T75 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 57.8 | 2.14 | Bitmap Heap Scan:20 |
| T75 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 132.0 | 23.6 | Bitmap Heap Scan:20 |
| T75 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 300.2 | 9.01 | Bitmap Heap Scan:20 |
| T75 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 406.0 | 129.5 | Bitmap Heap Scan:20 |
| T100 | ho1 | 0.02013 | 1.000 | 1.00 | 10 | 40.5 | 3.31 | Bitmap Heap Scan:20 |
| T100 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 57.5 | 2.08 | Bitmap Heap Scan:20 |
| T100 | ho3 | 0.07052 | 1.000 | 1.00 | 10 | 132.1 | 4.41 | Bitmap Heap Scan:20 |
| T100 | ho4 | 0.14352 | 1.000 | 1.00 | 10 | 301.3 | 13.8 | Bitmap Heap Scan:20 |
| T100 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 380.3 | 12.5 | Bitmap Heap Scan:20 |

### Arm: forced-hnsw

| table | filter | sel | mean rec | min rec | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|
| T0 | ho1 | 0.02013 | 0.060 | 0.00 | 0 | 0.57 | 0.23 | Index Scan:20 |
| T0 | ho2 | 0.02962 | 0.115 | 0.00 | 1 | 0.97 | 0.32 | Index Scan:20 |
| T0 | ho3 | 0.07052 | 0.255 | 0.00 | 2 | 0.80 | 0.43 | Index Scan:20 |
| T0 | ho4 | 0.14352 | 0.535 | 0.20 | 6 | 1.11 | 0.26 | Index Scan:20 |
| T0 | ho5 | 0.18029 | 0.685 | 0.40 | 7 | 1.26 | 0.42 | Index Scan:20 |
| T25 | ho1 | 0.02013 | 0.100 | 0.00 | 0 | 0.95 | 0.36 | Index Scan:20 |
| T25 | ho2 | 0.02962 | 0.065 | 0.00 | 0 | 0.92 | 0.37 | Index Scan:20 |
| T25 | ho3 | 0.07052 | 0.225 | 0.00 | 2 | 0.91 | 0.25 | Index Scan:20 |
| T25 | ho4 | 0.14352 | 0.580 | 0.20 | 5 | 0.91 | 0.31 | Index Scan:20 |
| T25 | ho5 | 0.18029 | 0.625 | 0.30 | 8 | 0.98 | 0.31 | Index Scan:20 |
| T50 | ho1 | 0.02013 | 0.070 | 0.00 | 0 | 0.67 | 0.23 | Index Scan:20 |
| T50 | ho2 | 0.02962 | 0.090 | 0.00 | 1 | 0.65 | 0.18 | Index Scan:20 |
| T50 | ho3 | 0.07052 | 0.175 | 0.00 | 2 | 0.57 | 0.22 | Index Scan:20 |
| T50 | ho4 | 0.14352 | 0.555 | 0.10 | 6 | 0.81 | 0.40 | Index Scan:20 |
| T50 | ho5 | 0.18029 | 0.575 | 0.20 | 6 | 0.74 | 0.27 | Index Scan:20 |
| T75 | ho1 | 0.02013 | 0.090 | 0.00 | 0 | 0.71 | 0.18 | Index Scan:20 |
| T75 | ho2 | 0.02962 | 0.085 | 0.00 | 1 | 0.74 | 0.21 | Index Scan:20 |
| T75 | ho3 | 0.07052 | 0.080 | 0.00 | 1 | 0.67 | 0.29 | Index Scan:20 |
| T75 | ho4 | 0.14352 | 0.530 | 0.10 | 4 | 0.77 | 0.19 | Index Scan:20 |
| T75 | ho5 | 0.18029 | 0.450 | 0.00 | 3 | 0.91 | 0.31 | Index Scan:20 |
| T100 | ho1 | 0.02013 | 0.075 | 0.00 | 0 | 0.71 | 0.27 | Index Scan:20 |
| T100 | ho2 | 0.02962 | 0.085 | 0.00 | 0 | 0.75 | 0.21 | Index Scan:20 |
| T100 | ho3 | 0.07052 | 0.025 | 0.00 | 0 | 0.58 | 0.26 | Index Scan:20 |
| T100 | ho4 | 0.14352 | 0.470 | 0.00 | 5 | 0.70 | 0.27 | Index Scan:20 |
| T100 | ho5 | 0.18029 | 0.375 | 0.00 | 2 | 0.80 | 0.20 | Index Scan:20 |

### Arm: iterative-relaxed

| table | filter | sel | mean rec | min rec | med rows | med lat ms | IQR ms | scan nodes |
|---|---|---|---|---|---|---|---|---|
| T0 | ho1 | 0.02013 | 0.995 | 0.90 | 10 | 5.04 | 2.52 | Index Scan:20 |
| T0 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 5.82 | 3.40 | Index Scan:20 |
| T0 | ho3 | 0.07052 | 0.990 | 0.90 | 10 | 2.75 | 2.30 | Index Scan:20 |
| T0 | ho4 | 0.14352 | 0.990 | 0.90 | 10 | 2.03 | 1.00 | Index Scan:20 |
| T0 | ho5 | 0.18029 | 0.980 | 0.90 | 10 | 1.74 | 0.57 | Index Scan:20 |
| T25 | ho1 | 0.02013 | 0.995 | 0.90 | 10 | 7.74 | 13.6 | Index Scan:20 |
| T25 | ho2 | 0.02962 | 0.980 | 0.80 | 10 | 6.93 | 4.14 | Index Scan:20 |
| T25 | ho3 | 0.07052 | 0.995 | 0.90 | 10 | 3.19 | 1.69 | Index Scan:20 |
| T25 | ho4 | 0.14352 | 0.995 | 0.90 | 10 | 1.56 | 0.70 | Index Scan:20 |
| T25 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 1.66 | 0.48 | Index Scan:20 |
| T50 | ho1 | 0.02013 | 0.980 | 0.80 | 10 | 8.40 | 5.66 | Index Scan:20 |
| T50 | ho2 | 0.02962 | 1.000 | 1.00 | 10 | 5.26 | 1.99 | Index Scan:20 |
| T50 | ho3 | 0.07052 | 0.995 | 0.90 | 10 | 3.00 | 1.50 | Index Scan:20 |
| T50 | ho4 | 0.14352 | 0.985 | 0.90 | 10 | 1.55 | 1.14 | Index Scan:20 |
| T50 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 1.43 | 0.52 | Index Scan:20 |
| T75 | ho1 | 0.02013 | 0.995 | 0.90 | 10 | 10.5 | 6.21 | Index Scan:20 |
| T75 | ho2 | 0.02962 | 0.985 | 0.80 | 10 | 5.96 | 1.97 | Index Scan:20 |
| T75 | ho3 | 0.07052 | 0.990 | 0.90 | 10 | 4.19 | 2.07 | Index Scan:20 |
| T75 | ho4 | 0.14352 | 0.995 | 0.90 | 10 | 1.56 | 0.86 | Index Scan:20 |
| T75 | ho5 | 0.18029 | 1.000 | 1.00 | 10 | 1.86 | 1.30 | Index Scan:20 |
| T100 | ho1 | 0.02013 | 0.895 | 0.10 | 10 | 18.5 | 77.1 | Index Scan:20 |
| T100 | ho2 | 0.02962 | 0.985 | 0.80 | 10 | 7.38 | 6.96 | Index Scan:20 |
| T100 | ho3 | 0.07052 | 0.950 | 0.50 | 10 | 8.10 | 5.59 | Index Scan:20 |
| T100 | ho4 | 0.14352 | 0.975 | 0.50 | 10 | 1.82 | 1.44 | Index Scan:20 |
| T100 | ho5 | 0.18029 | 0.980 | 0.80 | 10 | 3.75 | 3.11 | Index Scan:20 |

## 4. Policies on the 25 held-out cells

| policy | pass both SLAs | recall fail | latency fail | both | cells with invalid vectors |
|---|---|---|---|---|---|
| P1 v1 matrix (policy.py + phase_a_v1/thresholds.json) | **21** / 25 | 0 | 4 | 0 | 0 |
| P4 always forced-exact | **21** / 25 | 0 | 4 | 0 | 0 |
| P5 always forced-hnsw | **0** / 25 | 25 | 0 | 0 | 0 |
| P6 always iterative-relaxed | **24** / 25 | 1 | 0 | 0 | 0 |
| policy_v2 (forced-exact if s < 0.1 else iterative-relaxed) | **24** / 25 | 0 | 1 | 0 | 0 |

| policy | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|
| P1 | 3/5 | 3/5 | 5/5 | 5/5 | 5/5 |
| P4 | 3/5 | 3/5 | 5/5 | 5/5 | 5/5 |
| P5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 |
| P6 | 5/5 | 5/5 | 5/5 | 5/5 | 4/5 |
| policy_v2 | 5/5 | 4/5 | 5/5 | 5/5 | 5/5 |

Route per held-out filter under each policy (policy_v2 and P1 vary only through selectivity and, for P1, the table tier) [V]:

| filter | sel | policy_v2 arm | P1 arm(s) over tables |
|---|---|---|---|
| ho1 | 0.02013 | FE | FE |
| ho2 | 0.02962 | FE | FE |
| ho3 | 0.07052 | FE | FE |
| ho4 | 0.14352 | IR | FE |
| ho5 | 0.18029 | IR | FE |

### Failing cells per policy

**P1 v1 matrix (policy.py + phase_a_v1/thresholds.json)** — 4 failing cell(s)
- ho3 (0.07052): T25:L(1.00/528ms)
- ho4 (0.14352): T0:L(1.00/572ms)
- ho5 (0.18029): T0:L(1.00/712ms), T25:L(1.00/1255ms)

**P4 always forced-exact** — 4 failing cell(s)
- ho3 (0.07052): T25:L(1.00/528ms)
- ho4 (0.14352): T0:L(1.00/572ms)
- ho5 (0.18029): T0:L(1.00/712ms), T25:L(1.00/1255ms)

**P5 always forced-hnsw** — 25 failing cell(s)
- ho1 (0.02013): T0:R(0.06/1ms), T25:R(0.10/1ms), T50:R(0.07/1ms), T75:R(0.09/1ms), T100:R(0.07/1ms)
- ho2 (0.02962): T0:R(0.11/1ms), T25:R(0.07/1ms), T50:R(0.09/1ms), T75:R(0.09/1ms), T100:R(0.09/1ms)
- ho3 (0.07052): T0:R(0.26/1ms), T25:R(0.23/1ms), T50:R(0.18/1ms), T75:R(0.08/1ms), T100:R(0.03/1ms)
- ho4 (0.14352): T0:R(0.54/1ms), T25:R(0.58/1ms), T50:R(0.56/1ms), T75:R(0.53/1ms), T100:R(0.47/1ms)
- ho5 (0.18029): T0:R(0.68/1ms), T25:R(0.63/1ms), T50:R(0.57/1ms), T75:R(0.45/1ms), T100:R(0.38/1ms)

**P6 always iterative-relaxed** — 1 failing cell(s)
- ho1 (0.02013): T100:R(0.89/18ms)

**policy_v2 (forced-exact if s < 0.1 else iterative-relaxed)** — 1 failing cell(s)
- ho3 (0.07052): T25:L(1.00/528ms)

## 5. Hypotheses H7-H9

**H7** policy_v2 passes all 25 held-out cells: **FAILS** (24/25). [V]

**H8** P6 (always iterative) fails recall in >= 1 held-out cell on hm_clothes_100 at s <= 0.03: **HOLDS**. Cells covered (hm_clothes_100, s <= 0.03): ho1 (s=0.02013): iterative-relaxed mean recall 0.895; ho2 (s=0.02962): iterative-relaxed mean recall 0.985. [V]

**H9** policy_v2 passes more held-out cells than P1: **HOLDS** (policy_v2 24 vs P1 21 of 25). [V]

| H | verdict |
|---|---|
| H7 | fails |
| H8 | holds |
| H9 | holds |

## 6. Combined picture (in-sample and held-out kept separate)

In-sample = the 65 cells of the three-arm run (`reports/policy_evaluation_2026-10-10.md`; P1 and policy_v2 = P8 with T = 0.1 evaluated there; policy_v2's T was fitted on these cells). Held-out = the 25 cells above, tested once with T fixed in advance. The two sets are not independent samples of one population (same tables, same vector pool), so the combined row is a convenience, not an overall estimate. [V]

| policy | in-sample | held-out | combined |
|---|---|---|---|
| P1 v1 matrix (policy.py + phase_a_v1/thresholds.json) | 29 / 65 (in-sample) | 21 / 25 (held-out) | 50 / 90 |
| P4 always forced-exact | 27 / 65 (in-sample) | 21 / 25 (held-out) | 48 / 90 |
| P5 always forced-hnsw | 11 / 65 (in-sample) | 0 / 25 (held-out) | 11 / 90 |
| P6 always iterative-relaxed | 54 / 65 (in-sample) | 24 / 25 (held-out) | 78 / 90 |
| policy_v2 (forced-exact if s < 0.1 else iterative-relaxed) | 65 / 65 (in-sample) | 24 / 25 (held-out) | 89 / 90 |


## 7. Interpretation (hand-written after reading sections 1-6; [V] numbers from this report, [I] interpretation)

**Verdicts [V].** **H7 fails**: policy_v2 (T = 0.1) passes 24 of 25 held-out cells. **H8 holds** (P6 fails recall on hm_clothes_100 at ho1, mean recall 0.895; ho2 is 0.985, so H8 rests on one cell that misses 0.90 by 0.005). **H9 holds** (policy_v2 24 vs P1 21). Per the protocol the H7 outcome is reported as a failure and T is not changed.

**The single failing cell [V].** hm_clothes_25 x ho3 (s = 0.07052): policy_v2 uses forced-exact there; recall is 1.000 and the median latency is **528.4 ms**, 28.4 ms over the 500 ms limit. It is a latency failure, not a recall failure; policy_v2 has no recall failure in any of the 25 cells (arms used: forced-exact for ho1-ho3, iterative-relaxed for ho4-ho5). The cell is not an outlier artefact of one vector: 18 of 20 per-vector medians are above 500 ms and they are tightly clustered (508-539 ms; IQR 16 ms).

**Why I think it failed [I, not proven].** The same filter on the other tables costs 132-175 ms for forced-exact, i.e. 3-4x less. The elevation is table-wide and follows run order, not selectivity: hm_clothes_25 ran first (12:28:00-12:35:19 UTC) and its forced-exact medians are 3.3-4.0x those of the three "quiet" tables hm_clothes_50 / 100 / 75 at ho1, ho2, ho3 and ho5 (ho1 144 vs 39-41 ms, ho2 207 vs 56-58, ho3 528 vs 132-133, ho5 1,255 vs 371-406) and unchanged at ho4 (309 vs 300-308); hm_clothes_0 (fourth, 12:42:21-12:47:47) is elevated at ho2-ho5 (105, 175, 572, 712 ms vs 56-58, 132, 300, 371-406). hm_clothes_25 also took 7.3 min against 3-5.5 min for the other tables. The pages were not read from disk (median `shared_read_blocks` = 0 in the cell), so this looks like CPU contention rather than a cold cache. A Jupyter kernel (PID 41292) not part of this project used 3,410 CPU-seconds between the start and end notes (31.7 minutes, about 1.8 cores on average; the run itself ended at 18:21), with host load 100% at the start and 50% at the end (`machine_notes.txt`), and the harness self-test had already shown the exact arm running about 3x slower than in the main run. The load over time was not recorded, so the link between the kernel and the two slow tables is an inference. If forced-exact had run at the 132 ms level seen on the quiet tables, the cell would pass; this does not change the verdict, because the protocol commits to a single run reported as measured.

**What it means for the rule [I].**
- The rule's two failure modes seen so far are different in kind: iterative-relaxed fails on **recall** on the least-correlated table (in-sample lo3 0.82, lo4 0.42; held-out ho1 0.895), forced-exact fails on **latency**, and its latency is the less stable of the two measurements on this machine (3x run-to-run spread).
- Iterative-relaxed passed ho3 on all five tables (recall 0.95-0.995, 2.7-8.1 ms). A lower threshold (for example T = 0.05, which routes ho3 to iterative) would have passed all 25 held-out cells, **but that is a post-hoc observation made on the held-out data: it is in-sample for that T and is not evidence for it.** The in-sample analysis scored T = 0.05 and T = 0.1 identically (65/65), so my choice of 0.1 was a midpoint between the two bounds, not something the data determined.
- Lowering T is not free: on hm_clothes_100 the iterative arm's recall is not a smooth function of selectivity (lo3 0.0105: 0.82; ho1 0.0201: 0.895; ho2 0.0296: 0.985; **lo4 0.0478: 0.42**; ho3 0.0705: 0.95; lo5 0.106: 0.93). Moving T below 0.0478-0.07 would send filters like lo4 (garment group `Shoes`) to the iterative arm where it failed in-sample. T = 0.1 keeps those on the exact arm at the price of exact-arm latency, which is where the held-out failure occurred.
- On the held-out cells policy_v2 does not beat always-iterative (P6: 24/25 as well); it differs in the kind of failure (P6: one recall miss on hm_clothes_100/ho1; policy_v2: one latency miss on hm_clothes_25/ho3). In-sample P6 passed 54/65 against 65/65 for policy_v2, but the policy_v2 figure is fitted.

**In-sample vs held-out [V].** In-sample (fitted): policy_v2 65/65. Held-out (tested once, T fixed beforehand): 24/25. P1: 29/65 in-sample, 21/25 held-out; P4: 27/65, 21/25; P5: 11/65, 0/25; P6: 54/65, 24/25. The held-out set is easier for the baselines than the in-sample set because it has no filter above 0.18 (the region where forced-exact and the matrix fail on latency in-sample) and no filter at lo1-lo2 selectivities; its 25 cells are also not independent of the in-sample tables and vector pool.

**Not shown [V].** Held-out coverage is 0.020-0.180 only (five filters, one an IN list, 20 vectors); nothing is tested above 0.18 or below 0.02, on FinQA, on other table sizes or under controlled machine load.

**Options (decisions for the user, not taken here).** (a) Accept 24/25 and report the single latency miss as it stands. (b) Repeat the held-out run once more with the machine quiet (the Jupyter kernel stopped), reported as a separate run, to see whether hm_clothes_25 x ho3 is reproducible; this is permitted only as a separate, labelled run. (c) Choose a new T (e.g. 0.05) and test it on a fresh held-out set (new filters, vectors 41-60); the T = 0.05 result above would stay labelled post-hoc. Step 4 (implementing policy_v2) was **not** done because H7 did not hold.
