# Phase D local run (qwen2.5:7b), 2026-10-12

Numbers below are computed from the files named; nothing is interpreted beyond what the data show. Times +05:30 unless marked UTC.

## 1. Commits and tags

| What | Hash | Tag |
|---|---|---|
| Stage 1 (policy_v2, LLM layer, scoring, stats, runner, checksums) | `e0536f3` | `experiments-frozen-2026-10-12` |
| Stage 2 protocol | `0d2f71e` | `phase-d-protocol-frozen-2026-10-12` |
| Stage 3 prep (rerun wrapper, deviation entry) | `e0f898a` | |
| Stage 3 rerun results | `606f29b` | |
| Stage 4 outputs + this report | see final message / `git log` | |

The local run executed at commit `606f29b`; `run_meta.json` records `uncommitted_used_files = null`. Left as found (not mine, not committed): notebook, `logger.py`, `sweep_orchestrator.py`, `outputs/sweep_results.jsonl` edits and many untracked scripts/outputs. `outputs/data_checksums.json` hashes every file in `outputs/` at 2026-10-12 (88 files, including six DB dumps in `outputs/db_dumps_2026-10-12/`, 4.9 GB, git-ignored). The tag freezes tracked files only; untracked outputs are covered by the checksums.

## 2. Tests

`.venv/Scripts/python -m pytest tests src/phase_b_router/test_router.py`: **71 passed** (policy_v2 16, scoring 34, LLM client / paid lock / cost 6, router graphs 7, stats 5, legacy policy tests 3). `src/phase_d_validation/test_retest_*.py` have no collectable tests. Tests run in the repo `.venv` (system Python lacks `langgraph`); `pytest`, `google-auth`, `scipy` were installed there and added to `requirements.txt`.

## 3. Stage 3 held-out quiet rerun

Seed 20261014 (original 20261012), run id `holdout_rerun_20261014`, table order hm_clothes_75, 0, 50, 25, 100 (original 25, 50, 100, 0, 75), `outputs/phase_a_holdout_rerun/`, 1,500 rows, 0 errors, 08:03:42-08:19:10 UTC. Ollama stopped, no Jupyter or python process. Full analysis: `reports/holdout_results_2026-10-12-rerun.md`.

**Original: policy_v2 passes 24/25; P1 passes 21/25.** Rows = table, columns = filter.

| table          | ho1   | ho2   | ho3   | ho4   | ho5   |
|:---------------|:------|:------|:------|:------|:------|
| hm_clothes_0   | pass  | pass  | pass  | pass  | pass  |
| hm_clothes_100 | pass  | pass  | pass  | pass  | pass  |
| hm_clothes_25  | pass  | pass  | FAIL  | pass  | pass  |
| hm_clothes_50  | pass  | pass  | pass  | pass  | pass  |
| hm_clothes_75  | pass  | pass  | pass  | pass  | pass  |

**Rerun: policy_v2 passes 25/25; P1 passes 25/25.** Rows = table, columns = filter.

| table          | ho1   | ho2   | ho3   | ho4   | ho5   |
|:---------------|:------|:------|:------|:------|:------|
| hm_clothes_0   | pass  | pass  | pass  | pass  | pass  |
| hm_clothes_100 | pass  | pass  | pass  | pass  | pass  |
| hm_clothes_25  | pass  | pass  | pass  | pass  | pass  |
| hm_clothes_50  | pass  | pass  | pass  | pass  | pass  |
| hm_clothes_75  | pass  | pass  | pass  | pass  | pass  |

Original: H7 FAILS (24/25), H8 holds, H9 holds. Rerun: H7 holds (25/25), H8 holds, H9 FAILS (policy_v2 25 vs P1 25, not strictly more). The rerun does not replace the original.

**hm_clothes_25 x ho3, forced-exact, latency in ms per held-out vector 20-39:**

| run | 20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 | 31 | 32 | 33 | 34 | 35 | 36 | 37 | 38 | 39 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| original | 406.1 | 521.4 | 531.3 | 535.4 | 525.5 | 521.1 | 523.5 | 521.8 | 507.6 | 533.7 | 492.9 | 536.9 | 537.2 | 536.1 | 515.6 | 535.9 | 532.5 | 539.1 | 509.1 | 533.8 |
| rerun | 124.0 | 127.1 | 122.3 | 124.0 | 128.1 | 122.2 | 123.0 | 126.9 | 124.7 | 120.4 | 124.0 | 123.2 | 122.7 | 122.2 | 122.7 | 120.5 | 120.7 | 122.0 | 123.5 | 121.8 |

- original: median 528.4 ms, min 406.1, max 539.1
- rerun: median 122.8 ms, min 120.4, max 128.1

Host CPU load (typeperf, 3 one-second samples, %): run_start 08:03:33Z [18, 21, 20]; table_start_warmup 08:03:40Z [12, 22, 22]; table_start_warmup 08:06:45Z [15, 20, 15]; table_start_warmup 08:09:46Z [11, 9, 10]; table_start_warmup 08:12:51Z [13, 11, 3]; table_start_warmup 08:15:55Z [6, 11, 5]; run_end 08:19:13Z [5, 3, 4]. The original run had 100% load at start (Jupyter kernel) and 50% at end (`outputs/phase_a_holdout/machine_notes.txt`). The rerun's load readings (first ~20%, last ~4%) came from the Claude desktop app and Docker; no heavy process. The same cell took about 123 ms in the rerun versus 528 ms in the original. This report does not prove the cause. The original result stands as reported.

## 4. Stage 4 local run

- Model `qwen2.5:7b`, digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`, Ollama **0.40.2** (the 30 Sept files record 0.35.0). Embedding `nomic-embed-text:latest` digest `0a109f422b47`. A plain `ollama serve` did not see the model; it needs `OLLAMA_MODELS=D:\Models`, which the desktop app sets.
- DB: finqa_evidence 35862 rows, 278 ticker/year groups (35,862 in the 30 Sept census; same).
- Run `2026-10-12T08:21:26.102360+00:00` to `2026-10-12T08:23:33.852934+00:00` UTC, commit `606f29b`, 50 queries x 3 arms x 2 passes = 300 rows, 0 errors, cost USD 0.
- Settings: k 6, ef_search 40, L2, temperature 0, seed 0, num_ctx 8192, max output tokens 256 (router and answer), no thinking. DM tier `hm_clothes_0`; all five tiers give pre-filter for all 50 queries.

### 4.1 Smoke test (3 queries, `outputs/phase_d_local_smoke_2026-10-12/results.jsonl`)

| query | arm | selectivity | route | gold | raw output | parsed | correct | retrieval hit | tokens in/out | embed/db/router/gen/total ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ADI/2011/page_61.pdf-1 | decision_matrix | 0.00145 | pre-filter | 18.8 | `18.75` | 18.75 | 1 | 1 | 815/6 | 133/17/0/498/655 |
| ADI/2011/page_61.pdf-1 | policy_v2 | 0.00145 | exact | 18.8 | `18.75` | 18.75 | 1 | 1 | 815/6 | 19/9/0/149/181 |
| ADI/2011/page_61.pdf-1 | naive_llm | 0.00145 | post-filter | 18.8 | `18.75` | 18.75 | 1 | 1 | 815/6 | 33/129/833/239/1236 |
|  | router raw output | | | | `{"route": "post-filter", "reason": "The question does not contain explicit company ticker or fiscal year, so a post-filter approach is more appropriate to narrow down relevant results first."}` | | | | | |
| CDW/2015/page_70.pdf-1 | policy_v2 | 0.00463 | exact | -84 | `-61.1` | -61.1 | 0 | 1 | 430/6 | 44/34/0/305/384 |
| CDW/2015/page_70.pdf-1 | naive_llm | 0.00463 | pre-filter | -84 | `-61.1` | -61.1 | 0 | 1 | 430/6 | 40/10/387/148/586 |
|  | router raw output | | | | `{"route": "pre-filter", "reason": "reduces search space"}` | | | | | |
| CDW/2015/page_70.pdf-1 | decision_matrix | 0.00463 | pre-filter | -84 | `-61.1` | -61.1 | 0 | 1 | 430/6 | 14/10/0/133/159 |
| DG/2005/page_44.pdf-3 | naive_llm | 0.00259 | pre-filter | 12.1 | `0.5` | 0.5 | 0 | 1 | 464/4 | 3038/16/469/484/4010 |
|  | router raw output | | | | `{"route": "pre-filter", "reason": "reduces the search space for relevant vectors"}` | | | | | |
| DG/2005/page_44.pdf-3 | decision_matrix | 0.00259 | pre-filter | 12.1 | `0.5` | 0.5 | 0 | 1 | 464/4 | 30/10/0/122/163 |
| DG/2005/page_44.pdf-3 | policy_v2 | 0.00259 | exact | 12.1 | `0.5` | 0.5 | 0 | 1 | 464/4 | 33/10/0/119/164 |

One smoke row (DG/2005/page_44.pdf-3, naive arm) had embed 3,038 ms; the other embeds were 14-133 ms. Not investigated (section 6).

### 4.2 Pass 1 per arm (`stats_pass1.json`)

| arm | correct/50 | accuracy | retrieval hit (all gold keys in top 6) | parse failures | route parse failures | routes |
|---|---|---|---|---|---|---|
| decision_matrix | 11 | 0.22 | 0.24 (12/50) | 3 | 0 | {'pre-filter': 50} |
| policy_v2 | 11 | 0.22 | 0.24 (12/50) | 3 | 0 | {'exact': 50} |
| naive_llm | 11 | 0.22 | 0.22 (11/50) | 2 | 0 | {'post-filter': 11, 'pre-filter': 39} |

Naive-arm post-filter share: **11/50 = 22%** (P-a was left blank in the protocol, so there is nothing to compare). DM vs policy_v2 identical routes: **50/50** (DM `pre-filter` = policy_v2 `exact`).

### 4.3 Paired tests, pass 1

| X vs Y | both correct | b (X only) | c (Y only) | both wrong | exact McNemar p | acc. diff X-Y | 95% CI (Newcombe hybrid-score, paired) | mean total-latency diff X-Y, ms | 95% CI (paired bootstrap, 10,000 resamples, seed 20261012) |
|---|---|---|---|---|---|---|---|---|---|
| decision_matrix vs naive_llm | 10 | 1 | 1 | 38 | 1.000 | +0.000 | [-0.067, +0.067] | -281.0 | [-592.0, +251.6] |
| policy_v2 vs naive_llm | 10 | 1 | 1 | 38 | 1.000 | +0.000 | [-0.067, +0.067] | -519.8 | [-616.7, -375.7] |
| decision_matrix vs policy_v2 | 11 | 0 | 0 | 39 | 1.000 | +0.000 | [-0.040, +0.040] | +238.8 | [-123.7, +790.6] |

### 4.4 Latency split, pass 1 (ms, median [IQR]) and mean tokens

| arm | embed | DB | router | generation | total | input tok | output tok | router in/out tok |
|---|---|---|---|---|---|---|---|---|
| decision_matrix | 18.8 [14.5] | 11.4 [4.2] | 0.0 [0.0] | 135.9 [147.2] | 168.5 [155.1] | 475 | 4.3 | - |
| policy_v2 | 16.8 [5.4] | 11.2 [3.9] | 0.0 [0.0] | 114.2 [130.8] | 149.0 [139.4] | 475 | 4.3 | - |
| naive_llm | 18.2 [15.8] | 11.6 [9.8] | 525.9 [109.5] | 169.7 [117.8] | 742.2 [208.9] | 443 | 4.4 | 133/25.5 |

Thinking tokens 0 (model has none); cost USD 0 in all rows.

### 4.5 Pass 1 vs pass 2 agreement (same query, same arm)

| arm | same answer | same route | same correctness |
|---|---|---|---|
| decision_matrix | 47/50 | 50/50 | 49/50 |
| policy_v2 | 49/50 | 50/50 | 49/50 |
| naive_llm | 50/50 | 50/50 | 50/50 |

## 5. Comparison with the 30 Sept local run (`phase_d_results_ollama_corrected.jsonl`)

| | 30 Sept | 12 Oct pass 1 |
|---|---|---|
| DM correct | 10/50 | 11/50 |
| naive correct | 8/50 | 11/50 |
| naive route split | 45 post-filter / 5 pre-filter | 11 post-filter / 39 pre-filter |
| DM all-gold retrieval hit | 12/50 | 12/50 |
| McNemar DM vs naive | not computed | b=1, c=1, p=1.000 |

Differences attributable to a verified code change:

- **Scoring:** re-scoring the 30 Sept answers with the new `scoring.py` gives the same correct/wrong label as the old scorer for all 50 DM and all 50 naive answers (checked). The scorer did not move any count.
- **Naive routes:** the naive router prompt changed (new system prompt requesting `{"route", "reason"}`; the old one requested `{"route", "sub_queries"}`), and 36 of 50 queries got a different route. This is a prompt change.
- **DM answers:** 41/50 raw answers equal those of 30 Sept. The 9 that differ all occur where the retrieved evidence set is identical to 30 Sept but the order of the 6 rows in the prompt differs (sets identical for all 50, order different for all 50, prompt token counts identical for all 50). Evidence order is the only input difference I observed for those 9. I did not establish why the order differs (tie order among equal-distance duplicate rows is possible; Ollama also moved from 0.35.0 to 0.40.2). Cause: not determined.

## 6. Surprising or uncertain

- 22% of naive routes are post-filter here versus 90-92% on 30 Sept; this follows the router prompt I changed.
- All-gold retrieval hit is 24% (12/50) for DM and policy_v2 and 22% for naive, so most wrong answers coincide with missing evidence before routing matters. DM and policy_v2 use the same exact retrieval and prompt; their correctness agrees on all 50 queries (b=c=0).
- Between passes the DM arm changed its raw answer on 3/50 queries and policy_v2 on 1/50 at temperature 0 and seed 0 (naive 0/50). Cause not determined.
- Occasional multi-second embed calls (3.0 s once in the smoke test) when the embedding and chat models alternate in Ollama; I did not check whether a model reload happened. The DM-vs-naive latency CI includes 0 and the policy_v2-vs-naive CI does not; the difference is mostly the naive router's own LLM call (median 526 ms).
- Percent answers are compared on the percent scale after stripping `%`; a model answering 0.359 for gold 35.9% is scored wrong by design.
- Unverified against docs: the Claude global-endpoint URL, Gemini usage field names, gpt-oss `reasoning_effort`; the Claude doc page does not list `temperature`.
- The rerun's H9 fails because P1 also passes all 25 cells in the quiet run (original: 24 vs 21).
- Legacy `local_ollama_runner.py` was committed in its working-tree state; it was not used for the new run.

## 7. Five examples per arm, correct and wrong (pass 1, first five in query order)

**decision_matrix - correct**

| query | route | gold | raw output | parsed | parse failure | retrieval hit |
|---|---|---|---|---|---|---|
| ADI/2011/page_61.pdf-1 | pre-filter | 18.8 | `18.75` | 18.75 | 0 | 1 |
| HIG/2011/page_53.pdf-3 | pre-filter | 307 | `307` | 307.0 | 0 | 1 |
| MRO/2003/page_45.pdf-2 | pre-filter | 1056 | `1056.5` | 1056.5 | 0 | 1 |
| HOLX/2008/page_143.pdf-1 | pre-filter | 23.4 | `23.5` | 23.5 | 0 | 1 |
| ABMD/2007/page_78.pdf-1 | pre-filter | 74 | `74%` | 74.0 | 0 | 1 |

**decision_matrix - wrong**

| query | route | gold | raw output | parsed | parse failure | retrieval hit |
|---|---|---|---|---|---|---|
| CDW/2015/page_70.pdf-1 | pre-filter | -84 | `-61.1` | -61.1 | 0 | 1 |
| DG/2005/page_44.pdf-3 | pre-filter | 12.1 | `0.5` | 0.5 | 0 | 1 |
| TMUS/2017/page_29.pdf-3 | pre-filter | 83333 | `N/A` | None | 1 | 0 |
| HIG/2004/page_140.pdf-1 | pre-filter | 9.8 | `0` | 0.0 | 0 | 0 |
| V/2010/page_28.pdf-1 | pre-filter | 44.9 | `2.2` | 2.2 | 0 | 0 |

**policy_v2 - correct**

| query | route | gold | raw output | parsed | parse failure | retrieval hit |
|---|---|---|---|---|---|---|
| ADI/2011/page_61.pdf-1 | exact | 18.8 | `18.75` | 18.75 | 0 | 1 |
| HIG/2011/page_53.pdf-3 | exact | 307 | `307` | 307.0 | 0 | 1 |
| MRO/2003/page_45.pdf-2 | exact | 1056 | `1056.5` | 1056.5 | 0 | 1 |
| HOLX/2008/page_143.pdf-1 | exact | 23.4 | `23.5` | 23.5 | 0 | 1 |
| ABMD/2007/page_78.pdf-1 | exact | 74 | `74%` | 74.0 | 0 | 1 |

**policy_v2 - wrong**

| query | route | gold | raw output | parsed | parse failure | retrieval hit |
|---|---|---|---|---|---|---|
| CDW/2015/page_70.pdf-1 | exact | -84 | `-61.1` | -61.1 | 0 | 1 |
| DG/2005/page_44.pdf-3 | exact | 12.1 | `0.5` | 0.5 | 0 | 1 |
| TMUS/2017/page_29.pdf-3 | exact | 83333 | `N/A` | None | 1 | 0 |
| HIG/2004/page_140.pdf-1 | exact | 9.8 | `0` | 0.0 | 0 | 0 |
| V/2010/page_28.pdf-1 | exact | 44.9 | `2.2` | 2.2 | 0 | 0 |

**naive_llm - correct**

| query | route | gold | raw output | parsed | parse failure | retrieval hit |
|---|---|---|---|---|---|---|
| ADI/2011/page_61.pdf-1 | post-filter | 18.8 | `18.75` | 18.75 | 0 | 1 |
| HIG/2011/page_53.pdf-3 | pre-filter | 307 | `307` | 307.0 | 0 | 1 |
| HIG/2004/page_140.pdf-1 | post-filter | 9.8 | `9.8` | 9.8 | 0 | 1 |
| HOLX/2008/page_143.pdf-1 | pre-filter | 23.4 | `23.5` | 23.5 | 0 | 1 |
| ABMD/2007/page_78.pdf-1 | post-filter | 74 | `74%` | 74.0 | 0 | 1 |

**naive_llm - wrong**

| query | route | gold | raw output | parsed | parse failure | retrieval hit |
|---|---|---|---|---|---|---|
| CDW/2015/page_70.pdf-1 | pre-filter | -84 | `-61.1` | -61.1 | 0 | 1 |
| DG/2005/page_44.pdf-3 | pre-filter | 12.1 | `0.5` | 0.5 | 0 | 1 |
| TMUS/2017/page_29.pdf-3 | post-filter | 83333 | `500000` | 500000.0 | 0 | 0 |
| V/2010/page_28.pdf-1 | pre-filter | 44.9 | `2.2` | 2.2 | 0 | 0 |
| EMR/2017/page_78.pdf-2 | post-filter | 251599.67 | `245` | 245.0 | 0 | 0 |

## 8. Before a paid run, you must

1. Fill `config/prices.json` (input/output USD per 1M tokens) from your Vertex console for claude-sonnet-5-5, gemini-3.8-flash, gemini-3.5-flash-lite, gpt-oss-120b and set `verified: true`.
2. Confirm the router decision (same model routes and answers) and the naive-router schema-failure rule (scored wrong, no retry), both marked DECISION in `PHASE_D_LLM_PROTOCOL.md`.
3. Fill P-a ("TO FILL BEFORE RUN") and re-tag the protocol if its text changes.
4. Check Vertex quotas, credits and model availability (gpt-oss-120b on your project, else Claude Haiku 5.5), enable the APIs, set `GOOGLE_CLOUD_PROJECT` and application-default credentials.
5. Run a 5-query pilot with `--allow-paid --budget-usd <cap>` and verify the unverified request details before the full run.
