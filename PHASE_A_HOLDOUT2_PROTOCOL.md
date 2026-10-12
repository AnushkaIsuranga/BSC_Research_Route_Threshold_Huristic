# policy_v2 second held-out protocol (selectivity 0.20-0.47)

**Status: DRAFT for user review. Not frozen, not tagged, not run.** No query has been run on the filters or vectors below. The only things done with them: row counts per filter (selectivity), a SHA-256 of the 20 vector lines, and evaluating the original v1 policy's route for each table x filter from the selectivity alone (a function of selectivity, no outcome data). After the user approves, this file is committed and tagged (suggested tag `phase-a-holdout2-protocol-frozen-<date>`) before the harness is written, self-tested and run.

## Purpose

The first held-out test (`PHASE_A_HOLDOUT_PROTOCOL.md`) used filters with selectivity 0.020-0.180, below the region where v1 found its recall and latency danger zones (0.329-0.4705 on hm_clothes_100; gap region 0.20-0.47). policy_v2 (`exact` if s < T = 0.1, else `iterative-relaxed`) has therefore not been tested out of sample at s >= 0.2, where it routes everything to iterative-relaxed. This protocol tests that region on new filters and new vectors. `T = 0.1` is unchanged and will not be re-tuned on these data.

## Frozen rule under test and comparison policies

Same definitions as the first held-out protocol:

- **policy_v2:** forced-exact if s < 0.1 else iterative-relaxed. On every filter here (s >= 0.23) it selects iterative-relaxed.
- **P1:** the original v1 matrix: unmodified `src/phase_b_router/policy.py` with `outputs/phase_a_v1/thresholds.json`, table name = tier; `pre-filter` -> forced-exact, `post-filter` -> forced-hnsw.
- **P4:** always forced-exact. **P5:** always forced-hnsw. **P6:** always iterative-relaxed.

## New filters (not used in the in-sample or the first held-out set)

None of these (column, value) pairs appears in `outputs/phase_a_arms/filters.json` (13 filters) or `outputs/phase_a_holdout/filters.json` (ho1-ho5). Every single value in the range 0.20-0.47 was already used (Jersey Fancy 0.204, Black 0.214, Baby/Children 0.329, Ladieswear 0.376, Solid 0.4705; no other single (column, value) lies in 0.19-0.48), so each new filter is an `IN` list of values none of which was used before. Selectivities are exact counts; identical in all five tables (checked: the same row count in hm_clothes_0, _25, _50, _75, _100); denominator 105,100.

| id | filter | matched rows (each table) | selectivity | v1 route per table (0 / 25 / 50 / 75 / 100) |
|---|---|---:|---:|---|
| h2a | `graphical_appearance_name IN ('Melange','Stripe','Denim','Front print','Placement print','Check')` | 24,213 | 0.23038 | pre / pre / pre / pre / pre |
| h2b | `garment_group_name IN ('Accessories','Jersey Basic','Knitwear')` | 26,932 | 0.25625 | pre / pre / pre / pre / pre |
| h2c | `perceived_colour_master_name IN ('White','Pink','Beige','Green','Khaki green')` | 34,284 | 0.32620 | post / pre / post / post / post |
| h2d | `product_type_name IN ('Dress','Sweater','T-shirt','Top','Blouse','Jacket')` | 39,590 | 0.37669 | pre / pre / pre / pre / post |
| h2e | `product_type_name IN ('Dress','Sweater','T-shirt','Top','Blouse','Jacket','Shorts','Shirt')` | 46,919 | 0.44642 | pre / pre / pre / pre / post |

(`pre` = P1 chooses forced-exact, `post` = forced-hnsw.) Disclosures about the choice, made before any run:

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
- Order shuffled with a **new seed** recorded in `run_meta.json` (to be fixed at approval, not equal to 20261012 or 20261014); pre-flight plain-EXPLAIN plan check of all 75 table x filter x arm combinations (forced-exact must be Seq/Bitmap Heap Scan, the other two an Index Scan on `*embedding_idx`); resumable writer; refuses to start with uncommitted used files.
- Outputs `outputs/phase_a_holdout2/` (new folder); expected rows 25 x 20 x 3 = **1,500**.
- Implementation: a thin wrapper around `holdout_run.py` (as `holdout_rerun.py` did) that sets seed, output folder, filters and vector range, and records host CPU load at the start of each table. A self-test (`--selftest`-style replay of a main-run filter) is run and compared to the main run before the freeze run, as before.
- Quiet-machine conditions: Ollama and Jupyter stopped, top-5 CPU processes and total CPU load recorded at start, at each table start and at end; if the machine is not quiet the run is not started.

## Pass criterion and cell definition (unchanged SLAs)

A cell (table, filter) passes under a policy if the arm that policy selects there has **mean recall@10 >= 0.90 over the valid vectors AND median latency <= 500 ms** (median of per-vector medians). A cell with any invalid vector (error or timeout) is reported separately and counts as not passing.

## Pre-registered hypotheses

- **H10:** policy_v2 (T = 0.1) passes both SLAs in all 25 cells (i.e. iterative-relaxed passes in every cell).
- **H11:** for each of the five filters, P1 (the v1 matrix) fails at least one of the five table cells.
- **H12:** P4 (always forced-exact) fails the latency SLA (median > 500 ms) in every cell with s >= 0.2, i.e. in all 25 cells.

**Reporting commitments.** Hypotheses are reported as held or failed exactly as defined; failing cells are listed with recall, latency and the arm used. No T or hypothesis is changed after seeing data. A repeat run, if wanted, is reported separately.

## Known risks to the hypotheses (stated before any run, from existing data; the user may amend the hypotheses before the freeze)

- **H12 at the low end.** In the quiet rerun of the first held-out test, forced-exact median latency scaled roughly linearly with selectivity (about 37, 53, 123, 282 and 352 ms at 0.020, 0.030, 0.071, 0.144 and 0.180; `outputs/phase_a_holdout_rerun/analysis/cell_summary.csv`, means over tables). Extrapolated linearly (about 1.9-2.0 ms per 0.001 of selectivity), forced-exact reaches 500 ms near s = 0.25-0.27, so h2a (0.230) and possibly h2b (0.256) may **pass** the latency SLA for P4 on a quiet machine, which would make H12 fail. The in-sample main run, under heavy CPU load, had forced-exact at 489-6,567 ms for s >= 0.2. H12 is therefore sensitive to machine load as well as to selectivity. Option for the user: keep H12 as written (a conservative test) or restate it for s >= 0.3.
- **H11 for h2a and h2b.** P1 routes every table of h2a and h2b to forced-exact, so P1 can fail a cell there only by latency > 500 ms, which is the same borderline as above. H11 may fail on h2a/h2b on a quiet machine. For h2c-h2e, P1 uses forced-hnsw in some tables (inside its recall danger zone), where failure is expected from the v1 findings, not assumed.
- **H10.** iterative-relaxed passed all 13 in-sample filters (65/65 cells) and 25/25 held-out cells, but with `max_scan_tuples` = 20000 and very high selectivity its recall at 0.38-0.45 on the most correlated table (hm_clothes_100) is the least tested region.

## Size and run time

500 (table, filter, vector) combinations; per combination 1 reference + 3 arms x 7 = 22 executions, i.e. 11,000 executions (500 reference, 1,500 recall, 1,500 warm-up, 7,500 timed). Dominated by the exact arm and the reference (8 exact executions per combination). Estimate [I]: the quiet rerun took 927 s for 500 combinations with a mean forced-exact median of about 170 ms, i.e. about 1.85 s per combination, of which about 1.35 s is the 8 exact executions and about 0.5 s other overhead. At the planned selectivities (0.230, 0.256, 0.326, 0.377, 0.446; mean 0.327) forced-exact is extrapolated at about 0.45-0.9 s (mean about 0.64 s), so about 5.6 s per combination x 500 = about 2,800 s, **about 45-60 minutes on a quiet machine**. Under the heavy load of the original run the exact arm was up to 3x slower, giving up to about 2.5 hours. Disk: results about 2 MB.

## Limits

H&M only, k = 10, `ef_search` = 40, default `max_scan_tuples`, one machine and configuration, categorical `IN`-list filters, 105,100-row tables, five filters (two share a column), 20 vectors per cell. Tests transfer to new filters and vectors on the same data; not other table sizes or FinQA.
