# H&M three-arm danger-zone protocol

**Status:** frozen before any measured run (this commit). The hypotheses may be
edited by the author before the full run; any edit must be committed before
`outputs/phase_a_arms/results.jsonl` is created.

## Purpose

The policy audit (`reports/policy_audit_2026-10-10.md`) found that
`policy.py` returns `post-filter` (Phase D: forced HNSW, `iterative_scan=off`)
inside recall danger zones, the plan type that lost recall in Phase A. Before
changing the routing rule, measure every candidate route inside and around the
H&M danger zones. This run does not modify `policy.py`, `router.py`, Phase A
v1/v2 outputs or the frozen Phase D outputs.

## Design

- Tables: `hm_clothes_0`, `_25`, `_50`, `_75`, `_100` (105,100 rows each; the
  attribute distributions are identical across tables, verified for every
  filter below).
- Parameters for all arms: `k = 10`, `hnsw.ef_search = 40`, `jit = off`
  (set explicitly and recorded), `statement_timeout = 120000 ms` (recorded).
- Query vectors: the same 20 vectors as the Phase A v2 run, i.e. the first 20
  lines of `ann-filtering-benchmark-datasets/data/tests.jsonl`
  (`run_phase_a_v2.py` calls `main(..., limit_vectors=20)`, and
  `load_query_vectors` reads the first N lines; the v2 results contain
  `query_vector_idx` 0-19). The SHA-256 of those 20 lines is stored in
  `run_meta.json`.
- SQL (same form as Phase A):
  `SELECT id FROM {table} WHERE {filter} ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048) LIMIT 10`.

### Selectivity points (`outputs/phase_a_arms/filters.json`, measured, identical on all five tables)

| id | role | filter | selectivity | rows |
|---|---|---|---:|---:|
| ctl  | control (below gap; v2 filter f_040) | `garment_group_name = 'Jersey Fancy'` | 0.20376 | 21,415 |
| gap1 | gap, single-attribute equality | `perceived_colour_master_name = 'Black'` | 0.21388 | 22,479 |
| gap2 | gap, IN list (one column) | `perceived_colour_master_name IN ('Blue','Red')` | 0.23094 | 24,272 |
| gap3 | gap, IN list (one column) | `perceived_colour_master_name IN ('Blue','Grey')` | 0.25991 | 27,317 |
| gap4 | gap, IN list (one column) | `perceived_colour_master_name IN ('Black','Grey')` | 0.29859 | 31,382 |
| idx1 | Phase A index-scan point (f_041) | `index_group_name = 'Baby/Children'` | 0.32901 | 34,579 |
| idx2 | Phase A index-scan point (f_042) | `index_group_name = 'Ladieswear'` | 0.37633 | 39,552 |
| idx3 | Phase A index-scan point (f_043) | `graphical_appearance_name = 'Solid'` | 0.47050 | 49,450 |

Filter types used: single-attribute equality (ctl, gap1, idx1-3) and IN lists
over one column (gap2-4). No 2-column AND is used. All filtered columns have a
B-tree index, as in Phase A (`sql/index_setup.sql`).

Candidate search for the unsampled gap 0.204-0.329 (hm_clothes_100; counts are
identical on all tables). Only five filterable columns exist
(`index_group_name`, `product_type_name`, `garment_group_name`,
`perceived_colour_master_name`, `graphical_appearance_name`); the other table
columns are `id`, `vector_id` and `embedding`.

- Single-attribute equality values with frequency in [0.20, 0.34]: only
  `Baby/Children` 0.32901 (= idx1), `Jersey Fancy` 0.20376 (= ctl) and
  **`Black` 0.21388 (new, used as gap1)**. No other single value lies in the gap,
  so IN lists were needed for the rest.
- IN-list candidates found (value frequencies summed) near the targets:
  - near 0.23: `garment_group_name IN ('Jersey Fancy','Swimwear')` 0.23027;
    `perceived_colour_master_name IN ('Blue','Red')` 0.23094 **(used)**;
    `('Black','Turquoise')` 0.23123; `('Blue','Beige')` 0.22882.
  - near 0.26: `perceived_colour_master_name IN ('Blue','Grey')` 0.25991 **(used)**;
    `index_group_name IN ('Divided','Menswear')` 0.26249; `garment_group_name
    IN ('Jersey Fancy','Blouses')` 0.25923; `colour IN ('Blue','Pink')` 0.26414.
  - near 0.30: `perceived_colour_master_name IN ('Black','Grey')` 0.29859 **(used)**;
    `('Black','Pink')` 0.30282; `('Blue','White')` 0.29526.
- 2-column AND: the only combination found (of 27 pairs from the top values of
  three column pairs) inside the gap was `index_group_name='Ladieswear' AND
  graphical_appearance_name='Solid'` at 0.22159; not used.
- All gap points use the same column (`perceived_colour_master_name`) so that
  the filter column is not confounded with selectivity. The other candidates
  are recorded here but excluded to bound run time. Note that gap2-4 are
  multi-value filters; a difference between them and equality filters (idx1-3)
  in plan choice is possible and will be reported, not assumed away.

### Arms

| Arm | Session settings (after `RESET` of `enable_indexscan`, `enable_seqscan`, `enable_bitmapscan`, `enable_sort`, `hnsw.iterative_scan`) |
|---|---|
| 1 `planner-default` | none of `enable_*`; `hnsw.iterative_scan = off` (reproduces Phase A) |
| 2 `forced-exact` | `enable_indexscan = off` (the plan node, Seq Scan or Bitmap Heap Scan, is recorded) |
| 3 `forced-hnsw` | `enable_indexscan = on`, `enable_seqscan = off`, `enable_bitmapscan = off`, `hnsw.iterative_scan = off` |
| 4 `iterative-relaxed` | as `forced-hnsw` but `hnsw.iterative_scan = 'relaxed_order'` (`hnsw.max_scan_tuples` recorded; server default 20000) |
| 5 `iterative-strict` | as `forced-hnsw` but `hnsw.iterative_scan = 'strict_order'` (kept; it was cheap in the prototype, 1.5 ms) |

Each row records `plan_as_intended`: for arms 3-5 the scan node must be an
`Index Scan` on `*embedding_idx`; for arm 2 it must be `Seq Scan` or
`Bitmap Heap Scan`; arm 1 has no expectation.

### Measurement per (table, filter, arm, vector)

- Recall@10 = |returned ids ∩ exact top-10| / |exact top-10|. The exact
  top-10 is computed once per (table, filter, vector) on a dedicated
  connection with `enable_indexscan = off` (as Phase A's `truth_conn`), and
  reused for all arms. `forced-exact` is itself an exact plan, so its recall
  is expected to be 1.0; it is still measured, not assumed.
- The recall query is a normal execution (not EXPLAIN), via
  `recall_calculator.fetch_top_k_ids`; `rows_returned` (under-fill indicator)
  is taken from it.
- Latency: one untimed warm-up, then 5 timed `EXPLAIN (ANALYZE, FORMAT JSON,
  BUFFERS, TIMING)` runs (Phase A v2 policy, `explain_analyze_wrapper`); the
  per-vector latency is the median `Execution Time`; all 5 raw values are kept.
- Plan: `scan_node` (first scan node, as Phase A), `index_used`, the full list
  of plan node types, and `Rows Removed by Filter`.
- Per-table warm-up (an unfiltered ANN query and one filtered query,
  untimed) runs before the first timed item of each table.
- Order: table order, per-table filter order, per-filter vector order and
  per-vector arm order are shuffled with `random.Random(20261010)`. The
  seed and the SHA-256 of the complete schedule are stored in `run_meta.json`.
- Aggregation per (table, filter, arm): mean recall over the 20 vectors
  (primary, as the v2 protocol), min recall and fraction of vectors with
  recall < 0.9 (secondary); latency = median over the 20 per-vector medians.
  Recall danger = mean recall < 0.9; latency danger = median latency > 500 ms
  (same thresholds as Phase A).
- Every result row contains: git commit, pgvector version, PostgreSQL
  version, `hnsw.ef_search`, `hnsw.iterative_scan`, `hnsw.max_scan_tuples`,
  `hnsw.scan_mem_multiplier`, `jit`, `enable_indexscan`, `enable_seqscan`,
  `enable_bitmapscan`, `enable_sort`, `statement_timeout`, arm, table,
  filter id and text, selectivity, vector index, recall, truth size,
  rows returned, scan node, index used, plan nodes, median latency, the 5 raw
  latencies, seed and timestamp. A statement timeout or error is stored in the
  `error` field and never silently dropped.

### Outputs

`outputs/phase_a_arms/filters.json`, `run_meta.json` (written when a run
starts), `results.jsonl` (full run), `dryrun.jsonl` and `dryrun_meta.json`
(dry run).

## Pre-registered hypotheses (verbatim from the author's specification)

- **H1:** forced-hnsw mean recall@10 < 0.90 at >=1 index-scan point on hm_clothes_75 and _100.
- **H2:** iterative-scan (relaxed) mean recall@10 >= 0.90 at every point on every table.
- **H3:** forced-exact median latency > 500 ms at >= 0.329 selectivity on at least one table.
- **H4:** iterative-scan median latency < forced-exact median latency at >= 0.329.

Operationalisation used in the analysis (editable before the full run):

- "index-scan point" = idx1, idx2, idx3; "point" in H2 = all 8 filters; "at
  >= 0.329" = idx1-3; "mean recall" = mean over the 20 vectors; "median
  latency" = median of per-vector medians.
- H1 holds if, separately for hm_clothes_75 and for hm_clothes_100, at least
  one of idx1-3 has forced-hnsw mean recall < 0.90.
- H2 holds if iterative-relaxed mean recall >= 0.90 in all 40 (table, filter) cells.
- H3 holds if forced-exact median latency > 500 ms in at least one (table, idx1-3) cell.
- H4 holds if iterative-relaxed median latency < forced-exact median latency
  in all 15 (table, idx1-3) cells; the count of cells where it holds is
  reported either way.
- `iterative-strict` is exploratory: it is not part of H2 or the decision rule.

### Decision rule (what each outcome implies for routing recall zones)

- If H1 & H2 & H3 hold, recall zones should route to iterative-scan.
- If H3 fails, route to forced-exact.
- If H2 fails, report that no route meets both SLAs there.

(The rule is stated as specified. If H1, H2 and H3 do not all hold and H3 does
not fail, e.g. H1 fails, the rule does not prescribe a route and the outcome
will be reported without a routing recommendation.)

## Consistency check (not a hypothesis)

On the shared filters (ctl, idx1-3) and vectors 0-19, the planner-default arm
should reproduce the Phase A v2 plan choices (Bitmap Heap Scan at ctl, Index
Scan at idx1-3). Differences will be reported.

## Size and expected run time

- Combinations: 5 tables x 8 filters x 20 vectors = 800 (table, filter, vector).
- Query executions per combination: 1 exact top-10 + 5 arms x (1 recall + 1
  warm-up + 5 timed) = 36. Total = 800 x 36 = **28,800** executions (800 exact
  reference, 4,000 recall, 4,000 warm-up, 20,000 timed) plus 2 per-table
  warm-ups.
- Run time is dominated by exact plans (the reference query and arm 2: 8
  exact executions per combination) and by arm 1 where the planner picks a
  bitmap plan. A-priori estimate: 4-30 s per combination, i.e. **about 2-7
  hours**; the dry run refines this and the refined figure is reported, not
  written back into this file.

## Limits (stated in advance)

- H&M only; categorical equality / IN filters on single columns; k = 10,
  ef_search = 40. No claim about FinQA, other k, other ef_search or numeric
  range filters.
- The Decision Matrix itself is not evaluated here; this run only measures the
  candidate routes.
- Row counts and attribute distributions are identical across the five
  tables, so selectivity is the same on every table by construction; only the
  embedding-attribute correlation differs.
