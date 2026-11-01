# Phase F results: policy_v3.1 on the EDGAR 10-K corpus (Amendment 11)

Pre-registration: `docs/preregistration/PHASE_F_AMENDMENT_11.md` (tag `phase-f-amendment-11-2026-11-01`, `b80d4a8`), which amends Amendment 9 and its Addenda 1 and 2 (tags `phase-e-amendment-9-2026-10-30`, `-addendum-1-`, `-addendum-2-`). Data: table `edgar_chunks` (158,308 chunks, 1024-d, HNSW, L2), PostgreSQL 16.14, pgvector 0.8.3, one Windows desktop. 40 evaluation questions x 4 filter breadths = 160 pairs, k = 15.

**Section A holds the pre-registered results. Section B holds exploratory analyses that were not pre-registered; they do not change any pre-registered score, class or verdict.**

Commits: Task 4-6 code `3d98f66`; calibration `5e8777d` (tag `phase-f-calibration-edgar-2026-11-01`); VecAdvisor adapter decision `36b85a2`; comparison results `b8920e8`; label X deviation and author labels `caa2161`; answers, analysis, exploratory outputs and this report in the commit tagged `final-results-edgar-2026-11-01`.

## Deviations (all in `DEVIATION_LOG.md`, repository root)

1. **Task 3 start refused three times** by the Addendum 2 quiet rule (Kaspersky `avp` scan; means 57.5 %, 60.7 %, 59.9 %). No data collected. After the scan was stopped, the calibration restarted with the same saved grid filters and a fresh check (passed at attempt 1, mean 22.0 %).
2. **VecAdvisor candidate with `ef_search` = 1500**, outside pgvector's range (1 .. 1000), on 2 pairs (`edgar_q059|year+section`, `edgar_q060|year+section`). Decided by the author before any timed data: skipped like a new-object candidate, the next-ranked runnable candidate executed with VecAdvisor's own parameters, recorded `vecadvisor_unavailable` (reason `invalid_parameter`). Task 4 restarted with a fresh quiet check.
3. **Label X (refusal)** added to the S/C/N validation labels by the author, recorded and committed (`caa2161`) before any statistic was computed from the labels. X rows are reported separately and excluded from the S/C/N agreement.

The prompt for this evaluation named `docs/preregistration/DEVIATION_LOG.md`; the log is at the repository root and was appended there (moving files was not allowed).

## A. Pre-registered results

### A1. Task 3: calibration (1,040 items, 0 errors, 31.6 min; quiet check 22.0 %)

Pass rule (Amendment 9, quoted in Amendment 11 section 3; recall@15 replaces recall@10 per difference (4)): mean recall >= 0.90 and median of the 20 per-vector medians <= 500 ms, all 20 vectors valid.

| cell | s | exact recall@15 / ms | iterative + guard recall@15 / ms | tuned + guard recall@15 | exact passes | iterative + guard passes |
|---|---|---|---|---|---|---|
| g00 | 0.00015 | 1.000 / 0.2 | 1.000 / 192.0 | 0.900 | yes | yes |
| g01 | 0.00095 | 1.000 / 1.0 | 0.923 / 185.8 | 0.993 | yes | yes |
| g02 | 0.0106 | 1.000 / 9.9 | 0.890 / 108.4 | 0.957 | yes | no |
| g03 | 0.0483 | 1.000 / 47.1 | 0.950 / 3.6 | 0.950 | yes | yes |
| g04 | 0.1063 | 1.000 / 152.1 | 0.907 / 4.6 | 0.907 | yes | yes |
| g05 | 0.2037 | 1.000 / 316.1 | 0.873 / 1.5 | 0.873 | yes | no |
| g06 | 0.2140 | 1.000 / 330.8 | 0.917 / 2.5 | 0.917 | yes | yes |
| g07 | 0.2317 | 1.000 / 193.0 | 0.893 / 2.5 | 0.893 | yes | no |
| g08 | 0.2601 | 1.000 / 215.5 | 0.893 / 2.7 | 0.893 | yes | no |
| g09 | 0.2991 | 1.000 / 242.6 | 0.883 / 2.5 | 0.883 | yes | no |
| g10 | 0.3290 | 1.000 / 268.0 | 0.853 / 1.8 | 0.853 | yes | no |
| g11 | 0.3787 | 1.000 / 297.2 | 0.930 / 1.4 | 0.930 | yes | yes |
| g12 | 0.4709 | 1.000 / 336.5 | 0.887 / 1.7 | 0.887 | yes | no |

Exact passes at every grid point (s_exact_max = 0.4709). The iterative route fails at the largest grid point, so no s_iter_min exists and there is **no safe interval**. Amendment 11 section 3: "If the procedure gives no interval, the empty-interval rule quoted above applies (it is Amendment 9's rule)". The rule, verbatim from the tagged Amendment 9 text: "Empty interval (lower endpoint >= s_exact_max) -> report the gap; T = the grid point with the fewest failing cells under "exact if s < T else iterative + guard" (ties -> smaller)." Failing cells by T fall from 7 at g00 to 1 at both 0.3787 and 0.4709; the tie goes to the smaller value. **T_default = T_tuned = 0.3787** (`config/policy_v3_1_edgar.json`). (See B2 for the wording of the rule.)

Routes decided for the 160 evaluation pairs: router (edgar T) exact on 160; router_hmT (H&M T = 0.0712) exact 92, iterative 68 (year+section 30, section 38). The two routers agree on 92 pairs.

### A2. Task 4: retrieval comparison (3,040 items, 0 errors, 9 early stops, 43.1 min; quiet check 16.5 %)

All breadths (160 pairs per mode). Latency = end-to-end wall-clock of `retrieve()`, median of 5 timed runs per pair, then median over pairs; llm_router and VecAdvisor decision time excluded (reported separately).

| mode | pairs recall@15 >= 0.90 | mean recall@15 | gold hit | median ms | under-filled | routes |
|---|---|---|---|---|---|---|
| router | 160 | 1.000 | 0.900 | 38.7 | 7 | exact 160 |
| router_tuned | 160 | 1.000 | 0.900 | 40.3 | 7 | exact 160 |
| router_no_guard | 160 | 1.000 | 0.900 | 33.7 | 7 | exact 160 |
| router_always_count | 160 | 1.000 | 0.900 | 34.4 | 7 | exact 160 |
| router_plus_probe | 160 | 1.000 | 0.900 | 49.8 | 7 | exact 160 |
| always_exact | 160 | 1.000 | 0.900 | 20.8 | 7 | exact 160 |
| llm_router | 160 | 1.000 | 0.900 | 22.1 | 7 | exact 160 |
| vbase | 146 | 0.965 | 0.894 | 15.6 | 7 | exact 130, iterative 30 |
| fixed_t_0_1 | 143 | 0.958 | 0.894 | 22.5 | 7 | exact 120, iterative 40 |
| retry_exact | 138 | 0.950 | 0.900 | 15.9 | 7 | hnsw 54, hnsw+exact 106 |
| router_hmT | 131 | 0.936 | 0.888 | 22.1 | 7 | exact 92, iterative 68 |
| local_probe | 128 | 0.933 | 0.888 | 19.1 | 7 | exact 74, iterative 86 |
| vecadvisor | 127 | 0.930 | 0.888 | 9.0 | 8 | exact 83, iterative 74, hnsw 3; 49 unavailable |
| milvus | 127 | 0.930 | 0.888 | 15.4 | 7 | exact 84, iterative 76 |
| planner_iterative | 126 | 0.930 | 0.888 | 9.3 | 7 | planner_iterative 160 |
| qdrant | 126 | 0.930 | 0.888 | 15.9 | 7 | exact 82, iterative 78 |
| iterative_tuned | 113 | 0.908 | 0.894 | 11.9 | 7 | 9 early stops, guard fired 7 |
| always_iterative | 103 | 0.891 | 0.894 | 11.3 | 9 | iterative 160 |
| default_hnsw | 34 | 0.538 | 0.781 | 9.1 | 106 | hnsw 160 |

The 7 under-filled pairs in every exact mode are filters matching fewer than 15 rows. Router vs always_exact, median ms by breadth: cik+year+section 22.1 vs 7.2; cik+year 20.4 vs 8.3; year+section 181.5 vs 162.6; section 287.2 vs 267.2. Full tables: `outputs/edgar_retrieval_comparison_2026-11-01/summary_by_mode_breadth.csv`.

### A3. Task 5: answer run

Pilot of 5 calls (excluded): mean USD 0.00443 per call, 355 unique prompts per pass. Projections: 5 passes USD 7.87, 3 passes USD 4.72, 1 pass USD 1.57. By the pre-registered rule ("the largest of 5, 3 or 1 passes whose projection is **at most USD 4.50** and keeps the session total under USD 6.00"), **1 pass** was run (see B3). 355 calls, 0 errors, all finish reason STOP. Answers are reused across modes that returned the identical passage list.

**Session spend: USD 1.4633** of the USD 6.00 cap (llm_router decisions 0.0447, pilot 0.0222, main pass 1.3963), `outputs/edgar_cost_log_2026-11-01/cost_log.jsonl`.

### A4. Task 6: accuracy and classes (1 pass, primary scoring rule)

Rates per pair; cluster-bootstrap 95 % CI over the 40 questions (10,000 resamples, seed 20261104).

| mode | accuracy (95 % CI) | abstained | wrong_in_context | wrong_not_in_context |
|---|---|---|---|---|
| router (= router_tuned, router_no_guard, router_always_count, router_plus_probe, always_exact, llm_router) | 0.906 [0.838, 0.963] | 0.006 | 0.069 | 0.019 |
| retry_exact | 0.906 [0.844, 0.956] | 0.000 | 0.081 | 0.013 |
| vbase | 0.900 [0.831, 0.956] | 0.006 | 0.075 | 0.019 |
| fixed_t_0_1 | 0.900 [0.831, 0.956] | 0.000 | 0.081 | 0.019 |
| router_hmT, vecadvisor, milvus, qdrant, local_probe, planner_iterative | 0.894 [0.825, 0.950] | 0.000 | 0.081 | 0.025 |
| iterative_tuned, always_iterative | 0.888 [0.819, 0.944] | 0.000 | 0.088 | 0.025 |
| default_hnsw | 0.800 [0.681, 0.906] | 0.013 | 0.100 | 0.088 |

Router accuracy by breadth: cik+year+section 1.000, cik+year 0.925, year+section 0.875, section 0.825 (default_hnsw 0.800, 0.825, 0.800, 0.775). Full table: `outputs/edgar_analysis_2026-11-01/answers_by_mode_breadth.csv`.

### A5. Predictions (Amendment 11 section 6)

| | prediction | result | verdict |
|---|---|---|---|
| P1 | router recall@15 >= 0.90 on >= 95 % of pairs | 160 / 160 (40 / 40 at each breadth) | **held** |
| P2 | router accuracy non-inferior to always_exact (CI lower bound > -0.10) | difference 0.000, CI [0.000, 0.000] | **held** (trivially: both routed all 160 pairs to exact, so prompts and answers were identical) |
| P3 | router more accurate than default_hnsw, exact McNemar on pass 1, p < 0.05 with more router-only-correct pairs | 145 vs 128 correct; b = 19, c = 2; p = 0.00022 | **held** |
| P4 | router `wrong_not_in_context` rate lower than default_hnsw's (descriptive, with CI) | 0.019 vs 0.088; difference -0.069, CI [-0.138, -0.013] | **held** |
| P5 | router median latency below always_exact's at year+section and section (descriptive) | 181.5 vs 162.6 ms; 287.2 vs 267.2 ms | **not held** |

Transfer (reported under section 6): router minus router_hmT accuracy +0.013, CI [-0.019, 0.056]; same route on 92 / 160 pairs.

### A6. Validation labels and proxy agreement

40 pass-1 wrong answers (seed 20261103): 14 from router (all of its pass-1 wrong answers) and 26 from default_hnsw (the remainder filled from the other mode, as specified). **Labels were drafted by the AI assistant and confirmed or changed by the author (one change: L13 S to N).** The author's file is committed as saved (`outputs/edgar_analysis_review_2026-11-01/label_sheet_author.csv`); only its `sample_id`, `author_label` and `author_note` columns were used, joined on `sample_id` to the original sheet (all 40 ids matched; every label in S, C, N, X): `outputs/edgar_analysis_labels_joined_2026-11-01/label_sheet_joined.csv`.

Labels: S 8, C 0, N 14, X 18. Confusion of the automatic class against the checked label:

| automatic class \ label | S | C | N | X | total |
|---|---|---|---|---|---|
| wrong_in_context | 8 | 0 | 2 | 16 | 26 |
| wrong_not_in_context | 0 | 0 | 12 | 2 | 14 |
| total | 8 | 0 | 14 | 18 | 40 |

Agreement on the 22 S/C/N rows (N vs `wrong_not_in_context`, S and C = supported): **20 / 22 = 0.909** (router 6 / 7, default_hnsw 14 / 15). Every answer the proxy flagged was labelled N (12 / 12); the proxy flagged 12 of the 14 N rows. Both misses are `$0` answers matched by rule A to an unrelated zero in a passage (L13, another company's unbilled revenue; L32, an unrelated sentence). The 18 X rows (refusals) are left out of the agreement; 16 of them were classed `wrong_in_context` and 2 `wrong_not_in_context`.

## B. Exploratory results (not pre-registered)

Everything in this section is descriptive and exploratory. The pre-registered scores, classes and P1-P5 verdicts above stay as computed.

### B1. Router decision overhead (from the route traces)

The timed route traces hold the stats check, planner estimate and capped count timings. Per pair, median over the 5 timed traces; then the median over the 40 pairs of each breadth (`outputs/edgar_report_inputs_2026-11-01/decision_overhead.json`):

| breadth | stats check ms | estimate ms | capped count ms (pairs) | decision total ms | exact route ms | router ms | always_exact ms | router - always_exact ms |
|---|---|---|---|---|---|---|---|---|
| cik+year+section | 10.3 | 4.0 | none (0) | 14.4 | 6.6 | 22.1 | 7.2 | +14.9 |
| cik+year | 8.1 | 4.0 | none (0) | 12.2 | 7.1 | 20.4 | 8.3 | +12.1 |
| year+section | 8.5 | 3.9 | none (0) | 12.5 | 167.5 | 181.5 | 162.6 | +19.0 |
| section | 6.4 | 3.8 | 8.4 (30 of 40) | 18.0 | 266.0 | 287.2 | 267.2 | +20.0 |

The 12-20 ms decision step accounts for the router's latency gap to always_exact: the router chose exact everywhere, so it paid for the decision and then ran the same query. At section breadth 30 pairs fell in the middle band and needed the capped count; all of them then went to exact.

### B2. The empty-interval rule on EDGAR

The empty-interval rule's wording ("lower endpoint >= s_exact_max") assumes a lower endpoint exists. On EDGAR none existed, because the iterative route failed at the largest grid point, so no s_iter_min could be found. The rule was applied through Amendment 11 section 3 ("If the procedure gives no interval, the empty-interval rule quoted above applies") and the behaviour of the frozen `src/phase_e_router/policy_v3.py`, which treats a missing s_iter_min as an empty interval. The 1-failing-cell tie between 0.3787 and 0.4709 was resolved to the smaller value, as the rule says.

### B3. One answer pass

The answer run used **1 pass**, by the pre-registered cost rule (3 passes were projected at USD 4.72, above the USD 4.50 answer limit). The FinQA answer runs used 5 passes. EDGAR accuracy estimates therefore carry no averaging over generation noise. Because P2 compares identical prompts, it is unaffected; P3 is defined on pass 1 in any case.

### B4. VecAdvisor's ef_search recommendation

VecAdvisor 0.1.0a6 recommended `ef_search = 1500`, which pgvector 0.8.3 rejects (range 1 .. 1000), on 2 of the 160 pairs (deviation 2). VecAdvisor was unavailable on 49 pairs in total: 47 because its top candidate needed a new database object (partial or partition index), and 2 because of this invalid parameter. This is a descriptive note and is not part of any score.

### B5. Host load during the timed sessions

Readings every 5 minutes (processor counter). Readings above 40 %, with the items whose result timestamp lies within 60 s of the reading (`outputs/edgar_report_inputs_2026-11-01/host_load.json`). "Top processes" is CPU seconds since the previous reading among the five processes with the most cumulative CPU time; a short-lived process outside that list would not show.

| session | UTC | CPU % | items within 60 s | top processes (CPU s since previous reading) |
|---|---|---|---|---|
| Task 3 calibration | none above 40 % (8 readings) | | | |
| Task 4 comparison | 04:38:24 | 75.1 | 285 | com.docker.backend 43.8, claude 22.6, explorer 19.1 |
| Task 4 comparison | 04:53:43 | 42.7 | 248 | com.docker.backend 41.7, claude 17.9, Docker Desktop 15.8 |
| Task 4 comparison | 04:58:48 | 47.2 | 114 | com.docker.backend 39.1, Docker Desktop 15.5, explorer 10.6 |
| Task 4 comparison | 05:06:14 (end) | 46.7 | 56 | com.docker.backend 18.8, Docker Desktop 7.4, explorer 4.9 |

The Docker backend (which hosts PostgreSQL) is the largest consumer, so much of this load is likely the workload itself. Amendment 9 Addendum 2 defines no in-session rule, and no item was excluded.

### B6. Refusals re-scored as abstained

A refusal is an answer stating that the evidence does not contain the figure. The pre-registered class rule counts an answer as abstained only if it says "not answerable" or gives no number. Refusals such as "... during fiscal year 2018" therefore get a year (or a figure quoted inside the refusal) parsed as their answer and are classed as wrong.

**Rule** (`src/phase_f_edgar/exploratory_edgar.py`, `REFUSAL`, tested in `tests/phase_f_edgar/test_edgar_labels.py`). An answer that is not correct is re-classed as `abstained` if it matches, case-insensitively, any of:

- `(does|do) not (contain|include|provide|mention|specify|state)`
- `no mention of`
- `is not [explicitly|directly] (stated|provided|mentioned|available|specified|given|disclosed|contained)`

The rule matches 25 of the 355 distinct answers. All 25 are refusals, and every answer longer than 40 characters is one of them. Those 25 answers count as **146 of the 312 wrong answers across all modes** (136 `wrong_in_context`, 10 `wrong_not_in_context`); the earlier informal count of 136 covered only `wrong_in_context`. No correct answer matches.

| mode | accuracy | abstained (primary -> refusal rule) | wrong_in_context (refusal rule) | wrong_not_in_context (primary -> refusal rule) |
|---|---|---|---|---|
| router and its 6 identical modes | 0.906 | 0.006 -> 0.050 | 0.025 | 0.019 -> 0.019 |
| retry_exact | 0.906 | 0.000 -> 0.038 | 0.044 | 0.013 -> 0.013 |
| vbase | 0.900 | 0.006 -> 0.050 | 0.031 | 0.019 -> 0.019 |
| fixed_t_0_1 | 0.900 | 0.000 -> 0.050 | 0.031 | 0.019 -> 0.019 |
| router_hmT, vecadvisor, milvus, qdrant, local_probe, planner_iterative | 0.894 | 0.000 -> 0.050 | 0.038 | 0.025 -> 0.019 |
| iterative_tuned, always_iterative | 0.888 | 0.000 -> 0.050 | 0.044 | 0.025 -> 0.019 |
| default_hnsw | 0.800 | 0.013 -> 0.088 | 0.038 | 0.088 -> 0.075 |

By breadth, under the refusal rule (abstained / wrong_not_in_context):

| breadth | router | default_hnsw |
|---|---|---|
| cik+year+section | 0.000 / 0.000 | 0.075 / 0.125 |
| cik+year | 0.000 / 0.025 | 0.050 / 0.075 |
| year+section | 0.100 / 0.025 | 0.125 / 0.050 |
| section | 0.100 / 0.025 | 0.100 / 0.050 |

Under this rule:

- **P3** is unchanged (b = 19, c = 2, p = 0.00022), because no correct answer changes.
- **P4:** router 0.019 vs default_hnsw 0.075. The difference is -0.056, CI [-0.119, -0.006], so the direction holds.

Files: `outputs/edgar_analysis_exploratory_2026-11-01/refusal_by_mode_breadth.csv`, `refusal_rescore.json`.

### B7. Scale-aware matching

Under the primary rule (Amendment 2), a trailing scale word is stripped without rescaling. In this re-score, the answer's and the gold's first numbers are compared with their scale words applied (thousand, million, billion), using the same tolerance as the primary rule (relative 1 %). 74 answers change result (`scale_changes.csv` lists every one). They come from three (answer, gold) combinations:

| answer | gold | change | pairs (modes) |
|---|---|---|---|
| `$42.9 million` | `$42,915 thousand` | wrong_in_context -> correct | `edgar_q028\|cik+year` (all 19 modes) |
| `34,500,000` | `34.5 million` | wrong_not_in_context -> correct | `edgar_q037\|cik+year+section`, `edgar_q037\|cik+year` (default_hnsw only; 0 passages, value from the model's own knowledge) |
| `$13,060 thousand` | `$13,060` | correct -> wrong_in_context | `edgar_q015\|cik+year+section` (18 modes), `edgar_q015\|cik+year` (16), `edgar_q015\|section` (19) |

The last row is a gold artefact, not a model error. The passage states the value in thousands, but the gold "$13,060" has no scale word, so scale-aware matching marks the faithful answer wrong. Net result: router accuracy goes from 0.906 to 0.894 and default_hnsw from 0.800 to 0.813. Under scale-aware matching:

- **P3:** b = 17, c = 4, p = 0.0072, held.
- **P4:** -0.056, CI [-0.113, -0.006], held.

Unaffected by either rule:

- **L39** (`$1.564 billion` vs `$1.6 billion`, 2.3 % apart) stays wrong.
- **L21** stays wrong. Its passage supports $51.2 million, but the passage is from the 2019 10-K, while the gold $25.3 million is for 2018.

File: `scale_rescore.json`.

### B8. Pairs whose prompt held 0 passages

Only default_hnsw returned 0 rows, on 8 pairs: 4 at cik+year+section, 2 at cik+year, 1 at year+section, 1 at section. On all 8 the model still gave a number. None of these answers was a refusal or abstained, and none was correct under the primary rule. 2 of the 8 (`edgar_q037`, 34.5 million shares) are correct under scale-aware matching, with the value coming from outside the prompt. No other mode had a 0-passage prompt. File: `zero_passages.csv`.

### B9. Wrong-source and wrong-year errors in the label sample

Counted from the author's notes:

- **Wrong source:** 2 of the 8 S rows, L04 and L33. In both, the number was copied from another company's passage.
- **Wrong year:** 1 of the 8 S rows, L21. The passage is from the 2019 10-K, but the question asks about the 2018 report.
- **L13** (N after the author's change) is a coincidental `$0` from another company's note.

So 3 of the 8 "supported" wrong answers are supported only by the wrong document. File: `label_error_sources.json`.

### B10. Other notes

- **P2 is trivial on EDGAR.** At T = 0.3787 every pair is far below T/2 or in the middle band and counted. Router and always_exact therefore run the same query and send the same prompt. The non-inferiority test compares a mode with itself.
- **Calibration and evaluation filters differ.** The calibration grid uses uncorrelated cik sets; the evaluation filters are query-correlated (Amendment 11 section 7). Of router_hmT's 68 iterative pairs, 39 reached recall@15 >= 0.90 (its 92 exact pairs all did).

## Limitations

- **One calibration per dataset.** T was calibrated once per dataset (H&M, then EDGAR), and there is no tested rule for when to recalibrate. Proposed triggers, **not tested**:
  - an index rebuild or a change to HNSW parameters;
  - a PostgreSQL, pgvector or hardware change;
  - a change of embedding model, or a shift in the data distribution (large inserts or deletes that move selectivities or cluster structure);
  - a change in memory or cache sizes.
  - Monitoring signals that could prompt it: the guard firing rate, recall drift against exact search on sampled queries, exact latency approaching the budget near T, and the share of queries in the middle band.
- **The pre-registered class rule counts refusals as wrong** (B6), and **the primary scoring rule does not rescale** (B7). Both are reported here without changing any score.
- **Small samples.** One corpus, 40 questions, 1 answer pass, and one desktop. Latency was measured under the quiet rule, with the load listed in B5.
- **Model overlap.** The question-drafting and answer models are both Gemini.
- **Re-implementations.** VecAdvisor's adapter and the prior-system rules are our re-implementations.
- **Labels are not independent.** They were drafted by the AI assistant and checked by the author, not labelled blind.

## Files

| folder | content |
|---|---|
| `outputs/edgar_calibration_2026-11-01/` | Task 3 results, cell summary, calibration, route counts, quiet checks, host load |
| `outputs/edgar_retrieval_comparison_2026-11-01/` | Task 4 results, summaries, llm and VecAdvisor decisions, quiet checks, host load |
| `outputs/edgar_answers_2026-11-01/` | prompts, reuse map, pilot, pass decision, responses, run log |
| `outputs/edgar_cost_log_2026-11-01/` | session cost log |
| `outputs/edgar_analysis_2026-11-01/` | scored answers, tables by mode and breadth, predictions, transfer, label sheet and key |
| `outputs/edgar_analysis_review_2026-11-01/` | author labels as saved |
| `outputs/edgar_analysis_labels_joined_2026-11-01/` | joined label sheet |
| `outputs/edgar_analysis_exploratory_2026-11-01/` | agreement, refusal and scale re-scores, zero-passage counts, label error sources |
| `outputs/edgar_report_inputs_2026-11-01/` | decision overhead, host-load listing |

All are added to `outputs/data_checksums.json` with their line endings.
