# PHASE G — AMENDMENT 12, ADDENDUM 3: analysis definitions

Date: 2026-11-16. Written before the main run; the smoke results are excluded from analysis. Amendment 12 and Addenda 1 and 2 are unchanged.

## 1. Data
The analysis uses the results file of the main run joined to the manifests on pair_id (qid, band, T_name, pool_id). Fixed-arm rows are shared per (qid, pool_id) (Addendum 2, section 3). A pair is valid for an arm if its row is valid and the exact ground truth of the pair is valid. A vecadvisor row logged as unavailable is not an invalid execution; it is reported as unavailable and excluded from the pass rule.

## 2. Band statistics and pass rule
For arm A and band b: mean recall@15 over the valid pairs, and the median over valid pairs of the per-pair median latency (latency_median_ms). The band passes if every pair is valid, mean recall@15 >= 0.90 and the median latency <= 500 ms. If any pair is invalid for the arm, the band does not pass; the number of invalid pairs is reported and the statistics above are computed on the valid pairs. The group above_T on EDGAR (near_above and far_above pooled) and the group below_T (far_below and near_below pooled) are evaluated by the same rule on their pooled pairs.

## 3. Bootstrap
10,000 resamples, numpy Generator seeded with 20261115 (independent streams per statistic via SeedSequence spawn), 95% percentile intervals. Question-clustered: resample questions with replacement within the manifest and keep all their pairs in the band or group. Filter-clustered: resample pool_id values with replacement and keep all their pairs. An interval crosses the threshold if it contains 0.90 (recall) or 500 ms (latency). Following Addendum 2, section 6, a band is reported as inconclusive for a criterion when the question-clustered and the filter-clustered intervals disagree about whether they cross the threshold; otherwise the point-estimate outcome stands and the report states whether both intervals cross.

## 4. Hypothesis tests
One-sided bootstrap p-values use the question-clustered resamples, with (count + 1) / (B + 1); the filter-clustered p-values are reported as a robustness check.
- "Meets the rule" in a band or group: p = max(P*(mean recall < 0.90), P*(median latency > 500 ms)).
- "Fails the recall criterion" in a band: p = P*(mean recall >= 0.90).
- H1a: router, EDGAR primary (T_edgar), far_below and near_below, each band separately; p = max of the two band p-values.
- H1b: router, EDGAR primary, the above_T group (pooled near_above and far_above); p as for "meets the rule".
- H3: default_hnsw, EDGAR primary, far_below and near_below; p = max of the two "fails the recall criterion" p-values.
- H5a: router_hmT, FinQA primary, the four bands; p = max of the four band p-values.
- H5b: router_hmT, EDGAR secondary (T_hm), far_below, near_above, far_above; p = 3 x min of the three "fails the recall criterion" p-values, capped at 1.
- Holm correction across the five hypotheses at alpha = 0.05, with the replications (H1a, H3, H5b) and the open questions (H1b, H5a) reported as two groups. A hypothesis that is not supported is reported as not supported, not as evidence of the opposite.

## 5. Secondary and descriptive outputs
Per-pair pass rate (recall@15 >= 14/15 and median latency <= 500 ms) with question-clustered intervals; natural and plausible_constructed tiers separately; the boundary stratum |s - T| / T <= 0.25; results for the sensitivity and random-ticker manifests; always_exact latency against matched rows per table with a least-squares slope (ms per 1,000 rows) and a question-clustered interval (E1); router overhead by band (router median latency minus the median latency of the always_* arm that matches route_taken); vecadvisor availability and its results where it ran; an oracle computed offline per pair (the fastest valid arm among always_exact, default_hnsw, always_iterative, vecadvisor where available, and the router, that meets recall@15 >= 14/15). Any further analysis is labelled exploratory.

## 6. Exclusions
The smoke results are not read by the analysis, except in a run flagged --validation that writes to a separate directory and is not reported. No hypothesis, threshold, band or tier definition is changed after the main run.