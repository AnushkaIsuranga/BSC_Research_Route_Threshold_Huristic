# Gemini 3.8 Flash paid pilot, 2026-10-12

Pipeline check only: 5 queries (first 5 of the frozen order) x 3 arms x 1 pass. These rows are **not** part of the primary analysis. Command:

```
.venv/Scripts/python -m src.phase_d_validation.comparison_runner --model gemini-3.8-flash --correlation-level hm_clothes_0 --limit 5 --passes 1 --table finqa_evidence_qwen3 --query-embeddings outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json --expect-rows 35862 --allow-paid --budget-usd 2 --output-dir outputs/phase_d_gemini_pilot_2026-10-12
```

`run_meta.json`: k = 15, distinct = True, evidence table `finqa_evidence_qwen3`, query-embedding cache sha256 `930cadc0bdea177b0951a6891c227606cc47a3b4a1ce8c437563635f9be9ff23`, commit `7842e01` (tag `phase-d-amendment-1-filled-v2-2026-10-12`), uncommitted used files: None, run 2026-10-12T13:23:36.124556+00:00 to 2026-10-12T13:24:26.453429+00:00 UTC (50 s). 15 rows, 20 Gemini calls (5 router + 15 answer), 0 errors.

## Every call (router raw output, answer raw output, parsed, correct, finish reason, tokens, cost, latency)

| query | arm (position) | route | router raw output | answer raw output | parsed | gold | correct | parse failure | finish (router/answer) | tokens prompt/cand/thought, router | tokens prompt/cand/thought, answer | cached | cost USD router + answer | rows returned | ms db / router / gen / total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ADI/2011/page_61.pdf-1 | naive_llm (1) | post-filter | `{"route": "post-filter", "reason": "No specific company ticker or fiscal year is provided in the query, so a global vect` | `$18.75 million` | None | 18.8 | 0 | 1 | STOP / STOP | 122/37/171 | 427/7/74 | 0 | 0.000871 + 0.000624 | 3 | 120 / 4943 / 2212 / 7281 |
| ADI/2011/page_61.pdf-1 | decision_matrix (2) | pre-filter | `` | `$18.75 million` | None | 18.8 | 0 | 1 | - / STOP | - | 1119/7/102 | 0 | - + 0.001248 | 15 | 14 / 0 / 1759 / 1775 |
| ADI/2011/page_61.pdf-1 | policy_v2 (3) | exact | `` | `$18.75 million` | None | 18.8 | 0 | 1 | - / STOP | - | 1119/7/0 | 0 | - + 0.000865 | 15 | 15 / 0 / 1527 / 1544 |
| CDW/2015/page_70.pdf-1 | decision_matrix (1) | pre-filter | `` | `$ -61.1` | -61.1 | -84 | 0 | 0 | - / STOP | - | 939/6/0 | 0 | - + 0.000727 | 15 | 18 / 0 / 1164 / 1184 |
| CDW/2015/page_70.pdf-1 | policy_v2 (2) | exact | `` | `$ -61.1` | -61.1 | -84 | 0 | 0 | - / STOP | - | 939/6/499 | 0 | - + 0.002598 | 15 | 12 / 0 / 5145 / 5159 |
| CDW/2015/page_70.pdf-1 | naive_llm (3) | post-filter | `{"route": "post-filter", "reason": "No specific company ticker or fiscal year metadata was mentioned in the query to pre` | `-61.1` | -61.1 | -84 | 0 | 0 | STOP / STOP | 109/32/0 | 175/5/318 | 0 | 0.000202 + 0.001342 | 2 | 124 / 1580 / 3516 / 5222 |
| DG/2005/page_44.pdf-3 | naive_llm (1) | pre-filter | `{"route": "pre-filter", "reason": "Pre-filtering is ideal because the query specifies a narrow, well-defined time range ` | `$0.5 million` | None | 12.1 | 0 | 1 | STOP / STOP | 112/42/0 | 892/5/189 | 0 | 0.000241 + 0.001396 | 15 | 16 / 1985 / 2913 / 4916 |
| DG/2005/page_44.pdf-3 | decision_matrix (2) | pre-filter | `` | `$0.5 million` | None | 12.1 | 0 | 1 | - / STOP | - | 892/5/169 | 0 | - + 0.001321 | 15 | 11 / 0 / 2250 / 2262 |
| DG/2005/page_44.pdf-3 | policy_v2 (3) | exact | `` | `-$0.5 million` | None | 12.1 | 0 | 1 | - / STOP | - | 892/5/314 | 0 | - + 0.001865 | 15 | 12 / 0 / 3002 / 3015 |
| HIG/2011/page_53.pdf-3 | decision_matrix (1) | pre-filter | `` | `$39` | 39.0 | 307 | 0 | 0 | - / STOP | - | 943/3/120 | 0 | - + 0.001169 | 15 | 17 / 0 / 2136 / 2155 |
| HIG/2011/page_53.pdf-3 | policy_v2 (2) | exact | `` | `$39` | 39.0 | 307 | 0 | 0 | - / STOP | - | 943/3/141 | 0 | - + 0.001247 | 15 | 12 / 0 / 2567 / 2580 |
| HIG/2011/page_53.pdf-3 | naive_llm (3) | post-filter | `{"route": "post-filter", "reason": "The query does not specify a specific company ticker or fiscal year metadata filter.` | `$39` | 39.0 | 307 | 0 | 0 | STOP / STOP | 126/28/0 | 820/3/163 | 0 | 0.000199 + 0.001237 | 13 | 130 / 1139 / 3828 / 5099 |
| TMUS/2017/page_29.pdf-3 | naive_llm (1) | post-filter | `{"route": "post-filter", "reason": "No specific company ticker or fiscal year was specified in the query to pre-filter o` | `83333.33` | 83333.33 | 83333 | 1 | 0 | STOP / STOP | 111/31/0 | 339/8/130 | 0 | 0.000200 + 0.000772 | 5 | 87 / 1692 / 2110 / 3890 |
| TMUS/2017/page_29.pdf-3 | decision_matrix (2) | pre-filter | `` | `83333.33` | 83333.33 | 83333 | 1 | 0 | - / STOP | - | 822/8/48 | 0 | - + 0.000827 | 15 | 16 / 0 / 1714 / 1732 |
| TMUS/2017/page_29.pdf-3 | policy_v2 (3) | exact | `` | `83333.33` | 83333.33 | 83333 | 1 | 0 | - / STOP | - | 822/8/54 | 0 | - + 0.000849 | 15 | 11 / 0 / 2027 / 2039 |

## Totals

- **Total cost: USD 0.019802** (cap 2.00; the runner's cumulative counter agrees: 0.019802). Largest single call USD 0.002598 (0.26 cents).
- Cost per query per arm: naive_llm USD 0.001417; decision_matrix USD 0.001058; policy_v2 USD 0.001485 (naive includes its router call: router part USD 0.000343 per query).
- Thinking tokens per call (thinking_level LOW): mean 125, median 111, min 0, max 499; 6 of 20 calls used 0. Router calls mean 34, answer calls mean 155. Thinking is 47% of the total cost.
- Truncations (finish reason MAX_TOKENS): **0** of 20 (all STOP). Empty outputs: 0. Route (JSON) parse failures: 0 of 5. Answer parse failures: 2 per arm (see flags).
- Naive router: post-filter on 4 of 5 queries (80%); P-a was 10%.
- traffic_type: ON_DEMAND on all 20 calls. Cached tokens: 0 on all calls.
- Latency (ms, medians of 5): total naive 5099, DM 1775, policy_v2 2580; naive router call median 1692. Median generation_ms by arm position: position 1: 2136, position 2: 2250, position 3: 3002 (n = 5 each; no first-position slowdown visible, and no cached tokens).

## Extrapolated cost of the full run (50 queries x 3 arms x 2 passes = 300 arm-runs)

Pilot: USD 0.019802 over 15 arm-runs = USD 0.001320 per arm-run. 300 x 0.001320 = **USD 0.40** (per arm: 100 arm-runs each; DM 0.11 + policy_v2 0.15 + naive 0.14). Budget cap USD 10. The estimate rests on 5 queries and a thinking-token count that varies from 0 to 499 per call, so treat it as +/- a factor of 2 or 3, still far below the cap.

## Flags (B3)

1. **Answer format vs. the frozen scoring rule (would affect the full run).** Gemini wrote units despite the instruction to return only the number: `$18.75 million` (ADI, all 3 arms) and `$0.5 million` / `-$0.5 million` (DG). The frozen rule (Amendment 1 section 6) treats text such as `5 million` as unparseable: scored wrong and flagged `parse_failure` (6 of 15 rows). ADI's `18.75` equals the gold `18.8` within tolerance, so the rule scored a numerically correct answer wrong in all three arms (3 label flips if a trailing `million` were ignored; the DG answers are wrong either way). qwen2.5:7b did not do this. It affects all three arms alike, so a paired comparison stays valid, but absolute accuracy is understated and the effect depends on the model's formatting habit. No change was made; changing the rule or the answer prompt needs a documented amendment before the full run.
2. **Thinking length is not controlled by `thinking_level=LOW`** and is not deterministic at temperature 0: for the identical prompt on CDW/2015 the DM answer used 0 thinking tokens and the policy_v2 answer 499; DM 102 vs policy_v2 0 on ADI. Cost and latency per call therefore vary by a factor of about 3 for the same input. (Answers differed too: DG `$0.5 million` vs `-$0.5 million`.)
3. **Naive router chose post-filter on 4 of 5 queries (P-a was 10%, range 0-25%).** Its stated reasons are all of the form "no company ticker or fiscal year was specified in the query": the router prompt gives only the question, so the router cannot know that the filter always exists. Pilot only; P-a is not changed. For the full run this predicts a post-filter share far above P-a and, on those queries, under-filled prompts (rows returned 3, 2, 13, 5 of 15).
4. **No sign of looping, repeated text or empty output** at temperature 0: all answers are 3-8 tokens, all 20 finish reasons are STOP, no empty text.
5. Temperature 0 was accepted (no API error). All calls ON_DEMAND. Cost per call is at most 0.26 cents.
6. Accuracy in the pilot is 1/5 per arm (TMUS correct in all three; CDW -61.1 vs gold -84 and HIG 39 vs 307 wrong in all arms, as with qwen2.5:7b). 5 queries say nothing about accuracy.

## To check tomorrow

Billing console, Billing > Reports: expected charge for this pilot about USD 0.02 (computed from the token counts above at 0.75 / 3.75 per 1M tokens). Compare with what the console shows.
