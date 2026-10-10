# policy_v2 held-out protocol

**Status:** frozen before any held-out query. No retrieval query has been run on the held-out filters or the held-out vectors; the only things done with them before this commit are row counts per filter (to measure selectivity) and plain `EXPLAIN` plan checks at run start (no execution).

## Purpose

`docs/POLICY_V2_PROPOSAL.md` proposes: forced-exact if estimated selectivity `s < T`, else iterative-relaxed, with `T = 0.1` chosen from the in-sample analysis (`reports/policy_evaluation_2026-10-10.md`, P8). That rule was fitted on the 65 cells of the three-arm run (13 filters, vectors 0-19) and scored 65/65 there, which says nothing about new data. This protocol tests the frozen rule on filters and vectors not used before.

## Frozen rule under test

**policy_v2 = forced-exact if `s < T` else iterative-relaxed, `T = 0.1`.** `T` is fixed now and will **not** be re-tuned on held-out data. `s` is the exact measured selectivity (matched rows / 105,100) of the filter.

Evaluated on the same held-out cells, unchanged from their definitions in the evaluation report:

- **P1** the original v1 matrix: unmodified `src/phase_b_router/policy.py` (commit `acc590c`) with `outputs/phase_a_v1/thresholds.json`, per-table tier = table name; `pre-filter` -> forced-exact, `post-filter` -> forced-hnsw.
- **P4** always forced-exact. **P5** always forced-hnsw. **P6** always iterative-relaxed.

## Held-out filters (not among the 13 used so far)

None of these (column, value) pairs appears in `outputs/phase_a_arms/filters.json`. Selected by closeness of selectivity to the targets (|ln(s/target)|), single-attribute equality preferred; selectivities measured on all five tables (identical row counts) by `holdout_run.py --build-filters` into `outputs/phase_a_holdout/filters.json`.

| id | target | filter | selectivity | rows |
|---|---:|---|---:|---:|
| ho1 | 0.02 | `garment_group_name = 'Shirts'` | 0.02013 | 2,116 |
| ho2 | 0.03 | `perceived_colour_master_name = 'Yellow'` | 0.02962 | 3,113 |
| ho3 | 0.07 | `garment_group_name = 'Under-, Nightwear'` | 0.07052 | 7,412 |
| ho4 | 0.15 | `index_group_name = 'Divided'` | 0.14352 | 15,084 |
| ho5 | 0.18 | `graphical_appearance_name IN ('All over pattern', 'Colour blocking')` | 0.18029 | 18,948 |

Choices made before measuring, stated for transparency:
- ho2: `Khaki green` (0.03021) is nominally closest to 0.03, but `Yellow` (0.02962) was taken so that both ho1 and ho2 satisfy `s <= 0.03`, which H8 requires.
- ho4: the closest single value to 0.15 is `Divided` (0.1435). ho5: no single value lies within 5% of 0.18 (the closest, `All over pattern`, is 0.163), so a two-value IN list over one column was used (closest of the candidate lists, 0.18029). ho5 is therefore not a plain equality filter.
- ho1-ho5 selectivities lie in 0.020-0.180; `T = 0.1` lies between ho3 (0.0705) and ho4 (0.1435), so ho1-ho3 are routed to forced-exact and ho4-ho5 to iterative-relaxed by policy_v2.
- I chose the filters knowing the in-sample results, but by selectivity only; I have not looked at any recall or latency for these filters.

## Held-out vectors

0-based line indices 20-39 of `ann-filtering-benchmark-datasets/data/tests.jsonl` (lines 21-40). The file has 10,000 lines, so all 20 exist. They were not used by the three-arm run (vectors 0-19) or by the exploratory diagnostic. `vector_idx` in the results is this 0-based line index (20-39). SHA-256 of the 20 lines (each with its newline) is stored in `run_meta.json`.

## Tables, arms, measurement

- Tables: hm_clothes_0, _25, _50, _75, _100. 5 tables x 5 filters = **25 held-out cells**, 20 vectors each.
- Arms: forced-exact, forced-hnsw, iterative-relaxed only, with the exact Amendment 2 settings of `arm_comparison.py` (`ARMS`, `apply_arm`; forced-hnsw and iterative include `enable_sort = off`, `enable_bitmapscan = off`, `enable_seqscan = off`, `enable_indexscan = on`; forced-exact has `enable_indexscan = off`), `k = 10`, `hnsw.ef_search = 40`, `hnsw.max_scan_tuples` = 20000 (default), `jit = off`, `statement_timeout = 120000 ms`.
- Per (table, filter, vector, arm): exact top-10 reference cached per (table, filter, vector) on a connection with `enable_indexscan = off`; recall@10 from one normal execution; one untimed warm-up; 5 timed `EXPLAIN ANALYZE` runs, median. Rows returned, scan node, index, buffers recorded. Per-table warm-up before timing.
- Order: tables, filters, vectors and arms shuffled with `random.Random(20261012)` (new seed); seed and schedule hash recorded in `run_meta.json`.
- **Pre-flight plan check** before any measured query: plain `EXPLAIN` for every table x filter x arm (75 checks, vector index 20); forced-exact must be Seq/Bitmap Heap Scan, the other two an Index Scan on `*embedding_idx`; any mismatch aborts the run. Saved to `outputs/phase_a_holdout/preflight.json`.
- Resumable writer: rows appended and flushed, existing keys skipped, `run_meta.json` written once, connection loss stops the run without recording a row, a full run refuses to start with uncommitted used files.
- Outputs: `outputs/phase_a_holdout/` (`filters.json`, `preflight.json`, `run_meta.json`, `results.jsonl`, `resumes.jsonl`, logs). Expected rows: 25 x 20 x 3 = **1,500**.
- Harness check before the freeze: `holdout_run.py --selftest` replays hm_clothes_100 x idx1 (a filter of the main run, not held-out) for vectors 0 and 1 into `selftest.jsonl` and is compared with `results.jsonl` of the main run.

## Pass criterion and cell definitions

A cell (table, filter) passes under a policy if the arm that policy selects there has **mean recall@10 >= 0.90 over the valid vectors AND median latency <= 500 ms** (median of the per-vector medians). Clarification added now: a cell with any invalid vector (error or timeout) is reported separately and counted as **not passing**.

## Pre-registered hypotheses

- **H7:** policy_v2 (T=0.1) passes both SLAs (mean recall >= 0.90 over all valid vectors, median latency <= 500 ms) in all 25 held-out cells.
- **H8:** P6 (always iterative) fails recall in >= 1 held-out cell on hm_clothes_100 at s <= 0.03. (Cells covered: hm_clothes_100 x ho1 and hm_clothes_100 x ho2; failing recall = mean recall < 0.90.)
- **H9:** policy_v2 passes more held-out cells than P1. (Strictly more, counted over the 25 cells.)

**Reporting commitments.** If policy_v2 fails any cell, the report states it as a failure of H7 and lists the cells with recall, latency and the arm used. Any T chosen after seeing held-out data is labelled in-sample and is not evidence for the rule.

## Size and run time

Combinations 5 x 5 x 20 = 500 (table, filter, vector); executions per combination 1 reference + 3 arms x 7 = 22, i.e. **11,000** executions (500 reference, 1,500 recall, 1,500 warm-up, 7,500 timed). Run time is dominated by the exact arm and the reference, 8 exact executions per combination. From the main run, forced-exact medians were 24-68 ms at 0.0105, 98-285 ms at 0.048 and 253-317 ms at 0.106, and 547-1,080 ms at 0.204 [V, `outputs/phase_a_arms/analysis/cell_summary.csv`]; I expect roughly 0.6 s (ho1) to 5 s (ho5) of exact work per combination plus about 1 s of per-arm settings overhead, i.e. about 4 s per combination on average and **about 0.5-1.5 hours** in total [I; not measured at these filters].

## Limits

H&M only, k = 10, `ef_search` = 40, default `max_scan_tuples`, one machine and server configuration (`shared_buffers` = 128MB, `work_mem` = 4MB), categorical filters, 105,100-row tables, five held-out filters (one of them an IN list), 20 held-out vectors per cell. The held-out set tests transfer to new filters and vectors on the same data; it does not test other table sizes or FinQA.

## Machine conditions observed before the run (disclosed, not controlled)

- A Jupyter kernel (`ipykernel_launcher` from a `codex-runtimes` Python, PID 41292, started 2026-10-10 10:36, not part of this project's scripts) had used about 24,600 CPU-seconds by 2026-10-10 ~17:50 and the host CPU load read 100%. It started before the three-arm run (10:47), so that run probably saw similar conditions, but its load over time was not recorded. It was not stopped or touched.
- In the harness self-test (hm_clothes_100 x idx1, vectors 0 and 1, a main-run filter) forced-exact took 2,685 and 2,701 ms against 882 and 825 ms in the main run for the same points, while recall, rows and plan nodes were identical. Exact-arm latency can therefore differ by about 3x between runs on this machine. Latency verdicts for the exact cells (ho1-ho3 under policy_v2, and forced-exact for P4/P1) are sensitive to this.
- Commitment: the held-out run is executed once and reported as measured, with the kernel's cumulative CPU seconds noted at start and end. No re-run to obtain better latencies; a repeat run, if wanted, is reported separately.
