# Hallucination-oriented classification of wrong answers (Amendment 5), 2026-10-23

Pre-registered in `docs/preregistration/PHASE_D_AMENDMENT_5.md` (tag `phase-d-amendment-5-2026-10-23`, commit `0ac1bd2`, written and tagged before anything was computed). Existing outputs only: no model call, no API call (cost USD 0), no database write (the only database access is the read-only evidence `SELECT` for the labelling sheet). Primary results of Amendments 1-3 are not re-analysed. Each model is analysed separately.

**Naming.** `wrong_ungrounded` is called "ungrounded wrong answer (hallucination proxy)" below: a wrong, parsed answer where the gold evidence was not fully in the prompt. It is a proxy, not proof of fabrication; the word hallucination is not used for it until the blind manual sample (section 7) has been labelled.

**Grounding field (decision of the user, 2026-10-23).** `retrieval_hit_passage` (every gold row's text among the retrieved passage texts) for the Amendment 1+ runs; the strict page-id field `retrieval_hit` only for the 12 Oct baseline (its rows have no other field). The strict field is shown as a sensitivity table, "strict page-id test, shown for transparency only". No null grounding values were found in any run.

Classes in order: `correct`; `abstain_or_parse_fail` (wrong and no number parsed); `wrong_ungrounded` (wrong, parsed, grounding field 0); `wrong_grounded` (wrong, parsed, grounding field 1). `correct_ungrounded` = correct while the grounding field is 0.

## Gemini 3.8 Flash full run (4 arms x 50 questions x 5 passes)

Grounding field: retrieval_hit_passage. 1000 rows.

**Pass 1** (count/rows (rate; Wilson 95% CI))

| arm | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | correct_ungrounded (subset of correct) |
|---|---|---|---|---|---|
| policy_v2 | 36/50 (72.0%; 58.3%-82.5%) | 2/50 (4.0%; 1.1%-13.5%) | 6/50 (12.0%; 5.6%-23.8%) | 6/50 (12.0%; 5.6%-23.8%) | 9/50 (18.0%; 9.8%-30.8%) |
| decision_matrix | 34/50 (68.0%; 54.2%-79.2%) | 2/50 (4.0%; 1.1%-13.5%) | 7/50 (14.0%; 7.0%-26.2%) | 7/50 (14.0%; 7.0%-26.2%) | 9/50 (18.0%; 9.8%-30.8%) |
| naive_llm | 32/50 (64.0%; 50.1%-75.9%) | 0/50 (0.0%; 0.0%-7.1%) | 11/50 (22.0%; 12.8%-35.2%) | 7/50 (14.0%; 7.0%-26.2%) | 9/50 (18.0%; 9.8%-30.8%) |
| naive_informed | 34/50 (68.0%; 54.2%-79.2%) | 0/50 (0.0%; 0.0%-7.1%) | 8/50 (16.0%; 8.3%-28.5%) | 8/50 (16.0%; 8.3%-28.5%) | 10/50 (20.0%; 11.2%-33.0%) |

**Pooled over 5 passes** (count/rows (rate; Wilson 95% CI))

| arm | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | correct_ungrounded (subset of correct) |
|---|---|---|---|---|---|
| policy_v2 | 176/250 (70.4%; 64.5%-75.7%) | 6/250 (2.4%; 1.1%-5.1%) | 35/250 (14.0%; 10.2%-18.8%) | 33/250 (13.2%; 9.6%-18.0%) | 45/250 (18.0%; 13.7%-23.2%) |
| decision_matrix | 174/250 (69.6%; 63.6%-75.0%) | 8/250 (3.2%; 1.6%-6.2%) | 34/250 (13.6%; 9.9%-18.4%) | 34/250 (13.6%; 9.9%-18.4%) | 45/250 (18.0%; 13.7%-23.2%) |
| naive_llm | 158/250 (63.2%; 57.1%-68.9%) | 5/250 (2.0%; 0.9%-4.6%) | 52/250 (20.8%; 16.2%-26.3%) | 35/250 (14.0%; 10.2%-18.8%) | 47/250 (18.8%; 14.4%-24.1%) |
| naive_informed | 176/250 (70.4%; 64.5%-75.7%) | 2/250 (0.8%; 0.2%-2.9%) | 38/250 (15.2%; 11.3%-20.2%) | 34/250 (13.6%; 9.9%-18.4%) | 47/250 (18.8%; 14.4%-24.1%) |

**Paired comparison per question (secondary, pre-specified, descriptive; no margin, no multiplicity correction).** Pass 1: b = questions where the first arm has the class and the second does not; c = the reverse; exact McNemar p. Pooled: per-question mean class indicator over the passes, paired bootstrap (10,000 resamples, seed 20261012).

| comparison | class | pass 1 rates (x / y) | b | c | exact McNemar p | pooled rates (x / y) | pooled difference x - y [95% CI] |
|---|---|---|---|---|---|---|---|
| policy_v2 vs naive_llm | wrong_ungrounded | 12.0% / 22.0% | 0 | 5 | 0.062 | 14.0% / 20.8% | -6.8 pp [-14.4, -0.8] |
| policy_v2 vs naive_llm | wrong_grounded | 12.0% / 14.0% | 0 | 1 | 1.000 | 13.2% / 14.0% | -0.8 pp [-2.8, +0.8] |
| policy_v2 vs naive_llm | abstain_or_parse_fail | 4.0% / 0.0% | 2 | 0 | 0.500 | 2.4% / 2.0% | +0.4 pp [-1.6, +3.2] |
| policy_v2 vs naive_informed | wrong_ungrounded | 12.0% / 16.0% | 0 | 2 | 0.500 | 14.0% / 15.2% | -1.2 pp [-3.2, +0.0] |
| policy_v2 vs naive_informed | wrong_grounded | 12.0% / 16.0% | 0 | 2 | 0.500 | 13.2% / 13.6% | -0.4 pp [-2.4, +1.2] |
| policy_v2 vs naive_informed | abstain_or_parse_fail | 4.0% / 0.0% | 2 | 0 | 0.500 | 2.4% / 0.8% | +1.6 pp [+0.0, +3.6] |

**Split by chosen route** (naive arms; all passes pooled):

| arm | route | rows | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | mean rows returned |
|---|---|---|---|---|---|---|---|
| naive_llm | post-filter | 108 | 63 | 0 | 25 (23.1%) | 20 (18.5%) | 4.9 |
| naive_llm | pre-filter | 142 | 95 | 5 | 27 (19.0%) | 15 (10.6%) | 14.7 |
| naive_informed | post-filter | 11 | 3 | 0 | 4 (36.4%) | 4 (36.4%) | 5.5 |
| naive_informed | pre-filter | 239 | 173 | 2 | 34 (14.2%) | 30 (12.6%) | 14.8 |

(Pass-1 route split: `summary_route_split_gemini_full.csv`.)

## local qwen2.5:7b v5 (4 arms x 50 x 5 passes)

Grounding field: retrieval_hit_passage. 1000 rows.

**Pass 1** (count/rows (rate; Wilson 95% CI))

| arm | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | correct_ungrounded (subset of correct) |
|---|---|---|---|---|---|
| policy_v2 | 10/50 (20.0%; 11.2%-33.0%) | 3/50 (6.0%; 2.1%-16.2%) | 13/50 (26.0%; 15.9%-39.6%) | 24/50 (48.0%; 34.8%-61.5%) | 3/50 (6.0%; 2.1%-16.2%) |
| decision_matrix | 12/50 (24.0%; 14.3%-37.4%) | 3/50 (6.0%; 2.1%-16.2%) | 12/50 (24.0%; 14.3%-37.4%) | 23/50 (46.0%; 33.0%-59.6%) | 4/50 (8.0%; 3.2%-18.8%) |
| naive_llm | 13/50 (26.0%; 15.9%-39.6%) | 2/50 (4.0%; 1.1%-13.5%) | 14/50 (28.0%; 17.5%-41.7%) | 21/50 (42.0%; 29.4%-55.8%) | 4/50 (8.0%; 3.2%-18.8%) |
| naive_informed | 11/50 (22.0%; 12.8%-35.2%) | 2/50 (4.0%; 1.1%-13.5%) | 12/50 (24.0%; 14.3%-37.4%) | 25/50 (50.0%; 36.6%-63.4%) | 4/50 (8.0%; 3.2%-18.8%) |

**Pooled over 5 passes** (count/rows (rate; Wilson 95% CI))

| arm | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | correct_ungrounded (subset of correct) |
|---|---|---|---|---|---|
| policy_v2 | 56/250 (22.4%; 17.7%-28.0%) | 14/250 (5.6%; 3.4%-9.2%) | 61/250 (24.4%; 19.5%-30.1%) | 119/250 (47.6%; 41.5%-53.8%) | 19/250 (7.6%; 4.9%-11.6%) |
| decision_matrix | 58/250 (23.2%; 18.4%-28.8%) | 14/250 (5.6%; 3.4%-9.2%) | 60/250 (24.0%; 19.1%-29.7%) | 118/250 (47.2%; 41.1%-53.4%) | 20/250 (8.0%; 5.2%-12.0%) |
| naive_llm | 61/250 (24.4%; 19.5%-30.1%) | 10/250 (4.0%; 2.2%-7.2%) | 70/250 (28.0%; 22.8%-33.9%) | 109/250 (43.6%; 37.6%-49.8%) | 20/250 (8.0%; 5.2%-12.0%) |
| naive_informed | 58/250 (23.2%; 18.4%-28.8%) | 12/250 (4.8%; 2.8%-8.2%) | 60/250 (24.0%; 19.1%-29.7%) | 120/250 (48.0%; 41.9%-54.2%) | 20/250 (8.0%; 5.2%-12.0%) |

**Paired comparison per question (secondary, pre-specified, descriptive; no margin, no multiplicity correction).** Pass 1: b = questions where the first arm has the class and the second does not; c = the reverse; exact McNemar p. Pooled: per-question mean class indicator over the passes, paired bootstrap (10,000 resamples, seed 20261012).

| comparison | class | pass 1 rates (x / y) | b | c | exact McNemar p | pooled rates (x / y) | pooled difference x - y [95% CI] |
|---|---|---|---|---|---|---|---|
| policy_v2 vs naive_llm | wrong_ungrounded | 26.0% / 28.0% | 1 | 2 | 1.000 | 24.4% / 28.0% | -3.6 pp [-10.0, +0.8] |
| policy_v2 vs naive_llm | wrong_grounded | 48.0% / 42.0% | 3 | 0 | 0.250 | 47.6% / 43.6% | +4.0 pp [-2.8, +12.0] |
| policy_v2 vs naive_llm | abstain_or_parse_fail | 6.0% / 4.0% | 1 | 0 | 1.000 | 5.6% / 4.0% | +1.6 pp [+0.0, +4.8] |
| policy_v2 vs naive_informed | wrong_ungrounded | 26.0% / 24.0% | 1 | 0 | 1.000 | 24.4% / 24.0% | +0.4 pp [+0.0, +1.2] |
| policy_v2 vs naive_informed | wrong_grounded | 48.0% / 50.0% | 0 | 1 | 1.000 | 47.6% / 48.0% | -0.4 pp [-2.8, +2.0] |
| policy_v2 vs naive_informed | abstain_or_parse_fail | 6.0% / 4.0% | 1 | 0 | 1.000 | 5.6% / 4.8% | +0.8 pp [+0.0, +2.4] |

**Split by chosen route** (naive arms; all passes pooled):

| arm | route | rows | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | mean rows returned |
|---|---|---|---|---|---|---|---|
| naive_llm | post-filter | 55 | 16 | 0 | 15 (27.3%) | 24 (43.6%) | 4.5 |
| naive_llm | pre-filter | 195 | 45 | 10 | 55 (28.2%) | 85 (43.6%) | 14.8 |
| naive_informed | pre-filter | 250 | 58 | 12 | 60 (24.0%) | 120 (48.0%) | 14.8 |

(Pass-1 route split: `summary_route_split_local_v5.csv`.)

## Rows returned for ungrounded wrong answers, and 0-row cases

How many `wrong_ungrounded` rows had 0 rows returned (the post-filter route returned nothing, so the model answered with no evidence at all). All passes pooled, and pass 1 only.

| run | arm | wrong_ungrounded rows (all passes) | with 0 rows returned | rows returned: 0 / 1-3 / 4-7 / 8-14 / 15 | mean rows | pass 1: wrong_ungrounded | pass 1: with 0 rows |
|---|---|---|---|---|---|---|---|
| gemini_full | decision_matrix | 34 | 0 | 0 / 0 / 0 / 0 / 34 | 15.0 | 7 | 0 |
| gemini_full | naive_informed | 38 | 0 | 0 / 0 / 0 / 4 / 34 | 14.6 | 8 | 0 |
| gemini_full | naive_llm | 52 | 10 | 10 / 5 / 5 / 5 / 27 | 9.7 | 11 | 2 |
| gemini_full | policy_v2 | 35 | 0 | 0 / 0 / 0 / 0 / 35 | 15.0 | 6 | 0 |
| local_v5 | decision_matrix | 60 | 0 | 0 / 0 / 0 / 0 / 60 | 15.0 | 12 | 0 |
| local_v5 | naive_informed | 60 | 0 | 0 / 0 / 0 / 0 / 60 | 15.0 | 12 | 0 |
| local_v5 | naive_llm | 70 | 5 | 5 / 5 / 0 / 5 / 55 | 12.6 | 14 | 1 |
| local_v5 | policy_v2 | 61 | 0 | 0 / 0 / 0 / 0 / 61 | 15.0 | 13 | 0 |
| local_v4 | decision_matrix | 24 | 0 | 0 / 0 / 0 / 0 / 24 | 15.0 | 12 | 0 |
| local_v4 | naive_informed | 24 | 0 | 0 / 0 / 0 / 0 / 24 | 15.0 | 12 | 0 |
| local_v4 | naive_llm | 28 | 2 | 2 / 2 / 0 / 2 / 22 | 12.6 | 14 | 1 |
| local_v4 | policy_v2 | 25 | 0 | 0 / 0 / 0 / 0 / 25 | 15.0 | 13 | 0 |
| local_v3 | decision_matrix | 26 | 0 | 0 / 0 / 0 / 0 / 26 | 15.0 | 13 | 0 |
| local_v3 | naive_llm | 30 | 2 | 2 / 2 / 0 / 2 / 24 | 12.7 | 15 | 1 |
| local_v3 | policy_v2 | 26 | 0 | 0 / 0 / 0 / 0 / 26 | 15.0 | 13 | 0 |
| local_oct12_baseline | decision_matrix | 62 | not logged | not logged | not logged | 31 | not logged |
| local_oct12_baseline | naive_llm | 66 | not logged | not logged | not logged | 33 | not logged |
| local_oct12_baseline | policy_v2 | 62 | not logged | not logged | not logged | 31 | not logged |

## Other runs (pooled counts per arm; all passes)

**local qwen2.5:7b v4 (4 arms x 50 x 2 passes)**; grounding field: retrieval_hit_passage.

**Pooled over 2 passes** (count/rows (rate; Wilson 95% CI))

| arm | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | correct_ungrounded (subset of correct) |
|---|---|---|---|---|---|
| policy_v2 | 21/100 (21.0%; 14.2%-30.0%) | 6/100 (6.0%; 2.8%-12.5%) | 25/100 (25.0%; 17.5%-34.3%) | 48/100 (48.0%; 38.5%-57.7%) | 7/100 (7.0%; 3.4%-13.7%) |
| decision_matrix | 23/100 (23.0%; 15.8%-32.2%) | 6/100 (6.0%; 2.8%-12.5%) | 24/100 (24.0%; 16.7%-33.2%) | 47/100 (47.0%; 37.5%-56.7%) | 8/100 (8.0%; 4.1%-15.0%) |
| naive_llm | 25/100 (25.0%; 17.5%-34.3%) | 4/100 (4.0%; 1.6%-9.8%) | 28/100 (28.0%; 20.1%-37.5%) | 43/100 (43.0%; 33.7%-52.8%) | 8/100 (8.0%; 4.1%-15.0%) |
| naive_informed | 23/100 (23.0%; 15.8%-32.2%) | 4/100 (4.0%; 1.6%-9.8%) | 24/100 (24.0%; 16.7%-33.2%) | 49/100 (49.0%; 39.4%-58.7%) | 8/100 (8.0%; 4.1%-15.0%) |

policy_v2 vs naive_llm, pass 1 (b = policy_v2 only, c = naive_llm only; exact McNemar p): wrong_ungrounded: b = 1, c = 2, p = 1.000; pooled diff -3.0 pp [-10.0, +2.0]; wrong_grounded: b = 3, c = 0, p = 0.250; pooled diff +5.0 pp [-1.0, +12.0]; abstain_or_parse_fail: b = 1, c = 0, p = 1.000; pooled diff +2.0 pp [+0.0, +6.0].

**local qwen2.5:7b v3 (3 arms x 50 x 2 passes)**; grounding field: retrieval_hit_passage.

**Pooled over 2 passes** (count/rows (rate; Wilson 95% CI))

| arm | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | correct_ungrounded (subset of correct) |
|---|---|---|---|---|---|
| policy_v2 | 25/100 (25.0%; 17.5%-34.3%) | 4/100 (4.0%; 1.6%-9.8%) | 26/100 (26.0%; 18.4%-35.4%) | 45/100 (45.0%; 35.6%-54.8%) | 8/100 (8.0%; 4.1%-15.0%) |
| decision_matrix | 25/100 (25.0%; 17.5%-34.3%) | 3/100 (3.0%; 1.0%-8.5%) | 26/100 (26.0%; 18.4%-35.4%) | 46/100 (46.0%; 36.6%-55.7%) | 8/100 (8.0%; 4.1%-15.0%) |
| naive_llm | 24/100 (24.0%; 16.7%-33.2%) | 2/100 (2.0%; 0.6%-7.0%) | 30/100 (30.0%; 21.9%-39.6%) | 44/100 (44.0%; 34.7%-53.8%) | 8/100 (8.0%; 4.1%-15.0%) |

policy_v2 vs naive_llm, pass 1 (b = policy_v2 only, c = naive_llm only; exact McNemar p): wrong_ungrounded: b = 0, c = 2, p = 0.500; pooled diff -4.0 pp [-10.0, +0.0]; wrong_grounded: b = 2, c = 2, p = 1.000; pooled diff +1.0 pp [-6.0, +8.0]; abstain_or_parse_fail: b = 1, c = 0, p = 1.000; pooled diff +2.0 pp [+0.0, +6.0].

**local qwen2.5:7b 12 Oct baseline (nomic, k = 6, non-distinct; 3 arms x 50 x 2 passes)**; grounding field: retrieval_hit (strict; the only field in its rows).

**Pooled over 2 passes** (count/rows (rate; Wilson 95% CI))

| arm | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | correct_ungrounded (subset of correct) |
|---|---|---|---|---|---|
| policy_v2 | 21/100 (21.0%; 14.2%-30.0%) | 6/100 (6.0%; 2.8%-12.5%) | 62/100 (62.0%; 52.2%-70.9%) | 11/100 (11.0%; 6.3%-18.6%) | 8/100 (8.0%; 4.1%-15.0%) |
| decision_matrix | 21/100 (21.0%; 14.2%-30.0%) | 6/100 (6.0%; 2.8%-12.5%) | 62/100 (62.0%; 52.2%-70.9%) | 11/100 (11.0%; 6.3%-18.6%) | 8/100 (8.0%; 4.1%-15.0%) |
| naive_llm | 22/100 (22.0%; 15.0%-31.1%) | 4/100 (4.0%; 1.6%-9.8%) | 66/100 (66.0%; 56.3%-74.5%) | 8/100 (8.0%; 4.1%-15.0%) | 8/100 (8.0%; 4.1%-15.0%) |

policy_v2 vs naive_llm, pass 1 (b = policy_v2 only, c = naive_llm only; exact McNemar p): wrong_ungrounded: b = 1, c = 3, p = 0.625; pooled diff -4.0 pp [-12.0, +4.0]; wrong_grounded: b = 1, c = 0, p = 1.000; pooled diff +3.0 pp [+0.0, +8.0]; abstain_or_parse_fail: b = 1, c = 0, p = 1.000; pooled diff +2.0 pp [+0.0, +6.0].

## Sensitivity: the same class counts with the strict page-id test (shown for transparency only)

`wrong_ungrounded` and `correct_ungrounded` recomputed with the strict `retrieval_hit` (all passes pooled; rows per arm in parentheses). For the 12 Oct baseline the strict field is the grounding field, so its row is identical to the main table.

| run | arm | correct | wrong_ungrounded (passage level, main) | wrong_ungrounded (strict) | wrong_grounded (strict) | correct_ungrounded (passage level, main) | correct_ungrounded (strict) |
|---|---|---|---|---|---|---|---|
| gemini_full | policy_v2 (250) | 176 | 35 | 53 | 15 | 45 | 137 |
| gemini_full | decision_matrix (250) | 174 | 34 | 54 | 14 | 45 | 135 |
| gemini_full | naive_llm (250) | 158 | 52 | 73 | 14 | 47 | 119 |
| gemini_full | naive_informed (250) | 176 | 38 | 57 | 15 | 47 | 138 |
| local_v5 | policy_v2 (250) | 56 | 61 | 145 | 35 | 19 | 36 |
| local_v5 | decision_matrix (250) | 58 | 60 | 143 | 35 | 20 | 38 |
| local_v5 | naive_llm (250) | 61 | 70 | 144 | 35 | 20 | 41 |
| local_v5 | naive_informed (250) | 58 | 60 | 145 | 35 | 20 | 38 |
| local_v4 | policy_v2 (100) | 21 | 25 | 59 | 14 | 7 | 13 |
| local_v4 | decision_matrix (100) | 23 | 24 | 57 | 14 | 8 | 15 |
| local_v4 | naive_llm (100) | 25 | 28 | 57 | 14 | 8 | 17 |
| local_v4 | naive_informed (100) | 23 | 24 | 59 | 14 | 8 | 15 |
| local_v3 | policy_v2 (100) | 25 | 26 | 57 | 14 | 8 | 17 |
| local_v3 | decision_matrix (100) | 25 | 26 | 58 | 14 | 8 | 17 |
| local_v3 | naive_llm (100) | 24 | 30 | 60 | 14 | 8 | 16 |
| local_oct12_baseline | policy_v2 (100) | 21 | 62 | 62 | 11 | 8 | 8 |
| local_oct12_baseline | decision_matrix (100) | 21 | 62 | 62 | 11 | 8 | 8 |
| local_oct12_baseline | naive_llm (100) | 22 | 66 | 66 | 8 | 8 | 8 |

## What the data show (descriptive; the paired comparisons are secondary and uncorrected)

- **Gemini, ungrounded wrong answers (hallucination proxy):** 14.0% of policy_v2 rows against 20.8% of naive_llm rows over 5 passes (pass 1: 6/50 against 11/50; b = 0, c = 5, exact McNemar p = 0.062; pooled difference -6.8 pp, 95% CI [-14.4, -0.8]). Grounded wrong answers (13.2% vs 14.0%) and abstain/parse-failure rows (2.4% vs 2.0%) barely differ: the accuracy difference between these two arms sits almost entirely in the ungrounded class.
- **Where naive_llm's extra ungrounded answers come from:** its post-filter route returned few rows (mean 4.9 against 14.7 on pre-filter) and had ungrounded wrong answers in 25/108 rows (23.1%) against 27/142 (19.0%) on pre-filter. Of its 52 ungrounded wrong answers, **10 had 0 rows returned** (no evidence at all in the prompt, and a number was given), 5 had 1-3 rows, 5 4-7, 5 8-14 and 27 the full 15. The ungrounded rows of every deterministic arm all had 15 rows: for them "ungrounded" means exact retrieval missed some gold evidence, not that routing failed.
- **The proxy is imprecise in both directions.** `correct_ungrounded` is 18.0% of policy_v2 rows and 18.8% of naive_llm rows: many correct answers were produced although not all gold evidence units were in the prompt (a partial set can suffice, or the number is derivable elsewhere). So `wrong_ungrounded` can contain answers that are derivable from other retrieved passages; this is why the manual sample (section 7) is needed before the word hallucination is used.
- **Strict page-id test (sensitivity, not used for conclusions).** With `retrieval_hit`, 119 of the 158 correct naive_llm answers (Gemini) would be labelled ungrounded, and `wrong_ungrounded` would rise from 52 to 73. That is why the passage-level field is the grounding field.
- **Local qwen2.5:7b (v5) has a different profile:** the largest wrong class is wrong_grounded (47.6% of policy_v2 rows, 43.6% of naive_llm rows) against ungrounded 24.4% and 28.0%; abstain/parse-failure 5.6% and 4.0%. Most local errors occur with the gold evidence in the prompt. The policy_v2 vs naive_llm differences in these classes are small; their pooled 95% CIs include 0 (wrong_ungrounded, wrong_grounded) or have 0 as the lower bound (abstain_or_parse_fail), table above.
- **12 Oct baseline:** classified with the strict field (only field available); its rows do not log `rows_returned`, so its row counts are shown as "not logged"; its ungrounded rates are not comparable with the other runs'.
- Models are never pooled; the five local/Gemini runs are separate analyses; v3, v4 and v5 share inputs (v4 pass 1 = v5 pass 1) and are not independent.

## 7. Blind manual validation sample (not yet labelled)

Gemini full run, pass 1, all arms; seed 20261023; **40 rows** (20 `wrong_ungrounded`, 20 `wrong_grounded`; up to 20 of each, drawn at random and shuffled). `labelling_sheet.csv` has `sample_id`, `question`, `gold_answer`, `model_answer` (raw output) and the full text of every retrieved passage in prompt order; it does not contain the proxy class, the arm or the route. `labelling_key.csv` (separate) maps `sample_id` to query id, arm, pass and proxy class. Labels to be entered by the user: **S** = the answer number appears in the retrieved text; **C** = the answer can be calculated from numbers in the retrieved text; **N** = not supported by the retrieved text. The confusion table (proxy class vs human label, N = unsupported, S/C = supported) is **not** computed until the labels arrive.
