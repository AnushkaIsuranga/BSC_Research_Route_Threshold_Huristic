# Phase D LLM protocol (FinQA, three arms)

**Status:** written and frozen before any run of the new runner for results. Smoke tests of the harness (2 queries, scratch folder, not analysed) were run during development. Local run first, paid runs only after the user's review. No paid backend is run under this protocol until the items marked **DECISION** and **TO FILL BEFORE RUN** are completed by the user.

## Question

Does routing a filtered vector search with a rule (Decision Matrix, policy_v2) instead of an LLM ("naive router") change the end-to-end numeric answer accuracy and the cost/latency of FinQA question answering?

## Arms

| Arm | Router | Route names | Retrieval it triggers |
|---|---|---|---|
| Decision Matrix (DM) | original `src/phase_b_router/policy.py` with `outputs/thresholds.json` (tier fixed per run, see below) | `pre-filter` / `post-filter` / `iterative-scan` | `pre-filter`: exact (index scan off, seq scan on) |
| policy_v2 | `src/phase_b_router/policy_v2.py`, `exact` if s < T else `iterative-relaxed`, T = 0.1 from `config/policy_v2.json` (frozen, `fe06e9b`) | `exact` / `iterative-relaxed` | `exact`: identical retrieval SQL and planner settings to DM `pre-filter` |
| Naive LLM router | the model itself, JSON `{"route": "pre-filter"\|"post-filter", "reason": str}` | `pre-filter` / `post-filter` | `post-filter`: HNSW index scan, `hnsw.iterative_scan = off`, metadata filter applied by the WHERE clause |

**Expected and to be verified, not assumed.** On FinQA both deterministic rules should route every query to exact retrieval, so DM and policy_v2 are expected to give identical routes. Measured while writing this protocol (exact per-query selectivity = rows with the query's ticker+year / 35,862 rows, 50 frozen queries): minimum 0.000558, maximum **0.019436**. The figure 0.0297 used when the task was set is the maximum of the wider census, not of the 50 queries. For every one of the five threshold tiers in `outputs/thresholds.json`, DM returns `pre-filter` for all 50 queries; policy_v2 returns `exact` for all 50. Because the tier does not change any DM route, `--correlation-level hm_clothes_0` is used (as on 30 Sept) and this is recorded in `run_meta.json`. The run reports `dm_vs_v2_route_identical` (expected 50/50) from the data; if it is not 50/50 that is reported as measured.

Consequence if the expectation holds: DM and policy_v2 use the same route, the same query vector and the same prompt at temperature 0, so their answers are expected to match; any difference between them is generation nondeterminism, not routing. They are reported as two arms, and the DM-vs-policy_v2 comparison serves as a determinism check.

## Router / answer model design

**DECISION — confirm before paid run.** Default: in the naive arm the same model routes and answers; the deterministic arms use the same model as answer model. Run script flag `--router-model` can separate them; if not given it equals `--model`. The local run uses qwen2.5:7b for both.

## Models

- Local (this task, free): `qwen2.5:7b` via Ollama (digest recorded in `run_meta.json`).
- Planned paid, via Vertex AI global endpoint, locked (`--allow-paid`, `--budget-usd`, verified `config/prices.json`): Claude Sonnet 5.5 (`claude-sonnet-5-5`), Gemini 3.8 Flash (`gemini-3.8-flash`), Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`), gpt-oss-120b (`openai/gpt-oss-120b-maas`, optional; substitute Claude Haiku 5.5 `claude-haiku-5-5` if gpt-oss-120b is not available on the Vertex project). Model IDs and request formats are cited in `src/phase_d_validation/llm_client.py`; the Claude global-endpoint URL, Gemini usage field names and gpt-oss `reasoning_effort` are **unverified against the docs** and must be confirmed in the paid pilot.

## Fixed settings (all in `config/generation.json`, identical for every arm)

- Corpus: `finqa_evidence`, 35,862 rows, 278 ticker/year groups (checked at start with `--expect-rows 35862`). 50 frozen queries `outputs/phase2_selection_output/finqa_phase2_selected_50_20260819_140501.csv`.
- Embedding: `nomic-embed-text:latest` via Ollama (768-d), the model the corpus was built with. Distance L2 (`<->`). Top-k = 6. `hnsw.ef_search` = 40.
- Selectivity: exact per-query count (matching ticker/year rows / total rows), no hardcoded value.
- Temperature 0 where the backend allows it; the settings actually sent are logged per call (`settings_used`). Ollama: seed 0, `num_ctx` 8192.
- Max output tokens: router 256, answer 256. Thinking: qwen2.5:7b none; Claude Sonnet 5.5 no thinking field sent; Gemini 3.8 Flash `thinking_level=LOW`; Gemini 3.5 Flash-Lite `MINIMAL`; gpt-oss-120b `reasoning_effort=low`. Paid thinking settings are proposals to confirm.
- Prompts: answer system prompt and naive-router system prompt are in `src/phase_b_router/router.py` and copied to `run_meta.json`. The naive router receives only the question (not the selectivity); this is the "LLM chooses without data statistics" baseline.
- Scoring (`src/phase_d_validation/scoring.py`, no LLM judge): numeric, relative tolerance 1% of gold, abs tol 1e-9; `%` stripped and compared on the percent scale (`35.9%` = `35.9`; `0.359` is wrong); accounting negatives `(123)`; `$`, thousands commas; ratios `a/b`; yes/no gold matched to yes/no/true/false. Unparseable output = wrong, flagged `parse_failure`.
- Naive-router JSON that fails the schema: logged as `route_parse_failure`, counted, **no retry, no default route**; the query gets no retrieval and no answer and is scored wrong for that arm. **DECISION — confirm before paid run** (alternative: exclude such queries from the paired test and report both).
- Any other failure (DB, LLM call, budget) is written to the row and stops the run.
- Run order: arms rotated by query index; an untimed warm-up call loads the local model before the first logged row.

## Pre-registered predictions

- **P-a** expected share of the 50 queries on which the naive LLM chooses `post-filter`: **TO FILL BEFORE RUN** (user to enter a number before the first paid run). For reference, not as a prediction: the 30 Sept local run of qwen2.5:7b chose post-filter on 46/50 and 45/50 queries (two runs).
- **P-b** the DM-vs-naive accuracy gap (DM − naive) is largest for the weakest model. Mechanism: a post-filter route with `iterative_scan = off` retrieves only the filtered subset of the 40 nearest candidates, so it can miss gold evidence, and a weak model is less able to recover.
- **P-c** (competing) a weak model fails the arithmetic even with full context, so accuracy is low and similar for both arms and the gap shrinks. P-b and P-c predict opposite orderings of the gap for the weakest model.

## Outcomes

- **Primary:** numeric-answer accuracy per arm; paired exact McNemar test (b, c, p) on the 50 paired queries, pass 1. DM vs naive is the primary contrast; policy_v2 vs naive and DM vs policy_v2 are secondary.
- **Secondary:** 95% CI of the accuracy difference (Newcombe hybrid-score for paired proportions), latency split (embed, DB, router, generation, total; median and IQR), 95% CI of the total-latency difference (paired bootstrap, 10,000 resamples, seed 20261012), tokens (input / output / thinking, router and answer), cost (USD, paid runs), retrieval hit rate (all gold evidence keys retrieved), parse failures, route parse failures, naive post-filter share, pass-to-pass agreement (same answer, same route).
- No multiple-comparison correction is applied; three contrasts are reported and the primary is declared above.

## Run plan

1. Local qwen2.5:7b, 50 queries × 3 arms × 2 passes → user review. Output `outputs/phase_d_local_<date>/`.
2. Paid pilot, 5 queries per model → user review (checks usage fields, temperature acceptance, thinking settings, cost vs estimate).
3. Paid full run, 50 queries per model, 1 pass (+ 2nd pass if budget allows).
4. Budget: **$40 total cap, $30 for the main runs** (the remaining $10 for pilots/retries). The runner aborts before any call whose worst case could pass the cap.

## What counts as a deviation

Anything that changes, after the protocol tag, the arms, models, prompts, k, ef_search, embedding model, scoring rules, tolerance, temperature, token caps, thinking settings, query set, or statistical procedures; any retried or excluded query; any re-run to obtain a different result; any change of T; any edit of frozen files (`policy.py`, `PHASE_A_*_PROTOCOL.md`, `arm_comparison.py`, existing `outputs/` folders). Each is recorded in `DEVIATION_LOG.md` with date, reason, exact change and affected queries before the run is repeated. Bug fixes that do not change a measured quantity are also logged. Results are never overwritten; each run has a new folder.

## Limits

One corpus (FinQA, 35,862 rows), 50 queries, all with selectivity < 0.02, so the selectivity range where the rules differ (s ≥ 0.1) is not exercised: the test measures LLM-routing error against a rule that, here, always chooses exact. Local model results do not transfer to the paid models. A qwen2.5:7b answer-accuracy near 20% (30 Sept) leaves little power: with 50 pairs, small differences give few discordant pairs.
