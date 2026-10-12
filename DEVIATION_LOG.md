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
