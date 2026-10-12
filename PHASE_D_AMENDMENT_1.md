# Phase D, Amendment 1

**Status:** written 2026-10-12 before any run under it. It amends `PHASE_D_LLM_PROTOCOL.md` (frozen at tag `phase-d-protocol-frozen-2026-10-12`, file not edited). Where this file and the frozen protocol disagree, this file governs the runs named below; everything not mentioned stays as in the frozen protocol. Items marked **TO FILL BEFORE PAID RUN** must be filled and the file re-tagged before any paid call. The 12 Oct local run (`outputs/phase_d_local_2026-10-12`, nomic embeddings without the required prefixes, k = 6, non-distinct rows) is the baseline and is not replaced.

## 1. Research question (reframed)

Can the deterministic router (policy_v2; the Decision Matrix is reported alongside) replace an LLM router with no loss of numeric-answer accuracy, while reducing latency and cost?

- **Primary (non-inferiority):** the 95% CI of accuracy(policy_v2) − accuracy(naive LLM router) lies above **−MARGIN**, with **MARGIN = TO FILL BEFORE PAID RUN**. The CI is Newcombe's hybrid-score interval for paired proportions (pass 1, 50 paired queries). `src/phase_d_validation/paired_stats.py` takes `--margin` as a required argument and reports the check; it refuses to run without it.
- **Secondary (superiority):** total latency (embedding + retrieval + router + generation), 95% paired-bootstrap CI (10,000 resamples, seed 20261012) of policy_v2 − naive excludes 0 in favour of policy_v2; cost per query (paid runs).
- Also reported, as before: the exact McNemar test (b, c, two-sided p) for each pair; decision_matrix − naive alongside the primary pair.
- With 50 pairs the interval is wide (in the 12 Oct local run, b = c = 1 gave a CI of ±0.067); a margin smaller than that cannot be demonstrated with this design. This is a property of the design, stated before the margin is chosen.

## 2. Models

- Local: `qwen2.5:7b` (done as baseline; rerun under this amendment, see section 9).
- Hosted: **one** baseline, **Gemini 3.8 Flash** (`gemini-3.8-flash`, Vertex AI, global endpoint), used as router and answer model in the naive arm and as the answer model in the deterministic arms.
- Dropped from the plan: Claude Sonnet 5.5, Gemini 3.5 Flash-Lite, gpt-oss-120b (optional extension only; their code stays locked behind `--allow-paid`, verified prices and `--budget-usd`).
- Gemini settings from `config/generation.json` (temperature 0, `thinking_level=LOW`, 256 max output tokens, same for both arms) are proposals to confirm in the pilot. Open risk stated now: on Gemini, `maxOutputTokens` includes thinking tokens, so 256 may truncate answers; the pilot must check `finishReason` and token usage before the full run. Whether Gemini 3 honours temperature 0 well is not verified.

## 3. Paid plan

5-query pilot (all 3 arms), review by the user, then 50 queries × 3 arms × 2 passes. **Budget cap USD 10** (`--budget-usd 10`; the runner aborts before any call whose worst case could pass the cap). Prices in `config/prices.json` (entry `gemini-3.8-flash`) must be filled and `verified: true` by the user.

## 4. Retrieval and embedding (replaces the frozen protocol's nomic / k = 6 / non-distinct retrieval)

- **Embedding:** Qwen3-Embedding-8B (`qwen/qwen3-embedding-8b`), **1024 dimensions via the API `dimensions` parameter**; evidence table `finqa_evidence_qwen3` (35,862 rows, 10,843 unique texts, HNSW m = 16, ef_construction = 64, `vector_l2_ops`, ids identical to `finqa_evidence`; audit passed, `outputs/embedding_build_2026-10-12/audit_finqa_evidence_qwen3.json`). Documents embedded with no prefix.
- **Queries:** the 50 frozen questions embedded once with the template `Instruct: Given a financial question, retrieve the report passages and table rows that answer it\nQuery: {question}` and read from the cached file `outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json`, **SHA-256 `930cadc0bdea177b0951a6891c227606cc47a3b4a1ce8c437563635f9be9ff23`** (each input text's hash is stored in the file and verified at load). The runner called with `--query-embeddings` makes no embedding call and raises on a question not in the cache. No embedding API call is made in any run under this amendment.
- **Evidence for the embedding choice** (retrieval only, 50 queries, exact route, non-distinct, k = 6 / 10 / 15 / 20, all-gold pair-level hits; `reports/pre_paid_fixes_2026-10-12.md` section 7.3): nomic as-is 12 / 17 / 19 / 22; nomic with prefixes 14 / 19 / 20 / 24; Qwen3 16 / 19 / 20 / 24. Post-filter: nomic as-is 8 / 8 / 9 / 9; prefixed 11 / 12 / 13 / 14; Qwen3 15 / 16 / 17 / 19.
- **Retrieval = k distinct passages:** rows are ranked by (distance, id), repeats of the same passage are dropped by `md5(content)` (kept copy = smallest (distance, id)), over-fetching as needed on every route (`router.retrieve(distinct=True)`); the post-filter route can under-fill because a non-iterative HNSW scan offers at most `ef_search` = 40 candidates; the number of rows actually returned is logged for every query and route.
- **k = 15,** by the rule stated before the sweep was run: *chosen k = the smallest k whose exact-route all-gold hit is within 2 queries of the k = 20 value*. Result (Qwen3, distinct, `outputs/phase_d_k_sweep_distinct_2026-10-12/`): exact all-gold hit 21 / 27 / 33 / 35 of 50 at k = 6 / 10 / 15 / 20, so the k = 20 value is 35 and k = 15 (33) is the smallest k within 2. Post-filter: 19 / 20 / 21 / 21; it under-fills (mean distinct rows 4.2 / 5.1 / 5.3 / 5.3). Estimated prompt tokens at k = 15 on the exact route: about 930 (qwen2.5 token estimate).
- A gold hit with distinct retrieval is defined on passage text (every gold row's text is among the retrieved texts), because the kept copy of a repeated passage may carry another page's id. The strict (query_id, key) pair hit is still logged as `retrieval_hit`; `retrieval_hit_passage` is the primary retrieval metric under this amendment.
- Other retrieval settings unchanged: L2 distance, `ef_search` 40, route SQL as in the frozen protocol.
- Selectivity is still the exact per-query count (matching ticker/year rows / total rows), computed on `finqa_evidence`; `finqa_evidence_qwen3` has the same rows and metadata (row count and unique-text counts audited).

## 5. Determinism and order

- **Tie-break:** exact route in SQL (`ORDER BY distance, id`; for distinct retrieval `DISTINCT ON (md5(content))` then `ORDER BY distance, id`). Index routes: the index query keeps `ORDER BY distance` (adding `, id` makes the planner abandon the HNSW index), over-fetches, and the (distance, id) sort and cut to k are done in Python. `tie_truncated` is logged.
- **Arm order** is shuffled per (pass, query) with `random.Random("20261015|pass|query_id")` and recorded in every row (`arm_order`, `arm_position`).
- Generation is **not** deterministic at temperature 0 on the local model (12 Oct run: DM changed its raw answer on 3 of 50 queries between passes, policy_v2 on 1, with identical retrieved rows). **Pass 1 is primary; pass 2 is robustness only,** and pass-to-pass agreement is reported, not tested.

## 6. Scoring (the content of Draft Amendment 0, adopted here)

Numeric match iff `|p − g| ≤ max(0.01 · max(|p|, |g|), 1e-9)`. The percent sign is stripped and values are compared on the percent scale, with no ×100 or ÷100 rescaling (`35.9%` ≡ `35.9`; `0.359` does not match gold `35.9%`). Parsing: `$` and thousands commas removed, `(123)` and `−` are negative, `a/b` is a ratio, anything else is unparseable and scored wrong with `parse_failure`. Boolean gold matches yes/no/true/false. Sensitivity of the 12 Oct local labels to a scale-agnostic rule: 0 of 300 change.

## 7. Naive router JSON failure

The naive router must return JSON `{"route": "pre-filter"|"post-filter", "reason": str}`. Output that fails the schema is logged as `route_parse_failure` and counted; there is **no retry and no default route**; that query/arm gets no retrieval or answer and is **scored wrong**. The number of such failures is reported next to the accuracy result.

## 8. Pre-registered prediction

**P-a** (expected share of the 50 queries on which the naive LLM router chooses `post-filter`): **TO FILL BEFORE PAID RUN.** For reference only, not a prediction: qwen2.5:7b chose post-filter on 11/50 (12 Oct, new prompt) and on 45–46/50 (30 Sept, different prompt). P-b and P-c of the frozen protocol stand but now apply to the two models (qwen2.5:7b, Gemini 3.8 Flash).

## 9. Local rerun under this amendment

qwen2.5:7b, 50 queries × 3 arms × 2 passes, table `finqa_evidence_qwen3`, cached Qwen3 query embeddings, k = 15 distinct, tie-break, seeded arm order; output `outputs/phase_d_local_<date>_v3/`. Its result informs the user; it does not change this amendment.

## 10. Limitations (stated before the runs)

- The 12 Oct baseline used nomic embeddings **without** the required `search_document: ` / `search_query: ` prefixes (the table was built with raw text; the stored vectors equal a raw Ollama re-embedding at L2 = 0).
- OpenRouter routed the Qwen3 embedding calls across three providers (DeepInfra, Nebius, SiliconFlow). The API's 1024-d vector is not identical to the first 1024 values of the native 4096-d vector, re-normalised (cosine 0.997 on one text); not explained.
- Even at k = 20 some queries have no gold evidence: with distinct, passage-level matching on the exact route, 3 of 50 queries retrieve none (any-gold 47/50); the 7–10 of 50 stated in the earlier report used strict page-id matching of non-distinct rows and overstates the gap.
- All gold evidence is retrieved for 35/50 queries at k = 20 and 33/50 at k = 15 (exact route, distinct, passage level): for at least 15 queries some gold evidence is missing from the prompt whatever the router does.
- One hosted model only; one 50-query set; all queries have selectivity < 0.02, where the deterministic rules and an LLM router both route to a small filtered set, so the experiment tests LLM routing error against a rule that always chooses exact retrieval here.
- Non-inferiority with 50 pairs can only be shown for margins larger than the interval half-width (see section 1).
- Gemini 3.8 Flash behaviour at temperature 0, thinking LOW and 256 max output tokens is unverified until the pilot.
