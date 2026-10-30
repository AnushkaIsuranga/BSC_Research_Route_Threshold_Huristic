# Phase E, Amendment 9, Addendum 1: early stop for slow routes; llm_router prompt limitation

**Status:** written 2026-10-30, committed and tagged `phase-e-amendment-9-addendum-1-2026-10-30` before the D2 calibration session and before Task 4. Amends `PHASE_E_AMENDMENT_9.md` (tag `phase-e-amendment-9-2026-10-30`) only where stated; everything else is unchanged.

## Why it was added

While testing the router module, tuned iterative (`hnsw.max_scan_tuples` 100000, `hnsw.scan_mem_multiplier` 4) was timed on in-sample cells only (hm_clothes_0 lo1, hm_clothes_100 lo2/lo3, vectors 0-1) at **0.2-14 s per query**, against 150-190 ms for default iterative (`DEVIATION_LOG.md`, 2026-10-30). This rule was added after those smoke tests and **before any timed-session data existed** (no row of `outputs/phase_e_calibration_hm_2026-10-30/` or `outputs/phase_e_comparison_hm_2026-10-31/` had been written). Its purpose is to bound run time, not to change results.

## Early-stop rule (D2 session and Task 4)

- Applies to every route (D2: exact, default iterative, tuned iterative, probe) and every mode (Task 4), at every cell.
- Unit: one (cell, vector, route/mode). After the normal execution (rows and recall, always measured) and the untimed warm-up, the timed repetitions start. **If the median of the first 2 timed repetitions exceeds 3 x L = 1,500 ms**, the remaining 3 repetitions are skipped; that vector's latency is the median of the 2 (> 1,500 ms, i.e. > L); its recall and rows are kept; the row is flagged `early_stop`. Latency metric unchanged (D2: EXPLAIN ANALYZE Execution Time; Task 4: end-to-end wall-clock).
- A cell is flagged `early_stop` if any of its 20 vectors was early-stopped for that route/mode. The number of early-stopped cells (and vectors) is reported per route/mode.
- **Verdicts.** The pass rule (Amendment 1, A3) is unchanged and still computed on the median of the 20 per-vector medians. **Reading of "record the cell as failing on latency":** the stop acts per vector, because marking a whole cell failing from one slow vector could fail a cell whose median of per-vector medians is <= L, which would change a verdict, contrary to the rule's intent. An early-stopped vector is above L on 2 of 2 repetitions; with 5 repetitions its median could fall to <= L only if all 3 skipped repetitions were <= L, so a verdict can change only if, in addition, that vector decides the cell median. This possibility is stated, not tested. In practice every cell whose early-stopped vectors make up the majority fails latency either way.
- Guard latency (D2) = iterative + exact per-vector latency as before; with an early-stopped component it is > 1,500 ms.

## llm_router limitation (D5 confirmed)

The FinQA router system prompt (`NAIVE_INFORMED_ROUTER_SYSTEM`, `src/phase_b_router/router.py`) is used verbatim, as D5 requires. It describes the metadata filter as "(company ticker and fiscal year)", which is wrong for H&M; the user message states the actual H&M filter. This is a **limitation of the llm_router baseline on H&M**: the model routes from a prompt written for another corpus, and its results are not evidence about an LLM router with a corpus-specific prompt.

## Run time

The D2 session estimate is revised to about 3-3.5 h (`DEVIATION_LOG.md`); early stop bounds the tuned-iterative cost at low selectivity to about 2 timed repetitions per slow vector.
