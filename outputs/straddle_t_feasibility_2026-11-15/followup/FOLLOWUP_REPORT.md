# Straddle-T Feasibility Follow-up Report (2026-11-15)

## 1. Integrity Check on Modified Files
- Compared against tag `final-results-edgar-2026-11-01` (same diff as `HEAD`).
- `src/phase_a_sweep/logger.py` (mtime `2026-09-30 10:10:26`): **code change** (36 lines changed: `results_file` arg, `log_baseline` signature/keys, Windows `os.replace` retry loop, 5-tuple `completed`).
- `src/phase_a_sweep/sweep_orchestrator.py` (mtime `2026-09-30 10:01:14`): **code change** (8 lines changed: `SET hnsw.iterative_scan = off;`, updated `log_baseline` & `completed` 5-tuple).
- `outputs/sweep_results.jsonl` (mtime `2026-09-04 08:36:44`): **rewritten data change** (1,100 insertions, 1,100 deletions). SHA-256 `daacb6842222e7e42ffcf080c2c5ada503fa03bee6cdffa345bd89fa68c41249`; **no** entry in `outputs/data_checksums.json`.
- `notebooks/correlation_verification.ipynb` (mtime `2026-08-22 10:24:11`): **notebook code/output change** (281 insertions, 20 deletions; LF/CRLF warning).
- `Coding_TODO_List.md` (mtime `2026-11-15 08:21:14`): **ignored** via `.gitignore:27` (untracked); earlier edit landed at lines 95–103.

## 2. EDGAR `far_above` (`T_edgar`) and FinQA `s > 0.95`
See `far_above_and_high_s.csv`.
- `edgar_chunks` has **1** filter with `s = 1.0` (`fiscal_year IN (2018, 2019, 2020)`, `158,308` rows) and **2** at `s = 0.807672` (`section IN ('1A', '7', '8')` and its intersection with all 3 years).
- `finqa_evidence` has **9** filters with `s > 0.95`, including **1** with `s = 1.0` (`(metadata->>'year')::int BETWEEN 1999 AND 2019`, `35,862` rows).

## 3. Per-Question Gold-Containment Counts
See `per_question_gold_containment.csv`.

## 4. Gaps in `s` > 0.02 and Filters Within 25% of `T`
See `s_gaps.csv`.
- `edgar_chunks` within 25% of `T_edgar` (`[0.284019, 0.473365]`): **45** usable filters.
- `edgar_chunks` within 25% of `T_hm` (`[0.053394, 0.088990]`): **14** usable filters.
- `finqa_evidence` within 25% of `T_hm` (`[0.053394, 0.088990]`): **80** usable filters.
- `finqa_evidence` within 25% of `T_edgar` (`[0.284019, 0.473365]`): **49** usable filters.

## 5. Constructed Filter Rules by Band
See `constructed_rules_by_band.csv`.
