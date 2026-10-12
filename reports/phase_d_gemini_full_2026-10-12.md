# Phase D: Gemini 3.8 Flash full run (and local v5), 2026-10-12

Pre-registration: `PHASE_D_LLM_PROTOCOL.md` + Amendments 1 (filled, v2), 2 and 3 (tag `phase-d-amendment-3-2026-10-12`, commit `bf62be5`, placed before both runs). Primary test: policy_v2 vs naive_llm, pass 1, primary scoring, Newcombe 95% CI, non-inferior iff lower bound > -0.10. All numbers below are computed from the files named; nothing was re-run or excluded.

## Commits

| Step | Hash | Tag |
|---|---|---|
| Amendment 3 + pooled bootstrap (+ fix: only policy_v2 vs naive_llm is flagged primary in the stats output) | `bf62be5` | `phase-d-amendment-3-2026-10-12` |
| local v5 run + stats | `8ac3033` | |
| Gemini full run + this report | see final message | |

Tests: 131 passed, 0 skipped (`.venv`, PostgreSQL running). New tests: pooled means and CI, zero-width CI for identical arms, refusal on a missing pass or a duplicate row, multi-pass agreement counts.

## A. Gemini 3.8 Flash full run (`outputs/phase_d_gemini_full_2026-10-12/`)

Command: `.venv/Scripts/python -m src.phase_d_validation.comparison_runner --model gemini-3.8-flash --correlation-level hm_clothes_0 --passes 5 --table finqa_evidence_qwen3 --query-embeddings outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json --expect-rows 35862 --allow-paid --budget-usd 5 --output-dir outputs/phase_d_gemini_full_2026-10-12`. run_meta: commit `8ac3033`, k = 15, distinct = True, table `finqa_evidence_qwen3`, cache sha256 `930cadc0bdea...`, uncommitted used files None, 2026-10-12T14:21:31 to 2026-10-12T15:28:08 UTC. 1,000 rows (50 queries x 4 arms x 5 passes), 1,500 Gemini calls (1,000 answer + 500 router), 0 errors.

### A1. Primary result (pass 1, primary scoring)

**policy_v2 36/50 vs naive_llm 32/50; b = 4, c = 0, exact McNemar p = 0.125; difference +0.080, 95% CI [+0.004, +0.158]. The lower bound is above -0.10: non-inferiority HOLDS.** The lower bound is also above 0; superiority was not pre-registered and the exact McNemar test is not significant (p = 0.125), so no superiority claim is made. Latency: policy_v2 - naive_llm total latency -2827 ms [-3753, -1993]: superiority on latency holds (CI below 0). Cost per query (pass 1): policy_v2 USD 0.00135, naive_llm USD 0.00203.

**Noise reference next to it** (decision_matrix vs policy_v2: same route on all 50 queries, same prompt): b = 0, c = 2, p = 0.500, difference -0.040 [-0.101, +0.018]. Pooled over 5 passes: -0.008 [-0.028, +0.008]. Two arms that differ only by generation noise disagree on 2 of 50 queries in pass 1; the primary pair disagrees on 4, all in favour of policy_v2.

**A2. All pairs, pass 1, primary scoring**

| X vs Y | b | c | exact McNemar p | acc. X | acc. Y | diff X-Y | 95% CI (Newcombe) | non-inferior at 0.10 | total-latency diff ms [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| decision_matrix vs naive_llm | 3 | 1 | 0.625 | 0.68 | 0.64 | +0.040 | [-0.038, +0.118] | yes | -2558 [-3254, -1936] |
| policy_v2 vs naive_llm | 4 | 0 | 0.125 | 0.72 | 0.64 | +0.080 | [+0.004, +0.158] | yes | -2827 [-3753, -1993] |
| decision_matrix vs policy_v2 | 0 | 2 | 0.500 | 0.68 | 0.72 | -0.040 | [-0.101, +0.018] | n/a | +268 [-342, +1042] |
| policy_v2 vs naive_informed | 2 | 0 | 0.500 | 0.72 | 0.68 | +0.040 | [-0.018, +0.101] | yes | -2125 [-3033, -1356] |
| decision_matrix vs naive_informed | 1 | 1 | 1.000 | 0.68 | 0.68 | +0.000 | [-0.059, +0.059] | yes | -1857 [-2375, -1375] |
| naive_informed vs naive_llm | 3 | 1 | 0.625 | 0.68 | 0.64 | +0.040 | [-0.038, +0.118] | yes | -702 [-1385, -36] |

**A3. Secondary pooled analysis, primary scoring** (per-query mean correctness over passes [1, 2, 3, 4, 5]; paired bootstrap over 50 queries, 10,000 resamples, seed 20261012)

| X vs Y | mean acc. X | mean acc. Y | diff X-Y | 95% CI | non-inferior at 0.10 |
|---|---|---|---|---|---|
| policy_v2 vs naive_llm | 0.704 | 0.632 | +0.072 | [+0.012, +0.148] | yes |
| policy_v2 vs naive_informed | 0.704 | 0.704 | +0.000 | [-0.016, +0.020] | yes |
| decision_matrix vs policy_v2 (noise reference) | 0.696 | 0.704 | -0.008 | [-0.028, +0.008] | n/a |
| decision_matrix vs naive_llm | 0.696 | 0.632 | +0.064 | [+0.004, +0.140] | yes |

**A4. Strict (Amendment 1) scoring, for comparison**

| arm | correct/50 pass 1 primary | correct/50 pass 1 strict | parse failures primary / strict |
|---|---|---|---|
| policy_v2 | 36 | 31 | 2 / 10 |
| naive_llm | 32 | 28 | 0 / 7 |
| decision_matrix | 34 | 30 | 2 / 9 |
| naive_informed | 34 | 29 | 0 / 9 |

**Pairs, pass 1, strict scoring**

| X vs Y | b | c | exact McNemar p | acc. X | acc. Y | diff X-Y | 95% CI (Newcombe) | non-inferior at 0.10 | total-latency diff ms [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| decision_matrix vs naive_llm | 3 | 1 | 0.625 | 0.60 | 0.56 | +0.040 | [-0.036, +0.115] | yes | -2558 [-3254, -1936] |
| policy_v2 vs naive_llm | 4 | 1 | 0.375 | 0.62 | 0.56 | +0.060 | [-0.025, +0.143] | yes | -2827 [-3753, -1993] |
| decision_matrix vs policy_v2 | 0 | 1 | 1.000 | 0.60 | 0.62 | -0.020 | [-0.061, +0.020] | n/a | +268 [-342, +1042] |
| policy_v2 vs naive_informed | 2 | 0 | 0.500 | 0.62 | 0.58 | +0.040 | [-0.014, +0.094] | yes | -2125 [-3033, -1356] |
| decision_matrix vs naive_informed | 1 | 0 | 1.000 | 0.60 | 0.58 | +0.020 | [-0.019, +0.060] | yes | -1857 [-2375, -1375] |
| naive_informed vs naive_llm | 3 | 2 | 1.000 | 0.58 | 0.56 | +0.020 | [-0.065, +0.105] | yes | -702 [-1385, -36] |

**Pooled, strict scoring** (per-query mean correctness over passes [1, 2, 3, 4, 5]; paired bootstrap over 50 queries, 10,000 resamples, seed 20261012)

| X vs Y | mean acc. X | mean acc. Y | diff X-Y | 95% CI | non-inferior at 0.10 |
|---|---|---|---|---|---|
| policy_v2 vs naive_llm | 0.612 | 0.548 | +0.064 | [-0.004, +0.144] | yes |
| policy_v2 vs naive_informed | 0.612 | 0.596 | +0.016 | [-0.004, +0.044] | yes |
| decision_matrix vs policy_v2 (noise reference) | 0.600 | 0.612 | -0.012 | [-0.040, +0.008] | n/a |
| decision_matrix vs naive_llm | 0.600 | 0.548 | +0.052 | [-0.012, +0.128] | yes |

Under the strict rule the primary comparison is policy_v2 31/50 vs naive_llm 28/50, b = 4, c = 1, CI [-0.025, +0.143]: non-inferiority also holds; the strict rule adds 7-9 parse failures per arm (answers with scale words such as `million`), in every arm.

### A5. Post-filter shares

- **naive_llm (frozen prompt): 21/50 = 42% in pass 1** (all 5 passes: 108/250 = 43.2%). **Pre-registered P-a = 10% (range 0-25%): the prediction is wrong;** the observed share lies outside the stated range.
- naive_informed: 2/50 in pass 1 (all passes 11/250 = 4.4%). Stating the filter moved almost every route to pre-filter.
- policy_v2 and decision_matrix: exact / pre-filter on 50/50 in every pass.

### A6. Retrieval, truncations, thinking, latency, cached tokens, agreement, cost

| arm (pass 1) | passage-level retrieval hit | parse failures | route parse failures | truncations | mean thinking tokens per call | median total ms [IQR] | cost per query USD |
|---|---|---|---|---|---|---|---|
| policy_v2 | 0.66 | 2 | 0 | 0 | 161 | 2186 [901] | 0.00135 |
| naive_llm | 0.60 | 0 | 0 | 0 | 166 | 4329 [2484] | 0.00203 |
| decision_matrix | 0.66 | 2 | 0 | 0 | 191 | 2121 [835] | 0.00146 |
| naive_informed | 0.64 | 0 | 0 | 0 | 105 | 3906 [1445] | 0.00180 |

- **Truncations:** 0 in pass 1. All passes: 2 of 1500 calls ended with MAX_TOKENS (both in pass 2: decision_matrix on EMR/2017/page_78.pdf-2 and policy_v2 on SNA/2013/page_34.pdf-3). Both answers are 4-5k characters of visible reasoning ("Wait, looking at the table `table_0` ...") with 0 counted thinking tokens, ending mid-sentence; scored as given (wrong). One of them contains the text "Yes, exact FinQA question!": the model recognised the benchmark; this is a sign of possible training-data exposure, not proven here. No empty answers.
- **Thinking tokens per call (all 1500 calls, `thinking_level=LOW`):** mean 143, median 88, max 1966, 527 calls used 0.
- **Cached tokens:** 0 on every call. **traffic_type:** ON_DEMAND on all 1500 calls.
- **Latency by arm position** (pass 1, median generation ms, positions 1/2/3/4): policy_v2 2176/1955/2174/2500; naive_llm 2626/2605/1754/2199; decision_matrix 2372/2247/2088/1976; naive_informed 1998/2063/2101/2243. No first-position slowdown on Gemini (unlike the local model), consistent with 0 cached tokens.

**Pass agreement.** Pass 1 vs pass 2: policy_v2 same answer 44/50, same route 50/50, same correctness 50/50; naive_llm same answer 40/50, same route 48/50, same correctness 50/50; decision_matrix same answer 42/50, same route 50/50, same correctness 50/50; naive_informed same answer 43/50, same route 49/50, same correctness 48/50.

| arm | correct per pass 1/2/3/4/5 | same answer in all 5 | same correctness in all 5 | same route in all 5 |
|---|---|---|---|---|
| policy_v2 | 36/36/35/34/35 | 39/50 | 48/50 | 50/50 |
| naive_llm | 32/32/32/32/30 | 35/50 | 47/50 | 47/50 |
| decision_matrix | 34/34/35/36/35 | 39/50 | 48/50 | 50/50 |
| naive_informed | 34/36/35/36/35 | 36/50 | 48/50 | 46/50 |

**Total cost: USD 1.6580** (cap 5.00; Amendment 3 estimate about 1.4; the runner's cumulative counter: 1.6580). By arm over 5 passes: policy_v2 0.3786, naive_llm 0.4697, decision_matrix 0.3711, naive_informed 0.4385. Per arm-run USD 0.00166 (pilot: 0.00132). Prices: 0.75 / 3.75 USD per 1M tokens (introductory, valid through 2026-12-31); please compare with the Billing report.

## B. Local qwen2.5:7b v5 (`outputs/phase_d_local_2026-10-12_v5/`, 4 arms x 50 x 5 passes, 1,000 rows, 0 errors)

**Primary (pass 1, primary scoring): policy_v2 10/50 vs naive_llm 13/50, b = 0, c = 3, p = 0.250, diff -0.060 [-0.138, +0.011]: non-inferiority NOT shown** (as in v4). Pass 1 of v5 is identical to pass 1 of v4: all 200 raw answers match (same seeded arm order, same inputs), so the local model is reproducible for a given order of calls; the pass-to-pass differences come from the different arm order / call sequence in each pass, not from randomness that cannot be reproduced.

**Pass-1 pairs, primary scoring (local)**

| X vs Y | b | c | exact McNemar p | acc. X | acc. Y | diff X-Y | 95% CI (Newcombe) | non-inferior at 0.10 | total-latency diff ms [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| decision_matrix vs naive_llm | 0 | 1 | 1.000 | 0.24 | 0.26 | -0.020 | [-0.073, +0.030] | yes | -491 [-554, -422] |
| policy_v2 vs naive_llm | 0 | 3 | 0.250 | 0.20 | 0.26 | -0.060 | [-0.138, +0.011] | NO | -491 [-553, -428] |
| decision_matrix vs policy_v2 | 2 | 0 | 0.500 | 0.24 | 0.20 | +0.040 | [-0.022, +0.109] | n/a | +1 [-72, +71] |
| policy_v2 vs naive_informed | 0 | 1 | 1.000 | 0.20 | 0.22 | -0.020 | [-0.078, +0.033] | yes | -432 [-505, -358] |
| decision_matrix vs naive_informed | 1 | 0 | 1.000 | 0.24 | 0.22 | +0.020 | [-0.032, +0.076] | yes | -431 [-512, -351] |
| naive_informed vs naive_llm | 0 | 2 | 0.500 | 0.22 | 0.26 | -0.040 | [-0.107, +0.021] | NO | -59 [-123, +5] |

**Pooled, primary scoring (local)** (per-query mean correctness over passes [1, 2, 3, 4, 5]; paired bootstrap over 50 queries, 10,000 resamples, seed 20261012)

| X vs Y | mean acc. X | mean acc. Y | diff X-Y | 95% CI | non-inferior at 0.10 |
|---|---|---|---|---|---|
| policy_v2 vs naive_llm | 0.224 | 0.244 | -0.020 | [-0.068, +0.016] | yes |
| policy_v2 vs naive_informed | 0.224 | 0.232 | -0.008 | [-0.028, +0.008] | yes |
| decision_matrix vs policy_v2 (noise reference) | 0.232 | 0.224 | +0.008 | [-0.008, +0.028] | n/a |
| decision_matrix vs naive_llm | 0.232 | 0.244 | -0.012 | [-0.040, +0.008] | yes |

Locally, the pooled analysis shows non-inferiority (policy_v2 - naive_llm -0.020 [-0.068, +0.016]) while the pass-1 primary does not; the noise reference (decision_matrix vs policy_v2) is +0.040 in pass 1 and +0.008 pooled. Strict scoring gives the same local labels (no scale words). Multi-pass (local): policy_v2 correct per pass 10/11/12/12/11; naive_llm correct per pass 13/12/12/12/12; decision_matrix correct per pass 12/11/11/12/12; naive_informed correct per pass 11/12/12/12/11.

## C. What the data show, and what they do not

- On Gemini 3.8 Flash the pre-registered primary test is met: policy_v2 is non-inferior to the naive LLM router at margin 0.10 (pass 1), and it is about 2.8 s faster per query and about one third cheaper per query. The pooled secondary analysis agrees, and the strict scoring rule gives the same conclusion.
- On qwen2.5:7b the primary test is not met in pass 1 (difference -0.060), while the pooled analysis meets it; for that model the result depends on generation noise of the size shown by the noise reference.
- The naive LLM router chose post-filter on 42% of queries with the frozen prompt (P-a predicted 10%, range 0-25%: wrong). Post-filter prompts are under-filled (fewer distinct passages; passage-level retrieval hit naive_llm 0.60 vs policy_v2 0.66 in pass 1), one way in which routing can cost accuracy here; this run does not isolate that effect.
- The deterministic arms never route anything but exact retrieval on these 50 queries (all selectivities < 0.02), so this experiment compares "always exact" with an LLM router on low-selectivity queries; it does not test policy_v2's threshold.
- One model, one 50-query set, 5 passes of the same inputs.

## D. Skipped tests and legacy inventory (report only; nothing edited)

### D1. Skipped tests

- With PostgreSQL running: **131 passed, 0 skipped** (`.venv/Scripts/python -m pytest tests src/phase_b_router/test_router.py`).
- The only skip path: `tests/test_retrieval_determinism.py` (24 tests) - its module fixture calls `pytest.skip("PostgreSQL not available")` when it cannot connect within 3 s. All 24 ran and passed in this session with PostgreSQL up.
- Not skips, but worth knowing: `src/phase_d_validation/test_retest_reliability.py` and `test_retest_splitter.py` are scripts named like tests; pytest collects 0 tests from them. Running a bare `pytest` from the repository root fails at collection: pytest treats the root file `test_retest_results.txt` as a doctest file and cannot decode it (UnicodeDecodeError).

### D2. Inconsistent legacy scripts, options and documents

| item | file | what is inconsistent with the current pipeline | proposal |
|---|---|---|---|
| Legacy local runner | src/phase_d_validation/local_ollama_runner.py | Own scorer `_number` (no scale-word rule, different tolerance formula); router prompt with `sub_queries`; `--k` default 6; `--correlation-level` default `hm_clothes_0`; `--embedding-mode openrouter` option; no tie-break, no distinct retrieval; extra routes (`post-filter-app-top40`). Produced the 30 Sept results. | Label "legacy, not used (produced 30 Sept results)" in the module docstring; leave code frozen. |
| Old stats scripts | src/phase_d_validation/stats_calculator.py, stats_aggregator.py | Read `outputs/phase_d_results*.csv` (Sept-era CSVs); normal-approximation CI of means; "error rate reduction"; no McNemar, no paired CI; superseded by paired_stats.py. | Label legacy; optionally move to `src/legacy/`. |
| jsonl_stats.py | src/phase_d_validation/jsonl_stats.py | Summarises the Sept-era JSONL schema (`dm_*` / `naive_*` columns), not the current per-row schema. | Label legacy. |
| Self-retrieval check | src/phase_d_validation/retrieval_pilot.py | Uses cosine distance `<=>` on `finqa_evidence`; the tables, indexes and runs use L2 `<->`; table name fixed. | Fix to `<->` and add a `--table` option, or label legacy (gate C of the 30 Sept build). |
| Preflight gate | src/phase_d_validation/preflight.py | Checks Ollama embedding dimension against the nomic table only; does not know `finqa_evidence_qwen3`, the cached query embeddings or the Gemini/Vertex path. | Extend with `--table`/cache checks, or label as the 30 Sept gate. |
| DB build script | src/phase_d_validation/finqa_db_setup.py (untracked, yours) | `dim = 1536  # Default fallback`; prints the OpenRouter default model `qwen/qwen3-embedding-8b` though the table was built with nomic; no prefixes; writes only `finqa_evidence`. | Remove the fallback comment/value (fail instead), document that it built the nomic table; point to build_finqa_embedding_table.py for Qwen3. |
| Embedding client default | src/utils/finqa_utils.py `get_embedding_client` | OpenRouter/LangChain path with default `qwen/qwen3-embedding-8b`; not used by any current run (comment added in step 3 of Amendment 1 work). | Keep with the comment, or label legacy. |
| Runner defaults | src/phase_d_validation/comparison_runner.py | `--table` default `finqa_evidence` and no `--query-embeddings` default, so a run without flags uses the nomic table and live nomic embeddings (pre-Amendment-1 setup) while k/distinct come from the config (Amendment 1). Module docstring example still shows the 12 Oct command (`--passes 2`, no table/cache). | Make the Amendment 1 table and cache the defaults (or require them explicitly) and update the docstring example. |
| Config embedding block | config/generation.json `embedding` | Names nomic as the embedding model; only used when no cache is given (note added). | Rename to `embedding_legacy` or add `table`/`query_cache` fields for the current setup. |
| Router default table | src/phase_b_router/router.py `Deps.table` | Default `finqa_evidence` (nomic); the runner always passes the table, so not wrong in use. | Optional: no default. |
| Tie-break in diagnostics | src/phase_c_analysis/local_selectivity_check.py, local_selectivity_check_v2.py | `ORDER BY embedding <-> v` without the id tie-break; results can differ in tie order. | Label as 30 Sept diagnostics; leave as is. |
| Test location / naming | src/phase_b_router/test_router.py; test_retest_*.py; root test_retest_results.txt | One test module lives under src/; two scripts are named test_*; the .txt breaks bare `pytest`. | Add a `pytest.ini` with `testpaths = tests src/phase_b_router` (or move test_router.py to tests/); rename the scripts or exclude them. |
| requirements.txt | requirements.txt | Missing `google-genai` (Gemini backend) and `tiktoken` (k sweep token estimate); `langchain-openai/-community` no longer used by the runner. | Add the two packages with pinned versions; mark the LangChain ones optional. |
| Code manual | docs/CODE_MANUAL.docx | Describes the 30 Sept pipeline: `MockChatModel`, router embedding via OpenRouter `get_embedding_client`, k = 6, 768-d nomic, policy_v2 "not implemented"; nothing on Amendments 1-3, Qwen3 table, distinct retrieval, LLM client lock, Gemini, pooled stats. | Add a Phase D update chapter (or a short markdown addendum) pointing to the amendments and current scripts. |
| Deviation log | DEVIATION_LOG.md | No entries for the Phase D changes after 12 Oct morning (Amendments 1-3, embedding change, scoring rule, naive_informed, 5 passes, the pilot); they are documented in the amendment files only. | Add one-line entries pointing to each amendment file and tag. |
| Frozen protocol pointer | PHASE_D_LLM_PROTOCOL.md | Frozen; models/settings superseded (k = 6, nomic, 256 tokens, four paid models). | Do not edit; a README/index listing protocol + amendments in order would remove ambiguity. |
| TODO list | Coding_TODO_List.md | Dated 17 Aug 2026; does not reflect the current state. | Label as historical. |
| Root scratch files | connection_test.py, explain.py, replay.py, replay_output.txt (untracked) | Throwaway / exploratory files at the repository root. | Keep untracked (connection_test.py per your instruction) or move to a scratch folder. |

No file in this list was changed.
