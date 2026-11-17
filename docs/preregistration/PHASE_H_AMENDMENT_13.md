# Phase H, Amendment 13: `ef_search` sweep on H&M and EDGAR

**Status:** DRAFT (uncommitted, awaiting approval before tagging and before any timed measurement).
**Scope:** Retrieval and timing only on local PostgreSQL (`127.0.0.1:5433`, PostgreSQL 16.14, pgvector 0.8.3). Zero LLM or external API calls.

---

## 1. Research Question

Does raising `hnsw.ef_search` (`40, 100, 200, 400`) change whether `default_hnsw` or `always_iterative` pass the existing cell-level pass rule on:
1. the **H&M calibration grid** (`outputs/phase_a_arms/filters.json`, 65 cells = 5 scrambled tables × 13 selectivities × 20 query vectors), and
2. the **EDGAR calibration grid** (`outputs/edgar_calibration_2026-11-01/grid_filters.json`, 13 cells = 13 selectivities × 20 calibration queries from `outputs/edgar_eval_set_2026-11-01/calibration_queries.csv`)?

As a **secondary, descriptive-only** analysis, we also measure the 160 EDGAR Amendment 11 evaluation pairs (`outputs/edgar_eval_set_2026-11-01/pairs.csv`).

---

## 2. Experimental Arms, Fixed Parameters, and `ef` Override Verification

### Arms
- **`default_hnsw`** (forced HNSW, `hnsw.iterative_scan = off`, no guard) at `ef_search ∈ {40, 100, 200, 400}`.
- **`always_iterative`** (forced HNSW, `hnsw.iterative_scan = relaxed_order`, MATERIALIZED CTE, **no guard**) at `ef_search ∈ {40, 100, 200, 400}`.
- **`always_exact`** (`enable_indexscan = off`, `hnsw.iterative_scan = off`, `ORDER BY dist, id LIMIT k`) measured **once** per unit (`ef`-independent reference).
- **Excluded:** No router, LLM, VBASE, Milvus, Qdrant, or VecAdvisor arms. No re-calibration of any threshold `T`.
- **EDGAR baseline note:** The Amendment 11 calibration route (`iter_guard` in `src/phase_f_edgar/calibrate_edgar.py`) included the under-fill guard (`it["rows_returned"] < 15` falling back to `exact`), whereas `always_iterative` in `src/phase_e_router/retriever.py` (line 319) runs with `guard = False`. Therefore, `ef = 40` `always_iterative` results here are **not directly comparable** with the Amendment 11 `iter_guard` calibration table.

### Global Fixed Settings
- `hnsw.max_scan_tuples = 20000` (for `always_iterative`)
- `hnsw.scan_mem_multiplier = 1` (for `always_iterative`)
- `hnsw.iterative_scan`: per existing route settings (`off` for `default_hnsw` and `always_exact`; `relaxed_order` for `always_iterative`)
- `jit = off` (session level)
- `statement_timeout = 120000` (120,000 ms, session level)

### Dataset-Specific `k` and Recall Metric
- **H&M:** `k = 10`, **`recall@10`** against frozen exact top-10 ground truth (`outputs/ground_truth_hm/ground_truth.jsonl`, verified against `outputs/data_checksums.json`; no new ground truth generated).
- **EDGAR (primary & secondary):** `k = 15`, **`recall@15`** against frozen exact top-15 ground truth (`outputs/edgar_calibration_2026-11-01/ground_truth.json` for the 13-cell calibration grid; exact top-15 for the 160 evaluation pairs).

### Pass Rules
- **Primary (frozen cell-level pass rule, unchanged from `PHASE_E_AMENDMENT_9.md` line 5 for H&M and `PHASE_F_AMENDMENT_11.md` Section 3 lines 22 and 27 [k = 15, recall@15 override] for EDGAR; implemented in `src/phase_e_router/policy_v3.py:cell_passes`):**
  - All `20` vectors in the cell valid (error, timeout, or invalid return = cell fails)
  - `mean_recall >= 0.90` (`recall@10` on H&M; `recall@15` on EDGAR)
  - `median_latency_ms <= 500.0` (median of the 20 per-vector medians)
- **Secondary, descriptive-only (EDGAR 160 evaluation pairs):**
  - **New pair-level pass definition (not part of the frozen cell-level rule):** all timed reps valid, `recall@15 >= 14/15` (`0.9333...`), and per-vector median latency `<= 500.0 ms`.

### `ef_search` Override Mechanism & Smoke-Test Verification
- `src/phase_e_router/retriever.py` (tagged) reads `config["ef_search"]` from `RouterConfig.raw`. A new module `src/phase_h_efsweep/` will construct a per-`ef` `RouterConfig` copy (`RouterConfig(raw={**base_cfg.raw, "ef_search": ef}, ...)`) and pass it to `retrieve()` / `explain_route()` without modifying any tagged file.
- **Required in the smoke test:** Inside each route's transaction, read back `current_setting('hnsw.ef_search')` and assert it equals the intended `ef`; for `always_iterative`, also assert `current_setting('hnsw.max_scan_tuples') == '20000'` and `current_setting('hnsw.scan_mem_multiplier') == '1'`.

---

## 3. Grids and Datasets

1. **H&M Calibration Grid (Primary):**
   - Tables: `hm_clothes_0`, `hm_clothes_25`, `hm_clothes_50`, `hm_clothes_75`, `hm_clothes_100` (105,100 rows each; HNSW on `embedding::halfvec(2048)` with `halfvec_cosine_ops`, `m = 16`, `ef_construction = 64`).
   - Filters: `outputs/phase_a_arms/filters.json` (13 selectivities, `0.000124` to `0.470504`) × 5 tables = **65 cells**.
   - Query vectors: vectors `0–19` from `ann-filtering-benchmark-datasets/data/tests.jsonl` (**20 vectors per cell**, `1,300` `(cell, vector)` units).

2. **EDGAR Calibration Grid (Primary):**
   - Table: `edgar_chunks` (158,308 rows; HNSW on `embedding` `vector(1024)` with `vector_l2_ops`, `m = 16`, `ef_construction = 64`).
   - Filters: `outputs/edgar_calibration_2026-11-01/grid_filters.json` (`13` `cik IN (...)` filters `g00–g12`, achieved selectivities `0.000152` to `0.470892`, calibrated `T_edgar = 0.378692` under `PHASE_F_AMENDMENT_11.md` Section 3).
   - Query vectors: **20 calibration queries** from `outputs/edgar_eval_set_2026-11-01/calibration_queries.csv` (vectors in `outputs/edgar_questions_verify_2026-11-01/question_embeddings.json`), giving **13 cells × 20 vectors = 260 `(cell, vector)` units**.

3. **EDGAR Amendment 11 Evaluation Pairs (Secondary, descriptive-only):**
   - `outputs/edgar_eval_set_2026-11-01/pairs.csv` (**160 pairs** = 40 questions from `selected.csv` × 4 filter breadths, selectivities `2.5e-5` to `0.298`).

---

## 4. Timing, Early-Stop, and Measurement Protocol

- **`ef = 40` re-measured:** `ef = 40` is re-measured in the same session alongside `100, 200, 400` (no reuse of historical `ef = 40` latencies).
- **Randomisation:** Order of `(cell/pair)` and `(arm)` shuffled, and within each `(cell/pair, vector)` the order of `ef_search ∈ {40, 100, 200, 400}` randomised per pair/cell using **`random.Random(20261117)`**.
- **Repetitions:** `1` warm-up + `5` timed repetitions of `retrieve()` per `(unit, ef, arm)`.
- **Early-stop rule (`PHASE_E_AMENDMENT_9_ADDENDUM_1.md`, applied identically to both H&M and EDGAR per `PHASE_F_AMENDMENT_11.md` Sections 3–4):**
  - *"If the median of the first 2 timed repetitions exceeds 3 x L = 1,500 ms, the remaining 3 repetitions are skipped; that vector's latency is the median of the 2 (> 1,500 ms, i.e. > L); its recall and rows are kept; the row is flagged `early_stop`."*
  - An `early_stopped` flag is logged per repetition/vector; early-stopped vectors remain in the cell-level pass rule (as latency > 500 ms) and are **excluded from the latency-growth descriptive statistic**.
- **Timing metric:** End-to-end wall-clock latency (`time.perf_counter()` in `retrieve()`), summarised as the median of the timed repetitions per vector (and for cells, the median of the 20 per-vector medians).
- **Quiet-machine rule (`PHASE_E_AMENDMENT_9.md` line 32 + `PHASE_E_AMENDMENT_9_ADDENDUM_2.md`):**
  - Before starting a timed session: no torrent client, Ollama, or Jupyter process running, **and** mean `\Processor(_Total)\% Processor Time` across 6 consecutive samples at 5 s intervals (`Get-Counter -SampleInterval 5 -MaxSamples 6`, ~30 s) must be `<= 25%`; otherwise the session does not start.
  - 6 `Win32_Processor.LoadPercentage` readings recorded alongside for disclosure; host CPU and top-5 processes logged every 5 minutes (`host_load.json`).

---

## 5. Logging and Plan Verification

Each measured row records:
- `dataset`, `table`, `cell_id` / `pair_id`, `vector_idx` / `qid`
- `ef_search`, `arm`, `selectivity`
- `rows_returned`, `recall` (`recall@10` on H&M, `recall@15` on EDGAR)
- `rep_latencies_ms`, `median_latency_ms`, `early_stopped` (per-vector flag + per-rep status)
- `git_commit`, `pg_version`, `pgvector_version`, `timestamp`

Additionally, **one UNTIMED `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`** is executed per `(unit, ef, arm)` on its first vector (`vector_idx = 0` / first calibration query for cells; the pair's vector for EDGAR evaluation pairs) to record plan nodes and buffer statistics. In `default_hnsw` and `always_iterative`, **flag only a `Seq Scan` on the base table**; do **not** flag `Sort` (as `always_iterative` uses a `Sort` above the `MATERIALIZED` CTE by design).

---

## 6. Hypotheses and Analysis Plan

### Confirmatory Hypotheses (4)
For each `(arm, dataset) ∈ {default_hnsw, always_iterative} × {H&M, EDGAR primary}`:
- **H1a (`default_hnsw`, H&M):** Cell-level pass rate differs between `ef_search = 400` and `ef_search = 40` on the 65 H&M cells.
- **H1b (`always_iterative`, H&M):** Cell-level pass rate differs between `ef_search = 400` and `ef_search = 40` on the 65 H&M cells.
- **H2a (`default_hnsw`, EDGAR primary):** Cell-level pass rate differs between `ef_search = 400` and `ef_search = 40` on the 13 EDGAR calibration cells.
- **H2b (`always_iterative`, EDGAR primary):** Cell-level pass rate differs between `ef_search = 400` and `ef_search = 40` on the 13 EDGAR calibration cells.

**Statistical test:** Exact McNemar test on cell-level pass (`ef = 400` vs `ef = 40`), **two-sided**, with **Holm–Bonferroni** family-wise error control (`α = 0.05`) across the 4 confirmatory tests.

**Power statement (EDGAR primary, 13 cells):** For `n_discordant` discordant cells all falling in one direction, the exact two-sided McNemar p-value is `p = min(1, 2 * 0.5^n)`:
- `n_discordant = 1..5`: `p = 1.0000, 0.5000, 0.2500, 0.1250, 0.0625` (none significant at `α = 0.05`)
- `n_discordant = 6`: `p = 0.03125` (minimum to reach Holm rank-4 threshold `0.05`)
- `n_discordant = 7`: `p = 0.015625` (minimum to reach Holm rank-3 threshold `0.025` and rank-2 threshold `0.016667`)
- `n_discordant = 8`: `p = 0.0078125` (minimum to reach Holm rank-1 threshold `0.0125`)
Holm is step-down: a test at a larger threshold is rejected only if the tests ranked before it are also rejected. A non-significant EDGAR result is reported as not detectable with 13 cells, not as evidence of no effect.

### Descriptive Analyses
- **Pass-rule decomposition:** Recall-only pass count (`mean_recall >= 0.90`) and latency-only pass count (`median_latency_ms <= 500.0`) at each `ef_search ∈ {40, 100, 200, 400}` for each arm and dataset.
- **Operating-region subset (`selectivity >= T`):** Pass counts, recall, and latency curves restricted to cells with `selectivity >= T` — the region where the `router` mode (`src/phase_e_router/retriever.py` line 322, `config.T_default`) uses the index route:
  - **H&M primary `T`:** `T_default = 0.07119177617441379` (`config/policy_v3_hm.json`, used by `router` in `reports/phase_e_results_2026-10-31.md`), yielding **`45 / 65` cells** (`9 / 13` filters: `lo5, ctl, gap1–gap4, idx1–idx3` × 5 tables). Sensitivity subset `s >= 0.1` (`fixed_t_0_1` in `config/router_hm.json` line 19, also reported in `reports/phase_e_results_2026-10-31.md`) selects the identical `45 / 65` cells (descriptive only).
  - **EDGAR primary `T`:** `T_default = 0.3786921696945195` (`config/policy_v3_1_edgar.json`, used by `router` in `reports/phase_f_results_2026-11-01.md`). EDGAR operating-region subset = 2 cells (`g11`, `g12`); descriptive only, not informative for inference.
  - Neither subset is added to the Holm family.
- **Pre-stated `default_hnsw` cliff expectation (descriptive, not confirmatory):** In Mandarapu & Kunkunuru (`arXiv:2606.16341v1`, Section 2, p. 2: *"we identify the budget with the candidate-list size, K = B"*; Section 3, p. 3: *"a sigmoid in s with knee at s ≈ k/K"*; Section 5, p. 5: *"at ef= B its induced crossover matches the analytic one"*), the post-filter cliff lies at `s ≈ k / K`. Accordingly, for `default_hnsw`, the smallest selectivity at which `recall >= 0.90` should move toward `k / ef_search` (`H&M k = 10`: `0.25, 0.10, 0.05, 0.025`; `EDGAR k = 15`: `0.375, 0.15, 0.075, 0.0375` for `ef = 40, 100, 200, 400`), reported whether it holds or not. Define observed `s_pass(ef)` per table as the lowest selectivity such that every grid cell at or above it passes the recall-only rule (`mean recall >= 0.90`, all vectors valid, latency ignored); report the ratio `s_pass(ef) / (k / ef)` for each `ef`, with no pass/fail verdict. Caveat: the paper's analysis assumes no attribute-vector correlation, so the observed cliff may shift on the scrambled H&M tables and the EDGAR table.
- Recall and median latency curves across `ef_search` by selectivity and correlation tier (`hm_clothes_0..100`).
- Smallest `ef_search` reaching the pass rule per cell.
- Plan-node transitions across `ef_search` (flagging any `Seq Scan` on the base table in `default_hnsw` or `always_iterative`).
- Latency growth factor per `ef_search` step (`40 → 100`, `100 → 200`, `200 → 400`), **excluding early-stopped vectors**.
- **Secondary (descriptive-only):** EDGAR 160 evaluation pairs under the new pair-level pass definition (`recall@15 >= 14/15` and per-vector median `<= 500.0 ms`), broken down by filter breadth.

---

## 7. Interpretation Caveat and Limits

- **Interpretation caveat:** With `always_iterative` (`hnsw.iterative_scan = relaxed_order`), the fixed scan-tuple budget (`hnsw.max_scan_tuples = 20000`, `hnsw.scan_mem_multiplier = 1`) may cap recall independently of `ef_search`.
- **Non-independence of McNemar units:** The 65 H&M cells share the same 13 filters across 5 scrambled tables (`hm_clothes_0..100`), and the 13 EDGAR calibration cells share the same 20 calibration queries across all 13 cells (and 59 of 78 filter pairs share overlapping CIKs in `grid_filters.json`); therefore, McNemar units are not independent.
- **Limits:**
  - Single desktop machine under the quiet-machine rule.
  - One existing index build per table (`m = 16`, `ef_construction = 64` unchanged); no index rebuild.
  - Fixed `max_scan_tuples = 20000` and `scan_mem_multiplier = 1`.

---

## 8. Measurement Counts and Runtime Estimate

| Dataset (Role) | Units | Arms × `ef` | Measured Rows | Max Warm-up + Timed Reps | Untimed `EXPLAIN (ANALYZE, BUFFERS)` |
|---|---|---|---|---|---|
| H&M (Primary) | 65 cells × 20 vectors = 1,300 | (2 × 4) + 1 = 9 | 11,700 | 11,700 × (1 + 5) = 70,200 | 65 × 9 = 585 |
| EDGAR Calibration (Primary) | 13 cells × 20 vectors = 260 | (2 × 4) + 1 = 9 | 2,340 | 2,340 × (1 + 5) = 14,040 | 13 × 9 = 117 |
| **Primary Subtotal** | **1,560** | **9** | **14,040** | **84,240** | **702** |
| EDGAR Eval Pairs (Secondary) | 160 pairs × 1 vector = 160 | (2 × 4) + 1 = 9 | 1,440 | 1,440 × (1 + 5) = 8,640 | 160 × 9 = 1,440 |
| **Grand Total** | **1,720** | **9** | **15,480** | **92,880** | **2,142** |

**Runtime estimate and rate assumptions:**
- Phase G process-log rates: smoke test (`outputs/straddle_t_smoke_2026-11-15/`) = `70` fresh rows in `76.5 s` (`0.92 rows/s`, `1.092 s/row`); main run (`outputs/straddle_t_results_2026-11-16/`) = `5,708` fresh rows in `3,180.6 s` (`1.79 rows/s`, `0.557 s/row`).
- **Why Phase H per-row time may differ:** Phase G rows were dominated by cheap filters at `ef_search = 40` on `edgar_chunks` (`158k` rows, 1024-d) and `finqa_evidence_qwen3` (`35.8k` rows). In Amendment 13, H&M (`105,100` rows, `2,048`-d `halfvec`) `always_exact` scans at high selectivity and `ef_search ∈ {200, 400}` HNSW traversals are slower per row, partially bounded by the Addendum 1 early-stop rule (`> 1,500 ms` on median of first 2 reps).
- **Projected wall time (15,480 rows + 2,142 untimed EXPLAINs):**
  - Optimistic lower bound (`0.557 s/row` + ~15 min EXPLAINs): **~2.6 hours** (~2.4 h primary-only).
  - Baseline (`1.092 s/row` + ~20 min EXPLAINs): **~5.0 hours** (~4.5 h primary-only).
  - Conservative upper bound (`1.5×` smoke rate = `1.64 s/row` for `ef = 200/400` and H&M `always_exact`, mitigated by early stop): **~6.5–7.5 hours** (~5.8–6.8 h primary-only).

---

## 9. Consequence of the Result

This experiment is a **sensitivity analysis** of the frozen `ef_search = 40` assumption. Regardless of the outcome, **no frozen threshold `T` (`T_hm`, `T_edgar`), `policy_v3` / `policy_v3_1_edgar` artifact, or router configuration is changed**; any difference observed at higher `ef_search` is reported as a limitation or future-work finding.
