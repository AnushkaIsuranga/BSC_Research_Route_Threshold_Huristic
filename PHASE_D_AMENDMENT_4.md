# Phase D, Amendment 4: pre-registered scale-up of the Gemini comparison

**Status:** written 2026-10-13, before any scale-up model call; tagged `phase-d-amendment-4-2026-10-13` before the smoke test. Amendments 1-3 and the frozen protocol are not edited; everything not mentioned here is as there. The scale-up uses no new prompt, scoring rule, retrieval setting or model: `git diff --stat 8ac3033 HEAD -- src/phase_b_router src/phase_d_validation/scoring.py src/phase_d_validation/llm_client.py config` is empty (8ac3033 = the commit at which the Gemini full run executed, per its run_meta.json).

## 1. Population

- **Pool:** the 1,147 FinQA test questions (`data/raw/finqa_test.json`); all 50 frozen questions are in it.
- **Confirmation set (primary population): 1,075 questions** = pool minus the frozen 50 (1,097) minus 22 questions excluded by the rule below. File `outputs/scaleup_confirmation_2026-10-13/confirmation_1075.csv`, SHA-256 `aff43f1fb918e2d44dd1cdd934de2b8fccd4e64e2690fd5bd4e7f3d36d0704a3`.
- **Exposure check (read-only, `outputs/scaleup_checks_2026-10-13/checks.json`):** no confirmation question was ever asked to any model in any earlier run; their ids appear in earlier outputs only in the selectivity census (incl. a 20-question supplementary selection that was never run) and as ids of retrieved evidence rows (FinQA stores the same passages under neighbouring page ids). No retrieval-hit or k-sweep result exists for them.
- **Descriptive only:** the original 50 (Gemini full run, pass 1) plus the 1,075, i.e. 1,125 questions, are also reported together; no test is attached to that pooled set.
- **Selectivity:** confirmation-set selectivity 0.00020-0.02967 (<= 0.0297); policy_v2 routes all of them to exact; decision_matrix routes all to pre-filter (same exact retrieval). All gold evidence keys exist in `finqa_evidence_qwen3`.

### Exclusion rule (decided before any run; arm-independent)

A question is excluded **if and only if the frozen gold-answer parser raises on its gold answer** (`score_answer` would raise: the gold is not a boolean word and `parse_financial_number(gold, strip_scale=True)` raises `UnparseableNumber`). The rule looks only at the gold answer, never at any model output. 22 questions are excluded:

| question id | reason | gold answer (truncated) | breadth |
|---|---|---|---|
| MAS/2017/page_27.pdf-2 | empty gold answer | `` | dual |
| AON/2015/page_96.pdf-1 | gold answer is a sentence fragment | `[6] : in 2015 , 2014 , and 2013 , shares , respectively , were issued ...` | single |
| AES/2002/page_128.pdf-2 | empty gold answer | `` | dual |
| AAL/2010/page_72.pdf-1 | empty gold answer | `` | single |
| AWK/2018/page_146.pdf-4 | empty gold answer | `` | single |
| RSG/2015/page_98.pdf-2 | empty gold answer | `` | multi |
| PNC/2012/page_100.pdf-3 | empty gold answer | `` | dual |
| JPM/2010/page_120.pdf-2 | empty gold answer | `` | single |
| CE/2016/page_19.pdf-4 | empty gold answer | `` | single |
| HIG/2011/page_53.pdf-4 | empty gold answer | `` | single |
| DG/2007/page_67.pdf-2 | empty gold answer | `` | single |
| WRK/2018/page_107.pdf-3 | gold answer is a sentence | `the total balance in 2018 including interest and penalties would be $ 56.7 million .` | multi |
| ETR/2016/page_23.pdf-4 | empty gold answer | `` | dual |
| RSG/2018/page_135.pdf-2 | empty gold answer | `` | single |
| GPN/2013/page_87.pdf-4 | number with a unit word | `170 grants` | multi |
| DRE/2007/page_56.pdf-2 | empty gold answer | `` | multi |
| WRK/2018/page_107.pdf-2 | gold answer is a sentence | `the total balance in 2018 including interest and penalties would be $ 56.7 million .` | multi |
| AWK/2017/page_148.pdf-4 | empty gold answer | `` | single |
| ANSS/2016/page_47.pdf-2 | ratio written as a:b | `1.371:1` | multi |
| TFX/2017/page_78.pdf-3 | two values joined by "or" | `$ 411906848 or $ 411.91 million` | dual |
| NCLH/2018/page_64.pdf-4 | gold answer is a sentence | `the interest decreased 25.7% from year 1 to years 3-5` | dual |
| HOLX/2009/page_127.pdf-4 | number with "per share" | `$ 27.8 per share` | single |

(FinQA's numeric `exe_ans` exists for all 22 but is on a different scale for percentage questions, e.g. 0.11212 for 11.2%; it was not used.) Full list with `exe_ans`: `outputs/scaleup_confirmation_2026-10-13/excluded_unparseable_gold.csv`.

**Strict-rule note.** Two kept questions have gold answers that only the primary rule can parse (`GPN/2013/page_87.pdf-2`: `$ 13.4 million`; `TFX/2015/page_89.pdf-3`: `$ 7989 thousand`). They are in the primary analysis; under the strict (Amendment 1) rule they have no label and are excluded from the strict-rule secondary analysis only, for all arms (gold-only flag `strict_gold_unparseable`).

### Strata (evidence breadth = number of gold evidence items)

| set | single | dual | multi | total |
|---|---|---|---|---|
| frozen 50 | 20 | 15 | 15 | 50 |
| confirmation (before exclusion) | 548 | 439 | 110 | 1,097 |
| excluded | 10 | 6 | 6 | 22 |
| **confirmation set** | **538** | **433** | **104** | **1,075** |

**The primary analysis uses the natural mix of the confirmation set (9.7% multi-evidence), with no re-weighting; results by evidence breadth are secondary.**

## 2. Arms, model and settings

decision_matrix, policy_v2, naive_llm (frozen router prompt), naive_informed; **1 pass**; `gemini-3.8-flash` (router and answer model) on Vertex AI, global, ADC; all Amendment 1-3 settings: table `finqa_evidence_qwen3`, k = 15 distinct passages, (distance, id) tie-break, seeded per-(pass, question) arm order, temperature 0, 2048 max output tokens, `thinking_level=LOW`, primary scoring rule (strict reported alongside), naive JSON failure scored wrong without retry. Query embeddings: Amendment 1 recipe (Qwen3-Embedding-8B, 1024-d via the API `dimensions` parameter, instruction prefix), cached in `outputs/embedding_build_2026-10-13/query_embeddings_qwen3_confirmation_1075.json`, **SHA-256 `c5215bea79bbd486b084d276a0bc2a5e1fb632a8e66a6ae3385f16d4bc7f36ea`** (11 calls, 0 errors, providers Nebius 6 / DeepInfra 5, 49,427 tokens, USD 0.000494; the 50-question cache is unchanged).

## 3. Analysis (`src/phase_d_validation/scaleup_analysis.py`, written and tested before the run)

- **Primary:** policy_v2 vs naive_llm on the 1,075 questions, primary scoring; Newcombe hybrid-score paired 95% CI of the accuracy difference; **non-inferior iff the lower bound is above -0.10**; exact McNemar (b, c, two-sided p) reported.
- **Secondary:** (1) non-inferiority at margin 0.05; (2) superiority, claimable only if the two-sided exact McNemar p < 0.05 here and policy_v2 is ahead; (3) the primary pair by evidence breadth (single, dual, multi); (4) latency (total ms) and cost (USD) differences by paired bootstrap over questions (10,000 resamples, seed 20261012); (5) post-filter share of naive_llm (and naive_informed); (6) policy_v2 vs naive_informed with the same checks; (7) decision_matrix vs policy_v2 as the noise reference; (8) all of the above under the strict rule (2 questions excluded there).
- The analysis refuses if any question lacks a completed row for any arm.

## 4. Predictions (fixed before any scale-up result)

1. **naive_llm post-filter share: about 40%** (plausible range 25-55%). Basis: 42% for Gemini and 22% for qwen2.5:7b on the original 50 questions.
2. **policy_v2 − naive_llm accuracy: about +0.02** (plausible range −0.01 to +0.06). Expected to be smaller than the +0.08 seen on 50 questions, because small-sample estimates tend to shrink with more data and because the confirmation set has about 10% multi-evidence questions against 30% in the frozen 50 (an untested explanation).

## 5. Budget, time and abort rules

- **Estimate:** 1,075 × 4 = 4,300 arm-runs, 4,300 answer calls + 2,150 router calls = 6,450 calls. At the full run's rate (22.5 calls/min; 66.6 min for 1,500 calls) about **4.8 hours**; at its cost per arm-run (USD 0.0016580) about **USD 7.13**.
- **Budget cap USD 15** (`--allow-paid --budget-usd 15`); the cap includes spend from earlier segments when resumed.
- **Abort rules** (runner, pre-registered): (a) error rate > 2% over the arm-runs of the first 100 questions (more than 8 error rows) -> stop, no resume; (b) projected total cost > USD 12 (checked after every completed arm-run from the 40th) -> stop.
- **Resumable:** a stop for any error (including a rate limit) is logged to `errors.jsonl` and `error.log`; the run is resumed only by an explicit `--resume` (logged in `resumes.jsonl`, settings and code hashes must be unchanged); no silent retries. `results.jsonl` holds completed rows only.
- **Smoke test first:** 10 confirmation questions × 4 arms (`--budget-usd 1`); its rows are not part of the analysis; the full run starts only after "PROCEED SCALEUP".

## 6. Limitations

- One hosted model (Gemini 3.8 Flash).
- Ticker/year filters only: every question has selectivity below 0.03 and both deterministic rules route all of them to exact retrieval; the scale-up tests "always exact" against an LLM router, not policy_v2's threshold.
- Possible training contamination: FinQA is public, and one Gemini output in the full run said "Yes, exact FinQA question!".
- k (= 15 distinct), the embedding and the scoring rules were fixed on the original 50 questions; the scale-up confirms them on new questions but did not choose them.
- 22 questions (2.0%) are excluded for unparseable gold answers; 2 more have no strict-rule label.
- One pass: no estimate of generation noise on the new questions beyond the decision_matrix vs policy_v2 noise reference.
