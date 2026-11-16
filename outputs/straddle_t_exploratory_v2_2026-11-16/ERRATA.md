# EXPLORATORY, post hoc; not part of the pre-registered confirmatory analysis

## Errata for `outputs/straddle_t_exploratory_2026-11-16/` (v1)

- **(a) X1:** The `"overall"` pass list pools bands and is diluted by the below-threshold pairs, which have recall `1.0`; only the per-band and per-group results are meaningful.
- **(b) X2:** `"no arm qualifies"` is vacuous because `always_exact` has recall `1.0` by construction; the informative quantity applies recall and latency constraints together (`X2b`).
- **(c) X3:** Rows were flagged by host `cpu_total_pct > 25` within `150` s of a sample, but the session's own load (database and runner) keeps host CPU above `25%` during measurement, so `78.8%` of rows were flagged; the low-CPU subset is not a control group (`6` to `35` pairs per band, dominated by cheap pairs); recall does not depend on CPU load, so recall differences between `all_rows` and `low_cpu_only` reflect which pairs are in the subset and must not be read as a host-load effect. The outcome-change statement for `H5a` in X3 is withdrawn.
