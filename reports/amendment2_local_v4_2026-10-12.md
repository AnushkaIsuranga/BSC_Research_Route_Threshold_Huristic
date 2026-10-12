# Amendment 2, re-scoring, error audit and local rerun (v4), 2026-10-12

No Gemini call was made in this task; the full Gemini run has **not** been started and waits for your "PROCEED FULL". All numbers are computed from the files named.

## Commits and tags

| Step | Hash | Tag |
|---|---|---|
| 1 Amendment 2 + scoring rules + naive_informed arm + stats options | `732cd14` | `phase-d-amendment-2-2026-10-12` (placed before any run under it) |
| 2-3 derived re-scoring, error audit | `b46cde9` | |
| 4-5 local v4 run + this report | see final message | the tag above is not moved |

127 tests pass (`.venv/Scripts/python -m pytest tests src/phase_b_router/test_router.py`): scoring now 59 (scale-word cases, strict vs primary, no rescaling, garbage rejected), router graphs include the `naive_informed` prompt test.

## 1. Amendment 2 (`PHASE_D_AMENDMENT_2.md`)

New file; Amendment 1 files untouched. It states that items 1a and 1b were prompted by the 5-query pilot (rows excluded from every analysis). **1a:** primary scoring = Amendment 1 rule plus trailing scale words (million, billion, thousand, mn, bn, m, k; case-insensitive, optional final period) stripped without rescaling; strict = Amendment 1 rule, reported alongside; both labels are stored in every row. **1b:** new arm `naive_informed` (same router model, schema, no-retry rule; the user message additionally states `Metadata filter to be applied: ticker = X, year = Y`, no selectivity or row counts); the exact prompt text for both router arms is in the amendment; `naive_llm` with the frozen prompt stays the pre-registered primary comparison; policy_v2 vs `naive_informed` gets the same non-inferiority check (MARGIN 0.10). **1c:** P-a stays 10%; the pilot's 4 of 5 post-filter is recorded.

## 2. Re-scoring of all earlier outputs under both rules

Derived files: `outputs/rescored_2026-10-12/` (raw files untouched). "stored != strict" counts labels where the label stored in the original file differs from the strict rule applied now; "strict -> primary" counts labels changed by the scale-word rule.

| run | arm / pass | stored correct | strict correct | primary correct | stored != strict | strict -> primary |
|---|---|---|---|---|---|---|
| sept30_first_ollama | decision_matrix / pass1 | 10 | 10 | 10 | 0 | +0 / -0 |
| sept30_first_ollama | naive_llm / pass1 | 9 | 9 | 9 | 0 | +0 / -0 |
| sept30_corrected_ollama | decision_matrix / pass1 | 10 | 10 | 10 | 0 | +0 / -0 |
| sept30_corrected_ollama | naive_llm / pass1 | 8 | 8 | 8 | 0 | +0 / -0 |
| sept30_pilot_ollama | decision_matrix / pass1 | 2 | 2 | 2 | 0 | +0 / -0 |
| sept30_pilot_ollama | naive_llm / pass1 | 1 | 1 | 1 | 0 | +0 / -0 |
| oct12_local_nomic_k6 | decision_matrix / pass1 | 11 | 11 | 11 | 0 | +0 / -0 |
| oct12_local_nomic_k6 | policy_v2 / pass1 | 11 | 11 | 11 | 0 | +0 / -0 |
| oct12_local_nomic_k6 | naive_llm / pass1 | 11 | 11 | 11 | 0 | +0 / -0 |
| oct12_local_nomic_k6 | decision_matrix / pass2 | 10 | 10 | 10 | 0 | +0 / -0 |
| oct12_local_nomic_k6 | policy_v2 / pass2 | 10 | 10 | 10 | 0 | +0 / -0 |
| oct12_local_nomic_k6 | naive_llm / pass2 | 11 | 11 | 11 | 0 | +0 / -0 |
| oct12_local_v3_amendment1 | naive_llm / pass1 | 12 | 12 | 12 | 0 | +0 / -0 |
| oct12_local_v3_amendment1 | decision_matrix / pass1 | 12 | 12 | 12 | 0 | +0 / -0 |
| oct12_local_v3_amendment1 | policy_v2 / pass1 | 13 | 13 | 13 | 0 | +0 / -0 |
| oct12_local_v3_amendment1 | policy_v2 / pass2 | 12 | 12 | 12 | 0 | +0 / -0 |
| oct12_local_v3_amendment1 | naive_llm / pass2 | 12 | 12 | 12 | 0 | +0 / -0 |
| oct12_local_v3_amendment1 | decision_matrix / pass2 | 13 | 13 | 13 | 0 | +0 / -0 |
| oct12_gemini_pilot | naive_llm / pass1 | 1 | 1 | 2 | 0 | +1 / -0 |
| oct12_gemini_pilot | decision_matrix / pass1 | 1 | 1 | 2 | 0 | +1 / -0 |
| oct12_gemini_pilot | policy_v2 / pass1 | 1 | 1 | 2 | 0 | +1 / -0 |

The scale-word rule changes **no label in any local qwen run** (30 Sept, 12 Oct, v3) and no stored label differs from the strict rule; it changes **one label per arm in the Gemini pilot** (ADI, `$18.75 million` vs gold 18.8: wrong -> correct in all three arms; parse failures 2 -> 0 per arm).

## 3. Error audit (no LLM calls): `outputs/error_audit_2026-10-12/error_audit.md`

Full text of each query (question, gold, FinQA program and executed result, gold evidence, all 15 prompt rows, answers of every run) is in that file. Summary:

| query | question | gold | FinQA program -> executed here | gold evidence in k = 15 exact prompt | answers |
|---|---|---|---|---|---|
| CDW/2015/page_70.pdf-1 | what was total in millions of accumulated other comprehensive loss? | -84 | `table_sum(accumulated other comprehensive loss, none)` -> -61.1 + -16.6 + -6.3 = -84.0 | yes (`table_2`, rank 1) | qwen 30 Sept and 12 Oct and Gemini: -61.1 (the first column only); v3 qwen: -84.0 |
| HIG/2011/page_53.pdf-3 | total increase in net asbestos reserves ... | 307 | `add(169, 138)` -> 307 | yes (`text_13`, rank 1) | qwen 30 Sept and 12 Oct: 307; v3 qwen: 138; Gemini: $39 |
| DG/2005/page_44.pdf-3 | what is the cost difference over lifo in the last two years? | 12.1 | `add(5.8, 6.3)` -> 12.1 | yes (`text_3`, rank 1) | every run: 0.5 (a subtraction, 6.3 - 5.8), Gemini adds a unit and in one arm a sign |

**Is the gold value reproducible from the gold program?** Yes in all three: the program executed here equals FinQA's `exe_ans` and the gold answer string. **Any sign of a data, key-mapping or scoring bug?** None found: for the text keys the DB row equals the raw FinQA `pre_text + post_text` entry at that index; for the table key the DB row equals the raw table row joined with ` | `; the gold passage is in the prompt (rank 1 in each case); the scorer's labels are right for the answers given (-61.1 vs -84, 39 vs 307, 0.5 vs 12.1 are wrong). The failures are the model's reading of the question: CDW "total" read as the first-year value; DG "difference" read as subtraction although FinQA's program adds the two excess-cost values (the question wording and the gold program disagree on what "difference" means, which makes this an ambiguous item, not a pipeline fault); HIG: the sentence with 169 and 138 is rank 1 and the models still answer 138 or 39. One representation note, not a bug: for table rows the model sees the raw cells (`accumulated other comprehensive loss | $ -61.1 ( 61.1 ) | ...`), whereas FinQA's own `gold_inds` text is a verbalised sentence.

## 4. Local qwen2.5:7b run v4 (`outputs/phase_d_local_2026-10-12_v4/`)

4 arms x 50 queries x 2 passes = 400 rows, 0 errors, table `finqa_evidence_qwen3`, k = 15, distinct = True, cache sha256 `930cadc0bdea177b...`, qwen2.5:7b digest `845dbda0ea48`, commit `b46cde9` (tag `phase-d-amendment-2-2026-10-12` is an ancestor), uncommitted used files: None. Pass 1 is primary. The scale-word rule changes no label in this run, so primary and strict results are identical.

**Per arm (pass 1):**

| arm | correct/50 | passage-level retrieval hit | parse failures | route parse failures | routes | mean rows returned | median total latency ms |
|---|---|---|---|---|---|---|---|
| decision_matrix | 12 | 0.66 | 3 | 0 | {'pre-filter': 50} | pre-filter: 14.8 | 165 |
| policy_v2 | 10 | 0.66 | 3 | 0 | {'exact': 50} | exact: 14.8 | 147 |
| naive_llm | 13 | 0.62 | 2 | 0 | {'post-filter': 11, 'pre-filter': 39} | post-filter: 4.5, pre-filter: 14.8 | 740 |
| naive_informed | 11 | 0.66 | 2 | 0 | {'pre-filter': 50} | pre-filter: 14.8 | 640 |

Post-filter share: **naive_llm 11/50 (22%)** (frozen prompt; v3: 10/50); **naive_informed 0/50 (0%)**: given the filter, every query was routed pre-filter. DM and policy_v2 routes identical on 50/50. Truncations 0.

**Paired tests, pass 1, primary scoring** (X vs Y; b = X only correct, c = Y only correct):

| X vs Y | b | c | exact McNemar p | accuracy diff X-Y | 95% CI (Newcombe) | total-latency diff, ms | 95% CI (paired bootstrap, 10,000, seed 20261012) |
|---|---|---|---|---|---|---|---|
| decision_matrix vs naive_llm | 0 | 1 | 1.000 | -0.020 | [-0.073, +0.030] | -507 | [-572, -437] |
| policy_v2 vs naive_llm | 0 | 3 | 0.250 | -0.060 | [-0.138, +0.011] | -506 | [-570, -440] |
| decision_matrix vs policy_v2 | 2 | 0 | 0.500 | +0.040 | [-0.022, +0.109] | -1 | [-75, +72] |
| policy_v2 vs naive_informed | 0 | 1 | 1.000 | -0.020 | [-0.078, +0.033] | -434 | [-508, -358] |
| decision_matrix vs naive_informed | 1 | 0 | 1.000 | +0.020 | [-0.032, +0.076] | -434 | [-515, -353] |
| naive_informed vs naive_llm | 0 | 2 | 0.500 | -0.040 | [-0.107, +0.021] | -72 | [-139, -6] |

**Non-inferiority at MARGIN 0.10** (lower CI bound above -0.10): decision_matrix vs naive_llm: lower bound -0.073 -> holds; policy_v2 vs naive_llm: lower bound -0.138 -> NOT shown; policy_v2 vs naive_informed: lower bound -0.078 -> holds; decision_matrix vs naive_informed: lower bound -0.032 -> holds; naive_informed vs naive_llm: lower bound -0.107 -> NOT shown. **The primary comparison (policy_v2 vs naive_llm) does not meet non-inferiority on qwen2.5:7b in this run** (policy_v2 10/50, naive_llm 13/50, b = 0, c = 3, lower bound -0.138). Latency superiority holds for every deterministic arm against both naive arms (CI entirely below 0).

**Reading that result (what the data support):** DM and policy_v2 choose the same route on all 50 queries and send identical prompts, yet they differ by 2 answers (12 vs 10; b = 2, c = 0) and each changes 6 and 4 answers between passes; so run-to-run generation noise of this model is about as large as the policy_v2 - naive gap. The difference between policy_v2 and naive_llm here is not evidence that routing hurts: DM, which is the same retrieval as policy_v2, is within the margin of naive_llm (lower bound -0.073). With only 50 pairs and this noise, the margin test mostly measures the model's sampling noise. The same will apply to Gemini (thinking length varies per call at temperature 0).

**Latency by arm position** (median generation ms by position 1 / 2 / 3 / 4, pass 1):

| arm | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| decision_matrix | 448 | 136 | 132 | 97 |
| policy_v2 | 486 | 120 | 106 | 133 |
| naive_llm | 496 | 135 | 162 | 144 |
| naive_informed | 474 | 144 | 157 | 155 |

The first-position slowdown seen in v3 (about 3.5x) reappears for every arm (about 450-500 ms at position 1 against 100-160 ms at positions 2-4), so per-arm latency comparisons depend on where an arm happened to run; the router-call cost of the naive arms (median about 0.5 s) dominates the deterministic-vs-naive difference.

**Pass 1 vs pass 2:**

| arm | same answer | same route | same correctness |
|---|---|---|---|
| policy_v2 | 46/50 | 50/50 | 49/50 |
| naive_llm | 49/50 | 50/50 | 49/50 |
| decision_matrix | 44/50 | 50/50 | 49/50 |
| naive_informed | 47/50 | 50/50 | 49/50 |

## Comparison with v3 (same settings, 3 arms, pass 1)

| arm | v3 correct | v4 correct | queries gained / lost | identical raw answers v3 vs v4 |
|---|---|---|---|---|
| decision_matrix | 12 | 12 | +0 / -0 | 37/50 |
| policy_v2 | 13 | 10 | +0 / -3 | 38/50 |
| naive_llm | 12 | 13 | +1 / -0 | 39/50 |

Code and settings that differ between v3 and v4: the fourth arm (so each query's arm order is a different shuffle), `config` unchanged for the models, scale-word scoring (changes no label here), the `finish_reason` / cost logging. Retrieval, prompts and the frozen naive router prompt are the same. The accuracy differences (policy_v2 13 -> 10, naive_llm 12 -> 13, DM 12 -> 12) therefore come from generation nondeterminism and arm order, not from any rule change: 12-13 of 50 raw answers per arm differ between v3 and v4 for the same retrieval and the same prompts (mostly between wrong answers: the correctness label changes for 0, 3 and 1 queries for decision_matrix, policy_v2 and naive_llm), and within a run 4-6 answers per deterministic arm differ between pass 1 and pass 2.

## What is uncertain or unexpected

- The primary test fails on the local model, for a reason (noise) that will probably also affect the Gemini run; the margin and the 50-pair design were fixed before this. I changed nothing.
- `naive_informed` routes 50/50 to pre-filter, so on this data it is the same route as policy_v2 and differs from it only by the router's own call and its cost; its accuracy differences against policy_v2 (b = 0, c = 1) are noise.
- The scoring change was chosen after 5 pilot rows; the strict results are in `stats_pass1_strict.json` (identical here).
- The three audited queries are model reading errors, not pipeline faults, but DG shows that FinQA's wording and gold program can disagree.
- Not tested: why first-position generation is slower (prompt reuse is a hypothesis).

## Before "PROCEED FULL"

The full Gemini run (50 queries x 4 arms x 2 passes, `--allow-paid --budget-usd 5`) is ready: the pilot extrapolated to about USD 0.40 for 3 arms x 100 runs, so about USD 0.55 for 4 arms (rough). You may want to decide before it whether the qwen result changes how you want the primary test read (for example reporting policy_v2 vs DM as a noise reference), since the amendment text fixes the primary test as written.
