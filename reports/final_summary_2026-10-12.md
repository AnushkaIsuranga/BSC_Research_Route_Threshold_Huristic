# Final summary of results, 2026-10-12

One table per experiment with the pre-registered verdicts exactly as defined in the frozen protocols, followed by the limitations. Numbers are copied from the reports named under each table; nothing was recomputed or re-run for this summary. Tag: `final-results-2026-10-12`.

## 1. Three-arm run (H&M, 10 October 2026)

Protocol `PHASE_A_ARMS_PROTOCOL.md` (Amendments 1 and 2). 5 tables x 13 filters = 65 cells, vectors 0-19, arms planner-default, forced-exact, forced-hnsw, iterative-relaxed, iterative-strict. SLAs: mean recall@10 >= 0.90 and median latency <= 500 ms. Report: `reports/arms_results_2026-10-10.md`, `reports/policy_evaluation_2026-10-10.md`.

| Hypothesis | Verdict |
|---|---|
| H1 forced-hnsw mean recall < 0.90 at >= 1 index-scan point on hm_clothes_75 and hm_clothes_100 | holds |
| H2 iterative-relaxed mean recall >= 0.90 at every point on every table | fails over all 65 cells; holds over the 40 cells of the 8 originally frozen filters |
| H3 forced-exact median latency > 500 ms at s >= 0.329 on at least one table | holds (15 of 15 cells) |
| H4 iterative-relaxed faster than forced-exact at s >= 0.329 | holds (15 of 15) |
| H5 forced-exact <= 500 ms in every (table, lo1-lo3) cell | holds |
| H6 iterative-relaxed recall < 0.90 or median rows < 10 in >= 1 (table, lo1-lo2) cell | holds (9 of 10) |
| Policy evaluation (fixed before looking): P1, the original v1 matrix | 29 / 65 cells pass |
| policy_v2 (T = 0.1), proposed from these cells | 65 / 65 **in-sample** (describes fit, not evidence) |

## 2. First held-out test of policy_v2 (10 October 2026) and quiet rerun (12 October)

Protocol `PHASE_A_HOLDOUT_PROTOCOL.md`: filters ho1-ho5 (s = 0.020-0.180), vectors 20-39, 25 cells, T = 0.1 frozen. Reports: `reports/holdout_results_2026-10-10.md` (original), `reports/holdout_results_2026-10-12-rerun.md` (rerun).

| Hypothesis | Original run (reported result) | Quiet rerun (post-hoc robustness, seed 20261014) |
|---|---|---|
| H7 policy_v2 passes all 25 cells | **fails** (24/25; hm_clothes_25 x ho3 forced-exact 528.4 ms) | holds (25/25; same cell median 122.8 ms) |
| H8 always-iterative fails recall in >= 1 hm_clothes_100 cell at s <= 0.03 | holds (ho1 recall 0.895) | holds |
| H9 policy_v2 passes more cells than P1 | holds (24 vs 21) | fails (25 vs 25) |

The original result stands as reported (DEVIATION_LOG, 2026-10-12). CPU contention from a Jupyter kernel during the original run is a probable cause of the 528.4 ms, inferred, not proven.

## 3. Second held-out test (12 October 2026)

Protocol `PHASE_A_HOLDOUT2_PROTOCOL.md` (tag `phase-a-holdout2-frozen-2026-10-12`): five new `IN`-list filters h2a-h2e (s = 0.230, 0.256, 0.326, 0.377, 0.446), vectors 40-59, seed 20261017, 1,500 rows, 0 errors, quiet machine. Report: `reports/holdout2_results_2026-10-12.md`.

| Hypothesis | Verdict |
|---|---|
| H10 (primary) policy_v2 passes all 25 cells | **holds** (25/25) |
| H11 P1 fails >= 1 cell, per filter | h2a (exploratory): fails (0/5 cells fail); h2b: holds (1/5); h2c: holds (4/5); h2d: holds (5/5); h2e: holds (5/5) |
| H12 always-exact (P4) fails latency in every cell with s >= 0.30 | **holds** (15/15); h2a/h2b exploratory: 9 of 10 cells passed latency (436-491 ms), hm_clothes_75 x h2b 523 ms |
| Pass counts over 25 cells | P1 10, P4 9, P5 7, P6 25, policy_v2 25 (P6 = policy_v2 on these filters) |

## 4. Phase D, local qwen2.5:7b, final run v5 (12 October 2026)

`PHASE_D_LLM_PROTOCOL.md` + Amendments 1-3. Table `finqa_evidence_qwen3`, k = 15 distinct, 4 arms x 50 questions x 5 passes, 1,000 rows, 0 errors. Report: `reports/phase_d_gemini_full_2026-10-12.md` section B.

| Test | Result | Verdict |
|---|---|---|
| **Primary**: policy_v2 vs naive_llm, pass 1, primary scoring, non-inferior iff Newcombe CI lower bound > -0.10 | 10/50 vs 13/50; b = 0, c = 3, p = 0.250; diff -0.060 [-0.138, +0.011] | **not shown** |
| Pooled (secondary), passes 1-5 | -0.020 [-0.068, +0.016] | non-inferior |
| Noise reference decision_matrix vs policy_v2 (same route, same prompt) | pass 1 b = 2, c = 0, +0.040 [-0.022, +0.109]; pooled +0.008 [-0.008, +0.028] | reference only |
| policy_v2 vs naive_informed (secondary) | pass 1 -0.020 [-0.078, +0.033]; pooled -0.008 [-0.028, +0.008] | non-inferior |
| decision_matrix vs naive_llm | pass 1 -0.020 [-0.073, +0.030]; pooled -0.012 [-0.040, +0.008] | non-inferior |
| Latency superiority, policy_v2 - naive_llm (pass 1) | -491 ms [-553, -428] | holds |
| naive_llm post-filter share | 11/50 (P-a was registered for Gemini only) | - |

Earlier local runs (12 Oct with nomic k = 6; v3; v4) are reported in their own reports; v5 pass 1 reproduces v4 pass 1 exactly (200/200 raw answers).

## 5. Phase D, Gemini 3.8 Flash, full run (12 October 2026)

Same settings, 50 questions x 4 arms x 5 passes, 1,000 rows, 1,500 calls, 0 errors, cost USD 1.6580 (cap 5). Report: `reports/phase_d_gemini_full_2026-10-12.md`; mechanism check: `outputs/mechanism_check_2026-10-12/gemini_pass1.md`.

| Test | Result | Verdict |
|---|---|---|
| **Primary**: policy_v2 vs naive_llm, pass 1, primary scoring, MARGIN 0.10 | 36/50 vs 32/50; b = 4, c = 0, exact McNemar p = 0.125; diff +0.080 [+0.004, +0.158] | **non-inferior** (no superiority claim: not pre-registered, McNemar not significant) |
| Pooled (secondary), passes 1-5 | +0.072 [+0.012, +0.148] | non-inferior |
| Noise reference decision_matrix vs policy_v2 | pass 1 b = 0, c = 2, -0.040 [-0.101, +0.018]; pooled -0.008 [-0.028, +0.008] | reference only |
| policy_v2 vs naive_informed (secondary) | pass 1 +0.040 [-0.018, +0.101]; pooled 0.000 [-0.016, +0.020] | non-inferior |
| decision_matrix vs naive_llm | pass 1 +0.040 [-0.038, +0.118]; pooled +0.064 [+0.004, +0.140] | non-inferior |
| Strict (Amendment 1) scoring, primary pair | 31 vs 28; b = 4, c = 1; [-0.025, +0.143]; pooled +0.064 [-0.004, +0.144] | non-inferior |
| Latency superiority, policy_v2 - naive_llm (paired bootstrap) | -2,827 ms [-3,753, -1,993] | holds |
| Cost per question, pass 1 | policy_v2 USD 0.00135 vs naive_llm 0.00203 | - |
| **P-a** (naive_llm post-filter share 10%, range 0-25%) | 21/50 = 42% in pass 1 (43.2% over all passes) | **prediction wrong** |
| naive_informed post-filter share | 2/50 in pass 1 | - |
| Truncations / route JSON failures / non-ON_DEMAND calls / cached tokens | 0 in pass 1 (2 of 1,500 calls over all passes) / 0 / 0 / 0 | - |
| Mechanism check (pass 1) | all 4 discordant questions are naive_llm post-filter routes (2-7 rows, once 0 rows, vs 15); naive_llm accuracy 12/21 on post-filter vs 20/29 on pre-filter; on the 29 pre-filter questions both arms 20/29 | descriptive |

## Limitations

1. **FinQA selectivity range.** All 50 questions have selectivity below 0.02, where both deterministic rules choose exact retrieval. Phase D therefore compares "always exact" with an LLM router on low-selectivity queries; it does not test policy_v2's threshold T = 0.1 or the iterative branch on FinQA.
2. **Sample size and noise.** 50 paired questions; non-inferiority at 0.10 can only be shown when few questions are discordant. Repeated passes with identical inputs change 4-15 answers per arm (identical-prompt arms disagree on 2 questions in pass 1 on both models), and on qwen2.5:7b the pass-1 verdict differs from the pooled verdict. The pooled analysis resamples questions only.
3. **One hosted model, one local model, one question set.** Results do not transfer to other models, prompts or data; the planned additional hosted models were dropped (Amendment 1).
4. **Decisions made after seeing data, all labelled.** The embedding, k, distinct retrieval and tie-break (Amendment 1) were chosen from retrieval-only sweeps after the 12 Oct run; the scale-word scoring rule and the naive_informed arm (Amendment 2) after 5 pilot answers; 5 passes and the pooled analysis (Amendment 3) after the local v4 result; MARGIN was fixed after the local v3 result. The primary test itself was not changed after any Gemini result; strict-rule results are reported alongside.
5. **Router prompt dependence.** The naive router's post-filter share depends strongly on its prompt (about 90% with the 30 Sept prompt, 22% locally and 42% on Gemini with the frozen prompt, 0-4% when told the filter); the naive arm is one prompt, not "LLM routing" in general. P-a was wrong.
6. **Retrieval ceiling.** Even with k = 15 distinct passages on the exact route, all gold evidence is retrieved for 33/50 questions and no gold evidence for 4/50 (3/50 at k = 20); some FinQA items are ambiguous (e.g. DG/2005: the question says "difference", the gold program adds).
7. **Possible benchmark exposure.** One Gemini output said "Yes, exact FinQA question!"; training-data exposure of FinQA is possible and was not tested.
8. **Embedding provenance.** The baseline table (nomic) was built without nomic's required prefixes; the Qwen3 1024-d vectors from the API differ slightly from truncated 4096-d vectors (cosine 0.997 on one text), and OpenRouter routed calls to three providers.
9. **Latency measurement.** Local generation latency depends on arm position (first call about 3.5x slower, consistent with prompt reuse, not tested); H&M latencies depend on host load (the first held-out cell failed at 528.4 ms under load and passed at 122.8 ms when quiet). Single machine, one PostgreSQL configuration (shared_buffers 128 MB).
10. **Phase A scope.** H&M only, k = 10, ef_search 40, default max_scan_tuples, categorical filters, 105,100-row tables; held-out 2 filters are all `IN` lists and two share a column; policy_v2 equals always-iterative on held-out 2, so that test shows iterative-relaxed passes at s = 0.23-0.45 rather than that T = 0.1 is optimal.
11. **Cost.** Gemini prices are introductory (valid through 2026-12-31; double from 2027-01-01); the computed USD 1.658 should be checked against the billing report.

## Data freeze

`outputs/data_checksums.json`: 163 entries (88 initial, 5 embedding-table dumps and query caches, 70 output files written after the initial freeze, including local v3-v5, the Gemini pilot and full run, both held-out reruns/tests and derived files). All database tables (5 H&M, `finqa_evidence`, `finqa_evidence_nomic_prefixed`, `finqa_evidence_qwen3`) have `pg_dump` files listed there; no table was created or changed after those dumps. Frozen and amendment tags: `phase-a-holdout2-frozen-2026-10-12`, `phase-d-protocol-frozen-2026-10-12`, `phase-d-amendment-1-2026-10-12` (+ `-filled-`, `-filled-v2-`), `phase-d-amendment-2-2026-10-12`, `phase-d-amendment-3-2026-10-12`, `experiments-frozen-2026-10-12`, `final-results-2026-10-12`.
