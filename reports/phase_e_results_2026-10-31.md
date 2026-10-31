# Phase E results: band-rule router on H&M (Amendment 9)

Pre-registration: `docs/preregistration/PHASE_E_AMENDMENT_9.md` (tag `phase-e-amendment-9-2026-10-30`), Addendum 1 (early stop, tag `phase-e-amendment-9-addendum-1-2026-10-30`), Addendum 2 (quiet-rule CPU measure, tag `phase-e-amendment-9-addendum-2-2026-10-30`). Data: H&M tables hm_clothes_0/25/50/75/100 (105,100 rows each, 2,048-d embeddings, HNSW on `embedding::halfvec(2048)`, cosine), k = 10, ef_search 40, pass rule = mean recall@10 >= 0.90 and median of per-vector medians <= L = 500 ms with all 20 vectors valid. Server as found (shared_buffers 128MB, work_mem 4MB); WSL/Docker VM memory capped at 2 GB (`.wslconfig`, set 30 Oct 09:40 UTC, before both sessions). Per-mode, per-cell CSV for figures: `outputs/phase_e_final_2026-10-31/per_mode_cell_summary.csv`.

## 1. Calibration (D2 session, commit `ecc12aa`, tag `phase-e-calibration-hm-2026-10-30`; report `reports/phase_e_calibration_hm_2026-10-30.md`)

65 in-sample cells, 5,200 items, 0 errors, 152 min. Latency = EXPLAIN ANALYZE Execution Time.

| | safe interval | T |
|---|---|---|
| pooled, default iterative + guard | (0.0478, 0.1061] | **0.0712** |
| pooled, tuned iterative + guard | (0.0478, 0.1061] | **0.0712** |
| hm_clothes_100 | (0.0478, 0.1061] | 0.0712 |
| hm_clothes_25 | (0.0001, 0.1061] | 0.0036 |
| hm_clothes_0 / 50 / 75 | default (0.0008, 0.1061]; tuned (0.0001, 0.1061] | 0.0095 / 0.0036 |

Exact latency, quiet session vs stored runs (range over the five tables):

| s | 0.0001 | 0.0008 | 0.0105 | 0.0478 | 0.1061 | 0.2038 | 0.2139 | 0.4705 |
|---|---|---|---|---|---|---|---|---|
| quiet (ms) | 0.6 | 3.3-3.6 | 39-41 | 173-177 | 449-466 | 832-847 | 843-888 | 1,777-1,862 |
| stored (ms) | 0.3-0.5 | 1.9-2.5 | 24-68 | 98-285 | 253-317 | 547-1,080 | 489-1,271 | 1,131-3,419 |

Pooled s_exact_max is 0.1061 with either data set. **Correction to the calibration report:** per table, the stored runs would give s_exact_max = 0.2139 on hm_clothes_25 (491.1 ms) and hm_clothes_100 (488.9 ms), not 0.1061; the pooled value (all five tables must pass) is unaffected. The interval opens at the last iterative-failing grid point and closes at the last exact-passing one; no grid point lies in (0.0478, 0.1061), so any T there routes the in-sample cells identically.

## 2. Task 4 comparison (commit `82128e2`; 30,900 items, 0 errors, 642 min; end-to-end wall-clock latency)

| mode | in-sample | ho1 | ho2 | median ms in / ho1 / ho2 |
|---|---|---|---|---|
| router | 65/65 | 25/25 | 25/25 | 16.1 / 84.9 / 16.5 |
| router_tuned | 65/65 | 25/25 | 25/25 | 15.9 / 84.2 / 16.5 |
| router_no_guard | 65/65 | 25/25 | 25/25 | 16.0 / 84.6 / 16.4 |
| router_always_count | 65/65 | 25/25 | 25/25 | 19.1 / 87.3 / 20.1 |
| fixed_t_0_1 | 65/65 | 25/25 | 25/25 | 16.1 / 84.5 / 16.5 |
| oracle | 65/65 | 25/25 | 25/25 | 10.9 / 14.4 / 11.1 |
| iterative_tuned | 59/65 | 25/25 | 25/25 | 11.4 / 14.4 / 11.2 |
| always_iterative | 54/65 | 24/25 | 25/25 | 11.4 / 15.0 / 11.3 |
| local_probe | 64/65 | 23/25 | 23/25 | 23.1 / 123.5 / 23.3 |
| router_plus_probe | 64/65 | 23/25 | 23/25 | 28.3 / 128.5 / 28.7 |
| planner_iterative | 45/65 | 15/25 | 15/25 | 47.7 / 251.4 / 11.5 |
| retry_exact | 45/65 | 15/25 | 15/25 | 54.9 / 259.8 / 12.8 |
| always_exact | 25/65 | 15/25 | 0/25 | 827.9 / 248.7 / 1,236.1 |
| default_hnsw | 11/65 | 0/25 | 7/25 | 10.1 / 10.4 / 10.7 |
| llm_router | - | 15/25 | 3/25 | - / 250.5 / 983.9 |

(Median of the cell medians. Early-stopped vectors: always_exact 231 in 18 cells, retry_exact 48/12, llm_router 24/5, router_plus_probe 19/7, local_probe 18/6, iterative_tuned 2/2, planner_iterative 1/1, router variants 0. llm_router cost USD 0.0026.)

## 3. Hypotheses

- **H1 held (retrospective):** the guard fixes the under-fill cells (lo1 on all five tables: default iterative recall 0.18-0.26 with 18-20/20 under-filled; with guard 0.995-1.0) and not the full-k low-recall cells (hm_clothes_50 lo2 0.865, hm_clothes_100 lo3 0.85, lo4 0.795 with guard).
- **H2 held:** pooled T_default = 0.0712 lies in (0.0478, 0.2038]; the quiet exact latencies do not move the pooled s_exact_max (0.1061 with stored data too), but s_exact_max is 0.1061, not the earlier 0.2038.
- **H3 partly:** tuned iterative passes hm_clothes_100 lo3 (0.925, 127 ms) and hm_clothes_50 lo2 (0.985, 289 ms) but fails hm_clothes_100 lo4 on latency (0.94, 961 ms), so the pooled interval does not widen; cost up to ~1.45 s on lo1.
- **H4 held:** router 50/50 held-out cells vs default_hnsw 7, planner_iterative 30, always_exact 15, always_iterative 49.
- **H5 held:** estimate-based and count-based routes agree on 115/115 cells (17 in the count band).
- **H6 held:** per-table T range 0.0036-0.0712; hm_clothes_100 has the narrowest interval.
- **H7 failed:** local_probe 46/50 vs router 50/50; its 4 failures are latency failures (hm_clothes_75/100 on ho5 and h2b, about 715-997 ms) where the probe sent locally sparse vectors to exact; probe overhead about 12 ms end to end, not "a few ms"; 276 vector-level route differences (263 router iterative / probe exact).

## 4. Load during the sessions (item 1)

The tagged Addendum 2 text on in-session load is: "Disclosure: 6 `Win32_Processor.LoadPercentage` readings are taken right after and stored with the check, not used for the decision. The 5-minute host-load log during the session records both measures and the top-5 processes." It contains **no in-session pause or re-run rule** (no 60 s rolling mean, no 40 % limit); the 25 % limit applies at session start only. A pause/re-run rule (10 s sampling; pause and re-run when the 60 s rolling mean exceeds 40 %) was drafted on 30 Oct in the author's planning notes but was not passed to the implementation session; it was never part of the pre-registered protocol (`DEVIATION_LOG.md`, 2026-10-31). The CPU logs hold one 1 s reading every ~5 min, so a 60 s rolling mean cannot be computed. Every logged reading above 40 % and the items finished within 60 s of it (`outputs/phase_e_final_2026-10-31/load_spike_check.json`):

| session | reading (UTC) | CPU | items within 60 s | cells | cells within 20 % of L (400-600 ms) |
|---|---|---|---|---|---|
| calibration | 12:10:12 | 43.8 % | 53 | hm_clothes_25 gap3 | 0 |
| calibration | 12:20:22 | 53.0 % | 67 | hm_clothes_25 idx3, lo2 | 0 |
| calibration | 12:55:58 | 62.8 % | 65 | hm_clothes_100 idx3, gap1 | 0 |
| Task 4 | 01:49:48 | 41.5 % | 75 | ho2 hm_clothes_75 h2d | 0 |
| Task 4 | 01:54:53 | 43.0 % | 78 | ho2 hm_clothes_75 h2c/h2d | 0 |
| Task 4 | 02:30:27 | 100 % | 77 | in-sample hm_clothes_75 gap3 | 0 |
| Task 4 | 04:52:38 | 44.4 % | 65 | in-sample hm_clothes_50 gap3 | 0 |

No affected cell lies within 20 % of L (they are at <= 270 ms or >= ~980 ms), so no verdict could change; nothing was re-run. **Correction:** earlier progress reports omitted the calibration reading at 12:55:58 (62.8 %) and the Task 4 readings at 01:49:48 and 01:54:53. Logged in `DEVIATION_LOG.md` (2026-10-31).

## 5. Held-out coverage (item 3)

| filter | s | router (band -> route, 5 tables x 20 vectors) | fixed_t_0_1 | router pass | always_iterative pass |
|---|---|---|---|---|---|
| ho1 | 0.0201 | exact -> exact | exact -> exact | 5/5 | 4/5 |
| ho2 | 0.0296 | exact -> exact | exact -> exact | 5/5 | 5/5 |
| ho3 | 0.0705 | count -> exact | count -> exact | 5/5 | 5/5 |
| ho4 | 0.1435 | iterative (60) / count (40) -> iterative | count -> iterative | 5/5 | 5/5 |
| ho5 | 0.1803 | iterative -> iterative | count -> iterative | 5/5 | 5/5 |
| h2a-h2e | 0.2304-0.4464 | iterative -> iterative | iterative -> iterative | 25/25 | 25/25 |

- No held-out filter lies in (0.0712, 0.1) and none below 0.0105 (the lowest is 0.0201), so the held-out sets never reach the regime where always_iterative fails in-sample (lo1-lo3).
- always_iterative's one held-out failure: ho1 on hm_clothes_100 (s 0.0201), **recall 0.895** (< 0.90) with every vector returning 10 rows (full-k rate 1.0), median 36 ms, p95 152 ms: a full-k recall shortfall, not under-fill.
- fixed_t_0_1 matched the router on every cell because, with no held-out filter between 0.0712 and 0.1, both thresholds give the same final route for every held-out filter: ho3 is counted by both (7,412 rows, below both caps 7,483 and 10,511), ho4/ho5 reach iterative by the band (router) or by the count (fixed_t_0_1, band (0.05, 0.2)), and the rest are outside both bands.

## 6. Ablation (item 4)

- **Guard triggers: 0** for router, router_tuned, router_always_count, fixed_t_0_1, local_probe and router_plus_probe (normal and timed runs, all sets). It fired only in modes without routing: retry_exact 9,036 and iterative_tuned 18 calls. The router guard is unexercised: the router sends every filter small enough to under-fill to exact.
- **router_tuned differs only above T:** same T (0.0712) and identical route decisions; recall differs on one cell, in-sample hm_clothes_100 lo5 (s 0.1061 >= T, iterative route): 0.93 vs 0.975. No cell differs by more than 10 % in recall or latency.
- **Router variants vs router, cells differing by > 10 % (recall or latency):** router_no_guard 0; router_tuned 0; fixed_t_0_1 8 (all latency, ho4/ho5 count step, +5 ms; no verdict change); router_always_count 84 (all latency, count on every query, +3-5 ms; no verdict change); router_plus_probe 108 (latency; 5 verdict changes, the probe-to-exact cells above). No variant differs from router by more than 10 % in recall on any cell.

## 7. Other findings

- **llm_router (D5):** the FinQA prompt used verbatim describes the filter as "company ticker and fiscal year"; on H&M it chose pre-filter (exact) for 9/10 held-out filters and post-filter (default HNSW) for h2e. Exact fails latency on every cell from ho4 (s 0.14) to h2d (30 cells, 563-1,624 ms); default HNSW on h2e fails recall on 2 of 5 tables (0.73, 0.85). A limitation of this baseline, not evidence about a corpus-specific LLM router.
- **VecAdvisor (D4):** not scored; version 0.1.0a6 cannot see the HNSW index on the expression `embedding::halfvec(2048)` (crashes when given it), skips its local probe, ranks only partial/exact, and assumes L2 while the index is cosine (`outputs/vecadvisor_check_2026-10-30/`).
- **Exploratory, not pre-registered** (`reports/phase_e_exploratory_exact_cache_2026-10-31.md`): exact without any tuned-iterative runs reproduced the calibration's exact latencies within ~3 %, so cache eviction by tuned iterative does not explain the slower-than-stored exact at s = 0.1061; lo5 shows ~17,900 shared-buffer reads per query.
- **FinQA cross-reference:** on the frozen 50 FinQA questions the Phase E router (T = 0.0712) routes all 50 to exact; the planner's ticker-year JSON estimate is 1 row for every question, 20x-697x too low, so the routing is right only because every FinQA selectivity is below T/2 (`reports/finqa_router_v3_route_check_2026-10-31.md`; selectivity counting costs about 17.7 ms per question, the router's estimate path 2.9 ms). The no-routing index path, always_hnsw (Amendment 10), returned 5.3 of 15 passages on average and was less accurate than policy_v2 (exact on all 50): pooled 0.520 vs 0.704, difference -0.184 [-0.288, -0.088] (`reports/phase_d_always_hnsw_2026-10-31.md`).

## 8. Limitations

- One data family for retrieval (H&M, five variants of one catalogue); FinQA was used only for the routing check and the always_hnsw answer arm cross-referenced in section 7.
- Task 5 (concurrency test) was not run (author's decision, 31 Oct; first in the tagged cut order; `DEVIATION_LOG.md`).
- One table size (105,100 rows); T is expressed as a selectivity but was calibrated at one N.
- Held-out filters were chosen after the in-sample behaviour was seen.
- Held-out cells cannot separate router from always_iterative or iterative_tuned except on one cell (ho1 x hm_clothes_100); none lies below s 0.0105 or in (0.0712, 0.1).
- The guard was never exercised by the router.
- Calibration is per deployment (server settings, VM memory, data size); the 2 GB VM cap and server-as-found settings are part of these results.
- Global selectivity only: the router uses a table-wide estimate; local sparsity is addressed only by the probe modes, which failed H7.
- Load spikes up to 100 % (single readings) occurred during both sessions; none touched a cell near the latency limit, but the sessions were not continuously quiet.
