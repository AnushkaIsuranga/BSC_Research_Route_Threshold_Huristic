# Amendment 6 Part B: policy_v2 against published routing rules (H&M, offline), 2026-10-23

Governed by `docs/preregistration/PHASE_A_AMENDMENT_6.md` (tag `phase-a-amendment-6-2026-10-23`). **Part A (live runs A6-A9) was not run**, by the author's decision (`DEVIATION_LOG.md`, 23 Oct 2026); its predictions remain untested. Part B is offline: no database query, no model call. Script `src/phase_c_analysis/amendment6_partb.py`; outputs `outputs/phase_a_amendment6_2026-10-23/` (`partb_cells.csv`, `partb_summary.json`).

**B1-B4b are re-implementations of published rules in this harness, not the original systems.** Each rule picks a route per query from the filter's exact selectivity (or exact matched-row count for B3); the outcome is the recall@10 and latency **already measured** for that route, vector and cell. Routes used are forced-exact and iterative-relaxed, both measured for all 20 vectors in every cell of every set (0 errors, 0 plan mismatches), so **no cell is "not scored"** for any rule. Pass = mean recall@10 >= 0.90 over the 20 vectors and median latency <= 500 ms. policy_v2 verdicts are recomputed from the same files and reproduce the existing ones (65/65, 24/25, 25/25).

## Pass counts

| rule | in-sample (65) | held-out 1 (25) | held-out 2 (25) | held-out 1 quiet rerun (25, sensitivity) |
|---|---|---|---|---|
| **policy_v2** (exact if s < 0.1) | **65** | **24** | **25** | 25 |
| B1 VBASE (exact if s < 0.18) | 65 | 23 | 25 | 25 |
| B2 Milvus as reported in NaviX (exact if s <= 0.05) | 65 | 25 | 25 | 25 |
| B3 Qdrant (exact if matched rows < 1,250) | 64 | 24 | 25 | 24 |
| B4 Gan & Wang, recall/latency labels | 63 | 24 | 25 | 24 |
| B4b Gan & Wang, SLA labels | 64 | 25 | 25 | 25 |

## Failing cells and why

| rule | set | cell | s (rows) | route | mean recall | median ms | fails on |
|---|---|---|---|---|---|---|---|
| policy_v2 | held-out 1 | hm_clothes_25 x ho3 | 0.0705 (7,412) | exact | 1.000 | 528.4 | latency |
| B1 | held-out 1 | hm_clothes_25 x ho3 | 0.0705 (7,412) | exact | 1.000 | 528.4 | latency |
| B1 | held-out 1 | hm_clothes_0 x ho4 | 0.1435 (15,084) | exact | 1.000 | 572.1 | latency |
| B3 | in-sample | hm_clothes_100 x lo4 | 0.0478 (5,021) | iterative | 0.420 | 123.8 | recall |
| B3 | held-out 1 (and rerun) | hm_clothes_100 x ho1 | 0.0201 (2,116) | iterative | 0.894 | 18.5 (15.8) | recall |
| B4 | in-sample | hm_clothes_100 x lo3 | 0.0105 (1,108) | iterative | 0.820 | 95.0 | recall |
| B4 | in-sample | hm_clothes_100 x lo4 | 0.0478 (5,021) | iterative | 0.420 | 123.8 | recall |
| B4 | held-out 1 (and rerun) | hm_clothes_100 x ho1 | 0.0201 (2,116) | iterative | 0.894 | 18.5 (15.8) | recall |
| B4b | in-sample | hm_clothes_100 x lo4 | 0.0478 (5,021) | iterative | 0.420 | 123.8 | recall |

The hm_clothes_25 x ho3 latency failure (policy_v2 and B1, original held-out 1 run only) has no established cause (`DEVIATION_LOG.md`, 23 Oct 2026); the same cell passes in the quiet rerun. B2 passes ho3 because it sends s = 0.0705 to iterative-relaxed, which met both SLAs there. All recall failures are on hm_clothes_100 (strongest embedding-attribute correlation) at s between 0.0105 and 0.048 routed to iterative-relaxed.

## B3: fraction rule vs row-count rule

policy_v2's T = 0.1 is a fraction of the table: on H&M (105,100 rows) it means exact below **10,510** matched rows, on FinQA (35,862 rows) below **3,586**. B3's limit is a row count that depends on dimensionality, not table size: 10000 / (2048/256) = **1,250 rows** on 2048-d H&M, i.e. s = **0.0119**, and 10000 / (1024/256) = **2,500 rows** on 1024-d FinQA, i.e. s = **0.0697**. On H&M B3 therefore switches to iterative about 8x earlier than policy_v2: on hm_clothes_100 it sends lo3 (s = 0.0105, 1,108 rows) to exact and lo4 (s = 0.0478, 5,021 rows) to iterative-relaxed, whose measured mean recall there is 0.420, so B3 fails lo4 (and ho1, s = 0.0201, recall 0.894). On FinQA the two rules nearly coincide in fraction (0.0697 vs 0.1), and all frozen 50 questions have at most 697 matching rows (s <= 0.0194), so B3 routes all 50 to exact, as policy_v2 does. All numbers match the expectations stated with the task.

## B4 / B4b (Gan & Wang, arXiv:2602.17914, re-implemented; no code released)

scikit-learn `MLPClassifier` (64, 32), ReLU, Adam lr 1e-3, alpha 1e-4, batch 200, max 500 epochs, early stopping (validation 0.1, patience 10), seed 20261023; the two-class output is a logistic unit, equivalent to a two-class softmax. Feature: z-scored selectivity only (dimensionality and corpus size are constant here). Trained on the 1,300 in-sample queries only; the in-sample rows above are in-sample fit, the held-out rows are out of sample.

| model | training labels (exact / iterative) | epochs | training accuracy | learned boundary |
|---|---|---|---|---|
| B4 (higher recall@10 / latency; tie -> exact) | 240 / 1,060 | 23 | 0.969 | exact below s ~ 0.0044, iterative above |
| B4b (faster plan with recall >= 0.9, else exact) | 248 / 1,052 | 17 | 0.926 | exact below s ~ 0.032, iterative above |

With one feature the learned model is a single threshold. B4's labels reward speed per unit of recall, so iterative-relaxed wins even where its recall is 0.4-0.8, and the boundary lands far below policy_v2's; B4b's labels require recall >= 0.9 per query, which moves the boundary up but not past lo4 (s = 0.0478), where recall fails only on hm_clothes_100 (1 of 5 tables).

## Predictions (Part B)

- "B1 and B2 pass about as many cells as policy_v2": **held** (B1 65/23/25, B2 65/25/25 vs 65/24/25).
- "B3 fails hm_clothes_100 at s = 0.0478": **held** (recall 0.420; it also fails hm_clothes_100 x ho1).
- "B4 fails low-selectivity cells on hm_clothes_100 because recall/time favours fast low-recall plans": **held** (lo3, lo4, ho1, all recall).
- "B4b behaves like a threshold rule": **held** (single boundary at s ~ 0.032), and it fails hm_clothes_100 x lo4.
- Part A predictions (A6-A9): **not tested** (Part A not run).

## Limits

Re-implementations, not the original systems; B2's threshold is second-hand (as reported in NaviX). Each rule is scored on routes measured under one harness and server configuration (H&M, k = 10, ef_search 40). B4/B4b see only selectivity, so they cannot use the embedding-attribute correlation that separates hm_clothes_100 from the other tables; neither can the threshold rules. The held-out 1 original run had uncontrolled host load (quiet rerun shown as sensitivity). Within a set, cells share filters across tables and are not independent.
