# Amendment 8 Stage 1: RAGAS faithfulness judge vs the 40 labelled rows, 2026-10-23

Governed by `docs/preregistration/PHASE_D_AMENDMENT_8.md` (tag `phase-d-amendment-8-2026-10-23`, committed before any judge call). RAGAS 0.4.3 `Faithfulness` (LLM-based only), judge `openai/gpt-oss-120b-maas` on Vertex AI us-central1, temperature 0, one attempt per call, telemetry off. Reference labels: **model-drafted labels verified by the author** (N = unsupported; S and C = supported). Outputs `outputs/ragas_judge_2026-10-23/` (`judged_stage1.jsonl`, `judge_calls_stage1.jsonl`, `judge_run_stage1.json`, `stage1_agreement.json`). Run 18:06-18:13 UTC.

## Verdict: the gate fails, Stage 2 is not run

**Per-row Cohen's kappa = 0.258** (95% bootstrap CI 0.075-0.483), below the pre-registered gate of 0.4. As registered, Stage 2 (all 1,000 rows) is **not run** and the work stops here.

## Calls and spend

40 rows, 79 calls, 0 call errors. **3 rows ended in `judge_error`** (recorded, not retried): S040 (C) and S036 (N) truncated at the 4,096-token output limit (`finish_reason = length`); S034 (C) returned JSON with a wrong top-level key (`final{`), which failed the RAGAS schema. 0 rows had no statements. Below the setup-failure rule (5 of the first 20). Tokens: 98,280 input, 37,601 output (reasoning tokens not reported separately by the endpoint). **Tracked spend USD 0.0373** at the conservative USD 0.15 / 0.60 per 1M rate; at the third-party Vertex rate (USD 0.09 / 0.36) about USD 0.022. No other paid call was made today.

## Agreement

Primary: the 3 `judge_error` rows are excluded (37 rows; class balance **5 N vs 32 S/C**). Sensitivity: errors counted as unsupported (40 rows; **6 N vs 34 S/C**).

| unit | n | label balance (unsupported / supported) | accuracy (95% CI) | Cohen's kappa (95% CI) |
|---|---|---|---|---|
| per row, primary | 37 | 5 / 32 | 0.622 (0.461-0.759) | **0.258** (0.075-0.483) |
| per distinct question, primary | 17 | 3 / 14 | 0.647 (0.413-0.827) | 0.320 (0.000-0.658) |
| per row, errors as unsupported | 40 | 6 / 34 | 0.600 (0.446-0.737) | 0.252 (0.083-0.463) |
| per distinct question, errors as unsupported | 17 | 3 / 14 | 0.647 (0.413-0.827) | 0.320 (0.000-0.658) |

Per row (primary): label supported / judge supported 18, label supported / judge unsupported **14**, label unsupported / judge supported **0**, label unsupported / judge unsupported 5. With only 5-6 N rows the kappa CI is wide, as expected; the gate uses the point estimate.

## Where judge and labels disagree (per row, primary)

| label | rows | judge unsupported | judge supported |
|---|---|---|---|
| S (number appears in the context) | 7 | **5** | 2 |
| C (calculable from the context) | 25 | **9** | 16 |
| N (not supported) | 5 | 5 | 0 |

**Every disagreement is in the same direction:** the judge calls unsupported an answer the labels call supported. It never calls an N row supported. The judge's own reasons show why. RAGAS first restates the answer as a full sentence built from the question (e.g. "The total increase in net asbestos reserves from unfavorable development ... is $39"). The judge then requires that sentence to be "directly inferred" from the context:
- On S rows, the number is in the context but the question's framing is not stated (S003, S008, S016: "a table entry showing 39 ... but it does not explicitly state" the increase).
- On C rows, it declines to accept a computed percentage or difference (S002, S024: "does not state the percentage").
- On S022 it disagrees with the sign the answer took.

**Prediction** ("disagrees mainly on C rows, because the number does not appear verbatim"): **partly held**. Most disagreements are C rows (9 of 14), and the stated reason for C rows matches the prediction. But the disagreement *rate* is higher on S rows (5/7) than on C rows (9/25). For S rows the cause is the restated sentence, not the number.

## Reading

As configured, RAGAS faithfulness with this judge measures whether the answer **restated as a claim about the question** is explicitly stated in the passages. That is stricter than the S/C/N labels, which ask only whether the answer's number is in, or calculable from, the passages. For single-number FinQA answers the two notions diverge (kappa 0.26). The judge does agree with the labels on every unsupported (N) row: its unsupported verdicts include all of them, but also 14 supported rows. These results are descriptive; they are not a validation of either the labels or the judge.
