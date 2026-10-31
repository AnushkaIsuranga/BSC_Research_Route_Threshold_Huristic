# always_hnsw answer arm on the frozen 50 FinQA questions (Amendment 10)

Pre-registration: `docs/preregistration/PHASE_D_AMENDMENT_10.md` (tag `phase-d-amendment-10-2026-10-31`, commit `fa78730`), written before any call. Run `outputs/phase_d_always_hnsw_2026-10-31/` (commit `ddb3b2e`; 300 answers, 0 errors, 08:27-09:15 UTC 31 Oct); pilot `outputs/phase_d_always_hnsw_pilot_2026-10-31/` (5 answers, excluded). Analysis `src/phase_d_validation/always_hnsw_analysis.py` -> `outputs/phase_d_always_hnsw_2026-10-31/analysis/` (`summary.json`, `classes.csv`). Reference: the frozen Gemini run `outputs/phase_d_gemini_full_2026-10-12/` (stored policy_v2 and naive_llm, 5 passes). All comparisons are descriptive and secondary.

**Setup.** always_hnsw = forced HNSW index scan with the ticker-year filter for every question (`router.retrieve(route="post-filter", distinct=True)`: index scan on, seq scan off, iterative scan off, `hnsw.ef_search` 40, L2, k = 15 distinct passages, over-fetch 150, (distance, id) tie-break), the route naive_llm used when it chose post-filter. Gemini 3.8 Flash, same answer prompt, 2,048 max output tokens, thinking LOW, temperature 0, same price table; 5 passes. Drift reference: 1 pass of policy_v2 (exact) in the same session; the 300 items were shuffled with seed 20261031. Code differences from the frozen run (disclosed in the amendment): Amendment 4 strict-label rule and the single-attempt Gemini client. Selectivity was counted as in the frozen run (`exact_selectivity`, table `finqa_evidence`; counts identical to `finqa_evidence_qwen3` for all 50). Machine: no quiet rule, the author was using the machine; host CPU 68.8 % at start, 34.2 % at end.

## Drift reference

New policy_v2 pass vs stored policy_v2 pass 1: **same correctness label on 48/50** (34 vs 36 correct), same raw answer 35/50, same parsed answer 42/50, same retrieved passages 50/50. 2 <= 5 disagreements, so the stored policy_v2 stays the reference (no switch).

## Accuracy

| arm | pass 1 | pooled (5 passes; drift: 1) | strict pooled |
|---|---|---|---|
| always_hnsw | 24/50 (0.48) | 0.520 (130/250) | 0.464 |
| policy_v2, stored | 36/50 (0.72) | 0.704 (176/250) | 0.612 |
| naive_llm, stored | 32/50 (0.64) | 0.632 (158/250) | 0.548 |
| policy_v2, drift reference | 34/50 (0.68) | - | 0.56 |

always_hnsw per pass: 24, 27, 26, 26, 27 correct; same answer on all 5 passes for 35/50 questions; 24 questions always correct, 22 never.

| comparison (always_hnsw - reference) | pass 1: discordant (X only / Y only), exact McNemar p, diff [Newcombe 95% CI] | pooled diff [paired bootstrap 95% CI] |
|---|---|---|
| vs stored policy_v2 | 0 / 12, p = 0.0005, -0.24 [-0.35, -0.12] | -0.184 [-0.288, -0.088] |
| vs stored policy_v2, strict | 3 / 12, p = 0.035, -0.18 [-0.31, -0.03] | - |
| vs stored naive_llm | 0 / 8, p = 0.0078, -0.16 [-0.25, -0.06] | -0.112 [-0.200, -0.040] |
| vs stored naive_llm, strict | 2 / 8, p = 0.11, -0.12 [-0.23, -0.001] | - |

In pass 1 always_hnsw answered correctly no question that policy_v2 or naive_llm got wrong.

## Retrieval

| arm | mean passages (median; range) | rows < 15 | 0 rows | gold passage retrieved (`retrieval_hit_passage`) |
|---|---|---|---|---|
| always_hnsw | 5.32 (5; 0-15) | 245/250 (49/50 questions by median) | 10/250 | 0.42 |
| policy_v2, stored | 14.82 (15; 10-15) | 10/250 | 0 | 0.66 |
| naive_llm, stored (142 pre-filter, 108 post-filter) | 10.47 (15; 0-15) | 118/250 | 10/250 | 0.592 |

always_hnsw distribution of passages per answer: 0: 10, 1: 30, 2: 25, 3: 25, 4: 20, 5: 25, 6: 25, 7: 25, 8: 20, 9: 20, 10-13: 20, 15: 5 (identical across passes: retrieval is deterministic).

**0-row questions (always_hnsw):** 2 questions, all 5 passes; every answer is a number, none an abstention, all wrong:
- ECL/2016/page_52.pdf-3 (gold 9.2%): 17.1%, 14.1%, 29.7%, 20%, 14%.
- MRO/2004/page_125.pdf-1 (gold 5970): $7742.5, 0, 13, $12.5, 0.

## Amendment 5 classes (proxy; grounding field `retrieval_hit_passage`)

| arm | correct | abstain / parse fail | wrong, gold not retrieved (`wrong_ungrounded`) | wrong, gold retrieved | correct, gold not retrieved |
|---|---|---|---|---|---|
| always_hnsw (250) | 130 | 2 | **82** | 36 | 61 |
| policy_v2, stored (250) | 176 | 6 | 35 | 33 | 45 |
| naive_llm, stored (250) | 158 | 5 | 52 | 35 | 47 |
| policy_v2, drift (50) | 34 | 1 | 8 | 7 | 9 |

`wrong_ungrounded` is a proxy, not a fabrication count: in the Amendment 5 label check (Addenda 1-2, model-drafted labels verified by the author) only 6 of 20 sampled `wrong_ungrounded` rows were unsupported by the retrieved text, 14 being calculable from it. The 10 zero-row answers above are the exception: with no passage in the prompt, those answers have no support in the evidence. "Correct, gold not retrieved" (61 always_hnsw rows) means the answer was right without the gold passage in the prompt (from other passages, or from the model; not distinguished here).

## Predictions (Amendment 10)

- Fewer than 15 distinct passages on most questions: **held** (245/250 answers; mean 5.32, as Amendment 1's 5.3).
- Lower gold-passage hit rate than policy_v2: **held** (0.42 vs 0.66).
- Lower accuracy than policy_v2: **held** (pooled 0.520 vs 0.704; pass 1 0.48 vs 0.72).
- More wrong answers whose gold passage was not retrieved: **held** (82 vs 35 `wrong_ungrounded`).

## Cost and latency

Cost: run USD 0.5692 (always_hnsw 0.4871, drift reference 0.0821) + pilot USD 0.0101 = **USD 0.5793** of the USD 1.50 cap. always_hnsw costs more per answer than stored policy_v2 (USD 0.0019 vs 0.0015) despite shorter prompts: sparse evidence drew longer thinking on some answers (up to 1,967 thinking tokens; median 145 vs 122 for the drift reference). Latency (descriptive only; machine in use, 12 Oct and 31 Oct conditions differ): median `total_ms` always_hnsw 3,858 ms (database 19.8 ms, generation 3,837 ms), drift-reference policy_v2 2,817 ms (database 41.7 ms), stored policy_v2 2,296 ms, stored naive_llm 4,274 ms. Selectivity counting is outside `total_ms` in all arms (see `reports/finqa_router_v3_route_check_2026-10-31.md`).

## Reading

Using the HNSW index with the filter on every FinQA question (no routing) returns about 5 of the 15 requested passages, retrieves the gold passage less often, and is less accurate than policy_v2 (which, like PostgreSQL's planner and the Phase E router, uses exact search on all 50 questions) by 18 points pooled, and than naive_llm by 11 points. On these questions routing to exact search is what preserves answer quality; the index path's database time saving (about 20 ms) is small next to generation time.
