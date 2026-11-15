# Phase D Deviation Log

## 2026-09-30 — latency instrumentation correction

The first completed local run recorded retrieval-plus-answer latency because
the timer started after the naive router call and embedding generation. This
was an instrumentation bug, not model/prompt/threshold tuning. The runner was
updated to preserve the original retrieval-plus-answer fields and additionally
record end-to-end latency including route selection, embedding, retrieval, and
answer generation. The frozen configuration remains unchanged; the full run is
repeated with the corrected measurement.

Record any full-run infrastructure repair here before repeating a query or run:
date, failure, exact change, why it is a bug rather than tuning, affected
queries, and rerun result.

## 2026-10-10 — routing/detector code was untracked at the freeze tag

`phase-d-local-freeze` (b59c004) was tagged while five source files it depends
on were untracked: `local_ollama_runner.py` imports
`src.phase_b_router.policy`, which was not in that commit. This was found
during the read-only policy audit (`reports/policy_audit_2026-10-10.md`). The
files were committed unchanged in acc590c; no logic was edited. Times are
+05:30.

| File | sha256 (working tree, as committed) | mtime | .pyc records source mtime/size |
|---|---|---|---|
| src/phase_b_router/policy.py | 2363709e7b55aca5712044de92d4f50ce7941836721be03d896934a1e7843f68 | 2026-09-30 07:13:46 | 07:13:46 / 895 B (match) |
| src/phase_b_router/router.py | 28bebad0599a1f2cd98021be8d37a54625bd42dbc93762df281f4d48c926135e | 2026-10-06 15:23:11 | 2026-10-06 15:19:46 / 9403 B (no match; edited again after) |
| src/phase_b_router/test_router.py | 94c9e5b69933f7922b49d470754330b304175349cc22e775850cf46e8e55aae3 | 2026-10-06 15:22:41 | match |
| src/phase_d_validation/comparison_runner.py | 7da26ad87c8b981247172f27c570c3327af3393e52e2dfa9e6b5b733fe07d665 | 2026-09-30 08:12:03 | match |
| src/phase_c_analysis/threshold_detector.py | 2cb09756f3706b4c10bf3aa438960a422a229427303aee8c8005fb30d9ba26eb | 2026-09-30 10:12:38 | 2026-09-04 08:50:00 / 3618 B (no match; edited later) |

Reference times: frozen run outputs `phase_d_results_ollama_corrected.jsonl`
08:43:41 and `phase_d_results_ollama.jsonl` 08:31:17 on 2026-09-30; b59c004
committed 2026-09-30 08:58:56.

Evidence: `policy.py` (the only one of these that the frozen local runner
imports) was last modified 07:13:46 on 2026-09-30, before both frozen run
outputs and before b59c004, and its .pyc was compiled from exactly that
source (mtime and size match). This is consistent with the on-disk
`policy.py` being the version that ran, but mtimes and .pyc headers cannot
prove it. `router.py`, `test_router.py` and `threshold_detector.py` were
modified after the freeze, so their on-disk content may differ from what
existed at the freeze; `router.py` is not imported by the local runner.
`outputs/thresholds.json` (mtime 2026-09-04 09:23:44) predates every
modification of `threshold_detector.py` after 2026-09-04 08:50.

## 2026-10-10 — three-arm run: aborted start and Amendment 2

Failure: the first start of the H&M three-arm full run (commit 495d1b1,
2026-10-10 10:47:40 +05:30) was stopped by hand at 10:49:05 after 42 rows.
In 26 of them (hm_clothes_75, filter lo1; forced-hnsw, iterative-relaxed,
iterative-strict) `plan_as_intended` was false: the planner used an exact
B-tree Index Scan + Sort instead of the HNSW index, because the frozen arm
settings allowed it.

Exact change: `enable_sort = off` added to arms 3-5 in
`src/phase_a_sweep/arm_comparison.py` and `PHASE_A_ARMS_PROTOCOL.md`
(Amendment 2); a pre-flight plain-EXPLAIN check of all table x filter x arm 2-5
combinations (vector 0) that aborts the run before any measured query, saved
to `outputs/phase_a_arms/preflight.json`.

Why a bug, not tuning: the arm was defined as a forced HNSW scan; the plan
check showed it was not one for lo1-lo3. The change is made before any result
was analysed, and no recall or latency from the aborted rows was looked at.

Affected rows: the 42 aborted rows, kept unanalysed in
`outputs/phase_a_arms/results_aborted_frozen_arms.jsonl` (with
`run_meta_aborted.json`, `run_aborted.log`, `run.err_aborted.log`). They are
excluded from all results. Rerun result: see the restarted run.

## 2026-10-10 — PostgreSQL backend crash during the three-arm run (~14:51 +05:30)

Failure: the full three-arm run (commit a282da9, PID 41648) stopped at 5,609 of
6,500 rows when a PostgreSQL backend died and the server did crash recovery.
The run script detected the lost connection (`OperationalError: server closed
the connection unexpectedly`), stopped without recording a row, and was resumed
at 15:05 (PID 39204) with the same command; `outputs/phase_a_arms/resumes.jsonl`
records the resume (5,609 rows present). All 6,500 rows are unique keys.

Cause: **not logged / unknown.** The Postgres container log (`docker logs
vector_db`, 2026-10-10 09:21-09:22 UTC) contains only:

    09:21:18.449 UTC [14300] LOG:  could not send data to client: Broken pipe
    09:21:19.234 UTC [14300] FATAL:  connection to client lost
    09:21:19.620 UTC [1] LOG:  server process (PID 14299) exited with exit code 2
    09:21:19.708 UTC [1] LOG:  terminating any other active server processes
    09:21:24.577 UTC [1] LOG:  issuing SIGKILL to recalcitrant children
    09:21:24.816 UTC [1] LOG:  all server processes terminated; reinitializing
    09:22:13.699 UTC [14301] LOG:  database system was not properly shut down; automatic recovery in progress
    09:22:15.010 UTC [1] LOG:  database system is ready to accept connections

No out-of-memory, "killed" or signal message appears anywhere in the container
log (0 matches for out of memory / oom / killed / segfault / signal N).
`docker inspect`: OOMKilled=false, RestartCount=0, container memory limit 0
(none), shm_size 2 GiB, container started 2026-10-10T04:10:30Z, so the container
itself did not restart. Why server process 14299 exited with code 2 is not
determinable from these logs. The memory limit of the Docker Desktop VM was not
checked.

Impact: no measurement was lost or altered. 891 rows (all hm_clothes_50: lo1,
lo4, lo5, gap1-gap3, idx1-idx3) were written after the resume, with
shared_buffers cold after recovery; they are flagged `post_resume` in
`reports/arms_results_2026-10-10.md`. No verdict or route in that report
depends on the post-resume latencies.

## 2026-10-12 — H7 decision (policy_v2 held-out result)

Held-out result accepted as measured: policy_v2 24/25; H7 FAILED on hm_clothes_25 x ho3 (forced-exact 528.4 ms). Probable CPU contention from a Jupyter kernel is noted as an inference, not proven. T was not changed.

## 2026-10-12 — held-out quiet rerun (post-hoc robustness run)

Post-hoc robustness rerun after H7 failure; original result stands as reported. Same held-out design (filters ho1-ho5, vectors 20-39, 5 tables, 3 arms, T = 0.1), run through `src/phase_a_sweep/holdout_rerun.py` (reuses `holdout_run.py` unchanged) with seed 20261014 (original 20261012; chosen before the run so that hm_clothes_25 is not first), run id `holdout_rerun_20261014`, output `outputs/phase_a_holdout_rerun/`. Ollama stopped and no Jupyter kernel running; host CPU load recorded at the start of each table. Reported separately from the original run; neither replaces the other.

## 2026-10-12 — Phase D Amendment 1 (`PHASE_D_AMENDMENT_1.md`)

What changed: research question reframed as non-inferiority (policy_v2 vs naive LLM router, MARGIN 0.10, Newcombe CI, pass 1 primary); one hosted model (Gemini 3.8 Flash) instead of four; embedding changed from nomic-embed-text (unprefixed, table `finqa_evidence`) to Qwen3-Embedding-8B 1024-d (table `finqa_evidence_qwen3`, cached query embeddings, SHA-256 930cadc0…ff23); retrieval of k = 15 distinct passages (rule: smallest k within 2 all-gold hits of k = 20); deterministic (distance, id) tie-break; seeded per-query arm order; exact scoring rule written down; naive JSON failure scored wrong, no retry. Filled later the same day (appended sections): MARGIN 0.10, P-a 10% (range 0-25%), 2048 max output tokens, `thinking_level=LOW`, verified Gemini usage fields and prices, k/distinct in config.
Why: pre-paid fixes showed the nomic table was built without the model's prefixes, retrieval order had ties, k = 6 rows held about 2 distinct passages; the original four-model plan was reduced to one hosted model.
Governs: local v3 (`outputs/phase_d_local_2026-10-12_v3`), the Gemini pilot (excluded from analysis) and, with Amendments 2-3, all later runs.
Tags: `phase-d-amendment-1-2026-10-12`, `phase-d-amendment-1-filled-2026-10-12`, `phase-d-amendment-1-filled-v2-2026-10-12`. The frozen protocol `PHASE_D_LLM_PROTOCOL.md` (tag `phase-d-protocol-frozen-2026-10-12`) was not edited except for an appended, untagged Draft Amendment 0 (scoring text), later adopted by Amendment 1.

## 2026-10-12 — Phase D Amendment 2 (`PHASE_D_AMENDMENT_2.md`)

What changed: primary scoring rule = Amendment 1 rule plus trailing scale words (million, billion, thousand, mn, bn, m, k) stripped without rescaling; the Amendment 1 rule is kept as "strict" and reported alongside; new secondary arm `naive_informed` (router told the ticker/year filter, no selectivity); P-a unchanged (pilot showed post-filter on 4/5).
Why: the 5-query Gemini pilot (rows excluded) showed answers such as `$18.75 million` scored unparseable, and a naive router that cannot know a filter always exists.
Governs: local v4 (`outputs/phase_d_local_2026-10-12_v4`), local v5 and the Gemini full run. Earlier outputs re-scored into derived files only (`outputs/rescored_2026-10-12/`).
Tag: `phase-d-amendment-2-2026-10-12` (placed before any run under it).

## 2026-10-12 — Phase D Amendment 3 (`PHASE_D_AMENDMENT_3.md`)

What changed: passes increased from 2 to 5 (pass 1 primary, pass 2 robustness, passes 1-5 pooled secondary); pooled non-inferiority by paired bootstrap over queries (10,000 resamples, seed 20261012); decision_matrix vs policy_v2 reported as noise reference; Gemini budget cap USD 5. Primary test unchanged.
Why: in local v4, decision_matrix and policy_v2 (same route, same prompt) disagreed on 2 queries and 4-6 answers per arm changed between passes; the local v4 primary result (non-inferiority not shown, lower bound -0.138) is reported as measured.
Governs: local v5 (`outputs/phase_d_local_2026-10-12_v5`) and the Gemini full run (`outputs/phase_d_gemini_full_2026-10-12`).
Tag: `phase-d-amendment-3-2026-10-12` (placed before both runs).

## 2026-10-12 — final cleanup (no result changed)

`comparison_runner.py` now refuses to run without explicit `--table`, `--query-embeddings`, `--k`, `--distinct/--no-distinct`; legacy scripts carry a "LEGACY — not used in final results" header; `pytest.ini` and requirements added. Commit `b67d1f1`.

## 2026-10-23 — wording corrections after the headline audit (no result changed)

Source: `reports/headline_audit_2026-10-23.md` (commit `776109b`): 46 headline numbers recomputed from the raw files, 0 numeric mismatches. This entry corrects wording only. No tagged or frozen file is edited; where a tagged file contains the wording, this entry supersedes it.

**1. The held-out 1 failure has no established cause.** The failing cell is hm_clothes_25 x ho3, forced-exact, median 528.4 ms (limit 500 ms; recall 1.000). Host CPU was recorded only at the start (100%) and at the end (50%) of the original run, not in between; an unrelated Jupyter kernel used 3,410 CPU-seconds (about 1.8 cores on average) in the same window. In the quiet rerun host CPU read 17-21% at the start, falling to 3-5% at the end, and the same cell took 122.8 ms. The rerun also differed from the original in seed (20261014 vs 20261012), table order and time, so the difference between the two runs does not identify the cause. "CPU contention" remains an inference.

Statements that this entry corrects (they present the load as established):
- `reports/final_summary_2026-10-12.md`, limitation 9: "the first held-out cell failed at 528.4 ms under load and passed at 122.8 ms when quiet". Corrected reading: the cell failed at 528.4 ms in the original run (host load recorded only at start 100% and end 50%) and measured 122.8 ms in a rerun with 17-21% falling to 3-5% host CPU; the cause is not established.
- `PHASE_A_HOLDOUT2_PROTOCOL.md` (tag `phase-a-holdout2-frozen-2026-10-12`): "The in-sample run, under heavy CPU load, had forced-exact at 489-6,567 ms for s >= 0.2" and "Under the heavy load of the original run the exact arm was up to 3x slower". Corrected reading: the load during the three-arm run was not recorded (`PHASE_A_HOLDOUT_PROTOCOL.md` says it "probably saw similar conditions, but its load over time was not recorded"); the in-sample forced-exact medians at s >= 0.2038 range from 488.9 to 6,567 ms (40 cells). The **"3x" figure comes from the harness self-test** (hm_clothes_100 x idx1, vectors 0 and 1: forced-exact 2,685 and 2,701 ms against 882 and 825 ms in the main run for the same points, with identical recall, rows and plan nodes), **not from a load measurement**; its cause is not established. The 45-60 minute and up-to-2.5-hour run-time estimates in that protocol rest on this 3x figure and are estimates only (the held-out 2 run took about 50 minutes, 10:51-11:41 UTC).
- `reports/pre_paid_fixes_2026-10-12.md`: "up to about 2.5 h under heavy load" (run-time estimate for held-out 2). Same correction as above: an estimate that assumes the unexplained 3x slowdown, not a measured load effect.
- `docs/CODE_MANUAL.docx` section 12.9 is marked [I] and hedged ("appears to come from machine load"); it stays as written, read as inference.

**2. Cost and latency wording for the Gemini 3.8 Flash full run** (`outputs/phase_d_gemini_full_2026-10-12`; `reports/phase_d_gemini_full_2026-10-12.md` section C says "about 2.8 s faster per query and about one third cheaper per query", unqualified):
- **Cost.** policy_v2 vs naive_llm, mean cost per arm-run (question x arm), router call included for naive_llm: **19.4% cheaper pooled over the 5 passes** (USD 0.00151 vs 0.00188), **33.8% in pass 1** (USD 0.00135 vs 0.00203; 33.5% from the rounded values). "About one third" describes pass 1 only. **About three quarters of the pooled saving comes from the router call that policy_v2 does not make** (USD 0.00027 of 0.00036 per arm-run); the rest is the difference between the answer calls, which varies by pass (output and thinking tokens). Two runaway answers (MAX_TOKENS, pass 2) inflate the pooled cost of policy_v2 and decision_matrix; excluding those two question-pass cells the pooled saving is 20.5%.
- **Latency.** Mean paired difference in total time per question, policy_v2 minus naive_llm: **2.59 s faster pooled over 5 passes** (bootstrap 95% CI 2.03-3.22 s), **2.83 s in pass 1** (CI 1.99-3.75 s), and **2.14 s as a difference of pass-1 medians**. "About 2.8 s" is the pass-1 mean difference.
- Corrected sentence: "policy_v2 was about 2.6 s faster per question and about 19% cheaper over 5 passes (pass 1: 2.8 s and 34%); about three quarters of the cost saving is the router call it does not make."

**3. Other audit notes (no change of any result):** "490 ms to 6.6 s from 0.204 upward" in `reports/arms_results_2026-10-10.md` rounds the minimum 488.9 ms up; no report states "751-6,567 ms" (751.5 ms is the smallest of the 15 idx1-3 cells, whose largest is 3,419 ms; 6,567 ms is hm_clothes_50 x gap4, s = 0.2986).

## 2026-10-23 — Amendment 4 scale-up not run (no result changed)

The Amendment 4 scale-up (`PHASE_D_AMENDMENT_4.md`, tag `phase-d-amendment-4-2026-10-13`; 1,075 confirmation questions) was **not run**, by the author's decision on 23 Oct 2026, because of the time left before the 7 Nov deadline. The only output is the smoke test that stopped under the error-rate abort rule (`outputs/phase_d_gemini_scaleup_smoke_2026-10-13/`, commit `96fadc0`: 7 rows, 1 error row, USD 0.009). It is **excluded from all analysis**. Amendment 4 Addendum 1 (run control) therefore governs no run. The FinQA comparison remains the 50-question frozen set.

## 2026-10-23 — Amendment 5 Addendum 1: tag moved once, withdrawn v2 sheet, labelling method disclosed late (no result changed)

- **Tag moved.** `phase-d-amendment-5-addendum-1-2026-10-23` was first set on `2dbfc72` (2026-10-23 11:03:10 +05:30; first version, empty `gold_derivable` column in a new sheet) and moved once to `21d84de` (11:23:23 +05:30; second version). No label had been used at either commit; the label results followed in `1338264` and `3c167ba` (11:27:49 +05:30). The tag has not been moved since.
- **Withdrawn file.** `outputs/hallucination_classification_2026-10-23/labelling_sheet_v2.csv` (from `2dbfc72`) exists, is withdrawn and was never used; it stays in place and in `data_checksums.json`.
- **Labelling method disclosed late.** Neither Addendum 1 nor `reports/hallucination_labels_2026-10-23.md` says how the labels were made. They were drafted by a language model from a different model family than the answer model, blind to the key file, with the calculation written per row, and then checked row by row by the author; they are to be reported as "model-drafted labels verified by the author". This is disclosed in `docs/preregistration/PHASE_D_AMENDMENT_5_ADDENDUM_2.md` (tag `phase-d-amendment-5-addendum-2-2026-10-23`), written after the Addendum 1 results; it changes none of them. Where the Addendum 1 report speaks of "human labels", read "model-drafted labels verified by the author".

## 2026-10-23 — Amendment 6 Part A not run (no result changed)

Amendment 6 Part A (`docs/preregistration/PHASE_A_AMENDMENT_6.md`, tag `phase-a-amendment-6-2026-10-23`: live runs A6 planner_iterative, A7 fallback_iterative, A8 fallback_hnsw, A9 selectivity_estimate) is **not run**, by the author's decision on 23 Oct 2026. Reason: the demo application on a new 10-K corpus compares the same modes live (default HNSW + WHERE, LLM router, planner + iterative scan, retry-exact fallback, policy_v2), with shadow recall, and times the selectivity count query in its trace. No Part A query was run; no Part A output exists. **Amendment 6 Part B (offline, B1-B4b) still runs.** The tagged amendment is not edited; its Part A predictions remain untested.

## 2026-10-23 — Amendment 7 Step 1: selectivity counted on finqa_evidence_qwen3 (no result changed)

`PHASE_D_AMENDMENT_7.md` (tag `phase-d-amendment-7-2026-10-23`) says selectivity is counted on `finqa_evidence` "as Amendment 1". By the author's instruction of 23 Oct 2026 (embedding model for everything Qwen3-Embedding-8B, never the old `finqa_evidence` table), Step 1 counted on `finqa_evidence_qwen3` instead (same 35,862 rows and metadata, audited in Amendment 1). All 1,125 counts (frozen 50 and 1,075 confirmation questions) equal the recorded selectivities to 1e-12, so no number changes. The Step 1 script ran from HEAD `21a94ad` before it was committed; it is committed unchanged with its outputs. The 1,075-question Qwen3 query cache (`outputs/embedding_build_2026-10-13/query_embeddings_qwen3_confirmation_1075.json`) has no entry in `outputs/data_checksums.json`; its SHA-256 equals the value in the tagged Amendment 4 (`c5215bea...f36ea`).

## 2026-10-30 — Amendment 9: smoke timings, reproducibility-check selection, run-time estimate

Amendment 9 (`docs/preregistration/PHASE_E_AMENDMENT_9.md`, tag `phase-e-amendment-9-2026-10-30`).

1. **Smoke timings on in-sample cells before the calibration session.** While testing the module (commit `b447c1c`), tuned iterative (`max_scan_tuples` 100000, `scan_mem_multiplier` 4) was timed with EXPLAIN ANALYZE on hm_clothes_0 lo1 and hm_clothes_100 lo2/lo3, vectors 0-1 (in-sample only): 0.2-14 s per query vs 150-190 ms for default iterative; one cold first call 28.6 s. No held-out cell was queried. These timings are not used anywhere.
2. **Run-time estimate.** Because of (1), the D2 session is expected to take about 3-3.5 h, not the 1-1.5 h stated in the amendment (an estimate, not a rule; no rule changes).
3. **D3 reproducibility check.** The pre-registered selection (3 in-sample cells with the lowest stored forced-hnsw mean recall) picked hm_clothes_0 lo1, hm_clothes_0 lo2 and hm_clothes_100 lo1, whose stored and new recall are 0.0 for every vector; identical (20/20 each) but unable to detect a difference. A **supplementary, not pre-registered** check on the 3 cells with stored mean closest to 0.5 (hm_clothes_100 ctl 0.520, hm_clothes_75 gap2 0.530, hm_clothes_100 gap2 0.455) also reproduced 20/20 vectors exactly (`outputs/ground_truth_hm/repro_check_supplementary.json`).

## 2026-10-31 — Phase E: in-session CPU load during the calibration and Task 4 sessions (no result changed)

A pause/re-run rule (10 s CPU sampling during the session; pause and re-run items when the 60 s rolling mean exceeds 40%) was drafted on 30 Oct in the author's planning notes but was not passed to the implementation session. The recorded instruction was 'Amend the CPU measure' (30 Oct, 10:29 UTC), and the tagged Addendum 2 (`phase-e-amendment-9-addendum-2-2026-10-30`) contains only the start-of-session check. The rule is recorded here for transparency; it was never part of the pre-registered protocol.

The sessions logged one 1 s reading of `\Processor(_Total)\% Processor Time` every 5 minutes (`outputs/phase_e_calibration_hm_2026-10-30/host_load.json`, `outputs/phase_e_comparison_hm_2026-10-31/host_load_1793392187.json`), so a 60 s rolling mean cannot be computed. Every reading above 40 %, with the items finished within 60 s of it (cell: routes or modes, vector indices; full list in `outputs/phase_e_final_2026-10-31/load_spike_check.json`):

- Calibration (D2) 2026-10-30 12:10:12 UTC, 43.8 %: 53 items. hm_clothes_25 gap3: exact, iterative_default, iterative_tuned, probe; vectors 0, 1, 3, 7, 8, 9, 10, 12, 14, 15, 16, 17, 18 | hm_clothes_25 lo1: probe; vectors 18
- Calibration (D2) 2026-10-30 12:20:22 UTC, 53.0 %: 67 items. hm_clothes_25 idx3: exact, iterative_default, iterative_tuned, probe; vectors 0, 2, 3, 9, 10, 14, 15, 16, 18, 19 | hm_clothes_25 lo2: exact, iterative_default, iterative_tuned, probe; vectors 1, 4, 7, 8, 10, 11, 18, 19
- Calibration (D2) 2026-10-30 12:55:58 UTC, 62.8 %: 65 items. hm_clothes_100 gap1: probe; vectors 10 | hm_clothes_100 idx3: exact, iterative_default, iterative_tuned, probe; vectors 0, 1, 3, 4, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19
- Task 4 2026-10-31 01:49:48 UTC, 41.5 %: 75 items. hm_clothes_75 h2d (ho2): 14 modes; vectors 43, 45, 49, 53, 55, 56
- Task 4 2026-10-31 01:54:53 UTC, 43.0 %: 78 items. hm_clothes_75 h2c (ho2): 14 modes; vectors 40, 53, 55 | hm_clothes_75 h2d (ho2): 14 modes; vectors 48, 57, 58
- Task 4 2026-10-31 02:30:27 UTC, 100 %: 77 items. hm_clothes_75 gap3: 13 modes; vectors 2, 3, 7, 8, 14, 15, 18
- Task 4 2026-10-31 04:52:38 UTC, 44.4 %: 65 items. hm_clothes_50 gap3: 13 modes; vectors 0, 4, 5, 8, 15, 18

None of the affected cells is within 20 % of the 500 ms limit (cell latencies are <= 270 ms or >= about 980 ms for the routes or modes concerned), so no verdict could change. Nothing was re-run. Earlier progress reports omitted the readings at 12:55:58 (calibration) and 01:49:48 and 01:54:53 (Task 4); `reports/phase_e_results_2026-10-31.md` lists all of them.

## 2026-10-31 — Phase E Task 5 (concurrency test) not run (no result changed)

Task 5 of the Amendment 9 testing prompt (concurrency test, optional) was **not run**, by the author's decision on 31 Oct 2026, because of time; it is first in the tagged cut order of `PHASE_E_AMENDMENT_9.md`. No output exists for it; no Phase E result depends on it.

## 2026-10-31 — Checksum housekeeping (no result changed)

- **12 missing entries added** to `outputs/data_checksums.json` for committed 13 Oct outputs that had none (`outputs/embedding_build_2026-10-13/` 2 files, `outputs/phase_d_gemini_scaleup_smoke_2026-10-13/` 5, `outputs/scaleup_checks_2026-10-13/` 2, `outputs/scaleup_confirmation_2026-10-13/` 3), hashed as committed; the two cache/selection hashes equal those recorded in Amendment 7 Step 1. Total entries 285.
- **Two registered hashes no longer match the files on disk:** `outputs/hallucination_classification_2026-10-23/labelling_sheet.csv` and `labelling_sheet_check.csv`. Cause: line endings only. The files were registered as written by Python's csv module (CRLF row endings, LF inside quoted passages); git stored them with LF and checks them out with CRLF everywhere. Rewriting the committed content with CSV row endings reproduces both registered hashes exactly (99,823 and 100,024 bytes). The content is unchanged; the existing entries were not edited.

## 2026-11-01 — Phase F Task 3: calibration refused three times by the quiet-rule start check, then restarted (no data collected before the restart)

The edgar calibration (`PHASE_F_AMENDMENT_11.md` section 3) did not start: the start check refused it three times in a row, 5 minutes apart, on 2026-11-01 local time (2026-10-31 21:57, 22:03 and 22:09 UTC). The rule applied is the tagged Addendum 2 (`phase-e-amendment-9-addendum-2-2026-10-30`, `PHASE_E_AMENDMENT_9_ADDENDUM_2.md`), verbatim:

> - Measure: Windows performance counter `\Processor(_Total)\% Processor Time`, 6 consecutive samples at a 5 s interval (`Get-Counter -SampleInterval 5 -MaxSamples 6`, about 30 s); each sample is the average over its interval.
> - The session starts only if no torrent client, Ollama or Jupyter process runs **and** the mean of the 6 samples is **<= 25 %**. The limit, the process list and "otherwise the session does not start" are unchanged.

| attempt | UTC | samples (%) | mean | listed processes |
|---|---|---|---|---|
| 1 | 2026-10-31 21:57:10 | 39.74, 47.7, 46.61, 64.18, 71.74, 74.84 | 57.5 % | none |
| 2 | 2026-10-31 22:03:23 | 60.89, 60.78, 62.25, 58.73, 61.6, 59.89 | 60.7 % | none |
| 3 | 2026-10-31 22:09:37 | 56.56, 62.08, 58.04, 60.38, 59.81, 62.33 | 59.9 % | none |

The load came from the Kaspersky `avp` process (a per-process sample showed about 480 % of one core, about 40 % of the 12 logical processors). Three refusals in a row is a stop condition of the Phase F evaluation prompt, so the session stopped. **No timed data was collected and no paid call was made**; the only calibration outputs are `grid_filters.json` (built before any timing) and the three refused checks, kept in `outputs/edgar_calibration_2026-11-01/`.

The scan was stopped by the author. The calibration was then restarted with the same saved grid filters (`grid_filters.json`, unchanged) and a fresh quiet-rule start check (a new count of three attempts). The rule, its measure and its limit were not changed or overridden. Between the stop and the restart, tests for the Task 4-6 code were added and committed (`3d98f66`) so that no code or test work runs during timing.

## 2026-11-01 — Phase F Task 4: VecAdvisor candidate with ef_search outside pgvector's range (decided before any timed data)

The first Task 4 session (quiet check passed at attempt 1, 17.8 %) stopped in the pre-flight plan check, before ground truth and before any timed item: on 2 pairs the executed VecAdvisor strategy was `postfilter` with `ef_search = 1500`, and PostgreSQL rejected it (`1500 is outside the valid range for parameter "hnsw.ef_search" (1 .. 1000)`, pgvector 0.8.3). Only `quiet_checks_1793506395_1.json` was written.

The tagged Amendment 11 section 4 (`phase-f-amendment-11-2026-11-01`) covers two cases, verbatim:

> "if that candidate requires a new database object (partial or partition index), the pair is recorded **`vecadvisor_unavailable`** (reason `requires_new_object`) and VecAdvisor's next-ranked candidate that needs no new object is executed (its own ranking)."

> "If `recommend` errors or returns no usable candidate, the pair is recorded `vecadvisor_unavailable` (reason `error`) and **exact** is executed, the fallback VecAdvisor's own output names ("exact is the recall-safe fallback")."

It also states "Strategies run with VecAdvisor's own parameters, no guard". A candidate whose parameter is outside pgvector's allowed range (`hnsw.ef_search` 1-1000) is not covered by either case.

**Decision (author, 2026-11-01):** such a candidate is treated like one that needs a new database object: it is skipped, and VecAdvisor's next-ranked candidate that can run here is executed with VecAdvisor's own parameters; the pair is recorded `vecadvisor_unavailable`, reason `invalid_parameter`. Why: it is consistent with the new-object rule (the recommendation cannot be executed on this database as given, so VecAdvisor's own ranking decides the substitute), and no VecAdvisor parameter is changed (the value is not clamped to 1000). The full ranking stays in `vecadvisor_decisions.json` (the cached reports; the choices were re-derived from them without a new `recommend` call; each changed pair keeps its previous choice under `superseded_choice`, and every pair lists its skipped candidates under `skipped`). Code: `src/phase_f_edgar/vecadvisor_adapter.py` (`EF_SEARCH_MAX = 1000`), test `test_choose_skips_ef_search_above_pgvector_range`.

Affected pairs (both: rank 1 `partial` needs a new object; rank 2 `postfilter` ef_search 1500 skipped; rank 3 `iterative_relaxed`, ef_search 40, max_scan_tuples 20000, executed):

- `edgar_q059|year+section`
- `edgar_q060|year+section`

VecAdvisor decisions after the change: 111 top-ranked candidate executed, 47 `requires_new_object`, 2 `invalid_parameter`; executed strategies exact 83, iterative_relaxed 74, postfilter 3. Task 4 is restarted with a fresh quiet check.

## 2026-11-01 — Phase F Task 6: label X (refusal) added to the S/C/N validation labels (recorded before any statistic was computed from the labels)

The validation sample of `PHASE_F_AMENDMENT_11.md` section 6 (`phase-f-amendment-11-2026-11-01`) is labelled "S / C / N by the Amendment 5 definitions, verbatim: "**S** = the answer number appears in the retrieved text; **C** = the answer can be calculated from numbers in the retrieved text; **N** = the answer is not supported by the retrieved text."" The tagged Amendment 5 (`phase-d-amendment-5-2026-10-23`, `PHASE_D_AMENDMENT_5.md`) states the same definitions, verbatim: "**Human label** (entered by the user): **S** = the answer number appears in the retrieved text; **C** = the answer can be calculated from numbers in the retrieved text; **N** = the answer is not supported by the retrieved text."

These definitions describe an answer that gives a number. They do not cover a **refusal**: an answer stating that the evidence does not contain the figure, which the Amendment 11 class rule (`abstained` = "not answerable", no number, or a failed call) scores as wrong because the parsed number is a year or date in the refusal (e.g. "... during fiscal year 2018" parsed as 2018) or a figure quoted inside it. 18 of the 40 sampled rows are such refusals.

**Decision (author, 2026-11-01):** a fourth label **X** = refusal whose parsed number is a year or date or a figure quoted inside the refusal. X was drafted by the AI assistant and confirmed by the author on all 18 rows. X is **exploratory**: X rows are reported separately and excluded from the S/C/N agreement with the `wrong_not_in_context` proxy; the pre-registered classes, scores and P1-P5 verdicts are unchanged. Labels were drafted by the AI assistant and confirmed or changed by the author (one change: L13 S to N). Author file `outputs/edgar_analysis_review_2026-11-01/label_sheet_author.csv` (committed as saved); joined sheet (original columns plus the author's `author_label` and `author_note`) `outputs/edgar_analysis_labels_joined_2026-11-01/label_sheet_joined.csv`, code `src/phase_f_edgar/join_labels_edgar.py`.

## 2026-11-15 — Straddle-T evaluation plan (design note; no runs executed yet)

Planned follow-up to test both sides of `T` on EDGAR (`edgar_chunks`, k = 15) and FinQA (`finqa_evidence`, k = 15) without changing any frozen Phase E or Phase F outputs:

- **Primary vs. secondary:** Primary analysis is EDGAR under `T_edgar = 0.3786921696945195` (noting it came from Amendment 11's empty-interval minimum-failures fallback). Secondary analysis is EDGAR and FinQA under `T_hm = 0.07119177617441379` (transfer test).
- **Revised EDGAR bands:** Because `4 * T_edgar = 1.5148 > 1.0`, the `s >= 4T` band is empty on `edgar_chunks`. EDGAR uses Far below (`s <= T/2`), Near below (`T/2 < s <= T`), Near above (`T < s <= 2T`, up to ~0.7574), and an optional "very wide" band (`s > 2T`) if SQL enumeration finds filters there.
- **Scope:** Calibration sensitivity (varying recall target and latency limit L, plus 10/25/50/100% row subsamples) and a disjoint calibration/test split precede any new timed retrieval run; answer-level runs remain a separate later amendment.

## 2026-11-15 — Repository hygiene, post-hoc commits, and root `outputs/sweep_results.jsonl` audit

- **Post-hoc commits on 2026-11-15:**
  - `a56b4ec`: `src/phase_a_sweep/run_phase_a_v2.py`, `src/phase_a_sweep/targeted_sweeps.py`, `src/phase_d_validation/finqa_selectivity_census.py`, `src/phase_d_validation/test_retest_reliability.py`, `scripts/straddle_t_enumerate.py`.
  - `a4055b3`: `outputs/straddle_t_feasibility_2026-11-15/` (including `followup/` and `pool/`, all files < 5 MB).
  - `7169c48`: `outputs/data_checksums_posthoc_2026-11-15.json` (holds after-the-fact SHA-256, size, and mtime values recorded on 2026-11-15; not freeze-time checksums; `outputs/data_checksums.json` unchanged).
  - `447d932`: `DEVIATION_LOG.md` and `docs/preregistration/INDEX.md`.
- **Root `outputs/sweep_results.jsonl` status:** The working-tree `outputs/sweep_results.jsonl` (1,100 rows, timestamps `2026-09-04T02:48:30.704414+00:00` to `2026-09-04T03:06:44.780293+00:00`) differs in content from the committed `HEAD` version (1,100 rows, timestamps `2026-08-23T02:22:25.361953+00:00` to `2026-08-23T02:35:09.533592+00:00`) and has **not** been committed.
- **Step 1 audit result:** No number in any report or protocol is derived from the root `outputs/sweep_results.jsonl`. Phase A reports derive numbers from `outputs/phase_a_v1/sweep_results.jsonl` and `outputs/phase_a_v2/sweep_results.jsonl` (and `reports/phase_d_local_2026-10-12.md` only notes the dirty working-tree file as left as found).

## 2026-11-15 (Part 2) — Further repository hygiene, `thresholds_v2.json`, and Phase A script attribution

- **Tracking state (Step 1):** `outputs/phase_a_arms/` (27 files) and `outputs/phase_a_v1/` (3 files) were already tracked and clean; `outputs/phase_a_v2/` (5 files) was untracked. `outputs/phase_a_v1/sweep_results.jsonl` (SHA-256 `daacb684...`) matches the 2026-09-04 working-tree `outputs/sweep_results.jsonl`, not the 2026-08-23 `HEAD` version (`0c533f2a...`). `ann-filtering-benchmark-datasets` is a git submodule (`160000` at `ff4eda5`) with untracked content (~2.39 GB).
- **`outputs/thresholds_v2.json` (Step 2):** 2 bytes (`{}`), no git history. Tracked citations (`docs/POLICY_V2_PROPOSAL.md`, `reports/policy_audit_2026-10-10.md`) explicitly document that it is empty `{}` and would raise `ValueError` if passed. Left untracked and untouched.
- **October Phase A script attribution (Step 3):** `outputs/phase_a_v2/` (2026-09-30) was written by `run_phase_a_v2.py` -> `sweep_orchestrator.py` + `logger.py` (modified 2026-09-30). However, the October preregistered runs (`arm_comparison.py`, `holdout_run.py`, `holdout2_run.py`) do **not** import `logger.py` or `sweep_orchestrator.py` and log their own per-row schema (`hnsw_iterative_scan`, `hnsw_ef_search`, `git_commit`, `pg_version`, `pgvector_version`). Accordingly, `logger.py` and `sweep_orchestrator.py` were **not** committed under Step 5a.
- **Commits made:** `25f68fb` (`outputs/phase_a_v2/`), `485da5f` (Phase D Ollama `.jsonl`/`.csv`), `8981fc4` (root `outputs/sweep_results.jsonl`), `89b6209` (`METHODOLOGY_AUDIT.md`), `334e931` (early Phase A/C outputs), `ddcb11d` (early Phase D outputs), `d726704` (`outputs/data_checksums_posthoc_2026-11-15_part2.json`).
- **Deliberately not committed:** `src/phase_a_sweep/logger.py`, `src/phase_a_sweep/sweep_orchestrator.py`, `notebooks/correlation_verification.ipynb`, `notebooks/selectivity_impact_analysis.ipynb`, `outputs/thresholds_v2.json`, scratch files (`connection_test.py`, `explain.py`, `replay.py`, `replay_output.txt`), `reports/*.zip`, and `ann-filtering-benchmark-datasets`.

## 2026-11-15 (Part 3) — Final pre-straddle-T hygiene and environment snapshot

- **Step 1a (`data_checksums.json`):** SHA-256 `daacb6842222e7e42ffcf080c2c5ada503fa03bee6cdffa345bd89fa68c41249` (455,004 bytes) is recorded in `outputs/data_checksums.json` for both `outputs/phase_a_v1/sweep_results.jsonl` and `outputs/sweep_results.jsonl`.
- **Step 1b (October Phase A `git_commit` audit):** All 9 distinct `git_commit` hashes logged in `outputs/phase_a_arms/*.jsonl` and `outputs/phase_a_holdout*/*.jsonl` exist in this repository (dated `2026-10-10` to `2026-10-12`); `resumes.jsonl` logs `git_dirty_used_files = False`. All four previously modified files (`logger.py`, `sweep_orchestrator.py` `2026-09-30`; `sweep_results.jsonl` `2026-09-04`; `correlation_verification.ipynb` `2026-08-22`) had mtimes predating all 9 October commits.
- **Step 1c (Submodule):** `ann-filtering-benchmark-datasets` (`ff4eda5`, `https://github.com/qdrant/ann-filtering-benchmark-datasets.git`) contains 5 untracked data files (`data/filters.json`, `data/hnm.tgz`, `data/payloads.jsonl`, `data/tests.jsonl`, `data/vectors.npy`) totaling 2,390,026,680 bytes (~2.23 GB).
- **Commits made (Steps 2 & 3):** `ee08d38` (`logger.py`, `sweep_orchestrator.py`), `a025a88` (`connection_test.py`, `explain.py`, `replay.py`, `replay_output.txt`), `0690546` (`outputs/thresholds_v2.json`), `60f882c` (`notebooks/correlation_verification.ipynb`, `notebooks/selectivity_impact_analysis.ipynb`), `3a20691` (`.gitignore` zip entries), `dc129ee` (`outputs/straddle_t_env_snapshot_2026-11-15.{json,md}`).
- **Final status:** `config/`, `src/`, `scripts/`, and `docs/` are clean; ready for `pre-straddle-t-2026-11-15`.

## 2026-11-15 (Part 4) — Phase G Amendment 12 pre-registration

- **Pre-registration added:** `docs/preregistration/PHASE_G_AMENDMENT_12.md` and `docs/preregistration/INDEX.md` committed before any straddle-T recall or latency measurement, anchored to `pre-straddle-t-2026-11-15` (`5798a09`).
- **Pre-commit checks:** Verified Amendment 11 arm names (`src/phase_f_edgar/compare_edgar.py`), quiet-machine rule (`PHASE_E_AMENDMENT_9.md` line 32; `PHASE_E_AMENDMENT_9_ADDENDUM_2.md` lines 18-21; `PHASE_F_AMENDMENT_11.md` lines 25, 39), `default_hnsw` settings (`hnsw.ef_search = 40`, `hnsw.iterative_scan = off`, `hnsw.max_scan_tuples` unset), VecAdvisor compatibility (runs on `edgar_chunks` with `requires_new_object` fallback; cannot parse `finqa_evidence` JSONB expressions), and candidate pool counts (153/160 EDGAR usable, 3 `near_below` filters, 605 FinQA eligible in all 4 bands, 1 EDGAR `far_above` filter covering 30/40 questions, 6 EDGAR `T_hm` `near_below` filters covering 10/40 questions).

## 2026-11-15 (Part 5) — Phase G Amendment 12 Addendum 1

- **Addendum 1 added:** `docs/preregistration/PHASE_G_AMENDMENT_12_ADDENDUM_1.md` and `docs/preregistration/INDEX.md` committed before any straddle-T measurement. Corrects Amendment 12 Section 12 on `jit = off` / `statement_timeout = 120000 ms` (`configure_session`) and per-route `enable_*` / `hnsw.*` settings (`route_settings` in `src/phase_e_router/retriever.py`, `config/router_edgar.json`), documents VecAdvisor unavailability expectation, and clarifies that the oracle arm is computed offline.
