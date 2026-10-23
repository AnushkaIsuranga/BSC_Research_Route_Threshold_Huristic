# Headline audit, 2026-10-23 (read-only)

Recomputed directly from the raw files with independent code (`src/phase_d_validation/headline_audit.py`: own Wilson/Newcombe, own exact binomial via scipy, own paired bootstrap with the same seed and resamples, own cost formula); no model call, no database access, no new result, no existing report edited. All 46 checks with their reported value, recomputed value and source are in section 3 and `outputs/headline_audit_2026-10-23/audit.json`.

## 1. Mismatches first

**Numeric mismatches: 0 of 46 checks.** Every reported number reproduces from the raw files (accuracy counts, b/c, difference, Newcombe CI, McNemar p, per-arm medians, the paired-bootstrap latency CI, per-question and per-arm costs, the USD 1.6580 total, the H&M latency ranges and the held-out-1 cell statistics).

**Claims that are numerically right but whose scope or wording needs a flag** (nothing was edited; proposals are for you to decide):

1. **"About one third cheaper per query" (reports/phase_d_gemini_full_2026-10-12.md, section C, unqualified) holds for pass 1 only.** It is 1 - 0.00135/0.00203 = 33.5% from the rounded values in the report (33.8% exact) = pass-1 mean cost per arm-run (one question x one arm), router call included for naive_llm. Over all 5 passes the same ratio is **19.4%** (policy_v2 USD 0.00151 vs naive_llm USD 0.00188 per arm-run). Pass 1 is the most favourable of the five: policy_v2's pass-1 total is the lowest of its five passes (USD 0.0673 vs 0.0781, 0.0786, 0.0806, 0.0740 in passes 2-5) and naive_llm's is the highest (USD 0.1017 vs 0.0910, 0.0931, 0.0912, 0.0928). The final summary's table labels its figures "pass 1" and is correct; the unqualified sentence is not. A defensible statement: about 19% cheaper over 5 passes (paired bootstrap of the per-arm-run cost difference: USD -0.000364 [-0.000654, -0.000118]), about 34% in pass 1.
2. **"About 2.8 s faster per query" is the pass-1 mean of the paired per-question difference** (2.827 s, CI 1.99-3.75 s). The pass-1 difference of medians is 2.14 s, and the 5-pass pooled mean difference is 2.59 s (bootstrap CI 2.03-3.22 s). The claim names neither "mean" nor "pass 1".
3. **"751-6,567 ms" does not appear in any report** (grep of all `.md` files and the manual). The two ranges in circulation use different cell sets: see section 2 item 5. The pairing of 751 with 6,567 mixes the minimum of the 15 idx1-3 cells (s >= 0.329) with the maximum of all 40 cells at s >= 0.204 (which is gap4 x hm_clothes_50, s = 0.2986, not an idx cell).
4. **Held-out 1 cause wording (section 2 item 6):** most places label the cause inferred or unproven; two statements are stronger than the evidence (listed there).
5. Minor: `arms_results_2026-10-10.md` says forced-exact "490 ms to 6.6 s from 0.204 upward"; the minimum is 488.9 ms (hm_clothes_100 x gap1), so "490" is a rounding up, not an exact value.

## 2. The requested items

### Item 1: accuracy (pass 1, primary scoring)

Source: `outputs/phase_d_gemini_full_2026-10-12/results.jsonl` (`arm`, `pass`, `query_id`, `correct`). Reported values from `reports/phase_d_gemini_full_2026-10-12.md` section A1/A2.

| quantity | reported | recomputed | status |
|---|---|---|---|
| pass-1 correct count, policy_v2 | 36 | 36 | MATCH |
| pass-1 correct count, naive_llm | 32 | 32 | MATCH |
| pass-1 correct count, decision_matrix | 34 | 34 | MATCH |
| pass-1 correct count, naive_informed | 34 | 34 | MATCH |
| policy_v2 vs naive_llm b (policy_v2 only correct) | 4 | 4 | MATCH |
| policy_v2 vs naive_llm c (naive_llm only correct) | 0 | 0 | MATCH |
| accuracy difference policy_v2 - naive_llm | 0.08 | 0.08 | MATCH |
| Newcombe 95% CI lower bound | 0.004 | 0.004 | MATCH |
| Newcombe 95% CI upper bound | 0.158 | 0.158 | MATCH |
| exact McNemar two-sided p | 0.125 | 0.125 | MATCH |

### Item 2: latency (`total_ms`, pass 1 unless stated)

| arm | median ms (reported -> recomputed) | mean ms, pass 1 | median ms, 5 passes | mean ms, 5 passes |
|---|---|---|---|---|
| policy_v2 | 2186 -> 2186 | 2548 | 2296 | 2853 |
| naive_llm | 4329 -> 4329 | 5374 | 4274 | 5443 |
| decision_matrix | 2121 -> 2121 | 2816 | 2272 | 2912 |
| naive_informed | 3906 -> 3906 | 4673 | 4100 | 4764 |

Paired policy_v2 - naive_llm, pass 1, mean: reported -2827 [-3753, -1993]; recomputed -2827 [-3753, -1993] (10,000 resamples, seed 20261012): MATCH. Difference of pass-1 medians: -2143 ms. Pooled over 5 passes (per-question mean over passes): -2590 [-3215, -2033] ms. The "about 2.8 s faster" claim is the pass-1 mean difference (flag 2 above).

### Item 3: cost

Source: same file (`cost_usd`, `router_cost_usd`, `gen_cost_usd`, `input_tokens`, `output_tokens`, `thinking_tokens`, `gen_cached_tokens`, `rows_returned`). Per-row identity cost_usd = router_cost_usd + gen_cost_usd holds for all 1,000 rows, and recomputing every call from its logged tokens with the prices (0.75 / 3.75 USD per 1M tokens; thinking billed as output; cached input subtracted) reproduces the logged cost (max row difference < 1e-9).

**Pass 1 (50 questions per arm)**

| arm | total USD | mean per question USD | router part per question | answer part per question | answer call: mean input tok | output tok | thinking tok | mean rows returned |
|---|---|---|---|---|---|---|---|---|
| policy_v2 | 0.0673 | 0.00135 | 0.00000 | 0.00135 | 960 | 6.1 | 160.9 | 14.8 |
| naive_llm | 0.1017 | 0.00203 | 0.00032 | 0.00171 | 710 | 5.0 | 308.8 | 10.5 |
| decision_matrix | 0.0728 | 0.00146 | 0.00000 | 0.00146 | 960 | 5.8 | 190.6 | 14.8 |
| naive_informed | 0.0899 | 0.00180 | 0.00034 | 0.00145 | 941 | 5.3 | 194.5 | 14.5 |

**All 5 passes (250 arm-runs per arm)**

| arm | total USD | mean per question USD | router part per question | answer part per question | answer call: mean input tok | output tok | thinking tok | mean rows returned |
|---|---|---|---|---|---|---|---|---|
| policy_v2 | 0.3786 | 0.00151 | 0.00000 | 0.00151 | 960 | 27.3 | 184.5 | 14.8 |
| naive_llm | 0.4697 | 0.00188 | 0.00027 | 0.00160 | 707 | 7.3 | 279.3 | 10.5 |
| decision_matrix | 0.3711 | 0.00148 | 0.00000 | 0.00148 | 960 | 18.2 | 185.6 | 14.8 |
| naive_informed | 0.4385 | 0.00175 | 0.00033 | 0.00142 | 935 | 5.2 | 187.0 | 14.4 |

Router call (naive arms): mean router input 125 tokens, mean router thinking 10.2 tokens (5 passes, naive_llm).

**policy_v2 vs naive_llm cost, by which route naive_llm chose** (matched by question and pass; naive_llm cost includes its router call):

| scope | naive_llm route | arm-run pairs | policy_v2 USD | naive_llm USD | difference | policy_v2 cheaper by | naive_llm router part | answer cost policy_v2 / naive_llm | answer input tok policy_v2 / naive_llm | answer output+thinking tok policy_v2 / naive_llm | naive_llm rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 passes | pre-filter | 142 | 0.00150 | 0.00172 | -0.00022 | 12.8% | 0.00030 | 0.00150 / 0.00143 | 963 / 963 | 208 / 188 | 14.7 |
| 5 passes | post-filter | 108 | 0.00153 | 0.00208 | -0.00055 | 26.6% | 0.00024 | 0.00153 / 0.00184 | 956 / 370 | 216 / 416 | 4.9 |
| pass 1 | pre-filter | 29 | 0.00134 | 0.00187 | 0.00053 (naive - policy_v2) | 28.4% | - | - | - | - | - |
| pass 1 | post-filter | 21 | 0.00135 | 0.00225 | 0.00090 (naive - policy_v2) | 40.1% | - | - | - | - | - |

**Which definition gives the reported percentage.** "About one third cheaper" = pass-1 mean cost per arm-run (question x arm, router call included): (0.00203 - 0.00135) / 0.00203 = 33.5% (33.8% unrounded). Other definitions of the same comparison: all 5 passes, total cost per arm-run: 19.4%; answer call only (router excluded), pass 1: 21.2%; answer call only, 5 passes: 5.6%.

**Decomposition over 5 passes** (mean per arm-run): policy_v2 saves USD 0.00036; the router call that it does not make is USD 0.00027 of that (about three quarters), and the remaining USD 0.00009 is the difference between the two answer calls. That difference differs by group. When naive_llm chose pre-filter (identical prompts, 963 input tokens) policy_v2's answer call costs slightly MORE (USD 0.00150 vs 0.00143; output+thinking tokens 208 vs 188), so the saving there (12.8%) is the router call alone. When naive_llm chose post-filter its answer prompt is much shorter (about 370 vs 956 input tokens) yet its answer call costs more (USD 0.00184 vs 0.00153) because it uses more output and thinking tokens (416 vs 216 per call), so the saving there (26.6%) includes a thinking-token difference that varies from pass to pass.

**Runaway answers inflate the pooled cost.** Two answers ended with finish reason MAX_TOKENS (both in pass 2): decision_matrix on EMR/2017/page_78.pdf-2: USD 0.0085, 2043 output tokens; policy_v2 on SNA/2013/page_34.pdf-3: USD 0.0084, 2044 output tokens. Mean output tokens per answer over 5 passes are policy_v2 27.3 (pass 1: 6.1) and decision_matrix 18.2; excluding those two question-pass cells for every arm, the pooled saving of policy_v2 over naive_llm is 20.5% (248 arm-runs per arm kept).

Pass-1 paired bootstrap of the per-arm-run cost difference: USD -0.000688 [-0.001146, -0.000288].

### Item 4: total cost

Sum of `cost_usd` over all 1000 rows = **USD 1.658033** (reported USD 1.6580 / "USD 1.66": MATCH); the runner's last `cumulative_cost_usd` = 1.658033; recomputed from logged tokens x prices = 1.658033. By arm over 5 passes: policy_v2 0.3786, naive_llm 0.4697, decision_matrix 0.3711, naive_informed 0.4385. The folder has no `errors.jsonl`, so no billed-but-unlogged failed call is known; the Billing report remains the external check.

### Item 5: H&M forced-exact latency at s >= 0.204 (`outputs/phase_a_arms/analysis/cell_summary.csv`, arm = forced-exact, `median_latency_ms`, one value per table x filter cell)

| cell set | cells | min ms (cell) | max ms (cell) | cells > 500 ms |
|---|---|---|---|---|
| ctl (s = 0.20376; 5 cells) | 5 | 547.1 (hm_clothes_75 x ctl) | 1080.1 (hm_clothes_50 x ctl) | 5 |
| gap1-gap4 (s = 0.214-0.299; 20 cells) | 20 | 488.9 (hm_clothes_100 x gap1) | 6567.3 (hm_clothes_50 x gap4) | 18 |
| idx1-idx3 (s = 0.329-0.4705; 15 cells) | 15 | 751.5 (hm_clothes_25 x idx1) | 3419.2 (hm_clothes_50 x idx3) | 15 |
| all cells with s >= 0.204 (40 cells) | 40 | 488.9 (hm_clothes_100 x gap1) | 6567.3 (hm_clothes_50 x gap4) | 38 |

- **"547-1,080 ms"** (PHASE_A_HOLDOUT_PROTOCOL.md, run-time estimate, written "at 0.204") is the min-max of **forced-exact median latency over the 5 `ctl` cells only** (s = 0.20376, one per table): 547.1 ms (hm_clothes_75) to 1080.1 ms (hm_clothes_50). It is correct for that set and is not the range over all cells with s >= 0.204.
- **The arms-results report** states two different things: "490 ms to 6.6 s from 0.204 upward" = min-max over **all 40 cells with s >= 0.204** (8 filters ctl, gap1-4, idx1-3 x 5 tables): 488.9 ms (hm_clothes_100 x gap1) to 6567.3 ms (hm_clothes_50 x gap4, s = 0.2986); and "all 15 idx1-3 cells exceed 500 ms (smallest 751.5 ms, hm_clothes_25/idx1)" = the **minimum over the 15 idx cells only** (s >= 0.329), whose maximum is 3419.2 ms. The idx1-3 range is therefore 751.5-3419.2 ms, not 751-6,567.
- **Why the numbers differ:** 547-1,080 = 5 cells at one selectivity (ctl); 489-6,567 = 40 cells at s >= 0.204; 751.5 = the smallest of the 15 cells at s >= 0.329. 6,567 ms is a single outlier cell (hm_clothes_50 x gap4); the other four tables at gap4 are 644-1,383 ms. Also consistent: 38 of the 40 cells at s >= 0.204 exceed 500 ms (the two that do not are hm_clothes_100 x gap1 at 488.9 and hm_clothes_25 x gap1 at 491.2), as stated in POLICY_V2_PROPOSAL.md.

### Item 6: what the reports say about the cause of the held-out-1 failure (hm_clothes_25 x ho3, forced-exact 528.4 ms)

The numbers cited in the cause discussion reproduce (median 528.4; 18 of 20 per-vector medians above 500 ms, 508-539; IQR about 16 ms; the same filter on the other tables 132-175 ms; median `shared_read_blocks` 0; the kernel used 3,410 CPU-seconds in 31.7 minutes = 1.8 cores; quiet-rerun median of the same cell 122.8 ms).

| document | wording | established or inferred? |
|---|---|---|
| `reports/holdout_results_2026-10-10.md` ("Why I think it failed [I, not proven]") | "this looks like CPU contention rather than a cold cache"; "the link between the kernel and the two slow tables is an inference"; load over time not recorded | labelled inference; OK |
| `DEVIATION_LOG.md` (2026-10-12) | "Probable CPU contention from a Jupyter kernel is noted as an inference, not proven." | labelled inference; OK |
| `reports/final_summary_2026-10-12.md`, table note | "CPU contention from a Jupyter kernel during the original run is a probable cause of the 528.4 ms, inferred, not proven." | labelled inference; OK |
| `reports/phase_d_local_2026-10-12.md` and `reports/holdout_results_2026-10-12-rerun.md` | "This report does not prove the cause." | OK |
| `docs/CODE_MANUAL.docx` section 12.9 | "[I] The failing cell appears to come from machine load ... an unrelated Jupyter kernel was using about 1.8 CPU cores" | marked [I] and hedged ("appears"); the 1.8 cores is an average over the run window, verified |
| **`reports/final_summary_2026-10-12.md`, limitation 9** | "the first held-out cell failed at 528.4 ms **under load** and passed at 122.8 ms **when quiet**" | **FLAG: states the load as fact.** What was measured: host CPU 100% at the start and 50% at the end of the original run (not recorded in between) and 17-21% falling to 3-5% in the rerun; the rerun also differs in seed, table order and time. The cause is not established. |
| **`PHASE_A_HOLDOUT2_PROTOCOL.md`** (frozen; tag `phase-a-holdout2-frozen-2026-10-12`; not edited here) | "The in-sample run, **under heavy CPU load**, had forced-exact at 489-6,567 ms" and "Under the heavy load of the original run the exact arm was up to 3x slower" | **FLAG: states load as established for the three-arm run.** `PHASE_A_HOLDOUT_PROTOCOL.md` itself says that run "probably saw similar conditions, but its load over time was not recorded"; the "up to 3x" comes from the harness self-test (2,685/2,701 ms vs 882/825 ms for the same points), not from a load measurement. |
| `reports/pre_paid_fixes_2026-10-12.md` | "up to about 2.5 h under heavy load" (run-time estimate for held-out 2) | an estimate that assumes the 3x slowdown; same flag as above, lower stakes |

No wording was changed. If you want the frozen protocol's phrases corrected, the clean route is a dated note in `DEVIATION_LOG.md` (the tagged file itself must not be edited).

## 3. All 46 checks

| id | what | reported | recomputed | source | status |
|---|---|---|---|---|---|
| 1.correct.policy_v2 | pass-1 correct count, policy_v2 | 36 | 36 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.correct.naive_llm | pass-1 correct count, naive_llm | 32 | 32 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.correct.decision_matrix | pass-1 correct count, decision_matrix | 34 | 34 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.correct.naive_informed | pass-1 correct count, naive_informed | 34 | 34 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.b | policy_v2 vs naive_llm b (policy_v2 only correct) | 4 | 4 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.c | policy_v2 vs naive_llm c (naive_llm only correct) | 0 | 0 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.diff | accuracy difference policy_v2 - naive_llm | 0.08 | 0.08 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.ci_lo | Newcombe 95% CI lower bound | 0.004 | 0.004 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.ci_hi | Newcombe 95% CI upper bound | 0.158 | 0.158 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 1.p | exact McNemar two-sided p | 0.125 | 0.125 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, correct | MATCH |
| 2.median.policy_v2 | pass-1 median total_ms, policy_v2 | 2186 | 2186 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, total_ms | MATCH |
| 2.median.naive_llm | pass-1 median total_ms, naive_llm | 4329 | 4329 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, total_ms | MATCH |
| 2.median.decision_matrix | pass-1 median total_ms, decision_matrix | 2121 | 2121 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, total_ms | MATCH |
| 2.median.naive_informed | pass-1 median total_ms, naive_informed | 3906 | 3906 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, total_ms | MATCH |
| 2.diff | pass-1 mean paired total_ms difference policy_v2 - naive_llm | -2827 | -2827 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, total_ms | MATCH |
| 2.ci_lo | paired bootstrap CI lower (10,000, seed 20261012) | -3753 | -3753 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, total_ms | MATCH |
| 2.ci_hi | paired bootstrap CI upper | -1993 | -1993 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: arm, pass, query_id, total_ms | MATCH |
| 3.cost_per_q.policy_v2 | pass-1 mean cost per question, policy_v2 | 0.00135 | 0.00135 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 3.cost_per_q.naive_llm | pass-1 mean cost per question, naive_llm | 0.00203 | 0.00203 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 3.total_5pass.policy_v2 | cost over 5 passes, policy_v2 | 0.3786 | 0.3786 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 3.total_5pass.naive_llm | cost over 5 passes, naive_llm | 0.4697 | 0.4697 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 3.total_5pass.naive_informed | cost over 5 passes, naive_informed | 0.4385 | 0.4385 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 3.total_5pass.decision_matrix | cost over 5 passes, decision_matrix | 0.3711 | 0.3711 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 3.identity | cost_usd == router_cost_usd + gen_cost_usd for every row (max abs diff < 1e-12) | True | True | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 3.token_recompute | per-row cost recomputed from logged tokens x prices (0.75/3.75, thinking as output, cached subtracted): max abs diff < 1e-9 | True | True | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 3.claim_one_third | 'about one third cheaper per query' = 1 - 0.00135/0.00203 (pass 1, from the reported per-question values) | about 33% (1/3) | 33.5% from rounded values; 33.8% exact, pass 1 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH (pass 1 only) (holds for pass 1 only; over all 5 passes the same ratio is 19.4% cheaper (mean cost per arm-run)) |
| 4.total | sum of cost_usd over all 1,000 rows vs reported USD 1.6580 (final summary: 'USD 1.66') | 1.658 | 1.658 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 4.total_rounded | rounded to cents (reported 'USD 1.66') | 1.66 | 1.66 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 4.rows | number of rows | 1000 | 1000 | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 4.cumulative_counter | runner's last cumulative_cost_usd equals the sum of rows | True | True | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 4.recomputed_from_tokens | total recomputed from tokens x prices equals logged total | True | True | outputs\phase_d_gemini_full_2026-10-12\results.jsonl: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned | MATCH |
| 5.ctl_min | '547-1,080 ms at 0.204' (PHASE_A_HOLDOUT_PROTOCOL.md): minimum of the 5 ctl cells | 547 | 547 | outputs/phase_a_arms/analysis/cell_summary.csv: arm = forced-exact, median_latency_ms | MATCH |
| 5.ctl_max | '547-1,080 ms at 0.204': maximum of the 5 ctl cells | 1080 | 1080 | outputs/phase_a_arms/analysis/cell_summary.csv: arm = forced-exact, median_latency_ms | MATCH |
| 5.idx_min | 'smallest 751.5 ms' among the 15 idx1-3 cells (arms_results report / CODE_MANUAL) | 751.5 | 751.5 | outputs/phase_a_arms/analysis/cell_summary.csv: arm = forced-exact, median_latency_ms | MATCH |
| 5.all_max | '6.6 s' maximum from 0.204 upward (arms_results report) | 6567 | 6567 | outputs/phase_a_arms/analysis/cell_summary.csv: arm = forced-exact, median_latency_ms | MATCH |
| 5.all_min | '490 ms' minimum from 0.204 upward (arms_results report: '490 ms to 6.6 s') | 490 | 489 | outputs/phase_a_arms/analysis/cell_summary.csv: arm = forced-exact, median_latency_ms | MATCH (actual minimum 488.9 ms (hm_clothes_100 x gap1); '490' is a rounding up of 488.9) |
| 5.idx_all_over_500 | 'all 15 idx1-3 cells exceed 500 ms' | 15 | 15 | outputs/phase_a_arms/analysis/cell_summary.csv: arm = forced-exact, median_latency_ms | MATCH |
| 5.fails_38_of_40 | 'forced-exact fails 38 of those 40 on latency' (POLICY_V2_PROPOSAL.md) | 38 | 38 | outputs/phase_a_arms/analysis/cell_summary.csv: arm = forced-exact, median_latency_ms | MATCH |
| 6.median | failing cell median latency 528.4 ms | 528.4 | 528.4 | outputs/phase_a_holdout/results.jsonl: table, filter_id, arm, latency_ms, shared_read_blocks | MATCH |
| 6.over500 | '18 of 20 per-vector medians are above 500 ms' | 18 | 18 | outputs/phase_a_holdout/results.jsonl: table, filter_id, arm, latency_ms, shared_read_blocks | MATCH |
| 6.range | '508-539 ms' range of those 18 | 508-539 | 508-539 | outputs/phase_a_holdout/results.jsonl: table, filter_id, arm, latency_ms, shared_read_blocks | MATCH |
| 6.iqr | 'IQR 16 ms' | 16 | 16 | outputs/phase_a_holdout/results.jsonl: table, filter_id, arm, latency_ms, shared_read_blocks | MATCH (computed IQR 15.8 ms (numpy linear percentiles)) |
| 6.other_tables | 'the same filter on the other tables costs 132-175 ms' | 132-175 | 132-175 | outputs/phase_a_holdout/results.jsonl: table, filter_id, arm, latency_ms, shared_read_blocks | MATCH |
| 6.shared_read | 'median shared_read_blocks = 0 in the cell' | 0 | 0.0 | outputs/phase_a_holdout/results.jsonl: table, filter_id, arm, latency_ms, shared_read_blocks | MATCH |
| 6.kernel_cpu | 'Jupyter kernel used 3,410 CPU-seconds between the start and end notes (31.7 min, about 1.8 cores)' | 3410 s / 31.7 min / 1.8 cores | 3410 s / 31.7 min / 1.8 cores | outputs/phase_a_holdout/machine_notes.txt | MATCH |
| 6.rerun_median | rerun median for the same cell 122.8 ms | 122.8 | 122.8 | outputs/phase_a_holdout_rerun/results.jsonl | MATCH |
