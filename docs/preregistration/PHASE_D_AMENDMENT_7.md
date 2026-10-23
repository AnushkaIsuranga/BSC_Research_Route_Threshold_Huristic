# Phase D, Amendment 7, Step 1: which FinQA routes would the baselines choose? (no LLM)

**Status:** written 2026-10-23, committed and tagged `phase-d-amendment-7-2026-10-23` **before anything below is computed or run**. It amends no earlier file. **Step 1 only:** database queries and offline computation, no LLM, no embedding or other API call, no cost. Step 2 (paid answer runs) is not part of this amendment and needs its own amendment. Step 1 runs only after the author's go-ahead, on a quiet machine, after Amendment 6's Part A (never at the same time), because the training runs record latency.

## Settings (as Amendments 1-3)

Table `finqa_evidence_qwen3` (35,862 rows, 1024-d, HNSW m 16 / ef_construction 64, L2), filter `metadata->>'ticker' = ... AND metadata->>'year' = ...`, k = **15 distinct passages** (`router.retrieve(distinct=True)`), (distance, id) tie-break, `hnsw.ef_search` = 40, server defaults otherwise. Selectivity s = exact count of matching rows on `finqa_evidence` / total rows (as Amendment 1). Query vectors from the cached files only: frozen 50 `outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json`, 1,075 confirmation questions `outputs/embedding_build_2026-10-13/query_embeddings_qwen3_confirmation_1075.json` (SHA-256 checked at load, as recorded in Amendments 1 and 4).

## Routes computed for each of the frozen 50 questions

- **policy_v2:** exact if s < 0.1, else iterative-relaxed.
- **B1** exact if s < 0.18; **B2** exact if s <= 0.05; **B3** exact if matching rows < 2,500 (= 10000 / (1024/256)); else iterative-relaxed. (Sources as in `docs/preregistration/PHASE_A_AMENDMENT_6.md`.)
- **A6 planner_iterative:** plain `EXPLAIN (FORMAT JSON)` (no ANALYZE) with all `enable_*` reset and `hnsw.iterative_scan = relaxed_order`, of the index-route SQL that `retrieve()` issues (`ORDER BY embedding <-> v LIMIT 150`; the exact route's `, id` tie-break would by itself make the planner abandon HNSW). Route = iterative-relaxed if the scan node is an Index Scan on the HNSW index, else exact; the plan is recorded.
- **A8 fallback_hnsw:** forced-HNSW (`retrieve(route="post-filter", distinct=True)`); if it returns fewer than 15 distinct rows, exact. The number of fallbacks is recorded; route = forced-hnsw without fallback, exact with fallback.
- **B4 / B4b** (Gan & Wang re-implementation, model and settings exactly as Amendment 6 B4 / B4b, seed 20261023, feature selectivity only) **trained ONLY on retrieval-only runs of the 1,075 confirmation (non-frozen) questions**: for each, exact and iterative-relaxed retrieval; recall@15 = share of the exact distinct top-15 passages (by passage text, as Amendment 1's passage-level hit) returned by the route; latency = median of 5 timed `EXPLAIN (ANALYZE)` executions of the route's SQL after one untimed warm-up. B4 label: higher recall@15 / latency (tie: exact); B4b label: faster plan with recall@15 >= 0.9, else exact. If a label set has one class only, no model is fitted and this is reported.
- No retry; an error stops the run and is reported.

## Report

Per rule: the number of the 50 routes that **differ from policy_v2** (a route differs if its retrieval method differs: exact vs iterative-relaxed vs forced-hnsw). **Rules with 0 differences will not be run with the LLM in Step 2: they are identical to policy_v2 by construction.** Also: the training data of B4/B4b (label counts, recall and latency by route), A6 plans, A8 fallback count. Additionally, the selectivity distribution of a **year-only filter** (no ticker) for the 50 questions (count of rows with that year / total) and how many exceed 0.1. **It is not run** (no retrieval with it).

## Stated before computing (from existing data; not tests)

The frozen 50 have s = 0.00056-0.0194 (at most 697 matching rows; `outputs/phase_d_gemini_full_2026-10-12/results.csv`), so policy_v2, B1, B2 and B3 route all 50 to exact: B1-B3 are expected to show 0 differences. Forced-HNSW under-filled at k = 15 in Amendment 1's sweep (mean 5.3 distinct rows), so A8 is expected to fall back on most questions. The 1,075 training questions have s <= 0.0297, so B4/B4b learn only within that range. Outputs in a new folder `outputs/phase_d_amendment7_step1_2026-10-23/`, added to `outputs/data_checksums.json`, committed.
