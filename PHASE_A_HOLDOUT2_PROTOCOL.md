# policy_v2 second held-out protocol (selectivity 0.20-0.47)

**Status: FROZEN 2026-10-12 by the tag `phase-a-holdout2-frozen-2026-10-12`, before any query on these filters or vectors.** The only things done with them: row counts per filter (selectivity), a SHA-256 of the 20 vector lines, and evaluating the original v1 policy's route for each table x filter from the selectivity alone (`policy.py` + `outputs/phase_a_v1/thresholds.json`, no queries; the routes are in the table below). The harness (`src/phase_a_sweep/holdout2_run.py`, a wrapper that reuses `holdout_run.py` unchanged) and the analysis (`src/phase_c_analysis/holdout2_analysis.py`) are committed with the tag.

## Purpose

The first held-out test (`PHASE_A_HOLDOUT_PROTOCOL.md`) used filters with selectivity 0.020-0.180, below the region where v1 found its recall and latency danger zones (0.329-0.4705 on hm_clothes_100; gap region 0.20-0.47). policy_v2 (`exact` if s < T = 0.1, else `iterative-relaxed`) has therefore not been tested out of sample at s >= 0.2, where it routes everything to iterative-relaxed. This protocol tests that region on new filters and new vectors. `T = 0.1` is unchanged and will not be re-tuned on these data.

## Frozen rule under test and comparison policies

Same definitions as the first held-out protocol:

- **policy_v2:** forced-exact if s < 0.1 else iterative-relaxed. On every filter here (s >= 0.23) it selects iterative-relaxed.
- **P1:** the original v1 matrix: unmodified `src/phase_b_router/policy.py` with `outputs/phase_a_v1/thresholds.json`, table name = tier; `pre-filter` -> forced-exact, `post-filter` -> forced-hnsw.
- **P4:** always forced-exact. **P5:** always forced-hnsw. **P6:** always iterative-relaxed.

## New filters (not used in the in-sample or the first held-out set)

None of these (column, value) pairs appears in `outputs/phase_a_arms/filters.json` (13 filters) or `outputs/phase_a_holdout/filters.json` (ho1-ho5). Every single value in the range 0.20-0.47 was already used (Jersey Fancy 0.204, Black 0.214, Baby/Children 0.329, Ladieswear 0.376, Solid 0.4705; no other single (column, value) lies in 0.19-0.48), so each new filter is an `IN` list of values none of which was used before. Selectivities are exact counts; identical in all five tables (checked: the same row count in hm_clothes_0, _25, _50, _75, _100); denominator 105,100.

| id | filter | matched rows (each table) | selectivity | P1 (v1 matrix) route per table (0 / 25 / 50 / 75 / 100), computed | status |
|---|---|---:|---:|---|---|
| h2a | `graphical_appearance_name IN ('Melange','Stripe','Denim','Front print','Placement print','Check')` | 24,213 | 0.23038 | pre / pre / pre / pre / pre | exploratory / borderline |
| h2b | `garment_group_name IN ('Accessories','Jersey Basic','Knitwear')` | 26,932 | 0.25625 | pre / pre / pre / pre / pre | exploratory / borderline |
| h2c | `perceived_colour_master_name IN ('White','Pink','Beige','Green','Khaki green')` | 34,284 | 0.32620 | post / pre / post / post / post | confirmatory |
| h2d | `product_type_name IN ('Dress','Sweater','T-shirt','Top','Blouse','Jacket')` | 39,590 | 0.37669 | pre / pre / pre / pre / post | confirmatory |
| h2e | `product_type_name IN ('Dress','Sweater','T-shirt','Top','Blouse','Jacket','Shorts','Shirt')` | 46,919 | 0.44642 | pre / pre / pre / pre / post | confirmatory |

(`pre` = P1 chooses forced-exact, `post` = forced-hnsw. "Status": h2a and h2b lie where the latency prediction for forced-exact is borderline, see H11/H12; their cells are reported and labelled exploratory; they are still part of H10.) Disclosures about the choice, made before any run:

- Filters were chosen by selectivity and unused status only. I have not looked at any recall or latency for them.
- All five are `IN` lists; none is a plain equality filter, because no unused single value exists in the range.
- h2d is a subset of h2e (same column, six of the same eight values); h2a, h2b, h2c and h2d/h2e use four different columns. Their cells are therefore not independent.
- Target spread: 0.23, 0.26, 0.33, 0.38, 0.45. The first two are below idx1 (0.329), the zone where v1's recall danger begins on hm_clothes_100; h2c lies at its lower edge; h2d and h2e lie inside the danger zone [0.329, 0.4705].
- Filters are written to `outputs/phase_a_holdout2/filters.json` by the harness's `--build-filters` after approval, and the stored selectivities must equal the table above.

## Vectors

0-based line indices 40-59 of `ann-filtering-benchmark-datasets/data/tests.jsonl` (lines 41-60; the file has 10,000 lines). Checked on every result file in `outputs/`: no run has used vector indices above 39 (main run 0-19, first held-out 20-39, v1 sweeps 0-4). SHA-256 of the 20 lines (each with its newline): `82865edb747d5a3cec453678dd0d69692456d3e541a4dd9b60b331f3627a53f8`.

## Tables, arms, measurement (unchanged from the first held-out protocol)

- Tables hm_clothes_0, _25, _50, _75, _100; 5 tables x 5 filters = **25 cells**, 20 vectors each.
- Arms forced-exact, forced-hnsw, iterative-relaxed with the Amendment-2 settings of `arm_comparison.py` (`ARMS`, `apply_arm`), k = 10, `hnsw.ef_search` = 40, default `hnsw.max_scan_tuples` (20000), `jit = off`, `statement_timeout` = 120000 ms.
- Per (table, filter, vector, arm): exact top-10 reference cached per (table, filter, vector); recall@10 from one normal execution; one untimed warm-up; 5 timed `EXPLAIN ANALYZE`, median; rows returned, scan node, index and buffers recorded; per-table warm-up before timing.
- Order shuffled with the **new seed 20261017** (not 20261012 or 20261014), recorded in `run_meta.json`; pre-flight plain-EXPLAIN plan check of all 75 table x filter x arm combinations (forced-exact must be Seq/Bitmap Heap Scan, the other two an Index Scan on `*embedding_idx`); resumable writer; refuses to start with uncommitted used files.
- Outputs `outputs/phase_a_holdout2/` (new folder); expected rows 25 x 20 x 3 = **1,500**.
- Implementation: `src/phase_a_sweep/holdout2_run.py`, a thin wrapper around `holdout_run.py` (as `holdout_rerun.py` did) that sets seed 20261017, output folder `outputs/phase_a_holdout2/`, the five filters above (`--build-filters` writes `filters.json`; stored selectivities must equal the table) and vectors 40-59, and records host CPU load at the start of each table. The existing `--selftest` (replay of a main-run filter, vectors 0-1, no held-out data) is run first and compared to the main run.
- Quiet-machine conditions: Ollama and Jupyter stopped, top-5 CPU processes and total CPU load recorded at start, at each table start and at end; if the machine is not quiet the run is not started.

## Pass criterion and cell definition (unchanged SLAs)

A cell (table, filter) passes under a policy if the arm that policy selects there has **mean recall@10 >= 0.90 over the valid vectors AND median latency <= 500 ms** (median of per-vector medians). A cell with any invalid vector (error or timeout) is reported separately and counts as not passing.

## Pre-registered hypotheses

Latency prediction used below [I, extrapolation, not a measurement on these filters]: in the quiet rerun of the first held-out test the forced-exact median latency was about 1.95 ms per 0.001 of selectivity (37, 53, 123, 282, 352 ms at 0.020, 0.030, 0.071, 0.144, 0.180; `outputs/phase_a_holdout_rerun/analysis/cell_summary.csv`, means over tables). Linear extrapolation gives forced-exact medians of about 450 ms (h2a, 0.230), 500 (h2b, 0.256), 635 (h2c, 0.326), 735 (h2d, 0.377), 870 (h2e, 0.446). The SLA is 500 ms, so h2a and h2b are borderline by prediction and h2c-h2e are predicted to fail by margins of 130-370 ms. The in-sample run, under heavy CPU load, had forced-exact at 489-6,567 ms for s >= 0.2.

- **H10 (primary):** policy_v2 (T = 0.1) passes both SLAs in all 25 cells (iterative-relaxed has mean recall@10 >= 0.90 over the valid vectors and median latency <= 500 ms in every table x filter).
- **H11 (per filter; secondary):** P1 (the v1 matrix) fails at least one of the five cells of that filter. Computed P1 routes and the expected failure mode:
  - h2a, h2b: P1 routes all five tables to forced-exact; the only possible failure is latency (predicted about 450 / 500 ms, borderline). **Exploratory:** no confident prediction.
  - h2c (0.3262): forced-hnsw on hm_clothes_0, _50, _75 and _100 (inside or within the 0.0141 margin of v1's recall danger zone [0.3290, 0.4705]) -> expected failure mode **recall < 0.90**; forced-exact on hm_clothes_25 -> expected failure mode **latency about 635 ms**.
  - h2d (0.3767), h2e (0.4464): forced-exact on hm_clothes_0, _25, _50, _75 -> expected failure mode **latency about 735 / 870 ms**; forced-hnsw on hm_clothes_100 (inside the danger zone) -> expected failure mode **recall < 0.90**.
  H11 is reported separately for each of the five filters (held / failed), with the failing cells and their failure mode. Whether a P1 failure is by recall or by latency is reported, not assumed.
- **H12:** P4 (always forced-exact) fails the latency SLA (median > 500 ms) in every cell with s >= 0.30, i.e. in all 15 cells of h2c, h2d, h2e. The 10 cells of h2a (0.230) and h2b (0.256) are labelled exploratory/borderline: their P4 latency is reported with no pass/fail claim attached to H12.

**Reporting commitments.** Hypotheses are reported as held or failed exactly as defined, failing cells listed with recall, latency and the arm used, and the per-policy pass counts (P1, P4, P5, P6, policy_v2) over the 25 cells (and over the 15 confirmatory cells) are reported. No T, filter, vector or hypothesis is changed after seeing data. Ollama and Jupyter are stopped for the run and the top-5 CPU processes are recorded first; a repeat run, if wanted, is reported separately.

## Size and run time

500 (table, filter, vector) combinations; per combination 1 reference + 3 arms x 7 = 22 executions, i.e. 11,000 executions (500 reference, 1,500 recall, 1,500 warm-up, 7,500 timed). Dominated by the exact arm and the reference (8 exact executions per combination). Estimate [I]: the quiet rerun took 927 s for 500 combinations with a mean forced-exact median of about 170 ms, i.e. about 1.85 s per combination, of which about 1.35 s is the 8 exact executions and about 0.5 s other overhead. At the planned selectivities (0.230, 0.256, 0.326, 0.377, 0.446; mean 0.327) forced-exact is extrapolated at about 0.45-0.9 s (mean about 0.64 s), so about 5.6 s per combination x 500 = about 2,800 s, **about 45-60 minutes on a quiet machine**. Under the heavy load of the original run the exact arm was up to 3x slower, giving up to about 2.5 hours. Disk: results about 2 MB.

## Limits

H&M only, k = 10, `ef_search` = 40, default `max_scan_tuples`, one machine and configuration, categorical `IN`-list filters, 105,100-row tables, five filters (two share a column), 20 vectors per cell. Tests transfer to new filters and vectors on the same data; not other table sizes or FinQA.
