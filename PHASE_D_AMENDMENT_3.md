# Phase D, Amendment 3

**Status:** written 2026-10-12 **after the local v4 run** (`outputs/phase_d_local_2026-10-12_v4`, `reports/amendment2_local_v4_2026-10-12.md`) and **before any full-run Gemini call**; tagged `phase-d-amendment-3-2026-10-12` before any run under it. Amends Amendments 1 and 2 (files unchanged); everything not mentioned here stays as there (MARGIN 0.10, P-a 10%, primary/strict scoring, four arms, k = 15 distinct, Qwen3 table and cached query embeddings, tie-break, seeded arm order, 2048 max output tokens, `thinking_level=LOW`).

**Why.** Prompted by the generation noise seen in v4: decision_matrix and policy_v2 chose identical routes and sent identical prompts on all 50 queries, yet disagreed on 2 queries (b = 2, c = 0); 4-6 answers per arm changed between pass 1 and pass 2. With one pass, the 50-pair test cannot separate a routing effect from this noise.

## 1. Primary test: unchanged

policy_v2 vs naive_llm, **pass 1**, primary scoring rule (Amendment 2), Newcombe hybrid-score 95% CI of the paired accuracy difference, non-inferior iff the lower bound is above **−0.10**. Exact McNemar (b, c, p) reported as before. The local v4 primary result is reported as measured: **non-inferiority not shown** (policy_v2 10/50, naive_llm 13/50, b = 0, c = 3, lower bound −0.138).

## 2. Passes: 2 → 5

For the full Gemini run and for a new local qwen2.5:7b run (`outputs/phase_d_local_<date>_v5/`): **5 passes** of 50 queries × 4 arms. **Pass 1 = primary** (section 1); **pass 2 = robustness** as before (pass-1 vs pass-2 agreement); **passes 1-5 = secondary pooled analysis** (section 3). Each pass uses the same seeded per-(pass, query) arm-order shuffle rule.

## 3. Secondary pooled non-inferiority

For each arm and each query: mean correctness over the 5 passes (primary scoring). Difference per query: policy_v2 − naive_llm (secondary-primary), and policy_v2 − naive_informed. Point estimate = mean over the 50 queries; **95% CI by paired bootstrap over queries** (resampling the 50 queries; percentile interval; **10,000 resamples, seed 20261012**). Non-inferior iff the lower bound is above **−0.10**. Implemented as `pooled_compare` in `src/phase_d_validation/paired_stats.py` (`--pooled`), with unit tests; a query missing any pass for either arm makes the analysis refuse rather than drop it.

## 4. Noise reference

**decision_matrix vs policy_v2** (same route and same prompt on these data, so any difference is generation noise) is reported **next to the primary result**, with the same pass-1 statistics (b, c, McNemar p, Newcombe CI) and the same pooled statistics (section 3). decision_matrix vs naive_llm is also reported (pass 1 and pooled). Multi-pass agreement per arm (queries with the same answer / route / correctness in all 5 passes; correct count per pass) is reported.

## 5. Budget

Gemini 3.8 Flash full run: 50 queries × 4 arms × 5 passes = 1,000 arm-runs; **cap USD 5** (`--allow-paid --budget-usd 5`). Estimate **about USD 1.4** (pilot rate USD 0.00132 per arm-run × 1,000 arm-runs = USD 1.32; the naive arms cost more than the deterministic arms because of the router call, and thinking length varies per call).

## 6. Limitations added

- Passes are repeated calls with identical inputs; they measure generation noise of one model on one query set, not variation over queries or models. The pooled CI resamples queries only.
- This amendment was written after seeing the local v4 result (primary not shown); the primary test is not changed, and the pooled analysis is labelled secondary for that reason.
