# Retrospective policy evaluation on the 65 H&M cells — 2026-10-10

**[V]** = computed by `src/phase_c_analysis/policy_evaluation.py` from `outputs/phase_a_arms/results.jsonl` (via `arm_analysis.py`). **[I]** = interpretation. A cell passes when the arm the policy picks there has mean recall@10 >= 0.90 over all 20 vectors AND median latency <= 500 ms (median of the 20 per-vector medians). "Recall fail" and "latency fail" count the cells failing that SLA (a cell failing both is counted in both columns and in "both").

**In-sample warning.** P7 and P8 were chosen or tuned using these same 65 cells; their scores describe fit, not out-of-sample performance. P1-P6 are fixed before looking (P1/P2 are the unmodified `policy.py` with existing threshold files). The 65 cells are 5 tables x 13 filters over the same 20 query vectors and one set of 105,100 rows per table, so they are not 65 independent trials.

## 1. Summary

| policy | pass both SLAs | recall fail | latency fail | both fail | total fail |
|---|---|---|---|---|---|
| P1 matrix v1 (policy.py + phase_a_v1/thresholds.json, per-table tier; pre->FE, post->FH) | **29** / 65 | 5 | 31 | 0 | 36 |
| P2 matrix v2 (policy.py + phase_a_v2/thresholds.json, per-table tier; pre->FE, post->FH) | **27** / 65 | 7 | 31 | 0 | 38 |
| P3 planner-default (as measured) | **37** / 65 | 9 | 19 | 0 | 28 |
| P4 always forced-exact | **27** / 65 | 0 | 38 | 0 | 38 |
| P5 always forced-hnsw | **11** / 65 | 54 | 0 | 0 | 54 |
| P6 always iterative-relaxed | **54** / 65 | 11 | 0 | 0 | 11 |
| P7 route map of the amended decision rule [IN-SAMPLE: fitted on these cells] | **65** / 65 | 0 | 0 | 0 | 0 |
| P8 T=0.001: FE if selectivity < T else IR [IN-SAMPLE / exploratory] | **63** / 65 | 2 | 0 | 0 | 2 |
| P8 T=0.005: FE if selectivity < T else IR [IN-SAMPLE / exploratory] | **63** / 65 | 2 | 0 | 0 | 2 |
| P8 T=0.01: FE if selectivity < T else IR [IN-SAMPLE / exploratory] | **63** / 65 | 2 | 0 | 0 | 2 |
| P8 T=0.02: FE if selectivity < T else IR [IN-SAMPLE / exploratory] | **64** / 65 | 1 | 0 | 0 | 1 |
| P8 T=0.05: FE if selectivity < T else IR [IN-SAMPLE / exploratory] | **65** / 65 | 0 | 0 | 0 | 0 |
| P8 T=0.1: FE if selectivity < T else IR [IN-SAMPLE / exploratory] | **65** / 65 | 0 | 0 | 0 | 0 |

Pass counts by table [V]:

| policy | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|
| P1 | 6/13 | 6/13 | 6/13 | 5/13 | 6/13 |
| P2 | 5/13 | 6/13 | 5/13 | 5/13 | 6/13 |
| P3 | 9/13 | 9/13 | 8/13 | 6/13 | 5/13 |
| P4 | 5/13 | 6/13 | 5/13 | 5/13 | 6/13 |
| P5 | 4/13 | 3/13 | 3/13 | 1/13 | 0/13 |
| P6 | 11/13 | 12/13 | 11/13 | 11/13 | 9/13 |
| P7 | 13/13 | 13/13 | 13/13 | 13/13 | 13/13 |
| P8_0.001 | 13/13 | 13/13 | 13/13 | 13/13 | 11/13 |
| P8_0.005 | 13/13 | 13/13 | 13/13 | 13/13 | 11/13 |
| P8_0.01 | 13/13 | 13/13 | 13/13 | 13/13 | 11/13 |
| P8_0.02 | 13/13 | 13/13 | 13/13 | 13/13 | 12/13 |
| P8_0.05 | 13/13 | 13/13 | 13/13 | 13/13 | 13/13 |
| P8_0.1 | 13/13 | 13/13 | 13/13 | 13/13 | 13/13 |

Pass counts by selectivity region (cells per region = 5 tables x filters) [V]:

| policy | lo1-lo2 (0.0001-0.001) | lo3-lo5 (0.01-0.11) | ctl, gap1-gap3 (0.204-0.26) | gap4, idx1-idx3 (0.299-0.47) |
|---|---|---|---|---|
| P1 | 10/10 | 15/15 | 2/20 | 2/20 |
| P2 | 10/10 | 15/15 | 2/20 | 0/20 |
| P3 | 10/10 | 15/15 | 1/20 | 11/20 |
| P4 | 10/10 | 15/15 | 2/20 | 0/20 |
| P5 | 0/10 | 0/15 | 0/20 | 11/20 |
| P6 | 1/10 | 13/15 | 20/20 | 20/20 |
| P7 | 10/10 | 15/15 | 20/20 | 20/20 |
| P8_0.001 | 10/10 | 13/15 | 20/20 | 20/20 |
| P8_0.005 | 10/10 | 13/15 | 20/20 | 20/20 |
| P8_0.01 | 10/10 | 13/15 | 20/20 | 20/20 |
| P8_0.02 | 10/10 | 14/15 | 20/20 | 20/20 |
| P8_0.05 | 10/10 | 15/15 | 20/20 | 20/20 |
| P8_0.1 | 10/10 | 15/15 | 20/20 | 20/20 |

## 2. Routes per (table, filter)

**P1 matrix v1 (policy.py + phase_a_v1/thresholds.json, per-table tier; pre->FE, post->FH)** — cell text: arm (✓ pass / R recall fail / L latency fail / RL both) [V]

| filter | sel | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|---|
| lo1 | 0.00012 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo2 | 0.00085 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo3 | 0.01054 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo4 | 0.04777 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo5 | 0.10609 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| ctl | 0.20376 | FE L | FE L | FE L | FE L | FE L |
| gap1 | 0.21388 | FE L | FE ✓ | FE L | FE L | FE ✓ |
| gap2 | 0.23094 | FE L | FE L | FE L | FE L | FE L |
| gap3 | 0.25991 | FE L | FE L | FE L | FE L | FE L |
| gap4 | 0.29859 | FE L | FE L | FE L | FE L | FE L |
| idx1 | 0.32901 | FH ✓ | FE L | FH ✓ | FH R | FH R |
| idx2 | 0.37633 | FE L | FE L | FE L | FE L | FH R |
| idx3 | 0.47050 | FE L | FE L | FE L | FH R | FH R |

**P2 matrix v2 (policy.py + phase_a_v2/thresholds.json, per-table tier; pre->FE, post->FH)** — cell text: arm (✓ pass / R recall fail / L latency fail / RL both) [V]

| filter | sel | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|---|
| lo1 | 0.00012 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo2 | 0.00085 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo3 | 0.01054 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo4 | 0.04777 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo5 | 0.10609 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| ctl | 0.20376 | FH R | FH R | FE L | FE L | FE L |
| gap1 | 0.21388 | FE L | FE ✓ | FE L | FE L | FE ✓ |
| gap2 | 0.23094 | FE L | FE L | FE L | FE L | FE L |
| gap3 | 0.25991 | FE L | FE L | FE L | FE L | FE L |
| gap4 | 0.29859 | FE L | FE L | FE L | FE L | FE L |
| idx1 | 0.32901 | FE L | FE L | FE L | FH R | FH R |
| idx2 | 0.37633 | FE L | FE L | FE L | FE L | FH R |
| idx3 | 0.47050 | FE L | FE L | FE L | FH R | FH R |

**P7 route map of the amended decision rule [IN-SAMPLE: fitted on these cells]** — cell text: arm (✓ pass / R recall fail / L latency fail / RL both) [V]

| filter | sel | hm_clothes_0 | hm_clothes_25 | hm_clothes_50 | hm_clothes_75 | hm_clothes_100 |
|---|---|---|---|---|---|---|
| lo1 | 0.00012 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo2 | 0.00085 | FE ✓ | FE ✓ | FE ✓ | FE ✓ | FE ✓ |
| lo3 | 0.01054 | IR ✓ | IR ✓ | IR ✓ | IR ✓ | FE ✓ |
| lo4 | 0.04777 | IR ✓ | IR ✓ | IR ✓ | IR ✓ | FE ✓ |
| lo5 | 0.10609 | IR ✓ | IR ✓ | IR ✓ | IR ✓ | IR ✓ |
| ctl | 0.20376 | IR ✓ | IR ✓ | IR ✓ | IR ✓ | IR ✓ |
| gap1 | 0.21388 | IR ✓ | IR ✓ | IR ✓ | IR ✓ | IR ✓ |
| gap2 | 0.23094 | IR ✓ | IR ✓ | IR ✓ | IR ✓ | IR ✓ |
| gap3 | 0.25991 | IR ✓ | IR ✓ | IR ✓ | IR ✓ | IR ✓ |
| gap4 | 0.29859 | FH ✓ | IR ✓ | IR ✓ | IR ✓ | IR ✓ |
| idx1 | 0.32901 | FH ✓ | FH ✓ | FH ✓ | IR ✓ | IR ✓ |
| idx2 | 0.37633 | FH ✓ | FH ✓ | FH ✓ | FH ✓ | IR ✓ |
| idx3 | 0.47050 | FH ✓ | FH ✓ | FH ✓ | IR ✓ | IR ✓ |

P3 = planner-default in every cell; P4 = forced-exact; P5 = forced-hnsw; P6 = iterative-relaxed; P8 = forced-exact if selectivity < T else iterative-relaxed. The per-cell data for all policies (arm, recall, latency, flags) is in `outputs/phase_a_arms/analysis/policy_evaluation_cells.csv`.

## 3. Failing cells per policy

Format: filter (selectivity): tables with R = recall fail, L = latency fail, RL = both. [V]

**P1 matrix v1 (policy.py + phase_a_v1/thresholds.json, per-table tier; pre->FE, post->FH)** — 36 failing cell(s)
- ctl (0.20376): T0:L(1.00/865ms), T25:L(1.00/993ms), T50:L(1.00/1080ms), T75:L(1.00/547ms), T100:L(1.00/611ms)
- gap1 (0.21388): T0:L(1.00/1271ms), T50:L(1.00/624ms), T75:L(1.00/621ms)
- gap2 (0.23094): T0:L(1.00/1448ms), T25:L(1.00/694ms), T50:L(1.00/760ms), T75:L(1.00/1408ms), T100:L(1.00/521ms)
- gap3 (0.25991): T0:L(1.00/1943ms), T25:L(1.00/640ms), T50:L(1.00/781ms), T75:L(1.00/1867ms), T100:L(1.00/601ms)
- gap4 (0.29859): T0:L(1.00/782ms), T25:L(1.00/758ms), T50:L(1.00/6567ms), T75:L(1.00/1383ms), T100:L(1.00/644ms)
- idx1 (0.32901): T25:L(1.00/751ms), T75:R(0.84/1ms), T100:R(0.72/1ms)
- idx2 (0.37633): T0:L(1.00/889ms), T25:L(1.00/1089ms), T50:L(1.00/1206ms), T75:L(1.00/965ms), T100:R(0.80/1ms)
- idx3 (0.47050): T0:L(1.00/3273ms), T25:L(1.00/2465ms), T50:L(1.00/3419ms), T75:R(0.87/1ms), T100:R(0.70/1ms)

**P2 matrix v2 (policy.py + phase_a_v2/thresholds.json, per-table tier; pre->FE, post->FH)** — 38 failing cell(s)
- ctl (0.20376): T0:R(0.82/1ms), T25:R(0.72/1ms), T50:L(1.00/1080ms), T75:L(1.00/547ms), T100:L(1.00/611ms)
- gap1 (0.21388): T0:L(1.00/1271ms), T50:L(1.00/624ms), T75:L(1.00/621ms)
- gap2 (0.23094): T0:L(1.00/1448ms), T25:L(1.00/694ms), T50:L(1.00/760ms), T75:L(1.00/1408ms), T100:L(1.00/521ms)
- gap3 (0.25991): T0:L(1.00/1943ms), T25:L(1.00/640ms), T50:L(1.00/781ms), T75:L(1.00/1867ms), T100:L(1.00/601ms)
- gap4 (0.29859): T0:L(1.00/782ms), T25:L(1.00/758ms), T50:L(1.00/6567ms), T75:L(1.00/1383ms), T100:L(1.00/644ms)
- idx1 (0.32901): T0:L(1.00/886ms), T25:L(1.00/751ms), T50:L(1.00/2261ms), T75:R(0.84/1ms), T100:R(0.72/1ms)
- idx2 (0.37633): T0:L(1.00/889ms), T25:L(1.00/1089ms), T50:L(1.00/1206ms), T75:L(1.00/965ms), T100:R(0.80/1ms)
- idx3 (0.47050): T0:L(1.00/3273ms), T25:L(1.00/2465ms), T50:L(1.00/3419ms), T75:R(0.87/1ms), T100:R(0.70/1ms)

**P3 planner-default (as measured)** — 28 failing cell(s)
- ctl (0.20376): T0:L(1.00/950ms), T25:L(1.00/1072ms), T50:L(1.00/890ms), T75:L(1.00/536ms), T100:L(1.00/678ms)
- gap1 (0.21388): T0:L(1.00/1303ms), T50:L(1.00/611ms), T75:L(1.00/676ms), T100:L(1.00/502ms)
- gap2 (0.23094): T0:L(1.00/1337ms), T25:L(1.00/683ms), T50:L(1.00/726ms), T75:L(1.00/1332ms), T100:L(1.00/525ms)
- gap3 (0.25991): T0:L(1.00/2047ms), T25:L(1.00/609ms), T50:L(1.00/768ms), T75:L(1.00/1809ms), T100:L(1.00/598ms)
- gap4 (0.29859): T25:R(0.88/1ms), T50:R(0.84/1ms), T75:R(0.80/1ms), T100:R(0.66/1ms)
- idx1 (0.32901): T75:R(0.84/1ms), T100:R(0.72/1ms)
- idx2 (0.37633): T100:R(0.80/1ms)
- idx3 (0.47050): T75:R(0.87/1ms), T100:R(0.70/1ms)

**P4 always forced-exact** — 38 failing cell(s)
- ctl (0.20376): T0:L(1.00/865ms), T25:L(1.00/993ms), T50:L(1.00/1080ms), T75:L(1.00/547ms), T100:L(1.00/611ms)
- gap1 (0.21388): T0:L(1.00/1271ms), T50:L(1.00/624ms), T75:L(1.00/621ms)
- gap2 (0.23094): T0:L(1.00/1448ms), T25:L(1.00/694ms), T50:L(1.00/760ms), T75:L(1.00/1408ms), T100:L(1.00/521ms)
- gap3 (0.25991): T0:L(1.00/1943ms), T25:L(1.00/640ms), T50:L(1.00/781ms), T75:L(1.00/1867ms), T100:L(1.00/601ms)
- gap4 (0.29859): T0:L(1.00/782ms), T25:L(1.00/758ms), T50:L(1.00/6567ms), T75:L(1.00/1383ms), T100:L(1.00/644ms)
- idx1 (0.32901): T0:L(1.00/886ms), T25:L(1.00/751ms), T50:L(1.00/2261ms), T75:L(1.00/1928ms), T100:L(1.00/852ms)
- idx2 (0.37633): T0:L(1.00/889ms), T25:L(1.00/1089ms), T50:L(1.00/1206ms), T75:L(1.00/965ms), T100:L(1.00/1694ms)
- idx3 (0.47050): T0:L(1.00/3273ms), T25:L(1.00/2465ms), T50:L(1.00/3419ms), T75:L(1.00/1131ms), T100:L(1.00/1162ms)

**P5 always forced-hnsw** — 54 failing cell(s)
- lo1 (0.00012): T0:R(0.00/1ms), T25:R(0.00/1ms), T50:R(0.00/1ms), T75:R(0.00/1ms), T100:R(0.00/1ms)
- lo2 (0.00085): T0:R(0.00/1ms), T25:R(0.01/1ms), T50:R(0.00/1ms), T75:R(0.01/1ms), T100:R(0.00/1ms)
- lo3 (0.01054): T0:R(0.04/1ms), T25:R(0.03/1ms), T50:R(0.03/1ms), T75:R(0.01/1ms), T100:R(0.00/1ms)
- lo4 (0.04777): T0:R(0.15/1ms), T25:R(0.20/1ms), T50:R(0.19/1ms), T75:R(0.15/1ms), T100:R(0.10/1ms)
- lo5 (0.10609): T0:R(0.41/1ms), T25:R(0.41/1ms), T50:R(0.37/1ms), T75:R(0.30/1ms), T100:R(0.20/1ms)
- ctl (0.20376): T0:R(0.82/1ms), T25:R(0.72/1ms), T50:R(0.60/1ms), T75:R(0.64/1ms), T100:R(0.52/1ms)
- gap1 (0.21388): T0:R(0.82/1ms), T25:R(0.69/1ms), T50:R(0.72/1ms), T75:R(0.62/1ms), T100:R(0.43/1ms)
- gap2 (0.23094): T0:R(0.84/1ms), T25:R(0.82/1ms), T50:R(0.72/2ms), T75:R(0.53/1ms), T100:R(0.45/1ms)
- gap3 (0.25991): T0:R(0.86/1ms), T25:R(0.89/1ms), T50:R(0.78/1ms), T75:R(0.69/1ms), T100:R(0.64/1ms)
- gap4 (0.29859): T25:R(0.88/1ms), T50:R(0.84/1ms), T75:R(0.80/1ms), T100:R(0.66/1ms)
- idx1 (0.32901): T75:R(0.84/1ms), T100:R(0.72/1ms)
- idx2 (0.37633): T100:R(0.80/1ms)
- idx3 (0.47050): T75:R(0.87/1ms), T100:R(0.70/1ms)

**P6 always iterative-relaxed** — 11 failing cell(s)
- lo1 (0.00012): T0:R(0.21/217ms), T25:R(0.21/166ms), T50:R(0.20/231ms), T75:R(0.26/375ms), T100:R(0.18/111ms)
- lo2 (0.00085): T0:R(0.86/111ms), T50:R(0.86/126ms), T75:R(0.75/125ms), T100:R(0.68/181ms)
- lo3 (0.01054): T100:R(0.82/95ms)
- lo4 (0.04777): T100:R(0.42/124ms)

**P7 route map of the amended decision rule [IN-SAMPLE: fitted on these cells]** — 0 failing cell(s)
- none

**P8 T=0.001: FE if selectivity < T else IR [IN-SAMPLE / exploratory]** — 2 failing cell(s)
- lo3 (0.01054): T100:R(0.82/95ms)
- lo4 (0.04777): T100:R(0.42/124ms)

**P8 T=0.005: FE if selectivity < T else IR [IN-SAMPLE / exploratory]** — 2 failing cell(s)
- lo3 (0.01054): T100:R(0.82/95ms)
- lo4 (0.04777): T100:R(0.42/124ms)

**P8 T=0.01: FE if selectivity < T else IR [IN-SAMPLE / exploratory]** — 2 failing cell(s)
- lo3 (0.01054): T100:R(0.82/95ms)
- lo4 (0.04777): T100:R(0.42/124ms)

**P8 T=0.02: FE if selectivity < T else IR [IN-SAMPLE / exploratory]** — 1 failing cell(s)
- lo4 (0.04777): T100:R(0.42/124ms)

**P8 T=0.05: FE if selectivity < T else IR [IN-SAMPLE / exploratory]** — 0 failing cell(s)
- none

**P8 T=0.1: FE if selectivity < T else IR [IN-SAMPLE / exploratory]** — 0 failing cell(s)
- none


## 4. EXPLORATORY diagnostic: why does iterative scan return 10 rows with low recall on hm_clothes_100 at lo3 / lo4?

**EXPLORATORY: not part of the pre-registered run, not used in any verdict or route above.** Script `src/phase_a_sweep/exploratory_diag_iterative.py`, data `outputs/phase_a_arms/exploratory_diag.jsonl` (600 rows) and `exploratory_diag_summary.md`. Scope: hm_clothes_100, filters lo3 (0.01054, 1,108 rows) and lo4 (0.04777, 5,021 rows), iterative-relaxed and iterative-strict (arm settings of Amendment 2, incl. `enable_sort=off`), the same 20 vectors, recall only (one untimed execution per point, no latency). Settings varied: `hnsw.ef_search` {40, 100, 200} at `max_scan_tuples` 20000; `max_scan_tuples` {20000, 100000} at `ef_search` 40. **Three extra configs not in the request** were added because pgvector 0.8.3 also limits an iterative scan by memory (`work_mem` x `hnsw.scan_mem_multiplier`, here 4MB x 1): mem4 (multiplier 4), cap+mem (cap 100000 and multiplier 4, `ef_search` 40) and all-raised (200 / 100000 / 4); cap+mem was added after the first pass to separate `ef_search` from the cap-and-memory pair.

**Check of the exact reference [V].** The exact top-10 was recomputed with a forced Seq Scan (EXPLAIN node `Seq Scan` for all 40 (filter, vector) pairs) and compared with the reference method of the run (`enable_indexscan=off`): identical in **40 of 40** pairs, and there is no distance tie between rank 10 and rank 11 in any of them (0 of 40). The base config (40 / 20000 / 1) reproduces the recall recorded in `results.jsonl` in **80 of 80** (filter, arm, vector) points. So the low recall is not an artefact of the exact reference or of nondeterminism.

| config (ef_search / max_scan_tuples / scan_mem_multiplier) | filter | arm | mean recall | min recall (any vector) | median rows | min rows | vectors with <10 rows |
|---|---|---|---|---|---|---|---|
| base (40 / 20000 / 1) | lo3 | iterative-relaxed | 0.820 | 0.00 | 10 | 6 | 1/20 |
| base (40 / 20000 / 1) | lo3 | iterative-strict | 0.800 | 0.00 | 10 | 6 | 1/20 |
| base (40 / 20000 / 1) | lo4 | iterative-relaxed | 0.420 | 0.00 | 10 | 4 | 8/20 |
| base (40 / 20000 / 1) | lo4 | iterative-strict | 0.400 | 0.00 | 10 | 4 | 8/20 |
| ef100 (100 / 20000 / 1) | lo3 | iterative-relaxed | 0.820 | 0.00 | 10 | 6 | 1/20 |
| ef100 (100 / 20000 / 1) | lo3 | iterative-strict | 0.800 | 0.00 | 10 | 6 | 1/20 |
| ef100 (100 / 20000 / 1) | lo4 | iterative-relaxed | 0.420 | 0.00 | 10 | 4 | 8/20 |
| ef100 (100 / 20000 / 1) | lo4 | iterative-strict | 0.400 | 0.00 | 10 | 4 | 8/20 |
| ef200 (200 / 20000 / 1) | lo3 | iterative-relaxed | 0.830 | 0.00 | 10 | 6 | 1/20 |
| ef200 (200 / 20000 / 1) | lo3 | iterative-strict | 0.805 | 0.00 | 10 | 6 | 1/20 |
| ef200 (200 / 20000 / 1) | lo4 | iterative-relaxed | 0.420 | 0.00 | 10 | 4 | 8/20 |
| ef200 (200 / 20000 / 1) | lo4 | iterative-strict | 0.400 | 0.00 | 10 | 4 | 8/20 |
| cap100000 (40 / 100000 / 1) | lo3 | iterative-relaxed | 0.870 | 0.00 | 10 | 10 | 0/20 |
| cap100000 (40 / 100000 / 1) | lo3 | iterative-strict | 0.845 | 0.00 | 10 | 10 | 0/20 |
| cap100000 (40 / 100000 / 1) | lo4 | iterative-relaxed | 0.480 | 0.00 | 10 | 7 | 5/20 |
| cap100000 (40 / 100000 / 1) | lo4 | iterative-strict | 0.450 | 0.00 | 10 | 7 | 5/20 |
| mem4 (extra) (40 / 20000 / 4) | lo3 | iterative-relaxed | 0.820 | 0.00 | 10 | 6 | 1/20 |
| mem4 (extra) (40 / 20000 / 4) | lo3 | iterative-strict | 0.800 | 0.00 | 10 | 6 | 1/20 |
| mem4 (extra) (40 / 20000 / 4) | lo4 | iterative-relaxed | 0.420 | 0.00 | 10 | 4 | 8/20 |
| mem4 (extra) (40 / 20000 / 4) | lo4 | iterative-strict | 0.400 | 0.00 | 10 | 4 | 8/20 |
| cap+mem (extra) (40 / 100000 / 4) | lo3 | iterative-relaxed | 0.925 | 0.10 | 10 | 10 | 0/20 |
| cap+mem (extra) (40 / 100000 / 4) | lo3 | iterative-strict | 0.875 | 0.00 | 10 | 10 | 0/20 |
| cap+mem (extra) (40 / 100000 / 4) | lo4 | iterative-relaxed | 0.940 | 0.60 | 10 | 10 | 0/20 |
| cap+mem (extra) (40 / 100000 / 4) | lo4 | iterative-strict | 0.775 | 0.10 | 10 | 10 | 0/20 |
| all-raised (extra) (200 / 100000 / 4) | lo3 | iterative-relaxed | 0.925 | 0.10 | 10 | 10 | 0/20 |
| all-raised (extra) (200 / 100000 / 4) | lo3 | iterative-strict | 0.875 | 0.00 | 10 | 10 | 0/20 |
| all-raised (extra) (200 / 100000 / 4) | lo4 | iterative-relaxed | 0.940 | 0.60 | 10 | 10 | 0/20 |
| all-raised (extra) (200 / 100000 / 4) | lo4 | iterative-strict | 0.780 | 0.10 | 10 | 10 | 0/20 |

**Findings [V], then interpretation [I].**
- **Not `ef_search`.** Going from 40 to 100 to 200 leaves recall unchanged for lo4 (0.420 / 0.420 / 0.420 relaxed; 0.400 strict) and changes lo3 by at most 0.01 (0.820 / 0.820 / 0.830). And with the cap and memory raised, `ef_search` 40 (cap+mem) and 200 (all-raised) give the same recall (0.925 / 0.940 relaxed).
- **Not the cap alone and not memory alone.** Raising only `max_scan_tuples` to 100000 helps a little (lo3 0.820 → 0.870, lo4 0.420 → 0.480) and removes most of the under-filled results (vectors with fewer than 10 rows: lo3 1 → 0, lo4 8 → 5 of 20). Raising only the memory multiplier changes nothing.
- **The two scan limits together explain most of it.** With both raised (cap 100000 and multiplier 4) relaxed recall is 0.925 (lo3) and 0.940 (lo4), no vector returns fewer than 10 rows, and the minimum rows is 10.
- **Residual weakness.** Even then single vectors are bad (minimum recall 0.10 at lo3 and 0.60 at lo4 for relaxed; 0.00 / 0.10 for strict). iterative-strict is lower than relaxed at the raised limits (lo3 0.875, lo4 0.775-0.780), which I did not expect and did not investigate.
- **Interpretation [I].** The low recall with 10 rows returned is best explained by the iterative scan stopping at a limit (`max_scan_tuples` or the memory budget, whichever is reached first) before it has visited enough of the graph to find the true nearest matching rows; the 10 rows returned are matches that were found, not the nearest 10. Each limit alone is not enough here because the other still binds. I did not measure a per-query scanned-tuple or memory count, so this stays an inference. It is a diagnosis for hm_clothes_100 at two filters only; the lo1/lo2 under-fill on the other tables was not examined.
- **Cost not measured.** I did not time these settings. Raising the limits probably increases iterative-scan latency, but how much is unknown, so these settings are **not** shown to meet the 500 ms SLA and must not be added to a route map without a latency run.
- **For the route map:** the measured result stands unchanged. At the frozen settings iterative-relaxed fails on hm_clothes_100 at lo3 and lo4, and the rule routes those cells to forced-exact.

## 5. Reading the evaluation (hand-written; [V] numbers from sections 1-3, [I] interpretation)

**Matrix as written (P1, P2) [V].** P1 passes 29 of 65 cells and P2 27 of 65; P4 (always forced-exact) also passes 27. Their failures are mostly **latency** (31 cells each), not recall (5 and 7). The reason is visible in the route grids: the recorded danger zones are narrow, so for most selectivities from 0.204 to 0.47 the matrix returns `pre-filter` (= forced-exact, 521-6,567 ms in the failing cells) and fails the 500 ms SLA. In the 7 cells where each matrix does return `post-filter` (= forced-hnsw), P1 passes 2 and P2 passes 0; every failure there is a recall failure (hm_clothes_75 and hm_clothes_100 at idx1-idx3, plus hm_clothes_0/25 at ctl for P2). Both matrices pass all 25 cells at selectivity <= 0.106, but only because forced-exact is fast there, not because of the zones.

**Planner-default (P3) [V].** 37 of 65: 19 latency failures (exact plan at 0.204-0.26, 611-890 ms median over tables) and 9 recall failures (HNSW plan from 0.2986: 20 cells, 11 pass).

**Fixed single arms [V].** Always forced-hnsw (P5) passes 11 of 65 (54 recall failures). Always iterative-relaxed (P6) passes 54 of 65: all 40 cells at selectivity >= 0.204, 13 of 15 at 0.01-0.11 and only 1 of 10 at lo1-lo2; it never fails on latency (max cell median 375 ms) and fails 11 cells on recall (the same 11 as in `arms_results_2026-10-10.md`).

**Two-route rule P8, in-sample / exploratory [V].** forced-exact below T, iterative-relaxed from T: T = 0.001, 0.005, 0.01 pass 63 of 65; T = 0.02 passes 64; T = 0.05 and T = 0.1 pass **65 of 65**. All failures at T <= 0.02 are on hm_clothes_100 (lo3 and lo4 for T <= 0.01, lo4 for T = 0.02), where iterative-relaxed has recall 0.82 and 0.42 (section 4). P7 (the amended decision rule, which picks the lowest-latency passing arm per cell) passes 65 of 65 by construction.

**What the cells bound for T [V, in-sample].** Lower bound: T must exceed 0.0478 (lo4) for hm_clothes_100, where iterative-relaxed fails at 0.0478 (recall 0.42) and at 0.0105 (0.82) but passes at 0.1061 (recall 0.93, minimum vector 0.70). Upper bound: forced-exact exceeds 500 ms at ctl (0.2038) on all five tables (547-1,080 ms), whereas at <= 0.1061 its largest cell median is 316.5 ms. So the data support T in (0.0478, 0.2038]. **Not sampled:** anything between 0.0478 and 0.1061 or between 0.1061 and 0.2038, so the interval is only as sharp as the 13 filters allow, and the edges are untested. At the 0.1 end, hm_clothes_100 at 0.1061 passes on iterative-relaxed with the smallest margin seen among passing iterative cells (recall 0.93 against 0.90), while forced-exact there also passes (262 ms) [I].

**What this does not establish [I].** The fits use the same 20 vectors, one table size (105,100 rows) and one server configuration; P7/P8 are in-sample. The latency side of T depends on how many rows match the filter and on the machine, so a selectivity threshold of this size is not shown to transfer to a corpus of a different size (for example FinQA, 35,862 rows). The exploratory diagnostic (section 4) suggests iterative scan on the least-correlated table could be made to work with larger scan limits, but its latency was not measured, so nothing in sections 1-3 rests on it.
