# EXPLORATORY, post hoc; not part of the pre-registered confirmatory analysis

## X1: Counterfactual Threshold Sweep (Descriptive Only)
> **Note:** This is a descriptive counterfactual over measured `always_exact` and `always_iterative` arms (ignoring estimate, count, and guard overhead), **not** a recommended threshold.

- **edgar_pairs_primary_T_edgar.csv:**
  - `T'` passing overall (`mean_recall >= 0.90` & `median_latency_ms <= 500`): `[0.325, 0.35, 0.375, 0.4, 0.425, 0.45, 0.475, 0.5, 0.525, 0.55, 0.575, 0.6, 0.625, 0.65, 0.675, 0.7, 0.725, 0.75, 0.775, 0.8, 0.825, 0.85, 0.875, 0.9, 0.925, 0.95]`
  - `T'` passing all 4 bands simultaneously: `[]`
- **finqa_pairs_primary_T_hm.csv:**
  - `T'` passing overall (`mean_recall >= 0.90` & `median_latency_ms <= 500`): `[0.02, 0.04, 0.06, 0.08, 0.1, 0.12, 0.14, 0.16, 0.18, 0.2, 0.22, 0.24, 0.26, 0.28, 0.3, 0.32, 0.34, 0.36, 0.38, 0.4, 0.42, 0.44, 0.46, 0.48, 0.5, 0.52, 0.54, 0.56, 0.58, 0.6, 0.62, 0.64, 0.66, 0.68, 0.7, 0.72, 0.74, 0.76, 0.78, 0.8, 0.82, 0.84, 0.86, 0.88, 0.9, 0.92, 0.94]`
  - `T'` passing all 4 bands simultaneously: `[0.02, 0.04, 0.06, 0.08, 0.1, 0.12, 0.14, 0.16, 0.18, 0.2, 0.22, 0.24, 0.26, 0.28, 0.3, 0.32, 0.34, 0.36, 0.38, 0.4, 0.42, 0.44, 0.46, 0.48, 0.5, 0.52, 0.54, 0.56, 0.58, 0.6, 0.62, 0.64, 0.66, 0.68, 0.7, 0.72, 0.74, 0.76, 0.78, 0.8, 0.82, 0.84, 0.86, 0.88, 0.9, 0.92, 0.94]`

## X2: Per-Pair Oracle Summary
- See `x2_oracle_summary.csv` and `x2_no_qualifying_pairs.csv` (`0` pairs where no arm qualifies).

## X3: Host-Load Sensitivity (`cpu_total_pct > 25` within 150s)
- Rows affected: `5337` / `6775` (`78.7749%`).
- See `x3_host_load_sensitivity.csv`.

## X4: Tier Split (`natural` vs `plausible_constructed`)
- See `x4_tier_split.csv`.

## X5: Estimate vs Count (Misrouting Rate)
- Total misrouted pairs across target manifests: `0`.
- See `x5_estimate_vs_count.csv` and `x5_misrouted_pairs.csv`.
