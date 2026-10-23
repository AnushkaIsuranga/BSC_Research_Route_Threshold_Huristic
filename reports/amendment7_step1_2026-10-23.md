# Amendment 7 Step 1: routes of the baselines on the frozen 50 FinQA questions (no LLM), 2026-10-23

Governed by `docs/preregistration/PHASE_D_AMENDMENT_7.md` (tag `phase-d-amendment-7-2026-10-23`). No LLM, embedding or other API call; no cost. Script `src/phase_d_validation/amendment7_step1.py`; outputs `outputs/phase_d_amendment7_step1_2026-10-23/` (`summary.json`, `frozen50_routes.csv`, `training_runs.jsonl`, `preflight.json`, `host_load.json`). Run 2026-10-23 17:48-17:56 UTC (470 s) from HEAD `21a94ad` with the script not yet committed (committed unchanged with these outputs; a 30-question smoke test into a scratch folder preceded it and is not part of any result).

## Inputs and checks

- **Embeddings: Qwen3-Embedding-8B, 1024-d, table `finqa_evidence_qwen3` (35,862 rows) only.** Query vectors from the two Qwen3 caches, no new embedding: frozen 50 `outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json` (SHA-256 `930cadc0...be9ff23`, equal to `data_checksums.json`); 1,075 confirmation questions `outputs/embedding_build_2026-10-13/query_embeddings_qwen3_confirmation_1075.json` (SHA-256 `c5215bea...f36ea`, equal to the value in the tagged Amendment 4; **this file has no entry in `data_checksums.json`**). Both caches state model `qwen/qwen3-embedding-8b`, dimension 1024; every question is present (50/50, 1,075/1,075), every vector has 1,024 values, every input text equals the instruction prefix + question and matches its stored hash. Confirmation file SHA-256 `aff43f1f...` verified.
- **Selectivity counted on `finqa_evidence_qwen3`**, not on the old `finqa_evidence` table named in the tagged text (author's instruction of 23 Oct; logged in `DEVIATION_LOG.md`). All 1,125 counts equal the recorded selectivities (frozen 50 from the Gemini full run, 1,075 from the confirmation file) to 1e-12, so no number depends on the choice.
- Settings: `hnsw.ef_search` 40, `hnsw.max_scan_tuples` 20000, `jit` on (server default, as Amendments 1-3), k = 15 distinct, (distance, id) tie-break via `router.retrieve(distinct=True)`. Pre-flight plain EXPLAIN: exact = Seq Scan, iterative-relaxed and forced-HNSW = Index Scan on `finqa_evidence_qwen3_embedding_idx`. Every timed plan matched its route.
- Machine: no notebook kernel, embedding job or demo; Ollama server idle and two idle MCP plugin processes were present. Host CPU % (3 one-second samples): start 9/6/10, 5 min 52/22/16, end 7/5/4.

## Routes on the frozen 50 and differences from policy_v2

The frozen 50 have s = 0.00056-0.0194 (median 0.0040), at most **697** matching rows. policy_v2 routes all 50 to exact.

| rule | routes on the 50 | differ from policy_v2 |
|---|---|---|
| B1 VBASE (s < 0.18) | exact 50 | **0** |
| B2 Milvus via NaviX (s <= 0.05) | exact 50 | **0** |
| B3 Qdrant (rows < 2,500) | exact 50 | **0** |
| A6 planner_iterative (plain EXPLAIN) | exact 50 (plan `Limit/Sort/Seq Scan` on all 50) | **0** |
| A8 fallback_hnsw | exact 49 (fallback), forced-HNSW 1 | **1** (V/2010/page_28.pdf-1, s = 0.0021, 75 rows: forced-HNSW returned 15 distinct rows) |
| B4 Gan & Wang, recall/latency labels | exact 50 | **0** |
| B4b Gan & Wang, SLA labels | exact 50 | **0** |

**By the pre-registered rule, B1, B2, B3, A6, B4 and B4b are identical to policy_v2 on the frozen 50 by construction and will not be run with the LLM.** Only A8 differs, on one question. A8 fell back on 49/50: forced-HNSW returned 0-13 distinct rows on those (median 5).

## B4 / B4b training (1,075 confirmation questions, retrieval only)

| route | recall@15 vs exact distinct top-15 (mean, min) | median latency ms (min-max) | fewer than 15 distinct rows |
|---|---|---|---|
| exact | 1.000 (reference) | 5.45 (4.21-13.89) | 64 (filter has fewer than 15 distinct passages) |
| iterative-relaxed | 0.995, min 0.733 (8 queries below 0.9) | 43.80 (1.62-98.33) | 66 |

Labels: exact 1,038, iterative-relaxed 37, the same under both label rules. The 37 iterative labels are queries with s = 0.0070-0.0213 where iterative-relaxed happened to be faster (1.7-6.6 ms vs 6-9 ms exact) at recall 1.0. Both models (seed 20261023, 12 epochs, training accuracy 0.966) predict exact over the whole range s in [0, 1] (no decision boundary), so they always choose exact. Training selectivities span only 0.0002-0.0297; the models have seen nothing above that.

## Year-only filter (no ticker), for the 50 questions; counted, not run

Selectivity of `year = Y` on `finqa_evidence_qwen3`: min 0.0088, median 0.0609, mean 0.0643, max **0.0998** (2017). **0 of 50 exceed 0.1.** The four largest: 2017 0.0998, 2012 0.0882, 2015 0.0864, 2008 0.0821. policy_v2 (T = 0.1) would therefore still route every year-only filter of these questions to exact, though 2017 lies 0.0002 below T.

## Limits

One server configuration; latencies are single-run medians of 5. B4/B4b see only selectivity and were trained within s <= 0.0297. A6 is a plan inspection (plain EXPLAIN), not a measured run. B1-B4b are re-implementations of published rules in this harness, not the original systems.
