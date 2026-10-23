# Phase D, Amendment 8: RAGAS faithfulness as an LLM judge of the Gemini answers

**Status:** written 2026-10-23, committed and tagged `phase-d-amendment-8-2026-10-23` **before any judge call**. Amends no earlier file. The only paid calls are the judge calls below; no answer-model or embedding call. Spend cap **USD 3 in total**; no call without `--allow-paid`.

## Judge and metric (fixed)

- **RAGAS 0.4.3** (latest on PyPI, 23 Oct 2026), in its own environment `.venv-ragas` (Python 3.11; full freeze `requirements-ragas.txt`; `langchain-community` pinned to 0.3.31 because 0.4.2 lacks a module RAGAS 0.4.3 imports). Telemetry off (`RAGAS_DO_NOT_TRACK=true`). **Only the LLM-based metric `ragas.metrics.collections.Faithfulness`**, no non-LLM metric. It makes two judge calls per row: (1) break the answer into statements, given the question; (2) give each statement a verdict 0/1 on whether it "can be directly inferred" from the context. Score = supported statements / statements. It uses no embeddings, so none are computed.
- **Judge: `openai/gpt-oss-120b-maas` on Vertex AI** (us-central1, project `bsc-research-project-511410`, OpenAI-compatible endpoint), a family different from Gemini (answer model) and Claude (label drafter). Via `llm_factory(provider="openai")` (instructor JSON mode). Settings: **temperature 0**, `max_tokens` 4096, `top_p` at the RAGAS default 0.1, reasoning effort at the provider default; **one attempt per call** (instructor `max_retries=1`, OpenAI client `max_retries=0`), 180 s timeout. OpenRouter is not used unless amended.
- **Inputs:** `outputs/ragas_judge_2026-10-23/judge_inputs.jsonl` (SHA-256 `f7f17f73...056bd0`, built read-only by `src/phase_d_validation/judge_inputs.py`): the 1,000 rows of `outputs/phase_d_gemini_full_2026-10-12` (4 arms x 50 x 5 passes). `user_input` = question; **`response` = `raw_output`**; **context = the retrieved passages exactly as in the answer prompt** (`[query_id::evidence_key] content`, retrieved order, from `finqa_evidence_qwen3`).

## Scoring rules

- **Binarisation:** "supported" if faithfulness >= 0.5, else "unsupported". Raw scores are reported too.
- **No context (10 rows, all naive_llm, retrieval returned 0 passages):** RAGAS refuses an empty context. These rows are not sent to the judge; primary: score 0, "unsupported" (nothing can be inferred from no context); sensitivity: excluded. None is among the 40 labelled rows.
- **No statements (score NaN)** and **judge errors** (failed call, unparseable or schema-invalid output, truncation): recorded as `no_statements` / `judge_error` with the raw output, never retried, never dropped. They are excluded from agreement and rates, with their count; sensitivity: counted as unsupported. If 5 or more of the first 20 rows end in `judge_error`, the run stops (setup failure) and Stage 1 is reported as failed.

## Stage 1: the 40 labelled rows (model-drafted labels verified by the author)

Reference: N = unsupported; S and C = supported (labels as used in `3c167ba`). Class balance **6 N vs 34 S/C** (per question 3 vs 14; labels are constant within every question). Reported: accuracy (Wilson 95% CI) and **Cohen's kappa** (95% CI by percentile bootstrap, 10,000 resamples, seed 20261023; resamples with undefined kappa are counted and dropped), **per row (40)** and **per distinct question (17**; question judgment = supported if the mean faithfulness of its judged rows >= 0.5, resampling questions). Disagreements are tabulated by S/C/N. With only 6 N rows kappa is unstable and its CI wide.

**Gate: Stage 2 runs only if the per-row kappa point estimate >= 0.4.** Otherwise Stage 1 is reported and the work stops.

## Stage 2: all 1,000 rows (secondary, descriptive)

The 40 Stage-1 judgments are reused (same inputs), the other 960 are judged once. Per arm: share supported (Wilson CI) and mean score, pooled over 5 passes and for pass 1. Paired policy_v2 vs naive_llm per (pass, question): difference in share supported, 95% CI by bootstrap over questions (10,000, seed 20261023), and discordant-pair counts. Reported **with and without the 40 labelled rows** (a pair is dropped if either row is labelled). No test of a hypothesis.

## Prediction (written before any call)

The judge marks some calculated (C) answers as unsupported because the number does not appear verbatim in the context, so it disagrees with the labels mainly on C rows.

## Budget and logging

Cost is tracked at **USD 0.15 / 0.60 per 1M input / output tokens** (OpenRouter list price, higher than the USD 0.09 / 0.36 Vertex price given by third-party lists; Google's page could not be read), so the true spend is at most the tracked spend. Before each row the run stops if tracked spend + the largest per-row cost so far would exceed USD 3. Estimate: about 1.8M input tokens for 990 rows; USD 0.75-2.05 tracked (USD 0.45-1.25 at Vertex rates); Stage 1 about USD 0.05. Every call is logged (`judge_calls.jsonl`: row, step, input / output / reasoning tokens, finish reason, tracked cost, latency, raw content, error). Outputs in `outputs/ragas_judge_2026-10-23/`, added to `outputs/data_checksums.json`.
