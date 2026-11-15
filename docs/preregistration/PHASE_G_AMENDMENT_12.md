# PHASE G — AMENDMENT 12: Straddle-T evaluation (retrieval-only)

Date: 2026-11-15. Baseline: tag pre-straddle-t-2026-11-15 (commit 5798a09).
Status: written before any straddle-T recall or latency measurement. The candidate pool was built from table contents only.

## 1. Purpose
Test the calibrated router, unchanged, on questions whose filters sit on both sides of its threshold T, on EDGAR and FinQA. No LLM calls.

## 2. Frozen inputs
- T_edgar = 0.3786921696945195 (config/policy_v3_1_edgar.json). It came from the empty-interval minimum-failures rule of Amendment 11 (no T satisfied both conditions).
- T_hm = 0.07119177617441379 (config/policy_v3_1_hm.json), calibrated on H&M; its use on EDGAR and FinQA is a transfer test.
- Bands for each T: far_below s <= T/2; near_below T/2 < s <= T; near_above T < s <= 2T; far_above s > 2T.
- Candidate pool: outputs/straddle_t_feasibility_2026-11-15/pool/ (checksums in POOL_CHECKSUMS.txt). Filters are distinct by matched-row set. Usable = n_rows >= 15, not matching every row, s <= 0.95. Tiers: natural, plausible_constructed, random_constructed (FinQA ticker lists, seed 20261115).
- k = 15. Recall@15 against exact search (exact top-15, enable_indexscan = off, ORDER BY distance, id), as in Amendment 11.
- Environment: outputs/straddle_t_env_snapshot_2026-11-15.json.

## 3. Seen and unseen data
The 40 EDGAR questions (selected.csv) were evaluated in Amendment 11 (160 pairs: 130 far_below, 30 near_below under T_edgar; 153 of the 160 are usable in the pool). The 30 near_below pairs use only 3 distinct filters (section = '7', '1A', '8'). Below-T results here are therefore replications on new draws. No data exist above T_edgar; that side is the new test.

## 4. Analyses
PRIMARY: EDGAR under T_edgar. Groups: below_T (far_below + near_below) and above_T (near_above + far_above). Tier set natural + plausible_constructed. For each band and each question with at least one usable gold-containing filter in that band, one filter is drawn uniformly (candidates sorted by pool_id) with random.Random(f"20261115|edgar|T_edgar|{band}|{qid}").
SECONDARY (transfer test): EDGAR and FinQA under T_hm. EDGAR near_below under T_hm is declared not testable (6 distinct filters, 10 of 40 questions eligible) and is reported descriptively. FinQA: 100 questions drawn with random.Random("20261115|finqa|questions") from the 605 eligible in all four bands (natural + plausible_constructed), one filter per band, same pair RNG scheme.
SENSITIVITY: natural-only filters; random_constructed ticker lists (FinQA) in a separate file.
DESCRIPTIVE ONLY: EDGAR far_above under T_edgar (one distinct filter, section IN ('1A','7','8'), 30 of 40 questions); the stratum |s - T|/T <= 0.25.

## 5. Arms
Those of the Amendment 11 runner: always_exact, default_hnsw (iterative scan off, session settings as in Amendment 11 and the snapshot), always_iterative, router (policy_v3.1 with T_edgar), router_hmT (policy_v3.1 with T_hm), vecadvisor where it can run (unavailable cases are logged), and an oracle computed offline from the fixed arms. Fixed arms are measured once per pair; the router is run live under each T. No new arm is added.

## 6. Measurement
Per pair: one normal execution (rows, recall, trace), one warm-up, 5 timed executions, median. Latency = end-to-end wall-clock of retrieve() for every arm (as in Amendment 11), so estimate, count and guard time are included. Valid = no error, timeout or route failure. Pair order and arm order are randomised with a recorded seed. Quiet-machine rule as defined in Amendments 9 and 11. No ANALYZE or VACUUM during the run; n_mod_since_analyze and the autovacuum state are recorded before and after. Every row logs session settings, PostgreSQL and pgvector versions, git commit and cache state.

## 7. Pass rule
Derived from Amendments 9 and 11: "mean recall >= 0.90 and median of the per-vector medians <= 500 ms, all vectors valid", with recall@15 and the pair set of a band as the cell. Band pass: all pairs valid, mean recall@15 >= 0.90, median of per-pair median latencies <= 500 ms. Secondary per-pair pass: recall@15 >= 14/15 and median latency <= 500 ms. This adapts a rule written for 20 query vectors per cell to one vector per pair and is not a verbatim reuse.

## 8. Hypotheses
Replications of seen results (R):
- H1a: under T_edgar the router meets the band pass rule in far_below and in near_below.
- H3: under T_edgar default_hnsw fails the recall criterion (mean recall@15 >= 0.90) in far_below and in near_below.
- H5b: router_hmT fails the recall criterion in at least one EDGAR band.
Open questions (N), no direction predicted:
- H1b: whether the router meets the band pass rule in the above_T group on EDGAR under T_edgar.
- H5a: whether the router under T_hm meets the band pass rule in each FinQA band.
A failure on H1b or H5a is reported as a finding. No hypothesis is pre-registered for always_exact latency or for router overhead; both are reported descriptively.
Exploratory (not confirmatory): E1 exact-search latency against matched rows per table, to compare cost per row between EDGAR and FinQA; E2 if time allows, a ceiling check of unfiltered HNSW recall@15 on EDGAR.

## 9. Analysis plan
Per band, never pooled across bands; tiers reported separately. Cluster bootstrap with questions as clusters (10,000 resamples, seed 20261115), with filter-clustered bootstrap as a robustness check; 95% percentile intervals. Report mean recall, median latency and pass/fail per band, and whether each interval crosses the threshold. Holm correction across the five hypotheses in section 8, with R and N hypotheses reported in separate groups.

## 10. Stopping and deviations
No pair is dropped or rerun after results are seen, except a recorded technical failure (crash, timeout), rerun once with the same pair and logged in DEVIATION_LOG.md. Empty bands and ineligible questions are reported, not replaced.

## 11. Order of work
This amendment is committed and tagged (phase-g-amendment-12) first. The manifest is built by scripts/straddle_t_build_manifest.py from these parameters and checksummed. A smoke test of 10 pairs (seed 20261116), run and logged but excluded from analysis, precedes the full run.

## 12. Limitations stated in advance
Constructed filters above T_edgar; T_edgar from the fallback rule; previously evaluated EDGAR questions; EDGAR has 3 fiscal years and 5 sections; FinQA JSONB filters have no pg_stats, so the estimate step is skipped there; T may depend on table size and cost per row; one machine, one PostgreSQL configuration (shared_buffers 128 MB, jit on).
