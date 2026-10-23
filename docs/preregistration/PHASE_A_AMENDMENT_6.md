# Phase A, Amendment 6: policy_v2 against developer and prior-system baselines (H&M)

**Status:** written 2026-10-23, committed and tagged `phase-a-amendment-6-2026-10-23` **before any query it governs is run or any rule below is computed**. It amends no earlier file (`PHASE_A_ARMS_PROTOCOL.md` with its Amendments 1-2, `PHASE_A_HOLDOUT_PROTOCOL.md`, `PHASE_A_HOLDOUT2_PROTOCOL.md` stay as written). No paid or LLM call. Part A starts only after the author's explicit go-ahead, on a quiet machine, and before Amendment 7's runs (one after the other, never together).

## Purpose

Compare policy_v2 (exact if s < 0.1, else iterative-relaxed) with what a developer would do (Part A) and with published rules of prior systems (Part B), on the same cells and pass rule. **policy_v2 results are the existing ones and are not re-run:** in-sample `outputs/phase_a_arms`, held-out 1 `outputs/phase_a_holdout` (the pre-registered original run; the quiet rerun `outputs/phase_a_holdout_rerun` is shown alongside as sensitivity), held-out 2 `outputs/phase_a_holdout2`.

## Cells, settings, pass rule (unchanged)

- Cells: the **65 in-sample** cells (5 tables x 13 filters, vectors 0-19); **held-out 1** (25 cells, ho1-ho5, vectors 20-39); **held-out 2** (25 cells, h2a-h2e, vectors 40-59). The three sets are always reported separately.
- Harness and settings as `PHASE_A_ARMS_PROTOCOL.md` + Amendments 1-2: k = 10, `hnsw.ef_search` = 40, `jit = off`, default `hnsw.max_scan_tuples` (20000), `statement_timeout` 120000 ms, same SQL; exact top-10 reference per (table, filter, vector) on an `enable_indexscan = off` connection; recall@10 from one normal execution; one untimed warm-up then 5 timed `EXPLAIN (ANALYZE)`, median; per-table warm-up; order shuffled with `random.Random(20261023)`, seed and schedule hash in `run_meta.json`.
- **Pass:** mean recall@10 >= 0.90 over all 20 vectors **and** median (of per-vector medians) latency <= 500 ms. Any error or timeout = cell not passing, reported separately.

## Part A: live runs (quiet machine: no notebook kernel, embedding job, demo or other run; host CPU % and top-5 processes recorded at start, every 5 minutes and at end, `host_load.json`)

- **A6 planner_iterative:** `RESET` all `enable_*`; `hnsw.iterative_scan = relaxed_order`, other iterative settings at defaults. The plan chosen (scan node, index, node list) is recorded for every query and every timed execution; a plan that changes within the 5 timed runs is recorded and reported.
- **A7 fallback_iterative:** iterative-relaxed (Amendment-2 settings). If the normal execution returns fewer than 10 rows, the same vector is re-run as forced-exact and those rows are used. Latency = median of the iterative query + median of the exact query (both timed as above).
- **A8 fallback_hnsw:** forced-HNSW (iterative off, Amendment-2 settings); if fewer than 10 rows, re-run as forced-exact, as in A7.
- **Pre-flight** plain `EXPLAIN` of every table x filter: A7/A8 first query must be an Index Scan on `*embedding_idx`, their fallback query Seq Scan or Bitmap Heap Scan; any mismatch aborts before any measured query. A6 has no expectation (its plan is the result). Fallback counts (vectors and cells) are reported per arm.
- **A9 selectivity_estimate (no vector search):** for every filter on every table (65 + 25 + 25) and for the 50 frozen FinQA filters (ticker/year on `finqa_evidence_qwen3`): exact `COUNT(*)` and its latency (median of 5), the planner's estimated rows from plain `EXPLAIN` of the count query (no ANALYZE) and its latency (median of 5). Reported: estimate/exact ratio, absolute selectivity difference, and the number of cases where policy_v2's route (T = 0.1) would change if the estimate replaced the exact count.
- No retry: an error stops the run and is reported; a resume skips completed rows and is logged.

## Part B: offline on existing per-query measurements

Each rule picks a route per query from the filter's exact selectivity s; the outcome is the **measured** recall and latency of that route for that vector and cell (in-sample from `phase_a_arms`, held-out from the files above). All routes used (forced-exact, iterative-relaxed) were measured in every held-out cell; if any needed route is found missing, it is listed and only that route is run under Part A's settings.

- **B1 VBASE** (Zhang et al., OSDI 2023): exact if s < 0.18, else iterative-relaxed.
- **B2 Milvus as reported in NaviX** (Sehgal & Salihoglu, PVLDB 2025; second-hand): exact if s <= 0.05, else iterative-relaxed.
- **B3 Qdrant default planner:** exact if matching rows < 10000 / (dims/256) = **1,250 rows** for 2048-d H&M, else iterative-relaxed (Qdrant `config.yaml` `full_scan_threshold_kb = 10000`, "1Kb = 1 vector of size 256"). Qdrant uses an estimated count; we use the exact count.
- **B4 Gan & Wang** (arXiv:2602.17914, re-implemented from the paper, no code released): MLP with hidden layers (64, 32), ReLU, softmax output (two classes), Adam lr 1e-3, L2 penalty, batch 200, max 500 epochs, early stopping, seed 20261023 (implemented with scikit-learn `MLPClassifier`; L2 alpha 1e-4, validation fraction 0.1 and patience 10 epochs are the library defaults, fixed here because they are not given by the author's specification). Classes: exact vs iterative-relaxed. Label per training query = the plan with the higher recall@10 / latency (ms); a tie goes to exact. **Feature: selectivity only** (z-scored on the training set); dimensionality and corpus size are constant here, so they carry no information. **Trained only on the 1,300 in-sample queries** (65 cells x 20 vectors); evaluated on all three sets (in-sample is in-sample fit, not evidence).
- **B4b:** the same model with SLA labels: the faster of the two plans among those with recall@10 >= 0.9 on that query, else exact.
- If a training label set has only one class, the model is not fitted and this is reported (no substitute).
- **B1-B4b are re-implementations of published rules in this harness, not the original systems**; the report says so.

## Predictions (author's, written before running)

- A6 fails latency where the planner still chooses exact at s >= 0.204 (about 0.204-0.26), so it passes clearly fewer than 65 in-sample cells.
- A7 fails on hm_clothes_100 at lo3 and lo4 (10 rows returned with recall below 0.9, so no fallback), and passes lo1/lo2 by falling back.
- A8 fails where forced-HNSW returns 10 rows with low recall (hm_clothes_100 and hm_clothes_75 at s >= 0.30).
- A9: estimates are close for single equality filters and less accurate for IN-lists; route changes only near s = 0.1.
- B1 and B2 pass about as many cells as policy_v2; B3 fails hm_clothes_100 at s = 0.0478; B4 fails low-selectivity cells on hm_clothes_100 because recall/time favours fast low-recall plans; B4b behaves like a threshold rule.

## Report and outputs

Pass counts per arm/rule (in-sample, held-out 1, held-out 2) next to policy_v2; failing cells and why (recall or latency); A6 plan choices per cell; how often each fallback triggered; A9 results; B4/B4b learned decision boundary. Outputs in a new folder `outputs/phase_a_amendment6_2026-10-23/`, added to `outputs/data_checksums.json`; results committed and tagged. **Limits:** Part A runs on a quiet machine, the policy_v2 held-out 1 results did not (its latency verdicts are not strictly comparable; the quiet rerun is shown as sensitivity); H&M only, k = 10, ef_search 40, one server configuration. Run-time estimate [I]: about 2-5 h for Part A (2,300 table x filter x vector combinations; dominated by A6 where it picks exact at s >= 0.2), refined from the first table.
