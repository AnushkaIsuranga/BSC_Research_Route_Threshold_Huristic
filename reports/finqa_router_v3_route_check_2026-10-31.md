# Phase E router on the frozen 50 FinQA questions: route check (read-only)

Read-only check: no retrieval, no model calls, no paid calls, no timed measurements; the database session was set to read-only. Script `src/phase_e_router/finqa_route_check.py`; outputs `outputs/finqa_router_v3_route_check_2026-10-31/` (`route_check.csv`, `meta.json`; checksummed).

## Method

- Questions: the frozen 50 (`outputs/phase2_selection_output/finqa_phase2_selected_50_20260819_140501.csv`). Filter per question: ticker and year from the question id (`extract_ticker_year`), applied as `metadata->>'ticker' = %s AND metadata->>'year' = %s`.
- Table `finqa_evidence_qwen3` (the table of the frozen Gemini run): reltuples 35,873 (actual rows 35,862); planner statistics exist for the `metadata` column as a whole, but there are no statistics on the expressions `metadata->>'ticker'` / `metadata->>'year'` and no extended statistics.
- Router path, as in `retriever.estimate()` / `_band_decision()`: `EXPLAIN (FORMAT JSON) SELECT 1 FROM finqa_evidence_qwen3 WHERE <filter>`, s_est = Plan Rows / reltuples (`policy_v3.estimate_selectivity`); band by `policy_v3.decide_band` with **T = 0.0712** (`config/policy_v3_hm.json`, T_default): exact below T/2 = 0.0356, iterative above 2T = 0.1424, capped count (cap floor(T x 35,873) + 1 = 2,554) in between.
- Exact selectivity: the existing `exact_selectivity()` (it counts on `finqa_evidence`); the same count on `finqa_evidence_qwen3` gives identical matching rows for all 50 questions.

## Results

| # | question | rows matching | exact s | Plan Rows | planner estimate | estimate / exact | count used | route |
|---|---|---|---|---|---|---|---|---|
| 1 | ADI/2011/page_61.pdf-1 | 52 | 0.00145 | 1 | 0.000028 | 0.0192 | no | exact |
| 2 | CDW/2015/page_70.pdf-1 | 166 | 0.00463 | 1 | 0.000028 | 0.0060 | no | exact |
| 3 | DG/2005/page_44.pdf-3 | 93 | 0.00259 | 1 | 0.000028 | 0.0107 | no | exact |
| 4 | HIG/2011/page_53.pdf-3 | 136 | 0.00379 | 1 | 0.000028 | 0.0074 | no | exact |
| 5 | TMUS/2017/page_29.pdf-3 | 116 | 0.00323 | 1 | 0.000028 | 0.0086 | no | exact |
| 6 | HIG/2004/page_140.pdf-1 | 159 | 0.00443 | 1 | 0.000028 | 0.0063 | no | exact |
| 7 | V/2010/page_28.pdf-1 | 75 | 0.00209 | 1 | 0.000028 | 0.0133 | no | exact |
| 8 | EMR/2017/page_78.pdf-2 | 70 | 0.00195 | 1 | 0.000028 | 0.0143 | no | exact |
| 9 | C/2009/page_243.pdf-1 | 265 | 0.00739 | 1 | 0.000028 | 0.0038 | no | exact |
| 10 | MRO/2004/page_125.pdf-1 | 156 | 0.00435 | 1 | 0.000028 | 0.0064 | no | exact |
| 11 | MO/2016/page_19.pdf-2 | 144 | 0.00402 | 1 | 0.000028 | 0.0069 | no | exact |
| 12 | MO/2016/page_19.pdf-1 | 144 | 0.00402 | 1 | 0.000028 | 0.0069 | no | exact |
| 13 | INTC/2015/page_41.pdf-3 | 580 | 0.01617 | 1 | 0.000028 | 0.0017 | no | exact |
| 14 | AAL/2014/page_15.pdf-1 | 132 | 0.00368 | 1 | 0.000028 | 0.0076 | no | exact |
| 15 | ECL/2016/page_52.pdf-3 | 164 | 0.00457 | 1 | 0.000028 | 0.0061 | no | exact |
| 16 | ECL/2016/page_52.pdf-2 | 164 | 0.00457 | 1 | 0.000028 | 0.0061 | no | exact |
| 17 | MRO/2003/page_45.pdf-2 | 213 | 0.00594 | 1 | 0.000028 | 0.0047 | no | exact |
| 18 | HOLX/2008/page_143.pdf-1 | 70 | 0.00195 | 1 | 0.000028 | 0.0143 | no | exact |
| 19 | ABMD/2007/page_78.pdf-1 | 156 | 0.00435 | 1 | 0.000028 | 0.0064 | no | exact |
| 20 | TFX/2017/page_78.pdf-1 | 84 | 0.00234 | 1 | 0.000028 | 0.0119 | no | exact |
| 21 | SLG/2001/page_48.pdf-3 | 123 | 0.00343 | 1 | 0.000028 | 0.0081 | no | exact |
| 22 | GS/2017/page_179.pdf-4 | 440 | 0.01227 | 1 | 0.000028 | 0.0023 | no | exact |
| 23 | MRO/2007/page_136.pdf-1 | 60 | 0.00167 | 1 | 0.000028 | 0.0167 | no | exact |
| 24 | CME/2010/page_69.pdf-4 | 550 | 0.01534 | 1 | 0.000028 | 0.0018 | no | exact |
| 25 | AMT/2012/page_144.pdf-2 | 185 | 0.00516 | 1 | 0.000028 | 0.0054 | no | exact |
| 26 | DVN/2015/page_79.pdf-2 | 87 | 0.00243 | 1 | 0.000028 | 0.0115 | no | exact |
| 27 | GRMN/2008/page_85.pdf-2 | 92 | 0.00257 | 1 | 0.000028 | 0.0109 | no | exact |
| 28 | HWM/2018/page_96.pdf-2 | 20 | 0.00056 | 1 | 0.000028 | 0.0500 | no | exact |
| 29 | AMT/2016/page_49.pdf-3 | 204 | 0.00569 | 1 | 0.000028 | 0.0049 | no | exact |
| 30 | IP/2006/page_75.pdf-2 | 697 | 0.01944 | 1 | 0.000028 | 0.0014 | no | exact |
| 31 | PNC/2014/page_111.pdf-1 | 74 | 0.00206 | 1 | 0.000028 | 0.0135 | no | exact |
| 32 | IP/2006/page_38.pdf-2 | 697 | 0.01944 | 1 | 0.000028 | 0.0014 | no | exact |
| 33 | IP/2006/page_75.pdf-1 | 697 | 0.01944 | 1 | 0.000028 | 0.0014 | no | exact |
| 34 | AAPL/2004/page_68.pdf-1 | 32 | 0.00089 | 1 | 0.000028 | 0.0312 | no | exact |
| 35 | GS/2014/page_165.pdf-2 | 380 | 0.01060 | 1 | 0.000028 | 0.0026 | no | exact |
| 36 | ECL/2017/page_79.pdf-1 | 244 | 0.00680 | 1 | 0.000028 | 0.0041 | no | exact |
| 37 | ALXN/2016/page_153.pdf-2 | 136 | 0.00379 | 1 | 0.000028 | 0.0074 | no | exact |
| 38 | ALXN/2016/page_153.pdf-1 | 136 | 0.00379 | 1 | 0.000028 | 0.0074 | no | exact |
| 39 | VRTX/2006/page_111.pdf-2 | 132 | 0.00368 | 1 | 0.000028 | 0.0076 | no | exact |
| 40 | HUM/2017/page_118.pdf-3 | 44 | 0.00123 | 1 | 0.000028 | 0.0227 | no | exact |
| 41 | ETR/2017/page_143.pdf-1 | 117 | 0.00326 | 1 | 0.000028 | 0.0085 | no | exact |
| 42 | AMT/2012/page_118.pdf-4 | 185 | 0.00516 | 1 | 0.000028 | 0.0054 | no | exact |
| 43 | ETR/2013/page_21.pdf-4 | 96 | 0.00268 | 1 | 0.000028 | 0.0104 | no | exact |
| 44 | SNA/2013/page_34.pdf-2 | 240 | 0.00669 | 1 | 0.000028 | 0.0042 | no | exact |
| 45 | ETR/2004/page_212.pdf-4 | 200 | 0.00558 | 1 | 0.000028 | 0.0050 | no | exact |
| 46 | SNA/2013/page_34.pdf-3 | 240 | 0.00669 | 1 | 0.000028 | 0.0042 | no | exact |
| 47 | RSG/2018/page_94.pdf-1 | 104 | 0.00290 | 1 | 0.000028 | 0.0096 | no | exact |
| 48 | ECL/2016/page_52.pdf-4 | 164 | 0.00457 | 1 | 0.000028 | 0.0061 | no | exact |
| 49 | ETFC/2011/page_144.pdf-2 | 60 | 0.00167 | 1 | 0.000028 | 0.0167 | no | exact |
| 50 | UNP/2016/page_52.pdf-3 | 140 | 0.00390 | 1 | 0.000028 | 0.0071 | no | exact |

- Routes: **exact 50/50**, all from the band rule; the capped count was never used (every estimate is below T/2). Routing from the exact selectivity (`decide_from_full_count`) also gives exact for all 50.
- Planner estimate: **Plan Rows = 1 for every question**, so s_est = 1/35,873 = 0.000028 regardless of the filter. True matches are 20-697 rows (s 0.00056-0.01944, median 142 rows). The estimate is too low by a factor of 20 to 697 (median 142); estimate / exact is 0.0014-0.050.

## (a) Was the exact_selectivity count inside policy_v2's end-to-end latency in the frozen Gemini run?

**No.** The run (`outputs/phase_d_gemini_full_2026-10-12/`, run_meta commit `8ac3033`) calls `exact_selectivity()` once per (pass, question) before the arm loop (`comparison_runner.py` at `8ac3033`, line 277); the timer starts per arm afterwards (line 285) and `total_ms` covers only `graphs[arm].invoke(...)` (line 290). The policy_v2 graph reads the precomputed `estimated_selectivity` from the state and runs no count. `paired_stats.py` uses `total_ms` for the latency comparison, so the reported policy_v2 vs naive_llm latency difference (-2,827 ms) excludes the cost of obtaining selectivity, which naive_llm does not need. The size of that cost was not measured here (no timed measurements in this check).

## (b) Do the census function and exact_selectivity ever disagree on the 1,147 test questions?

**No.** On all 1,147 questions of `data/raw/finqa_test.json`, `exact_selectivity()` raised for none (every ticker-year filter matches at least one row), and `local_ollama_runner.estimate_selectivity()` returned exactly the same value for every question. The census's return-0-on-no-match path was never taken.

## Conclusion

The Phase E router routes all 50 frozen FinQA questions to exact, and it would do so from the true selectivities as well (all below T/2 = 0.0356), so on this set the routing outcome is correct. It is correct for an uninformative reason: with no statistics on the JSON expressions, the planner returns Plan Rows = 1 for every ticker-year filter, an underestimate of 20x to 697x (median 142x). The router's estimate therefore carries no information about the filter on FinQA; it would send any ticker-year filter to exact without reaching the capped count, however many rows it matched. On this corpus that does no harm only because no FinQA question exceeds selectivity 0.0297.
