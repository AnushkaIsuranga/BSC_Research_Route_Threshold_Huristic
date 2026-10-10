# Decision Matrix policy audit — 2026-10-10

Read-only investigation. Nothing was modified, committed or re-run (no sweeps, no Phase D runs, no DB writes).
The only code I executed was the pure function `get_routing_decision` on hand-picked inputs and the pure function `extract_thresholds` on existing result files (to check provenance). Both were run from a scratch script outside the repo.

Legend: **[V]** = seen in code or output. **[I]** = my inference. Paths are relative to the repo root.

**Update:** the user started the DB after the first pass, and Tasks 3b and 4 were then run (read-only: session `SET`, `SHOW`, `SELECT`, `EXPLAIN ANALYZE` only). Results are in Task 3b and Task 4.

---

## Task 1 — policy.py

### 1a. The decision function in full [V]

`src/phase_b_router/policy.py:1-18`

```python
"""Pure decision-matrix routing policy, independent of LangGraph."""


def get_routing_decision(correlation_level: str, estimated_selectivity: float, thresholds_dict: dict) -> str:
    """Choose the safe route for a correlation tier and selectivity estimate.

    The threshold file stores explicit recall and latency danger intervals.
    The deadband margin is applied on both sides of each interval.
    """
    if correlation_level not in thresholds_dict:
        raise ValueError(f"Missing thresholds for correlation level: {correlation_level}")
    thresholds = thresholds_dict[correlation_level]
    margin = thresholds.get("margin", 0.01)
    for key in ("recall_danger_zones", "latency_danger_zones"):
        for start, end in thresholds.get(key, []):
            if start - margin <= estimated_selectivity <= end + margin:
                return "post-filter"
    return "pre-filter"
```

Callers [V]:
- Frozen/local path: `src/phase_d_validation/local_ollama_runner.py:201`, `dm_route = get_routing_decision(args.correlation_level, selectivity, thresholds)`.
- LangGraph path: `src/phase_b_router/router.py:37-41`, a node that calls the same function.
- The API runner `src/phase_d_validation/comparison_runner.py:91` hard-codes `Path("outputs/thresholds.json")`.

The function can only return the strings `"pre-filter"` or `"post-filter"`. `router.py` has an `"iterative-scan"` node (`router.py:157-160, 177`), but `policy.py` can never select it [V].

### 1b. Inputs and how each is obtained

| Input | Where it comes from | How it is computed or estimated |
|---|---|---|
| `estimated_selectivity` | `local_ollama_runner.py:71-78` (`estimate_selectivity`), called at `:197` | Exact count at query time: `SELECT COUNT(*) FROM finqa_evidence WHERE metadata->>'ticker'=%s AND metadata->>'year'=%s`, divided by `SELECT COUNT(*) FROM finqa_evidence` (`:184`). This is a global row fraction (ticker and year parsed from the query id by `extract_ticker_year`, `src/utils/finqa_utils.py:9-17`). It is not an estimate from planner statistics and not a neighbourhood-local selectivity. [V] |
| `correlation_level` | CLI `--correlation-level`, default `"hm_clothes_0"` (`local_ollama_runner.py:237`) | **Never measured on FinQA.** It is a manually chosen label that selects a column of the thresholds file. `comparison_runner.py:102-105` instead requires it explicitly. [V] |
| `thresholds_dict` | `--thresholds` (required in the current file, `:236`); `json.loads(Path(args.thresholds).read_text())` (`:175`) | At b59c004 the default was `outputs/thresholds.json` (`git show b59c004:src/phase_d_validation/local_ollama_runner.py`, line 198 of that version). [V] |
| `margin` | `thresholds[tier]["margin"]`, fallback `0.01` | Written by `src/phase_c_analysis/threshold_detector.py:76-86`: `max(0.005, 0.1 × span of all danger zones)`, or 0.005 if no zones. [V] |

### 1c. Branch table (real thresholds file, `outputs/thresholds.json`)

Outputs below are from my probe of the real function on the real file (script in the scratchpad).

| Zone / branch | Condition in code | Returns | Evidence |
|---|---|---|---|
| Below thresholds (safe) | not within `[start-m, end+m]` of any interval | `pre-filter` | `policy.py:18`; probe: 0.00001, 0.05, 0.2038 → pre-filter [V] |
| Recall danger zone | `start-m ≤ s ≤ end+m` for any `recall_danger_zones` pair | **`post-filter`** | `policy.py:14-17`; probe: 0.3149, 0.329, 0.4705, 0.4846 on tier 100 → post-filter [V] |
| Latency danger zone | same test on `latency_danger_zones` | **`post-filter`** | same lines. The v1 file has **no** latency zones for any tier (`"latency_danger_zones": []` ×5). [V] |
| Above sampled range | `s > end_of_last_zone + margin` | `pre-filter` (fall-through) | probe: 0.49, 1.0 → pre-filter on tier 100 [V] |
| Missing input: NaN | every comparison is False | `pre-filter`, silently | probe: NaN → pre-filter on all 5 tiers [V] |
| Missing input: None | `float <= None` | `TypeError` for tiers with zones. A tier with empty zones returns `pre-filter`. | probe [V] |
| Unknown tier | `policy.py:10-11` | `ValueError("Missing thresholds for correlation level: …")` | probe [V] |
| Missing `margin` key | `.get("margin", 0.01)` | default margin 0.01 | `policy.py:13` [V] |
| Negative or >1 selectivity | no validation | handled by the same comparisons (→ pre-filter) | probe: -0.1 → pre-filter [V] |

Real v1 thresholds (identical in `git show b59c004:outputs/thresholds.json` and `outputs/phase_a_v1/thresholds.json`):

| Tier | recall_danger_zones | latency_danger_zones | margin |
|---|---|---|---|
| hm_clothes_100 | [0.32901, 0.47050] | [] | 0.014149 |
| hm_clothes_75 | [0.32901, 0.32901] and [0.47050, 0.47050] (two point-zones) | [] | 0.014149 |
| hm_clothes_50 | [0.32901, 0.32901] | [] | 0.005 |
| hm_clothes_25 | [] | [] | 0.005 |
| hm_clothes_0 | [0.32901, 0.32901] | [] | 0.005 |

### 1d. Behaviour outside the sampled range and in the unsampled gap

[V] Phase A v1 sampled selectivities from 0.00012369 to 0.47050. The largest gap between adjacent sampled selectivities is 0.20375832540437677 → 0.3290104662226451 (computed from `outputs/phase_a_v1/filters.json`, 44 filters).

[V] There is **no interpolation, no nearest-bucket lookup and no explicit default for out-of-range values.** The logic is only "is `s` inside a padded interval?". Everything else falls through to `pre-filter` (`policy.py:18`). Probe results (hm_clothes_100 / 75 / 50 / 0):

| Selectivity | Result |
|---|---|
| < 0.00012 (0.00001) | pre-filter on all tiers |
| 0.2038, 0.25, 0.30 (the gap) | pre-filter on all tiers |
| 0.3148 | pre-filter. Post-filter starts at 0.3149 on tiers 100 and 75 (margin 0.01415) and only at 0.3240 on tiers 50 and 0 (margin 0.005). |
| > 0.4846 (tier 100/75), > 0.4705+0.005 (others) | pre-filter |
| Tier 50/0 anywhere except ≈0.324–0.334 | pre-filter (the only zone is the single point 0.329) |

[I] On the real file, a selectivity of 0.40 gives `pre-filter` on tiers 50, 25 and 0. That is the region where the Phase A planner picked HNSW (0.3763 and 0.4705 were Index Scans in every tier). The matrix therefore encodes "danger" at isolated sampled points, not as a continuous region.

### 1e. Unit tests — `src/phase_b_router/test_router.py`

Every assertion of `"post-filter"` [V]:

```python
# test_router.py:15-21  (mock thresholds, NOT the real file)
thresholds_dict = {"hm_clothes_100": {
    "recall_danger_zones": [(0.4705, 1.0)],
    "latency_danger_zones": [(0.2037, 0.2037)],
    "margin": 0.01 }}
:29-30  # exactly on latency danger -> post-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.2037, thresholds_dict), "post-filter")
:32-33  # on lower margin boundary (0.1937)            -> "post-filter"
:35-36  # inside the lower margin (0.1947)             -> "post-filter"
:47-48  # exactly on margin of recall collapse (0.4605) -> "post-filter"
:50-51  # inside margin of recall collapse (0.4655)    -> "post-filter"
:53-54  # above recall collapse (0.50)                 -> "post-filter"
:98-109 # LangGraph: selectivity 0.2037 -> chosen_route "post-filter", final_answer "post-filter executed"
```

Observations [V]:
- The tests use hand-written thresholds, `[(0.4705, 1.0)]` plus a latency zone at 0.2037. These do not match the real file (recall zone ends at 0.4705, latency zones empty). The test "above recall collapse (0.50) → post-filter" would be `pre-filter` on the real file.
- No test loads `outputs/thresholds.json`.
- No test covers NaN or None.
- `test_safe_table_routes_pre_filter` (`:56-67`) asserts that a tier with empty zones returns pre-filter at 0.99.
- `mock_exec` replaces `execute_vector_search`, so no test checks what "post-filter" actually runs.

**Answer (Task 1):** The policy is a pure interval lookup: inside any recall or latency danger interval (padded by `margin`) it returns `post-filter`, otherwise `pre-filter`. Out-of-range values, the unsampled gap and NaN all silently fall through to `pre-filter`; there is no interpolation. The tests encode a different threshold structure than the real file.

---

## Task 2 — What each route actually executes

### 2a. Phase D, frozen runner (`local_ollama_runner.py`, current working tree; `_retrieve` at `:81-123`) [V]

All arms: the session first runs `SET hnsw.ef_search = 40` (`:182`, default `--ef-search 40`). Connection is autocommit with pgvector registered (`:179-180`). Table `finqa_evidence(vector(768))` with `CREATE INDEX … USING hnsw (embedding vector_l2_ops) WITH (m=16, ef_construction=64)` (`finqa_db_setup.py:139-145, 174-176`). No other index except the primary key.

**pre-filter** (the `else` branch, `:115-123`):
```python
cur.execute("SET enable_indexscan = off; SET enable_seqscan = on;")
cur.execute("""SELECT query_id, content, evidence_key FROM finqa_evidence
               WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s
               ORDER BY embedding <-> %s::vector LIMIT %s""", (ticker, year, vector, k))
```

**post-filter / post-filter-indexscan** (`:105-114`):
```python
cur.execute("SET enable_indexscan = on; SET enable_seqscan = off;")
cur.execute("SET hnsw.iterative_scan = off;")
# same SELECT as pre-filter (WHERE ticker/year ... ORDER BY embedding <-> ... LIMIT k)
```

**post-filter-app-top40** (`:93-104`):
```python
cur.execute("SET enable_indexscan = on; SET enable_seqscan = off;")
cur.execute("SET hnsw.iterative_scan = off;")
cur.execute("""SELECT query_id, content, evidence_key, metadata->>'ticker', metadata->>'year'
               FROM finqa_evidence ORDER BY embedding <-> %s::vector LIMIT 40""", (vector,))
filtered = [r for r in raw if r[3] == ticker and r[4] == year][:k]   # filter in Python
```

**iterative-scan** (`:83-92`):
```python
cur.execute("SET enable_indexscan = on; SET enable_seqscan = off;")
cur.execute("SET hnsw.iterative_scan = 'relaxed_order';")
# same filtered SELECT, LIMIT k
```

The parallel copy in `src/phase_b_router/router.py:64-116` (`execute_vector_search`) has the same four branches and the same SQL, with `LIMIT 6` and `LIMIT 40` hard-coded. It is used by the API runner. It does not set `hnsw.ef_search`, so it relies on the server default. [V]

**What the frozen commit b59c004 ran** [V] (`git show b59c004:src/phase_d_validation/local_ollama_runner.py`, lines 71-85): only two arms existed.
```python
if route == "post-filter":
    cur.execute("SET enable_indexscan = on; SET enable_seqscan = off;")
else:
    cur.execute("SET enable_indexscan = off; SET enable_seqscan = on;")
# one shared SELECT ... WHERE ticker/year ... ORDER BY embedding <-> ... LIMIT k
```
`hnsw.iterative_scan` was **not set** at b59c004; it relied on the server default. The working-tree version adds the explicit `= off` and the two extra arms.

### 2b. Phase A sweep [V]

`src/phase_a_sweep/sweep_orchestrator.py` (v1 commit bccbb77, 2026-08-23, and the working tree):
- Latency connection `sweep_conn`: only `SET hnsw.ef_search = 40` (v1, `:79`). The working tree also adds `SET hnsw.iterative_scan = off;` (`:80`, uncommitted). **No `enable_*` setting. The planner default decided the plan.**
- Truth connection `truth_conn`: `SET enable_indexscan = off;` (`:74`) → exact reference for recall.
- Latency SQL (`explain_analyze_wrapper.py:92`): `SELECT id FROM {table} WHERE {col = %s AND …} ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048) LIMIT %s`, wrapped in `EXPLAIN (ANALYZE, FORMAT JSON, BUFFERS, TIMING)` with `SET statement_timeout`, `SET jit = off` (`:9-11`).
- Recall SQL (`recall_calculator.py:13`): same query without EXPLAIN, run on both connections.
- Index (`sql/index_setup.sql:9` and the equivalent for the other tiers): `hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m=16, ef_construction=64)` plus a B-tree on each of the 5 filter columns.
- **Arm named post-filter:** none. Only a `scan_strategy` label read off the plan. If the strategy is `Index Scan`, recall is measured. If it is `Bitmap Heap Scan` or `Seq Scan`, recall is set to 1.0 without measuring (`sweep_orchestrator.py:139-162`).

What the planner chose in v1 (computed from `outputs/phase_a_v1/sweep_results.jsonl`, 1100 rows): `Bitmap Heap Scan` 1025, `Index Scan` 75. The 75 Index Scans are exactly the three highest selectivities (0.3290, 0.3763, 0.4705) × 5 tiers × 5 vectors. At 0.2038 every tier was a Bitmap Heap Scan at 441–500 ms median latency. [V]

Recall at the Index Scan points (v1, 5 vectors each):

| Tier | sel 0.3290 | sel 0.3763 | sel 0.4705 |
|---|---|---|---|
| 100 | 1,1,0.4,1,0.3 | 1,0.9,0.6,0.6,1 | 1,1,1,0.1,1 |
| 75 | 1,1,0.4,1,0.5 | 1,0.9,1,0.9,1 | 1,1,1,0.5,1 |
| 50 | 1,1,1,1,0.8 | 1,0.9,1,1,1 | all 1 |
| 25 | 1,1,0.9,1,1 | 1,0.9,1,1,1 | all 1 |
| 0 | 1,0.9,0.8,1,1 | all 1 | all 1 |

### 2c. Side-by-side

| Term | Phase A mechanism | Phase D mechanism |
|---|---|---|
| "pre-filter" | **Not an arm.** The nearest equivalent is the planner choosing `Bitmap Heap Scan` (B-tree on the attribute, then exact sort), observed at selectivity ≤ 0.2038. Recall was assumed to be 1.0. | **Forced exact scan:** `enable_indexscan=off, enable_seqscan=on`; filtered SELECT, ordered by L2 distance. Verified in Task 4: `Seq Scan` + top-N Sort. [V] |
| "post-filter" | **Not an arm.** The nearest equivalent is planner-chosen `Index Scan` on the HNSW index (the filter is applied to the ≤`ef_search`=40 candidate stream). This is the mechanism whose recall collapsed. | **Forced HNSW:** `enable_indexscan=on, enable_seqscan=off, hnsw.iterative_scan=off`, same filtered SELECT. Verified in Task 4: HNSW `Index Scan` with the metadata test as `Filter`. [V] |
| Plan control | Planner default (nothing forced) | Forced via `enable_*` GUCs |
| Vector type, metric | `halfvec(2048)` cosine `<=>` | `vector(768)` L2 `<->` |
| k / ef_search | 10 / 40 | 6 / 40 |
| Filter | Categorical equality on 1–2 H&M columns | JSONB `metadata->>'ticker'` and `->>'year'` |
| Selectivity | fraction of H&M rows matching the filter | fraction of `finqa_evidence` rows for ticker/year |
| Recall | recall@10 vs exact top-10 on the same filter | none: `unit_recall` vs gold evidence keys (not ANN recall) |

### 2d. Which arm does the Decision Matrix call? [V]

- "pre-filter" → `_retrieve` `else` branch = `enable_indexscan=off, enable_seqscan=on` (exact).
- "post-filter" → `_retrieve` branch `route in {"post-filter","post-filter-indexscan"}` = `enable_indexscan=on, enable_seqscan=off, hnsw.iterative_scan=off`.
- `post-filter-app-top40` and `iterative-scan` are never returned by `get_routing_decision`. They can only be requested by name. The Naive router (LLM) is limited to `pre-filter` / `post-filter` (`local_ollama_runner.py:148`).

**Answer (Task 2):** Your suspicion is correct. In Phase A, neither word names an arm; they are labels read off whatever plan the planner picked (Bitmap Heap Scan = exact, HNSW Index Scan = approximate). In Phase D they are two forced arms (seq-scan-exact vs HNSW-forced) with a different vector type, metric, k and filter. The Decision Matrix's `post-filter` calls the forced-HNSW arm.

---

## Task 3 — `hnsw.iterative_scan` during the Phase A sweep

### 3a. File evidence (grep over scripts, configs, docker-compose, init SQL, `.env`)

- **v1 sweep code (commit bccbb77) sets only `hnsw.ef_search`.** `git show bccbb77:src/phase_a_sweep/sweep_orchestrator.py | grep -nE "SET |iterative|ef_search"` returns lines 74, 77, 79, 180. Line 74 is `SET enable_indexscan = off;` (truth connection) and line 79 is `SET hnsw.ef_search = {HNSW_EF_SEARCH};`. There is **no** `iterative_scan` setting. [V]
- v2 (uncommitted working-tree change, `sweep_orchestrator.py:80`): `SET hnsw.iterative_scan = off;`. `PHASE_A_V2_RERUN_PROTOCOL.md:10` states "`hnsw.iterative_scan=off`" for the primary arm. [V]
- `targeted_sweeps.py` sets only `hnsw.ef_search` (`:76, :102`). [V]
- `docker-compose.yml`: image `pgvector/pgvector:pg16`, no `command:`, no `postgresql.conf` mount, no HNSW settings. `sql/schema_setup.sql` and `sql/index_setup.sql` contain no `iterative_scan`, `ef_search` or `max_scan_tuples`. `.env` has these keys only (values not printed): POSTGRES_*, OPENROUTER_*, EMBEDDING_MODEL, AI_*. No HNSW variable. [V]
- `max_scan_tuples`: **zero occurrences** anywhere in the repo (excluding `.git`). [V]
- `Coding_TODO_List.md:29-31` items 6 and 7 are ticked "confirm iterative scan is active" and "fix the check script". **No result of that check is recorded anywhere I could find.** [V that none is present; I could not search shell history]
- `replay_output.txt` (UTF-16) line 1: `Has hnsw.iterative_scan parameter: True`. [V] This shows the DB used in the replay session knew the GUC, so it was pgvector ≥ 0.8. [I]. The replay was done after the Phase A runs, so it is not evidence about the Phase A session.

### 3b. Live checks (run after the DB was started) [V]

Environment: PostgreSQL 16.14, pgvector `extversion = 0.8.3`, `pg_db_role_setting` empty (0 rows).

A fresh session reports `unrecognized configuration parameter "hnsw.iterative_scan"` (also for `ef_search` and `max_scan_tuples`) because the library is not loaded until a vector function is used. After `SELECT '[1,2]'::vector <-> '[1,3]'::vector;` in the same session:

```
 hnsw.iterative_scan  | off
 hnsw.ef_search       | 40
 hnsw.max_scan_tuples | 20000

           name           | setting | source
--------------------------+---------+---------
 hnsw.ef_search           | 40      | default
 hnsw.iterative_scan      | off     | default
 hnsw.max_scan_tuples     | 20000   | default
 hnsw.scan_mem_multiplier | 1       | default
```

Indexes on the FinQA table (`pg_indexes`): `finqa_evidence_pkey` (btree on id) and `finqa_evidence_embedding_idx ... USING hnsw (embedding vector_l2_ops) WITH (m='16', ef_construction='64')`. No other index.

### 3c. Did any Phase A result record the setting?

[V] No. `outputs/phase_a_v1/sweep_results.jsonl` (1100 rows) and `outputs/phase_a_v2/sweep_results.jsonl` (4495 parseable rows + 1 truncated line, line 798) have exactly these keys: `timestamp, filter_id, table_name, query_vector_idx, k, hnsw_ef_search, success, scan_strategy, index_used, planning_time_ms, latency_ms, filter_time_ms, rows_removed, recall, error_msg, recall_error`. There is no iterative-scan field. `baselines_reference.json` entries carry `hnsw_ef_search, k, memcap` only. `PHASE_A_V2_RERUN_PROTOCOL.md:18` says v2 will "record … iterative-scan mode", but the v2 result rows do not contain it. [V]

**Conclusion: `off` today (source `default`); for the past v1 sweep, very probably off but not provable.**
- [V] Currently `hnsw.iterative_scan = off`, source `default`. There are no database or role overrides, and every `hnsw%` row in `pg_settings` has source `default`. pgvector is 0.8.3, which has the setting.
- [V] The v1 code never set it, and nothing in the repo (compose, SQL, `.env`) sets it.
- [I] So the v1 sweep very probably ran with it off. Residual uncertainty: the sweep ran on 2026-09-04 and no record of the server state or pgvector version at that time exists. A past session cannot be queried. v2 sets it explicitly to `off`, but that came after the thresholds were frozen.

---

## Task 4 — EXPLAIN plans on FinQA (run live)

Queries chosen from the frozen 50 (`outputs/phase_d_results_ollama_corrected.jsonl`):

| Position | Query id | Selectivity | Ticker / year | Rows matching filter (from plan) |
|---|---|---|---|---|
| Lowest | `HWM/2018/page_96.pdf-2` | 0.0005577 | HWM / 2018 | 20 |
| Middle (rank 25 of 50; rank 26 is `MO/2016/page_19.pdf-2`, 0.004015) | `UNP/2016/page_52.pdf-3` | 0.0039039 | UNP / 2016 | 140 |
| Highest | `IP/2006/page_75.pdf-1` | 0.0194356 | IP / 2006 | 697 |

**Deviations from the runner (stated, not hidden):**
- The runner embeds the question with Ollama; Ollama was not used here. The probe vector is the **stored embedding of that query's own gold row** (`(SELECT embedding FROM finqa_evidence WHERE query_id='…' LIMIT 1)::vector`). That adds an InitPlan seq scan to every plan (the `finqa_evidence_1` node). It is not part of the arm. The main scan's plan shape should be the same, but returned rows and timings are **not** those of the frozen run.
- `jit` was left at the server default (on), as in the runner (the runner never sets `jit`). The JIT block inflates the post-filter execution times below.
- Session: `SET hnsw.ef_search = 40`. Pre-filter: `SET enable_indexscan = off; SET enable_seqscan = on;`. Post-filter-indexscan: `SET enable_indexscan = on; SET enable_seqscan = off; SET hnsw.iterative_scan = off;`. Same SELECT as the runner, `LIMIT 6`.

SELECT used by both arms (`<t>`, `<y>`, `<id>` per query):

```sql
SELECT query_id, content, evidence_key FROM finqa_evidence
WHERE metadata->>'ticker'='<t>' AND metadata->>'year'='<y>'
ORDER BY embedding <-> (SELECT embedding FROM finqa_evidence WHERE query_id='<id>' LIMIT 1)::vector LIMIT 6;
```

### Query 1 — HWM/2018 (lowest selectivity)

(a) pre-filter
```
 Limit  (cost=1877.73..1877.73 rows=1 width=164) (actual time=35.352..35.356 rows=6 loops=1)
   Buffers: shared hit=308 read=1121
   InitPlan 1 (returns $0)
     ->  Limit  (cost=0.00..55.47 rows=1 width=18) (actual time=0.746..0.748 rows=1 loops=1)
           Buffers: shared hit=177
           ->  Seq Scan on finqa_evidence finqa_evidence_1  (cost=0.00..1553.28 rows=28 width=18) (actual time=0.744..0.745 rows=1 loops=1)
                 Filter: (query_id = 'HWM/2018/page_96.pdf-2'::text)
                 Rows Removed by Filter: 5665
                 Buffers: shared hit=177
   ->  Sort  (cost=1822.25..1822.26 rows=1 width=164) (actual time=35.350..35.351 rows=6 loops=1)
         Sort Key: ((finqa_evidence.embedding <-> ($0)::vector))
         Sort Method: top-N heapsort  Memory: 28kB
         Buffers: shared hit=308 read=1121
         ->  Seq Scan on finqa_evidence  (cost=0.00..1822.24 rows=1 width=164) (actual time=7.506..35.277 rows=20 loops=1)
               Filter: (((metadata ->> 'ticker'::text) = 'HWM'::text) AND ((metadata ->> 'year'::text) = '2018'::text))
               Rows Removed by Filter: 35842
               Buffers: shared hit=305 read=1121
 Planning:
   Buffers: shared hit=131 read=14 dirtied=1
 Planning Time: 3.633 ms
 Execution Time: 35.409 ms
```

(b) post-filter-indexscan
```
 Limit  (cost=10000000565.10..10000034865.68 rows=1 width=164) (actual time=363.794..364.255 rows=4 loops=1)
   Buffers: shared hit=439 read=439 dirtied=34
   InitPlan 1 (returns $0)
     ->  Limit  (cost=10000000000.00..10000000055.47 rows=1 width=18) (actual time=0.674..0.675 rows=1 loops=1)
           Buffers: shared hit=177
           ->  Seq Scan on finqa_evidence finqa_evidence_1  (cost=10000000000.00..10000001553.27 rows=28 width=18) (actual time=0.670..0.671 rows=1 loops=1)
                 Filter: (query_id = 'HWM/2018/page_96.pdf-2'::text)
                 Rows Removed by Filter: 5665
                 Buffers: shared hit=177
   ->  Index Scan using finqa_evidence_embedding_idx on finqa_evidence  (cost=509.63..34810.21 rows=1 width=164) (actual time=105.457..105.916 rows=4 loops=1)
         Order By: (embedding <-> ($0)::vector)
         Filter: (((metadata ->> 'ticker'::text) = 'HWM'::text) AND ((metadata ->> 'year'::text) = '2018'::text))
         Rows Removed by Filter: 147
         Buffers: shared hit=439 read=439 dirtied=34
 Planning:
   Buffers: shared hit=1
 Planning Time: 0.135 ms
 JIT:
   Functions: 13
   Options: Inlining true, Optimization true, Expressions true, Deforming true
   Timing: Generation 1.375 ms, Inlining 89.471 ms, Optimization 96.293 ms, Emission 72.616 ms, Total 259.755 ms
 Execution Time: 546.650 ms
```

### Query 2 — UNP/2016 (middle)

(a) pre-filter
```
 Limit  (cost=1877.73..1877.73 rows=1 width=164) (actual time=22.362..22.366 rows=6 loops=1)
   Buffers: shared hit=2882 read=77
   InitPlan 1 (returns $0)
     ->  Limit  (cost=0.00..55.47 rows=1 width=18) (actual time=3.840..3.842 rows=1 loops=1)
           Buffers: shared hit=1014
           ->  Seq Scan on finqa_evidence finqa_evidence_1  (cost=0.00..1553.28 rows=28 width=18) (actual time=3.838..3.839 rows=1 loops=1)
                 Filter: (query_id = 'UNP/2016/page_52.pdf-3'::text)
                 Rows Removed by Filter: 32974
                 Buffers: shared hit=1014
   ->  Sort  (cost=1822.25..1822.26 rows=1 width=164) (actual time=22.361..22.362 rows=6 loops=1)
         Sort Key: ((finqa_evidence.embedding <-> ($0)::vector))
         Sort Method: top-N heapsort  Memory: 30kB
         Buffers: shared hit=2882 read=77
         ->  Seq Scan on finqa_evidence  (cost=0.00..1822.24 rows=1 width=164) (actual time=9.495..22.236 rows=140 loops=1)
               Filter: (((metadata ->> 'ticker'::text) = 'UNP'::text) AND ((metadata ->> 'year'::text) = '2016'::text))
               Rows Removed by Filter: 35722
               Buffers: shared hit=2882 read=77
 Planning:
   Buffers: shared hit=1
 Planning Time: 0.188 ms
 Execution Time: 22.397 ms
```

(b) post-filter-indexscan
```
 Limit  (cost=10000000565.10..10000034865.68 rows=1 width=164) (actual time=146.228..146.230 rows=0 loops=1)
   Buffers: shared hit=1260 read=57 dirtied=25
   InitPlan 1 (returns $0)
     ->  Limit  (cost=10000000000.00..10000000055.47 rows=1 width=18) (actual time=4.254..4.255 rows=1 loops=1)
           Buffers: shared hit=1014
           ->  Seq Scan on finqa_evidence finqa_evidence_1  (cost=10000000000.00..10000001553.27 rows=28 width=18) (actual time=4.248..4.249 rows=1 loops=1)
                 Filter: (query_id = 'UNP/2016/page_52.pdf-3'::text)
                 Rows Removed by Filter: 32974
                 Buffers: shared hit=1014
   ->  Index Scan using finqa_evidence_embedding_idx on finqa_evidence  (cost=509.63..34810.21 rows=1 width=164) (actual time=18.614..18.614 rows=0 loops=1)
         Order By: (embedding <-> ($0)::vector)
         Filter: (((metadata ->> 'ticker'::text) = 'UNP'::text) AND ((metadata ->> 'year'::text) = '2016'::text))
         Rows Removed by Filter: 394
         Buffers: shared hit=1260 read=57 dirtied=25
 Planning:
   Buffers: shared hit=1
 Planning Time: 0.115 ms
 JIT:
   Functions: 13
   Options: Inlining true, Optimization true, Expressions true, Deforming true
   Timing: Generation 0.529 ms, Inlining 10.764 ms, Optimization 71.070 ms, Emission 45.833 ms, Total 128.196 ms
 Execution Time: 146.832 ms
```

### Query 3 — IP/2006 (highest selectivity)

(a) pre-filter
```
 Limit  (cost=1877.73..1877.73 rows=1 width=164) (actual time=41.707..41.710 rows=6 loops=1)
   Buffers: shared hit=5141 read=376
   InitPlan 1 (returns $0)
     ->  Limit  (cost=0.00..55.47 rows=1 width=18) (actual time=0.773..0.774 rows=1 loops=1)
           Buffers: shared hit=230
           ->  Seq Scan on finqa_evidence finqa_evidence_1  (cost=0.00..1553.28 rows=28 width=18) (actual time=0.772..0.773 rows=1 loops=1)
                 Filter: (query_id = 'IP/2006/page_75.pdf-1'::text)
                 Rows Removed by Filter: 7333
                 Buffers: shared hit=230
   ->  Sort  (cost=1822.25..1822.26 rows=1 width=164) (actual time=41.706..41.707 rows=6 loops=1)
         Sort Key: ((finqa_evidence.embedding <-> ($0)::vector))
         Sort Method: top-N heapsort  Memory: 28kB
         Buffers: shared hit=5141 read=376
         ->  Seq Scan on finqa_evidence  (cost=0.00..1822.24 rows=1 width=164) (actual time=2.297..41.407 rows=697 loops=1)
               Filter: (((metadata ->> 'ticker'::text) = 'IP'::text) AND ((metadata ->> 'year'::text) = '2006'::text))
               Rows Removed by Filter: 35165
               Buffers: shared hit=5141 read=376
 Planning:
   Buffers: shared hit=1
 Planning Time: 0.124 ms
 Execution Time: 41.731 ms
```

(b) post-filter-indexscan
```
 Limit  (cost=10000000565.10..10000034865.68 rows=1 width=164) (actual time=267.530..267.595 rows=6 loops=1)
   Buffers: shared hit=427 read=567 dirtied=15
   InitPlan 1 (returns $0)
     ->  Limit  (cost=10000000000.00..10000000055.47 rows=1 width=18) (actual time=1.124..1.126 rows=1 loops=1)
           Buffers: shared hit=230
           ->  Seq Scan on finqa_evidence finqa_evidence_1  (cost=10000000000.00..10000001553.27 rows=28 width=18) (actual time=1.119..1.120 rows=1 loops=1)
                 Filter: (query_id = 'IP/2006/page_75.pdf-1'::text)
                 Rows Removed by Filter: 7333
                 Buffers: shared hit=230
   ->  Index Scan using finqa_evidence_embedding_idx on finqa_evidence  (cost=509.63..34810.21 rows=1 width=164) (actual time=132.381..132.444 rows=6 loops=1)
         Order By: (embedding <-> ($0)::vector)
         Filter: (((metadata ->> 'ticker'::text) = 'IP'::text) AND ((metadata ->> 'year'::text) = '2006'::text))
         Rows Removed by Filter: 23
         Buffers: shared hit=427 read=567 dirtied=15
 Planning:
   Buffers: shared hit=1
 Planning Time: 0.107 ms
 JIT:
   Functions: 13
   Options: Inlining true, Optimization true, Expressions true, Deforming true
   Timing: Generation 0.535 ms, Inlining 9.953 ms, Optimization 74.797 ms, Emission 50.440 ms, Total 135.725 ms
 Execution Time: 268.217 ms
```

### Reading the plans [V]

- **Pre-filter is an exact scan.** In all three: `Limit → Sort (top-N heapsort) → Seq Scan on finqa_evidence` with the ticker/year `Filter`. It reads the whole table (matched rows + `Rows Removed by Filter` = 35,862, e.g. 20 + 35,842). There is no Bitmap Heap Scan (no btree on `metadata`) and the HNSW index is not touched. It returns the exact top-6 within the metadata subset.
- **Post-filter-indexscan is an HNSW Index Scan:** `Index Scan using finqa_evidence_embedding_idx … Order By: (embedding <-> …)`, with the ticker/year test applied as a plain `Filter` on the rows the index emits (not as an index condition). This is filter-after-traversal.
- **It under-fills.** With `ef_search = 40` and `iterative_scan = off`, the index emitted 151 rows for HWM (4 kept, 147 removed), 394 for UNP (0 kept) and 29 for IP (6 kept, 23 removed). Rows returned: **4, 0 and 6** against `LIMIT 6`. UNP/2016 has 140 matching rows in the table, yet the post-filter arm returned none. The index emits more than 40 rows because pgvector groups duplicate vectors into one graph element, consistent with `METHODOLOGY_AUDIT.md`. With the stand-in vector these counts are indicative, not the frozen run's counts.
- The 10000000000 costs in the InitPlan and Limit are the `enable_seqscan = off` penalty on my stand-in subquery's seq scan. They are an artefact of the probe, not of the arm.
- Timings are not comparable between arms. The post-filter times include JIT (about 130–260 ms per query) and cold buffers (`read=…`, `dirtied=…`). Do not quote them as arm latencies.

**Answer (Task 4):** Yes on both counts. Phase D pre-filter is an exact `Seq Scan + top-N Sort` with no index use, and post-filter-indexscan is an HNSW `Index Scan` with the metadata test as a post-hoc `Filter`. On this DB the HNSW arm returned 4, 0 and 6 of the requested 6 rows for the lowest, middle and highest selectivity query.

---

## Task 5 — Thresholds and baselines

### 5a. Thresholds file in the frozen run

- The runner's `--thresholds` argument is not recorded in any result row (`run_meta`, `local_ollama_runner.py:177`, has no thresholds path or correlation level), and I found no logged command line. **The exact `--thresholds` and `--correlation-level` used cannot be determined from the repo.** [V]
- At b59c004 the default was `outputs/thresholds.json` and the default tier was `hm_clothes_0`. [V] That file is added in b59c004 itself and is **byte-identical to the working tree** (`git diff --quiet b59c004 -- outputs/thresholds.json` → identical) and to `outputs/phase_a_v1/thresholds.json` (archived in 597666b; tag `phase-a-v1`).
- Contents: see the table in 1c.
- Generation [V]: I re-ran `extract_thresholds` (read-only) on `outputs/phase_a_v1/sweep_results.jsonl` + `outputs/phase_a_v1/filters.json`. With `recall_stat="min"` the output **equals** `outputs/thresholds.json`; with `mean` or `median` it does not. So the file came from `src/phase_c_analysis/threshold_detector.py` with `--recall-stat min` on the **Phase A v1** sweep. Rules (`threshold_detector.py:73-74`): recall zone = recall < 0.9, latency zone = median latency > 500 ms. A zone is a contiguous run of sampled selectivities.
- `threshold_detector.py` is **untracked** (`git status`: `?? src/phase_c_analysis/threshold_detector.py`).
- Other files [V]:
  - `outputs/phase_a_v2/thresholds.json` is produced by the same detector with `mean` on the v2 sweep (reproduced: equal). It differs from v1: tier 50 loses its recall zone, and tiers 25 and 0 gain a latency zone at the point 0.20376.
  - `outputs/thresholds_v2.json` contains `{}`. Passing it as `--thresholds` would make every call raise `ValueError`.

### 5b. baselines_reference.json

- `outputs/baselines_reference.json` is untracked. It holds 230 keys, each `"{table}_v{vector_idx}[_ef{N}][_k{N}][_memcap]"`, with value `{table_name, query_vector_idx, hnsw_ef_search, k, memcap, baseline_ms}`. `baseline_ms` is the median of 10 EXPLAIN-ANALYZE timings of an **unfiltered** HNSW top-k query on that table. [V]
- Breakdown by (ef, k, memcap): (40,10,F)×25, (100,10)×25, (200,10)×25, (400,10)×25, (40,50)×25, (40,10,memcap)×25, (100,50)×25, (200,50)×25, (400,50)×25, (800,50)×5. [V]
- It is read only by Phase A code: `src/phase_a_sweep/logger.py:10, 47-83`, `sweep_orchestrator.py:55-57`, `targeted_sweeps.py:42-44`. It is used to compute `filter_time_ms = execution_time - baseline`. **No Phase B, C or D code reads it.** [V]
- `outputs/phase_a_v2/baselines_reference.json` is the v2 counterpart (100 keys).

### 5c. Git state

```
$ git rev-parse HEAD
ab7857344f490290d3b23e3a8a2c97f30e86c0b0     (ab78573 "Freeze Phase A v2 rerun protocol")
$ git diff --stat b59c004 -- src/phase_b_router/policy.py src/phase_d_validation/comparison_runner.py src/phase_d_validation/local_ollama_runner.py outputs/thresholds.json
 src/phase_d_validation/local_ollama_runner.py | 64 +++++++++++++++++++++------
 1 file changed, 51 insertions(+), 13 deletions(-)
```

| File | Vs b59c004 |
|---|---|
| `outputs/thresholds.json` | identical [V] |
| `local_ollama_runner.py` | modified, uncommitted: adds `iterative-scan` and `post-filter-app-top40` arms, sets `hnsw.iterative_scan=off` in the post-filter arm, factors out `estimate_selectivity`, makes `--thresholds` required. The pre-filter SQL/SET is unchanged. [V] |
| `policy.py`, `router.py`, `test_router.py`, `comparison_runner.py` | **not in b59c004 and not tracked in any commit** (`git ls-tree -r b59c004` lists only `src/phase_b_router/__init__.py`; `git status`: `??`). `git diff` therefore cannot compare them. [V] |

[V] The frozen runner at b59c004 does `from src.phase_b_router.policy import get_routing_decision` (line 32), but `policy.py` is not in that commit. **The tag `phase-d-local-freeze` is not self-contained.** I cannot prove from git that the policy that ran is the one on disk. The `.pyc` timestamps could say more; I did not check them. The recorded output is consistent with it: all routes are `pre-filter` (see below).

**Answer (Task 5):** The frozen thresholds are the Phase A v1 file generated with the `min` recall statistic (unchanged since b59c004). The exact CLI arguments for the frozen run are not recorded. `baselines_reference.json` is Phase A latency baselining and nothing in Phases B–D reads it. The policy, router and detector code behind the frozen run are untracked.

---

## Mismatches and risks

Against the claim "the Decision Matrix prevents the recall collapse seen in Phase A":

1. **The frozen Phase D run never exercised the matrix.** [V] In `phase_d_results_ollama_corrected.jsonl` (50 rows, 0 errors), `dm_route` = `pre-filter` ×50. Selectivities range from 0.000558 to 0.019436; the lowest recall zone starts at 0.3149. I applied the policy to those 50 selectivities for all 5 tiers: all `pre-filter`. `FINQA_SELECTIVITY_CENSUS_PROTOCOL.md` makes the same prediction. So the matrix behaved as "always pre-filter" regardless of thresholds, tier or v1/v2. This cannot show that the matrix prevents a collapse. It can only show that an always-exact policy does not collapse.
2. **The danger zone is mapped to the mechanism that collapsed.** [V code and data, I interpretation] In Phase A the recall collapse happened only where the planner chose HNSW `Index Scan` (75 of 1100 points; Bitmap Heap Scan points all had recall 1.0 by assumption). `policy.py:17` returns `post-filter` inside recall danger zones, and Phase D's `post-filter` is the forced-HNSW arm. If the matrix were ever to fire in a recall zone, it would send the query to HNSW, the plan that lost recall in Phase A, and `pre-filter` (exact) would be the safe route there. The docstring says "Choose the safe route". Unless the intended meaning of `post-filter` differs from what `_retrieve` runs, the mapping is inverted for recall zones. It is sensible only for latency zones, where the exact plan was slow, and the v1 file has none. Please confirm what you intended.
3. **Different mechanisms behind the same words.** [V] Table in Task 2c: planner-chosen plan labels (Phase A) versus forced `enable_*` arms (Phase D), with halfvec-2048 cosine vs vector-768 L2, k=10 vs 6, and categorical columns vs JSONB. Only `ef_search=40` and the HNSW m/ef_construction match.
4. **Recall is measured in only one phase.** [V] Phase A recall = ANN recall@10 against an exact scan. Phase D "recall" is `unit_recall` against gold evidence. The Phase D pre-filter is exact (designed to be), so a collapse is not measurable on that arm.
5. **The failure seen in Phase D is a different one.** [V numbers] In the frozen jsonl, Naive-routed post-filter queries retrieved a mean of 3.91 rows out of k=6 (45 queries; unit_recall 0.279) versus 6 rows for pre-filter (unit_recall 0.384 for DM). `METHODOLOGY_AUDIT.md:69-72` attributes this to a candidate pool of up to about 400 heap tuples that is too small at low *local* selectivity (duplicate embeddings expand 40 graph elements). That is under-filling, not the Phase A recall drop, and it is driven by neighbourhood-local selectivity, which the global-fraction input does not capture.
6. **Selectivity input is the wrong kind for FinQA.** [V code, I consequence] The matrix input is a global row fraction (`local_ollama_runner.py:71-78`); the thresholds come from H&M global selectivities. The post-hoc audit says retrieval yield depends on local selectivity. No correlation measure exists for FinQA; the tier is a hand-supplied label, default `hm_clothes_0`, and the value used in the frozen run is unrecorded.
7. **The thresholds are sparse points, not regions.** [V] 44 sampled selectivities, no sample between 0.2038 and 0.329, and `policy.py` does not interpolate. Tiers 50 and 0 have a single-point recall zone (±0.005) at 0.329, though Phase A's planner used HNSW at 0.3763 and 0.4705 too. At those values (and above 0.4846 on tiers 100/75) the policy returns `pre-filter` by fall-through, not by evidence. v1 used the *minimum* recall over only 5 vectors; the v2 protocol uses the mean over 20 and gives different zones (tier 50 loses its zone, tiers 25 and 0 gain a latency zone).
8. **Silent failure modes.** [V] NaN → `pre-filter`; `None` → `TypeError` on tiers that have zones (but returns `pre-filter` on an empty-zone tier); no range validation; default `margin` 0.01 if absent.
9. **Reproducibility.** [V] `policy.py`, `router.py`, `test_router.py` and `threshold_detector.py` are untracked, and the freeze tag points at a commit that imports a file it does not contain. The runner now differs from the frozen one. The frozen run's `--thresholds` and `--correlation-level` are unrecorded. `outputs/thresholds_v2.json` is `{}`.
10. **Tests do not protect the claim.** [V] They use mock thresholds that differ from the real file (e.g. recall zone `(0.4705, 1.0)`), never load the real file, and mock out `execute_vector_search`.
11. **The `iterative_scan` state of the v1 sweep cannot be proven** (Task 3). The live server shows `off` (source `default`, no overrides, pgvector 0.8.3), and v1 never set it, so "off" is very probable [I]. It is not recorded in any v1 result.
12. **Plans confirmed (Task 4) [V].** Phase D pre-filter = `Seq Scan + top-N Sort`; post-filter = HNSW `Index Scan` with the metadata test as `Filter`. The post-filter arm returned 4, 0 and 6 of 6 rows on the three probe queries. So Phase D's `post-filter` is the same family of plan as Phase A's collapsing `Index Scan`, which strengthens risk 2.

### What would settle the open items
- Confirm the intended semantics of `post-filter` in a recall danger zone (risk 2).
- Commit or archive `policy.py`, `router.py`, `threshold_detector.py` so that the freeze tag is reproducible. That is a repository change, so I have not done it.
