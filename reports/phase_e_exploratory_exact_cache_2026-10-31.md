# Exploratory, not pre-registered: did tuned-iterative runs slow exact in the D2 session?

Changes no T, interval or verdict. Script `src/phase_e_router/explore_exact_cache.py`; outputs `outputs/phase_e_exploratory_exact_cache_2026-10-31/` (checksummed).

**Design.** Forced-exact only (no tuned iterative, no other route in the session) on the in-sample cells at s = 0.0478 (lo4) and 0.1061 (lo5), all five tables, vectors 0-19 (200 items). Per vector: normal execution, warm-up, 5 timed `EXPLAIN (ANALYZE, BUFFERS)` Execution Times (the D2 metric), shared-buffer hits/reads recorded on every timed repetition. Per table one untimed exact query first (D2 also ran one unfiltered ANN query there). Seed 20261101. Quiet check (Addendum 2) passed at 18.3 %; in-session host CPU 8-46 % (1-min log). Same server settings and the same 2 GB WSL VM as D2 and Task 4.

| table | lo4: this check / D2 / stored (ms) | lo5: this check / D2 / stored (ms) |
|---|---|---|
| hm_clothes_0 | 176.7 / 176.8 / 284.8 | 452.3 / 465.6 / 283.4 |
| hm_clothes_25 | 178.4 / 173.7 / 97.9 | 463.1 / 449.1 / 252.6 |
| hm_clothes_50 | 178.4 / 175.7 / 154.8 | 459.2 / 452.3 / 316.5 |
| hm_clothes_75 | 178.2 / 176.0 / 125.5 | 457.3 / 455.1 / 266.9 |
| hm_clothes_100 | 177.9 / 173.2 / 113.0 | 453.9 / 449.9 / 262.2 |

(cell medians of per-vector medians; recall 1.0 everywhere; 70 of 200 vectors faster than in D2.)

**Buffers per query (median).** lo4: about 26,400 shared hits, 0 reads (hit ratio 1.0). lo5: about 39,200 hits and 17,900 reads (hit ratio 0.68-0.69) on every table; the reads recur on every repetition, i.e. the lo5 working set does not stay in the 128 MB shared_buffers. Whether a "read" came from the OS page cache or from disk is not measured.

**Reading.** Without any tuned-iterative runs, exact reproduces the D2 latencies within about 3 % (lo4 within 5 ms, lo5 within 14 ms). Eviction by tuned-iterative runs in the mixed session therefore does **not** explain why D2 exact was slower than the stored runs at s = 0.1061 (about 450 vs 250-320 ms). The lo5 shared-buffer reads are consistent with a memory-bound cost, but this check does not identify why the stored runs were faster; the stored runs' VM memory is not recorded, and the 2 GB VM cap (set before D2) was not varied here.
