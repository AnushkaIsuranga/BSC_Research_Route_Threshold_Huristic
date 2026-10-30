# Phase E calibration on H&M (Amendment 9, Task 3)

Commit `ecc12aa`, tag `phase-e-calibration-hm-2026-10-30`. Outputs: `outputs/phase_e_calibration_hm_2026-10-30/` (checksummed), policy `config/policy_v3_hm.json`. Governing text: `PHASE_E_AMENDMENT_9.md`, Addendum 1 (early stop), Addendum 2 (quiet-rule CPU measure).

## Session

- 65 in-sample cells (13 filters x 5 tables), vectors 0-19, routes exact, default iterative, tuned iterative, probe; 5,200 items, 0 errors, 152 min (10:33-13:05 UTC, 30 Oct). Every plan as intended (pre-flight).
- Quiet check at start (Addendum 2): no blocking process; processor counter mean 20.5 % (17.0-24.7). In-session host CPU (5-min log, 1 s samples): mostly 15-30 %; **31-53 % during hm_clothes_25 (12:05-12:32 UTC)**, peak 53 % at 12:20. Reported, not corrected.
- **In-session load rule.** The tagged Addendum 2 (and Amendment 9, Addendum 1) contain no rule that pauses the session or re-runs items when load rises during a session; the 25 % limit applies at start only, and the in-session log is for disclosure. Nothing was re-run. The log samples every 5 min with a 1 s reading, so a 60 s rolling mean could not be computed from it in any case.
- **Host memory for the database (disclosure).** `%USERPROFILE%\.wslconfig` has `memory=2GB`; the file was saved at 09:40:15 UTC and the database container restarted at 09:40:55 UTC, 53 min before the session. The Docker/WSL VM therefore had 1.86 GB for the whole session, while each H&M table is about 1.7 GB (858 MB vectors + 825 MB index; 8.5 GB for five), so queries read largely from disk. The VM memory of the stored runs is not recorded. The environment record (`run_meta.json`) does not capture VM memory.

## Calibration (rule: exact if s < T, else iterative + guard)

| | safe interval | T |
|---|---|---|
| pooled, default iterative | (0.0478, 0.1061] | **0.0712** |
| pooled, tuned iterative | (0.0478, 0.1061] | **0.0712** |
| hm_clothes_100 | (0.0478, 0.1061] | 0.0712 |
| hm_clothes_25 | (0.0001, 0.1061] | 0.0036 |
| hm_clothes_0 / 50 / 75 | default (0.0008, 0.1061]; tuned (0.0001, 0.1061] | 0.0095; 0.0036 |

- Exact passes up to s = 0.1061 on every table (449-466 ms, limit 500 ms) and fails from 0.2038 (832-1,862 ms). The stored runs give the same s_exact_max (their exact at 0.2038 is 547-1,080 ms). Exact is slower than stored at 0.0478-0.1061 (about 450 vs 250-320 ms at 0.1061) and often faster at high s; cause not established.
- **H2** supported (0.0712 in (0.0478, 0.2038]). **H3** partly: tuned passes hm_clothes_100 lo3 (recall 0.925, 127 ms) and hm_clothes_50 lo2 (0.985, 289 ms) but fails hm_clothes_100 lo4 on latency (0.94, 961 ms), so the pooled tuned interval equals the default one. **H6** supported (hm_clothes_100 narrowest).
- Guard: default iterative under-fills lo1 (18-20/20 vectors per table); the guard brings recall to 0.995-1.0 at about 160-170 ms. Default iterative + guard still fails lo2 on four tables (recall 0.775-0.875) and hm_clothes_100 lo3/lo4.
- Early stop (Addendum 1): exact 131 vectors in 10 cells (idx2, idx3, all tables); tuned iterative 30 vectors in 5 cells (lo1, all tables); default iterative and probe none. All flagged cells fail latency either way.
- Probe: median about 5.5 ms; p < k for every vector at s <= 0.0105, and for a few vectors per cell at s >= 0.2038 (up to 11/20 on hm_clothes_100).

## Interval convention (T and procedure unchanged)

- As defined, the interval **closes at the last exact-passing grid point (0.1061)** but **opens at the last iterative-failing grid point (0.0478)**, the lower neighbour of s_iter_min = 0.1061 on hm_clothes_100. The two ends follow different conventions.
- On this grid no point lies strictly between 0.0478 and 0.1061, so any T in (0.0478, 0.1061] gives identical in-sample routing. Any T in (0.0478, 0.2038) gives identical in-sample **verdicts**: for T in (0.1061, 0.2038) the 0.1061 cells route to exact instead of iterative + guard, and both pass on all five tables.
- The earlier upper value 0.2038 was the first exact-failing grid point, not the last exact-passing one.

## Held-out filters near the threshold

- Held-out selectivities: ho1 0.0201, ho2 0.0296, ho3 0.0705, ho4 0.1435, ho5 0.1803; ho2 set 0.2304-0.4464 (same on all five tables).
- **No held-out filter lies between 0.0712 and 0.1**, so under true selectivity `fixed_t_0_1` and the calibrated router route every held-out cell the same way.
- Closest cases: ho3 (0.0705, 7,412 rows) is 71 rows below the router's count cap (floor(0.0712 x 105,100) + 1 = 7,483), so its count decides exact by a narrow margin; ho4 (0.1435) is just above 2T = 0.1424. Live routing uses planner estimates, which can differ from these values.
