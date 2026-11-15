# PHASE G — AMENDMENT 12, ADDENDUM 1

Date: 2026-11-15. Written before any straddle-T measurement. Amendment 12 (tag phase-g-amendment-12) is unchanged.

## 1. Correction to Section 12 and session settings
Section 12 lists "jit on" among the PostgreSQL configuration limitations. The server default is jit = on (see the environment snapshot), but retrieval sessions set jit = off and statement_timeout = 120000 ms (src/phase_e_router/retriever.py configure_session; config/router_edgar.json). A call that exceeds the statement timeout is an error and counts as not valid under the pass rule. The server-level shared_buffers = 128 MB limitation stands.

Per-route settings (src/phase_e_router/retriever.py route_settings):
- always_exact: enable_indexscan = off, hnsw.iterative_scan = off, hnsw.ef_search = 40; enable_seqscan, enable_bitmapscan and enable_sort are left at the PostgreSQL defaults.
- default_hnsw: enable_indexscan = on, enable_seqscan = off, enable_bitmapscan = off, enable_sort = off, hnsw.iterative_scan = off, hnsw.ef_search = 40, hnsw.max_scan_tuples not set.
- always_iterative: the same four enable_* settings as default_hnsw, hnsw.iterative_scan = relaxed_order, hnsw.ef_search = 40, hnsw.max_scan_tuples = 20000, hnsw.scan_mem_multiplier = 1.
- router and router_hmT: the exact settings when the decision is exact and the always_iterative settings when it is iterative; if the under-fill guard fires, the query is re-run with the exact settings.
Exact search is therefore timed with the planner free to choose its scan plan, whereas the index routes are forced to use the index.

## 2. VecAdvisor
In Amendment 11, vecadvisor was logged unavailable (requires_new_object) for all 160 EDGAR pairs, and VecAdvisor cannot parse the JSONB filter expressions used on finqa_evidence. It is expected to be unavailable for most or all pairs here. Unavailable cases are reported as such; no comparison with VecAdvisor is claimed beyond the pairs where it runs.

## 3. Oracle
No oracle arm exists in the Amendment 11 runner. The oracle in Section 5 of Amendment 12 is computed offline in the analysis script from the measured fixed arms (the fastest arm that passes the per-pair criterion) and is not run live.