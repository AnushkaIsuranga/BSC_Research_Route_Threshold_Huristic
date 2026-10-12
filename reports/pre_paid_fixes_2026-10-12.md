# Pre-paid fixes and embedding check, 2026-10-12

Steps run in the requested order: fixes 1-4, 6, 7 first; then the embedding check (5b), which includes the full k sweep (fixes step 5 had not been run). **Step 8 (local rerun) was NOT run**: it waits for your choice of embedding and k. Nothing here chooses an embedding or a k. No chat/answer LLM was called by any step; the only paid calls were embedding calls (section 8).

## Commits

| Step | Hash |
|---|---|
| 1 provenance label fix + regenerated rerun report | `747b76d` |
| 2-4 retrieval tie-break, row-count logging, seeded arm order, HIG/2004 case study | `872783e` |
| 6 draft scoring amendment + sensitivity | `3492e02` |
| 7 draft second held-out protocol | `8f26e97` |
| 5b embedding tables, query caches, k sweep, this report | see final message |

One slip, corrected before it left my machine: my first commit of steps 2-4 (`c13431d`) accidentally also staged your uncommitted work-in-progress files (`logger.py`, `sweep_orchestrator.py` and untracked scripts). I undid that commit (`reset --soft`, local, never pushed) and recommitted only my files as `872783e`. Your work-in-progress files are still uncommitted and unchanged. One exception, added in the 5b commit: `src/phase_d_validation/finqa_db_audit.py` (yours, untracked) is imported by the new table builder, so it is committed unmodified as a dependency.

## 1. Provenance of the rerun report

- All 88 files in `outputs/data_checksums.json` (written before the rerun) were re-hashed: no mismatch (the six DB dumps, over 300 MB each, were skipped in this re-hash). `git status` shows no change under `outputs/phase_a_holdout/`. The original held-out files were not overwritten.
- Cause of the confusing text: `holdout_analysis.py` hardcodes the string `outputs/phase_a_holdout/...` in its report text, while the data and `machine_notes.txt` it reads come from the redirected path (`outputs/phase_a_holdout_rerun/`), so the numbers and the quoted notes were the rerun's but the label named the original folder. Fixed in the wrapper `src/phase_c_analysis/holdout_analysis_rerun.py` (label rewrite only; `holdout_analysis.py` untouched) and the report regenerated from `outputs/phase_a_holdout_rerun/`: zero remaining references to `outputs/phase_a_holdout/`; results unchanged (H7 holds 25/25, H8 holds, H9 fails). The sha256 of original `results.jsonl` and `machine_notes.txt` was identical before and after the regeneration.

## 2. Deterministic retrieval order

**Tied distances in the queries whose answers changed between pass 1 and pass 2 of the 12 Oct run** (4 rows: DM on INTC/2015/page_41.pdf-3, ABMD/2007/page_78.pdf-1, ALXN/2016/page_153.pdf-2; policy_v2 on ABMD/2007/page_78.pdf-1):

- In all four, the exact top-9 contains blocks of **4 rows with identical distance** (the same passage under 4 page ids; e.g. INTC: ids 7601, 26, 31872, 21232 all at 0.592136, then 4 rows at 0.713641), so ties exist within the top 6 **and across the rank 6/7 boundary** (which 2 of 4 tied rows enter a 6-row prompt is arbitrary without a tie-break).
- But in all four, pass 1 and pass 2 retrieved **the same rows in the same order** (checked row by row), and the answers still differed (INTC `35%` vs `28%`; ABMD `74%` vs `76%`; ALXN `41%` vs `21%`). So the pass-to-pass answer changes are generation nondeterminism on an identical prompt, **not retrieval order**. The tie-break will remove the order differences between runs/sessions (section 5 of the 12 Oct report: 9 answers differed from 30 Sept where only the order differed) but it **cannot be expected to give 50/50 identical answers between passes**; I expect the target to be missed unless generation is also made deterministic (not tested).

**Implementation** (`src/phase_b_router/router.py: retrieve`): exact route `ORDER BY distance, id` in SQL. For the HNSW routes I did **not** add `, id` to the SQL: I checked with EXPLAIN that `ORDER BY embedding <-> v, id` makes the planner abandon the HNSW index (post-filter and iterative would silently become sequential scans). Instead the index query keeps `ORDER BY embedding <-> v` with `LIMIT 2k`, and rows are sorted by `(distance, id)` and cut to k in Python; `tie_truncated` is set if a tie group may extend past the fetched rows. The index routes now fetch 2k rows (a small cost difference). The legacy `local_ollama_runner.py` and `local_selectivity_check*.py` were not changed.

**Test:** `tests/test_retrieval_determinism.py` (integration, real DB, 14 cases): for three tied-distance groups x four routes, the same query twice gives identical row ids and `rows_fetched`; rows are ordered by (distance, id); the exact route breaks the tie at the top by id; unknown route raises. Full suite now **85 passed**.

## 3. HIG/2004/page_140.pdf-1: exact missed the gold row, post-filter did not

Full output: `outputs/pre_paid_fixes_2026-10-12/hig2004_case_study.txt` (script `src/phase_d_validation/retrieval_case_study.py`). Gold: key `table_2` (id 1870, HIG, 2004, text `reclassifying certain separate accounts to general account | 30 | 294`). Both statements filter `metadata->>'ticker' = 'HIG' AND metadata->>'year' = '2004'` (159 rows, 53 keys x 3 identical page copies), `ORDER BY embedding <-> :q LIMIT 12`:

- **Exact** (`enable_indexscan=off, enable_seqscan=on`; plan Seq Scan + Sort): ranks 1-12 = `table_0` x3 (0.785795), `text_46` x3 (0.796552), `table_2` x3 (**0.823608**, ranks 7-9), `text_17` x3 (0.866491). k = 6 therefore holds only `table_0` and `text_46`: the gold row is at rank 7. 12 rows returned.
- **Post-filter** (`enable_indexscan=on, enable_seqscan=off, iterative_scan=off`; plan Index Scan on `finqa_evidence_embedding_idx` with the WHERE as Filter): returned only 9 rows: `table_0` x3, `table_2` x3, `text_17` x3. `text_46` is **missing**, so `table_2` moved up into the top 6 and the hit was recorded.
- **Cause (from the data):** the HNSW graph's 40 unfiltered candidates (ef_search = 40) contain only 6 HIG/2004 rows, `table_0` and `table_2`; the **exact** unfiltered top-40 additionally contains the three `text_46` rows (0.7966, nearer than `table_2`). So the approximate index missed three rows that are closer than the gold row; the post-filter route's hit is an approximate-search miss that happened to remove competitors, not better retrieval. The exact route is correct and the gold row simply ranks 7th. Also visible: every passage exists as 3 identical copies (pages -1, -2, -3), so k = 6 is only 2 distinct passages here. (Gold rows' ticker/year equal the filter: HIG / 2004. No filter mismatch.)

**Logging from now on** (`comparison_runner.py`, per query per arm per route): `rows_returned`, `rows_fetched`, `retrieved_ids`, `retrieved_distances`, `tie_truncated` (plus the existing `retrieved_evidence_keys`). Visible in post-filter rows, which return fewer than k rows (section 7: mean 3.9 of 6 for nomic).

## 4. Arm order

Per (pass, query) the arms are shuffled with `random.Random(f"20261015|{pass}|{query_id}")` (deterministic, seeded), applied in the Phase D runner and recorded in every row as `arm_order` (list) and `arm_position`; the rule is also written to `run_meta.json`. Covered by the full-suite run only through the unit test that imports the runner; the new order has not been exercised in a full run yet (that is step 8).

## 5. Scoring (draft amendment, not tagged)

Appended to `PHASE_D_LLM_PROTOCOL.md` as "DRAFT AMENDMENT 0" (the frozen tag `phase-d-protocol-frozen-2026-10-12` still points to the unchanged text). Exact rules: tolerance `|p - g| <= max(0.01 * max(|p|, |g|), 1e-9)` (`math.isclose(rel_tol=0.01, abs_tol=1e-9)`, relative to the larger magnitude); the percent sign is stripped and values are compared on the percent scale (no x100 or /100 rescaling): `35.9%` = `35.9` match gold `35.9%`, `0.359` does not. **Sensitivity:** a scale-agnostic rule (accept p, 100p or p/100) changes **0 of 300** labels of the 12 Oct local run (`outputs/pre_paid_fixes_2026-10-12/scale_agnostic_sensitivity.json`). Sensitivity only; no rule changed.

## 6. Draft second held-out protocol

`PHASE_A_HOLDOUT2_PROTOCOL.md` (draft, not frozen, not run, no query executed). Five filters, all `IN` lists of values never used before, because no unused single (column, value) lies in 0.19-0.48 (the five single values there were all used): h2a 0.23038, h2b 0.25625, h2c 0.32620, h2d 0.37669, h2e 0.44642 (identical row counts in all five tables; counts and the v1 route per table are in the file). Vectors 0-based lines 40-59 (SHA-256 recorded; verified that no result file in `outputs/` uses vector indices above 39). Hypotheses H10-H12 as you specified. Run-time estimate **about 45-60 minutes quiet** (up to about 2.5 h under heavy load). **Risks I recorded in the draft for you to decide before freezing:** (a) H12 may fail at the low end on a quiet machine: forced-exact latency scaled about 2 ms per 0.001 of selectivity in the quiet rerun (352 ms at 0.18), which extrapolates to 500 ms near s = 0.25-0.27, so h2a (0.230) and perhaps h2b (0.256) may pass the latency SLA for P4; (b) H11 for h2a/h2b rests on the same borderline because P1 routes all their tables to forced-exact; (c) h2d and h2e share a column and six values; (d) all filters are `IN` lists.

## 7. Embedding check (5b)

### 7.1 Prefix check

No prefix is used anywhere (`grep -rn "search_document\|search_query\|prefix" src` finds nothing). Exact lines:

- Documents: `src/phase_d_validation/finqa_db_setup.py:94` `vectors = ollama.embed(ollama_model, [text for _, text in batch])` (Ollama path) and `:122` `batch_embeddings = embeddings_model.embed_documents(batch_texts)` (OpenRouter path); both pass the raw content.
- Queries: `src/phase_d_validation/comparison_runner.py:74` `json={"model": model, "input": text}` with `text` = the raw question (called from `router.py:150`, `deps.embed(state["question"])`); the legacy runner `local_ollama_runner.py:64` `client.embed(embedding_model, question)` also raw.
- **What actually built `finqa_evidence`:** I re-embedded 5 stored rows (ids 1001-1005) with Ollama `nomic-embed-text:latest` on the **raw** content: L2 distance to the stored vector **0.00000** (cosine 1.00000, vectors unit-norm). With the `search_document: ` prefix the L2 distance is 0.39-0.45 (cosine 0.90-0.92). So the existing table is nomic, raw text, 768-d, unprefixed, even though `.env` has `EMBEDDING_MODEL=qwen/qwen3-embedding-8b` (that variable is not what built the table). Both the documents and the queries of the 12 Oct run were therefore unprefixed, consistently, but not in the format nomic's model card asks for.

### 7.2 Tables built (new tables; `finqa_evidence` untouched; same ids as `finqa_evidence`; HNSW m=16, ef_construction=64, `vector_l2_ops`)

| table | model | dim | docs | queries | rows | unique (md5, ticker, year) | zero vectors | bad dims | unresolved gold pairs | self-retrieval |
|---|---|---|---|---|---|---|---|---|---|---|
| finqa_evidence_nomic_prefixed | nomic-embed-text:latest | 768 | `search_document: ` + content | `search_query: ` + question | 35862 | 10843 | 0 | 0 | 0 | 5/5 |
| finqa_evidence_qwen3 | qwen/qwen3-embedding-8b | 1024 | no prefix | `Instruct: Given a financial question, retrieve the report passages and table rows that answer it\nQuery: {question}` | 35862 | 10843 | 0 | 0 | 0 | 5/5 |

Both audits **passed** (row count 35,862, 10,843 unique texts as in the 30 Sept audit, 0 zero vectors, dimension correct, gold resolution complete, self-retrieval 5/5 with identical content at distance 0). Audit files: `outputs/embedding_build_2026-10-12/audit_*.json`. Query embeddings (50 frozen questions) cached once with the sha256 of the exact input text: `query_embeddings_nomic_prefixed.json`, `query_embeddings_qwen3.json` (and `outputs/phase_d_k_sweep_2026-10-12/query_embeddings_nomic_asis.json` for the as-is nomic).

**Qwen3 dimension:** the API's `dimensions=1024` parameter was used (every returned vector had 1024 values and unit norm). A check on one text: the API's 1024-d vector versus the first 1024 values of the native 4096-d vector, L2-normalised: cosine **0.99697**, max absolute coordinate difference 0.015, i.e. **not identical** to truncate-and-normalise. I did not establish why; OpenRouter routed the calls to three providers (DeepInfra, Nebius, SiliconFlow), so provider-level numerical differences between calls are possible.

### 7.3 k sweep: exact vs post-filter, 50 queries, deterministic (distance, id) retrieval

`all` = every gold evidence pair (query_id, key) retrieved (the runner's definition); `any` = at least one gold pair; `content-all` = extra diagnostic: every gold row's text is among the retrieved texts (identical copies under other page ids count). Tokens: mean prompt tokens of the exact answer prompt, estimated for qwen2.5 as 1.182 x (tiktoken cl100k count) + 4.1 (linear fit on the 50 DM pass-1 prompts of the 12 Oct run, R^2 0.967, mean absolute residual 18 tokens; an approximation, no Qwen tokenizer was available offline). `rows` = mean rows actually returned.

| embedding | route | k | all-gold | any-gold | content-all | rows | est. prompt tokens |
|---|---|---|---|---|---|---|---|
| nomic_asis | exact | 6 | 12/50 (24%) | 31/50 (62%) | 12/50 | 6.0 | 475 |
| nomic_asis | exact | 10 | 17/50 (34%) | 38/50 (76%) | 17/50 | 10.0 | 720 |
| nomic_asis | exact | 15 | 19/50 (38%) | 40/50 (80%) | 19/50 | 15.0 | 1043 |
| nomic_asis | exact | 20 | 22/50 (44%) | 43/50 (86%) | 22/50 | 20.0 | 1326 |
| nomic_asis | post-filter | 6 | 8/50 (16%) | 24/50 (48%) | 8/50 | 3.9 | 341 |
| nomic_asis | post-filter | 10 | 8/50 (16%) | 27/50 (54%) | 8/50 | 5.6 | 457 |
| nomic_asis | post-filter | 15 | 9/50 (18%) | 27/50 (54%) | 9/50 | 7.1 | 553 |
| nomic_asis | post-filter | 20 | 9/50 (18%) | 27/50 (54%) | 10/50 | 8.1 | 600 |
| nomic_prefixed | exact | 6 | 14/50 (28%) | 33/50 (66%) | 15/50 | 6.0 | 496 |
| nomic_prefixed | exact | 10 | 19/50 (38%) | 39/50 (78%) | 19/50 | 10.0 | 766 |
| nomic_prefixed | exact | 15 | 20/50 (40%) | 40/50 (80%) | 21/50 | 15.0 | 1089 |
| nomic_prefixed | exact | 20 | 24/50 (48%) | 40/50 (80%) | 24/50 | 20.0 | 1410 |
| nomic_prefixed | post-filter | 6 | 11/50 (22%) | 30/50 (60%) | 12/50 | 5.2 | 447 |
| nomic_prefixed | post-filter | 10 | 12/50 (24%) | 34/50 (68%) | 12/50 | 7.5 | 605 |
| nomic_prefixed | post-filter | 15 | 13/50 (26%) | 34/50 (68%) | 13/50 | 9.6 | 745 |
| nomic_prefixed | post-filter | 20 | 14/50 (28%) | 34/50 (68%) | 14/50 | 10.9 | 840 |
| qwen3 | exact | 6 | 16/50 (32%) | 34/50 (68%) | 17/50 | 6.0 | 467 |
| qwen3 | exact | 10 | 19/50 (38%) | 39/50 (78%) | 19/50 | 10.0 | 721 |
| qwen3 | exact | 15 | 20/50 (40%) | 39/50 (78%) | 20/50 | 15.0 | 1021 |
| qwen3 | exact | 20 | 24/50 (48%) | 41/50 (82%) | 24/50 | 20.0 | 1318 |
| qwen3 | post-filter | 6 | 15/50 (30%) | 34/50 (68%) | 16/50 | 5.3 | 426 |
| qwen3 | post-filter | 10 | 16/50 (32%) | 36/50 (72%) | 16/50 | 8.0 | 602 |
| qwen3 | post-filter | 15 | 17/50 (34%) | 36/50 (72%) | 17/50 | 10.9 | 789 |
| qwen3 | post-filter | 20 | 19/50 (38%) | 36/50 (72%) | 19/50 | 13.0 | 927 |

Sanity check: nomic as-is, exact, k = 6 gives all-gold 12/50 and any-gold 31/50, equal to the 12 Oct run's 12/50 all-gold rate (the tie-break did not change it). Files: `outputs/phase_d_k_sweep_2026-10-12/` (`summary.csv|json`, `per_query.jsonl`, `token_calibration.json`).

### 7.4 Observations from the table (no recommendation)

- At every k, the exact route returns exactly k rows and post-filter returns fewer (nomic as-is: 3.9 of 6 and 8.1 of 20 on average), because the HNSW index offers only ef_search = 40 candidates before the metadata filter; post-filter's all-gold rate is lower than exact's for each embedding at every k.
- Each passage exists as several identical copies, so k = 6 rows are only about 2 distinct passages in many queries (see section 3).
- Hit rates rise with k for the exact route in all three embeddings; on the exact route the any-gold rate is 40-43/50 at k = 20, i.e. no gold evidence is retrieved for 7-10 of 50 queries even at k = 20.
- The sweep measures retrieval, not answers: the 12 Oct run answered 11/50 with an all-gold rate of 12/50; whether more evidence helps qwen2.5:7b is not measured here.

### 7.5 Embedding cost (API log: `outputs/embedding_build_2026-10-12/api_calls.jsonl`, every call logged)

118 calls to `qwen/qwen3-embedding-8b` via OpenRouter (0 errors), **371,154 prompt tokens, $0.003712** in total (price listed by OpenRouter: $0.00000001 per token; cap $1.00, never approached). This includes 3 probe/check calls (1 `dimensions` probe, 2 for the truncation comparison), 109 document batches (10,843 unique texts), 1 batch of 50 queries and the 5 self-retrieval re-embeds. Nomic embeddings ran locally on Ollama (free; not counted). The key was read from the environment (`.env`, which is git-ignored and untracked: `git check-ignore -v .env` -> `.gitignore:2:.env`); the key is not in any log, cache, output or commit (grep of every file in the build folder for `Bearer`/`sk-or` finds 0 matches).

## 8. What I did not do, and what I need from you

- Step 8 (local rerun with the fixes) is **not run**. It needs your choice of embedding and k; the 12 Oct nomic run stays as the baseline.
- Changing the embedding changes the frozen setup (`phase-d-protocol-frozen-2026-10-12`). I did not edit the frozen file. After you choose: write `PHASE_D_AMENDMENT_1.md` with the reason and these retrieval numbers, fold in Draft Amendment 0 (scoring) if you accept it, and re-tag; paid runs wait for that tag. I can draft it.
- The new tables exist only in the local PostgreSQL (not in `outputs/db_dumps_2026-10-12/`, and `outputs/data_checksums.json` predates them); a dump + refreshed checksums should be taken once you choose.
- Decide the two open DECISION items in the protocol (router design; schema-failure scoring) and fill P-a before any paid run, as before.
