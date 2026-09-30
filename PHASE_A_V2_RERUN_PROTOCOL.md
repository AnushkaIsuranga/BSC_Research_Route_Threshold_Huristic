# Phase A v2 rerun protocol

**Status:** frozen before v2 execution.

## Primary arm

- Preserve the same frozen 44 filters and the same five H&M tables.
- Use 20 query vectors from `tests.jsonl`; vectors 0–4 are the original v1
  subset and must be retained unchanged.
- Use `k=10`, `hnsw.ef_search=40`, and `hnsw.iterative_scan=off`.
- For every filter/table/vector point, perform one warm-up followed by five
  timed executions. Store the median timed execution for that vector.
- Derive latency per selectivity as the median of the per-vector medians.
- Define primary recall danger as **mean recall across the 20 vectors < 0.9**.
- Report minimum recall and the fraction of vectors below 0.9 as secondary
  diagnostics. v1 used minimum recall and remains archived unchanged.
- Detect latency danger only when the median-of-medians exceeds 500 ms.
- Record PostgreSQL/pgvector versions, `ef_search`, `k`, iterative-scan mode,
  and `shared_buffers`.

## Supplementary iterative-scan arm

After the primary arm, run the three v1 index-scan danger-zone filters with
`hnsw.iterative_scan=on`, using the same 20 vectors, warm-up policy, five timed
executions, and metrics. This arm is supplementary and cannot alter primary
thresholds.

## Scope and reporting

The 21–32% selectivity gap will be checked by counting single-attribute H&M
values before the rerun. No multi-attribute filters will be added. v1 remains
available under the `phase-a-v1` tag; v2 outputs use a separate directory.
