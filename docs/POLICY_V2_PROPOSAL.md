# policy_v2 — proposal (document only, nothing implemented)

Date: 2026-10-10. Status: **proposal**. No code was changed for this document; `src/phase_b_router/policy.py`, `router.py` and `test_router.py` are untouched.
**[V]** = seen in a file or output (cited). **[I]** = my inference. Evidence comes from `reports/arms_results_2026-10-10.md` ("arms report"), `reports/policy_evaluation_2026-10-10.md` ("evaluation report"), `outputs/phase_a_arms/analysis/cell_summary.csv` ("cells") and `reports/policy_audit_2026-10-10.md` ("audit"). "Cell" = one (table, filter) pair, with mean recall@10 over 20 vectors and the median of the 20 per-vector median latencies.

## 1. Proposal in one paragraph

Route by estimated selectivity `s` only: **exact** (`forced-exact`, today's `pre-filter`) when `s < T`, **iterative scan** (`iterative-relaxed`) when `s >= T`, and **never** the plain forced-HNSW `post-filter` arm. On the H&M data a single `T` in (0.0478, 0.2038] makes every one of the 65 measured cells meet both SLAs (recall >= 0.90 and median latency <= 500 ms) in-sample; **provisionally T = 0.1**. The correlation tier is not used, so nothing about correlation has to be estimated on FinQA.

## 2. Evidence for each choice

**2.1 Never use forced-HNSW (the Phase D `post-filter` arm).** [V]
- Mean recall >= 0.90 in only **11 of 65 cells**, all at selectivity >= 0.2986 (arms report (i); evaluation report P5: 11/65, 54 recall failures). It is below 0.90 in every cell at or below 0.2599, and on hm_clothes_100 in all 13 cells (e.g. idx1/idx2/idx3 = 0.715 / 0.795 / 0.695, arms report (c) H1).
- On FinQA the same plan under-fills: 4, 0 and 6 rows of `LIMIT 6` on the three probe queries (`reports/arms_prep_2026-10-10.md` Step 2).
- The policy that exists today sends recall danger zones to this arm (audit Task 1, `policy.py:17`). Both existing threshold files, evaluated per table on the 65 cells, pass 29 (v1) and 27 (v2) cells; where they return `post-filter` that arm passed 2 of 7 (v1) and 0 of 7 (v2) times (evaluation report sections 1 and 5).

**2.2 Exact below the threshold.** [V]
- forced-exact has recall 1.000 in every cell. It passes the 500 ms SLA in all 25 cells at selectivity <= 0.1061 (largest cell median 316.5 ms; lo5 on hm_clothes_100 = 262 ms) and in all of lo1-lo2 (0.33-2.5 ms).
- Iterative scan fails at the lowest selectivities: lo1 (13 rows) recall 0.18-0.26 on all five tables, lo2 (89 rows) 0.675-0.865 on four tables (arms report (c) H2/H6). Exact is the only candidate there (route map, arms report (d)).

**2.3 Iterative scan from the threshold up.** [V]
- iterative-relaxed passes all **40 of 40** cells at selectivity >= 0.2038 (recall >= 0.9 in all; latency 1-2 ms; evaluation report region table, P6), while forced-exact fails 38 of those 40 on latency (P4 region table: 2/40 pass; ctl is above 500 ms on all five tables, 547-1,080 ms).
- planner-default is exact up to 0.2599 and HNSW from 0.2986 on every table (900/900 plan choices equal to Phase A v2, arms report (e)), so it inherits the exact plan's latency failures below that point and the HNSW plan's recall failures above it: 37 of 65 pass (evaluation report P3).

**2.4 The threshold.** [V in-sample; the choice is [I]]
- P8 (exact if `s < T`, else iterative-relaxed), evaluation report section 1: T = 0.001 / 0.005 / 0.01 pass 63 of 65; T = 0.02 passes 64; **T = 0.05 and T = 0.1 pass 65 of 65**. Every failure at T <= 0.02 is on hm_clothes_100: lo3 (0.0105, iterative recall 0.82) and lo4 (0.0478, 0.42).
- So the cells bound T from below by 0.0478 (hm_clothes_100/lo4) and from above by 0.2038 (forced-exact fails 500 ms at ctl on all five tables). The supported interval is **(0.0478, 0.2038]**. Nothing between 0.0478 and 0.1061 or between 0.1061 and 0.2038 was sampled.
- Proposed value **T = 0.1** [I]: it sits near the geometric middle of the interval (about 0.099) and is one of the two tested values that pass 65/65. Weak spots to keep in mind: hm_clothes_100 at 0.1061 passes iterative-relaxed with recall 0.93 (minimum vector 0.70, cells), where exact also passes (262 ms), so a somewhat higher T would put that case on the safer arm; and forced-exact at 0.1 is already 250-320 ms. Which end is safer is not decidable from 13 filters.

## 3. How selectivity would be estimated at query time

- **What exists:** the runner counts matching rows exactly per query (`SELECT COUNT(*) ... WHERE metadata->>'ticker'=%s AND metadata->>'year'=%s` divided by the table count, `src/phase_d_validation/local_ollama_runner.py:71-78`). The H&M selectivities in the arms run are also exact counts (`outputs/phase_a_arms/filters.json`). [V]
- **Proposal:** keep the exact count as the reference estimator for small corpora (FinQA: 35,862 rows; the count query is the same kind of scan as the exact retrieval, which took 18-21 ms warm). For larger tables use a cheaper estimate, in this order of preference [I]: (a) the planner row estimate of the filter alone (`EXPLAIN (FORMAT JSON)` `Plan Rows` / `pg_class.reltuples`), which needs fresh `ANALYZE` statistics and, for JSONB expressions such as `metadata->>'ticker'`, an expression index or `CREATE STATISTICS`; (b) `pg_stats.most_common_vals/freqs` for categorical columns, summing frequencies for IN lists.
- **Not validated:** I did not measure how close any cheap estimate is to the exact count. Before adoption, compare it to the exact counts for the 13 H&M filters and the 1,147 FinQA census selectivities (`outputs/finqa_selectivity_census/`).
- **Failure handling** [I]: raise on `None`, NaN, negative or > 1 (today NaN returns `pre-filter` silently, audit Task 1c), and log the estimate and the estimator used with every routed query.
- **Scale caveat** [I, untested]: T was derived on 105,100-row tables. The failure mechanisms depend on the number of matching rows (iterative scan fails at 13-5,021 matching rows on the cells above; exact latency grows with matching rows, 11,150 rows at 0.106 cost 253-317 ms). A selectivity threshold may not transfer to a corpus of another size; expressing T as a matched-row count is a candidate but nothing here tests it.

## 4. The most-correlated table (hm_clothes_100)

[V] iterative-relaxed fails there at lo3 (recall 0.82, min vector 0.0) and lo4 (0.42, min 0.0), while passing on the other four tables at both filters (cells; arms report (c) H2) and passing at lo5 (0.93) and from 0.2038 up (ctl 0.96). forced-exact passes all of lo1-lo5 there (0.33, 2.5, 24.7, 113, 262 ms).

Options:
- **A (proposed): no per-table rule.** A single `T` above 0.0478 already covers hm_clothes_100 (P8 at T = 0.05 and 0.1 pass its 13 cells, evaluation report by-table counts). It needs no correlation estimate, which is not available on FinQA anyway (the tier there is a hand-set label, audit Task 1b). Status: in-sample.
- **B (not adopted): make iterative scan work on hm_clothes_100 with larger limits.** The exploratory diagnostic (evaluation report section 4) found that raising both `hnsw.max_scan_tuples` to 100000 and `hnsw.scan_mem_multiplier` to 4 gives recall 0.925 (lo3) and 0.940 (lo4) for iterative-relaxed, with `ef_search` irrelevant (0.925/0.940 at both 40 and 200) and either limit alone insufficient. Latency was not measured and per-vector minimum recall stays low (0.10 and 0.60). **Exploratory, 20 vectors, one table, two filters.** Do not adopt without a timed run.
- **C (optional safeguard, untested):** if the iterative route returns fewer than `k` rows, rerun exact. This would catch the under-fill cases (minimum 0-6 rows in the failing cells: 0 at lo1; 5-7 at lo2 on the three tables that under-fill (10 on the other two); 4-6 on hm_clothes_100 lo3/lo4) but **not** the low-recall-with-10-rows cases (hm_clothes_100/lo4: median rows 10, recall 0.42), so it cannot replace `T`. No data here evaluates it.

## 5. What is tested, in-sample, exploratory, or untested

| Claim | Status |
|---|---|
| Per-arm recall/latency in 65 cells; forced-hnsw fails recall broadly; iterative-relaxed fails at lo1-lo2 and hm_clothes_100 lo3-lo4; forced-exact fast <= 0.106, slow >= 0.204 | **Measured** (arms report; 20 vectors x 65 cells, k=10, ef_search=40, one machine). Not independent trials: same vectors, same rows. |
| Planner-default reproduces Phase A plan choices | **Measured**, 900/900 |
| Exact reference is correct for hm_clothes_100 lo3/lo4 | **Checked**, 40/40 vs forced Seq Scan, no ties (evaluation report section 4) |
| T in (0.0478, 0.2038] gives 65/65; T = 0.1 | **In-sample** (fitted on the same 65 cells; P8, P7) |
| Iterative failure is a scan-limit effect, `ef_search` irrelevant | **Exploratory** (hm_clothes_100 lo3/lo4 only) |
| Selectivity estimator accuracy; transfer to other table sizes, other k / ef_search, other filter types (ranges, multi-column), concurrent load | **Untested** |
| FinQA behaviour | **Untested** for the proposed rule. All 1,147 FinQA queries have selectivity 0.0002-0.0297 (census `summary.json`, bands B3 and B4 empty), so the rule would route every one of them to exact. |

Suggested checks before adoption (not run) [I]: (1) held-out data: new filters at about 0.02, 0.03, 0.07, 0.15 and 0.18, and 20 new vectors (lines 21-40 of `tests.jsonl`), re-evaluate P8; (2) a timed run of option B; (3) the estimator comparison in section 3.

## 6. What would change if adopted

- **`src/phase_b_router/policy.py`** (18 lines today): replace the danger-interval loop (`policy.py:14-17`) with a single threshold comparison; keep returning two route names, but `"post-filter"` is replaced by an iterative route (`"iterative-scan"` already exists as a node, `router.py:157-160, 177`, and as a runner branch, `local_ollama_runner.py:83-92`); validate the input (None, NaN, < 0, > 1 raise); `correlation_level` becomes unused (keep the argument or drop it deliberately).
- **Thresholds file and generator:** `threshold_detector.py` emits recall/latency zones; v2 needs a single `route_threshold` (and the estimator name, the table size and the SLA values used), generated from the arm-comparison data or set by hand. `outputs/thresholds_v2.json` is currently `{}` and would break any run that still passes it.
- **Route execution:** the iterative branches set only `enable_indexscan=on`, `enable_seqscan=off` and `hnsw.iterative_scan='relaxed_order'` (`router.py:64-76`, `local_ollama_runner.py:83-92`). The H&M arm needed `enable_sort=off` and `enable_bitmapscan=off` to be guaranteed HNSW at low selectivity (Amendment 2). With policy_v2 the iterative route is used only at `s >= T`; on H&M the plan check made before Amendment 2 showed an HNSW plan under the frozen settings from lo4 (0.0478) upward, but on FinQA's JSONB filter (no B-tree on `metadata`) the plan shape has to be re-checked with a pre-flight. `hnsw.max_scan_tuples` and `scan_mem_multiplier` stay at their defaults unless option B is validated.
- **`src/phase_b_router/test_router.py`:** the tests encode mock thresholds `[(0.4705, 1.0)]` and a latency zone at 0.2037 that do not exist in the real file (audit Task 1e). Replace them with: below `T` returns exact; at and above `T` returns iterative; the function never returns `post-filter`; boundary `s == T`; NaN / None / negative / > 1 raise; unknown threshold file raises; one test that loads the real thresholds file. The Naive (LLM) router may still choose `post-filter` as the baseline arm (`router.py:186-217`), so that execution branch stays.
- **Phase D runner** (`local_ollama_runner.py`): the call at `:201` and the `--correlation-level` / `--thresholds` arguments change; record the route, `T`, the estimate and the estimator in each result row and `run_meta`; re-freeze as a new protocol with a `DEVIATION_LOG.md` entry. On FinQA the new rule would send all 1,147 queries to exact, i.e. it would give the same routes as the frozen Decision Matrix (all `pre-filter`); the benefit on FinQA is avoiding unsafe routing, not a change in the measured Phase D outcome, and the iterative route would not be exercised there.
- **Docs:** `PHASE_A_ARMS_PROTOCOL.md` and the reports stay as the record; a new protocol would cover any held-out validation.

## 7. Decisions needed from you

1. Is "exact / iterative / never forced-HNSW" with a single selectivity threshold the structure you want, or do you want to keep a per-tier table?
2. T: 0.1 as proposed, or run the held-out filters first and choose from those?
3. hm_clothes_100: accept option A, or spend a timed run on option B?
4. Selectivity estimator for FinQA: keep the exact count (cheap at 35,862 rows), or validate a planner/statistics estimate?
