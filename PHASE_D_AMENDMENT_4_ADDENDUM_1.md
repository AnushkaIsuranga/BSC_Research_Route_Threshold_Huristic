# Phase D, Amendment 4, Addendum 1: run control only

**Status:** written 2026-10-13, before any re-run of the smoke test and before any scale-up call; tagged `phase-d-amendment-4-addendum-1-2026-10-13`. It amends `PHASE_D_AMENDMENT_4.md` (tag `phase-d-amendment-4-2026-10-13`, not edited), section 5.

**Scope.** This addendum changes **run control only**: the error abort rule, the handling of HTTP 429, the call pace, an explicit single-attempt setting for the Gemini client, and error logging. It does **not** change the prompts, scoring, retrieval, model, generation settings, arms, analysis or the confirmation set (1,075 questions, SHA-256 `aff43f1f…04a3`). **No confirmation-set result existed when it was written:** the only confirmation-set model output is the aborted smoke test below (7 completed arm-runs, excluded from every analysis), and nothing in it informed these decisions beyond the occurrence of one 429 error.

## 1. Aborted smoke test

`outputs/phase_d_gemini_scaleup_smoke_2026-10-13/` (commit `96fadc0`; kept as it is, not edited or deleted): 10 questions × 4 arms planned, **7 arm-runs completed**, then the 8th call returned `429 RESOURCE_EXHAUSTED` from Vertex AI. That single error row exceeded the Amendment 4 rule (2% of 40 arm-runs = 0.8 rows) and aborted the run. USD 0.00904. The failed call's `total_ms` was 109,847 (about 110 s); the traceback in `error.log` is empty because it was captured outside the `except` block (a logging bug, fixed below).

## 2. Changes

1. **Abort rule (replaces Amendment 4 section 5(a)):** a fixed allowance of **8 error rows among the first 100 questions, regardless of run size** (also for runs with fewer than 100 questions). The run aborts, and cannot be resumed, when more than 8 counted error rows exist. Section 5(b) (projected cost > USD 12) and the USD 15 cap are unchanged.
2. **HTTP 429 RESOURCE_EXHAUSTED:** an error whose text contains `429` and `RESOURCE_EXHAUSTED` is classified `rate_limit_429` in `errors.jsonl` and is **not counted** toward the abort rule. Every error, including a 429, still **stops the run immediately**, is written to `errors.jsonl` and `error.log`, and is **never retried silently**. The run is continued only by the operator with `--resume` (logged in `resumes.jsonl`; settings and file hashes must be unchanged).
3. **Fixed pace:** at most **15 calls per minute**, implemented as a minimum spacing of **4.0 s between the starts of consecutive calls** (router and answer calls share one pacer); it only waits before a call: **no retries, no backoff**. Runner flag `--max-calls-per-minute 15`; the configured pace is recorded in `run_meta.json` (`pacing`). At this pace the scale-up (6,450 calls) takes at least 7.2 hours (the unpaced estimate was 4.8 hours at 22.5 calls per minute). No quota increase is requested.
4. **Single attempt per call (client-side retries disabled explicitly):** the Gemini backend now builds its client with `HttpOptions(retry_options=HttpRetryOptions(attempts=1))`. Recorded in `run_meta.json` (`client_retries`).
5. **Error logging:** the exception traceback is captured inside the `except` block and stored in `errors.jsonl` (`error_traceback`) and `error.log`; error rows carry `error_kind`. `run_meta.json` records the abort rules in force.

## 3. Finding behind item 4 (no paid call; documented here)

- Installed `google-genai` is 2.29.0. Its module comment says the client "will retry 4 times", but the code builds the retry strategy from `HttpOptions.retry_options`, and when that is `None` (the default, and what `llm_client.py` used until now) it returns `tenacity.stop_after_attempt(1)`: **one attempt, no retry.** The library's own retry defaults (5 attempts, delays from 1 s doubling to 60 s with jitter, on 408/429/5xx) apply only if `retry_options` is given without explicit values.
- Check made here: with the project's previous client construction and the HTTP transport call replaced by a function that raises 429, `generate_content` made **1 attempt and returned in 0.05 s**; with `HttpRetryOptions(attempts=3, …)` it made 3 attempts. So **client-side retries do not explain the 110 s** in the installed version. The cause of the 110 s is not established (candidates: a delay on the service side before the 429 was returned, or the network); no HTTP timeout is set in the client, so a slow response is not cut off. Item 4 therefore makes the existing single-attempt behaviour explicit and independent of library defaults; it does not change what was executed.
- `llm_client.py` set no retry option before; the Gemini full run of 12 October ran with the same defaults, i.e. single attempts. Its slowest rows: generation times median 2.3 s, 99th percentile 15.4 s, maximum 18.3 s (total up to 20.2 s); router maximum 12.1 s; 0 errors in 1,500 calls. No call approached 110 s.
- Not decided here: an explicit HTTP timeout (it would turn a long hang into an error and stop the run). Not added.

## 4. Tests (`tests/test_runner_resume.py`)

Fixed allowance independent of run size (10 and 100 questions; 8 rows pass, a 9th aborts; rows outside the first 100 questions are not counted); 429 not counted but classified; pacing spacing with an injected clock (starts at 0, 4, 9, 13 s for 15 calls/min; waits only when needed; shared by router and answer clients; none without a pacer); the Gemini client constructed with `attempts=1`; **one HTTP attempt per call with the real client and a 429, versus 3 attempts when retries are requested** (proves the difference); an integration test with the real database and cached embeddings in which a 429 stops the run although `--abort-error-rows 0`, is logged as `rate_limit_429` with a traceback, and `--resume` runs only the missing rows. Full suite: 147 passed, 0 skipped.

## 5. Next step

After this addendum is tagged, the smoke test is repeated once (10 questions × 4 arms, USD 1 cap, `--max-calls-per-minute 15`) into `outputs/phase_d_gemini_scaleup_smoke2_2026-10-13/`. Any error stops it; nothing is retried. The full scale-up waits for the user's explicit instruction.
