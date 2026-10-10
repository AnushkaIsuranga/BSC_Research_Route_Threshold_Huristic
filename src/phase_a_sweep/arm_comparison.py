"""H&M three-arm danger-zone run (see PHASE_A_ARMS_PROTOCOL.md).

Measures recall@10, rows returned, plan node and latency for several execution
arms on the five H&M tables at selected selectivity points.

Modes:
  --build-filters   read-only: measure the frozen filter list on all five tables
                    and write outputs/phase_a_arms/filters.json
  --dry-run         hm_clothes_100 x filter idx1 (0.3290) x all arms x vectors 0,1
                    -> outputs/phase_a_arms/dryrun.jsonl
  (default)         the full run -> outputs/phase_a_arms/results.jsonl
                    (do not start before the protocol is frozen and approved)

The existing Phase A helpers are reused: run_explain_analyze / parse_query_metrics
(explain_analyze_wrapper.py) and fetch_top_k_ids (recall_calculator.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src.database.connection import connect_pgvector
from src.phase_a_sweep.explain_analyze_wrapper import parse_query_metrics, run_explain_analyze
from src.phase_a_sweep.recall_calculator import fetch_top_k_ids

OUT_DIR = Path("outputs/phase_a_arms")
TESTS_FILE = Path("ann-filtering-benchmark-datasets/data/tests.jsonl")
TABLES = ["hm_clothes_0", "hm_clothes_25", "hm_clothes_50", "hm_clothes_75", "hm_clothes_100"]
N_VECTORS = 20          # first 20 lines of tests.jsonl = vectors 0-19 of the Phase A v2 run
K = 10
EF_SEARCH = 40
TIMED_REPEATS = 5
SEED = 20261010
STATEMENT_TIMEOUT_MS = 120000
RECALL_DANGER = 0.9

# Frozen filter definitions. Selectivities are measured, never assumed (--build-filters).
FILTER_SPECS = [
    # Amendment 1: low-selectivity points, reused from the Phase A v2 filters (v2_filter_id)
    {"filter_id": "lo1",  "role": "low", "v2_filter_id": "f_000", "conditions": [("product_type_name", ["Cap"])]},
    {"filter_id": "lo2",  "role": "low", "v2_filter_id": "f_006", "conditions": [("product_type_name", ["Costumes"])]},
    {"filter_id": "lo3",  "role": "low", "v2_filter_id": "f_016", "conditions": [("product_type_name", ["Blazer"])]},
    {"filter_id": "lo4",  "role": "low", "v2_filter_id": "f_028", "conditions": [("garment_group_name", ["Shoes"])]},
    {"filter_id": "lo5",  "role": "low", "v2_filter_id": "f_037", "conditions": [("product_type_name", ["Trousers"])]},
    {"filter_id": "ctl",  "role": "control",    "conditions": [("garment_group_name", ["Jersey Fancy"])]},
    {"filter_id": "gap1", "role": "gap",        "conditions": [("perceived_colour_master_name", ["Black"])]},
    {"filter_id": "gap2", "role": "gap",        "conditions": [("perceived_colour_master_name", ["Blue", "Red"])]},
    {"filter_id": "gap3", "role": "gap",        "conditions": [("perceived_colour_master_name", ["Blue", "Grey"])]},
    {"filter_id": "gap4", "role": "gap",        "conditions": [("perceived_colour_master_name", ["Black", "Grey"])]},
    {"filter_id": "idx1", "role": "index-scan", "conditions": [("index_group_name", ["Baby/Children"])]},
    {"filter_id": "idx2", "role": "index-scan", "conditions": [("index_group_name", ["Ladieswear"])]},
    {"filter_id": "idx3", "role": "index-scan", "conditions": [("graphical_appearance_name", ["Solid"])]},
]

# arm -> (SET statements applied after a full RESET of the planner GUCs, expected plan check)
ARMS = {
    "planner-default": {"sets": {"hnsw.iterative_scan": "off"}},
    "forced-exact": {"sets": {"enable_indexscan": "off", "hnsw.iterative_scan": "off"}},
    "forced-hnsw": {"sets": {"enable_indexscan": "on", "enable_seqscan": "off", "enable_bitmapscan": "off",
                             "hnsw.iterative_scan": "off"}},
    "iterative-relaxed": {"sets": {"enable_indexscan": "on", "enable_seqscan": "off", "enable_bitmapscan": "off",
                                   "hnsw.iterative_scan": "relaxed_order"}},
    "iterative-strict": {"sets": {"enable_indexscan": "on", "enable_seqscan": "off", "enable_bitmapscan": "off",
                                  "hnsw.iterative_scan": "strict_order"}},
}
RESET_GUCS = ["enable_indexscan", "enable_seqscan", "enable_bitmapscan", "enable_sort", "hnsw.iterative_scan"]
RECORDED_GUCS = ["enable_indexscan", "enable_seqscan", "enable_bitmapscan", "enable_sort", "hnsw.ef_search",
                 "hnsw.iterative_scan", "hnsw.max_scan_tuples", "hnsw.scan_mem_multiplier", "jit", "statement_timeout"]


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


def where_for(conditions):
    parts, params = [], []
    for col, values in conditions:
        if len(values) == 1:
            parts.append(f"{col} = %s")
        else:
            parts.append(f"{col} IN ({', '.join(['%s'] * len(values))})")
        params.extend(values)
    return " AND ".join(parts), params


def describe(conditions) -> str:
    return " AND ".join(f"{c} = {v[0]!r}" if len(v) == 1 else f"{c} IN {tuple(v)!r}" for c, v in conditions)


def load_vectors(n=N_VECTORS):
    vecs, raw = [], []
    with open(TESTS_FILE, "r") as f:
        for _ in range(n):
            line = f.readline()
            raw.append(line)
            vecs.append(json.loads(line)["query"])
    return [f"[{','.join(map(str, v))}]" for v in vecs], hashlib.sha256("".join(raw).encode()).hexdigest()


def connect():
    conn = connect_pgvector()
    conn.commit()
    conn.autocommit = True
    with conn.cursor() as cur:   # load the pgvector library so hnsw.* GUCs are real, not placeholders
        cur.execute("SELECT '[1,2]'::vector <-> '[1,3]'::vector")
    return conn


def build_filters():
    conn = connect()
    out = []
    with conn.cursor() as cur:
        for spec in FILTER_SPECS:
            where, params = where_for(spec["conditions"])
            per_table = {}
            for t in TABLES:
                cur.execute(f"SELECT COUNT(*) FROM {t} WHERE {where}", params)
                per_table[t] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM hm_clothes_100")
            total = cur.fetchone()[0]
            if len(set(per_table.values())) != 1:
                raise RuntimeError(f"{spec['filter_id']}: row counts differ between tables: {per_table}")
            n = per_table["hm_clothes_100"]
            out.append({"filter_id": spec["filter_id"], "role": spec["role"], "v2_filter_id": spec.get("v2_filter_id"), "description": describe(spec["conditions"]),
                        "conditions": [[c, v] for c, v in spec["conditions"]], "where": where, "params": params,
                        "matched_rows": n, "total_rows": total, "selectivity": n / total, "per_table_matched_rows": per_table})
    conn.close()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "filters.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for f in out:
        print(f"{f['filter_id']:5s} {f['role']:10s} sel={f['selectivity']:.5f} rows={f['matched_rows']} {f['description']}")


def apply_arm(cur, arm):
    for g in RESET_GUCS:
        cur.execute(f"RESET {g}")
    cur.execute(f"SET hnsw.ef_search = {EF_SEARCH}")
    cur.execute("SET jit = off")
    cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
    for k, v in ARMS[arm]["sets"].items():
        cur.execute(f"SET {k} = '{v}'")
    eff = {}
    for g in RECORDED_GUCS:
        cur.execute("SELECT current_setting(%s)", (g,))
        eff[g] = cur.fetchone()[0]
    return eff


def all_nodes(plan):
    nodes = [plan.get("Node Type")]
    for c in plan.get("Plans", []):
        nodes += all_nodes(c)
    return nodes


def plan_as_intended(arm, scan_node, index_used):
    hnsw = scan_node == "Index Scan" and (index_used or "").endswith("embedding_idx")
    if arm in ("forced-hnsw", "iterative-relaxed", "iterative-strict"):
        return hnsw
    if arm == "forced-exact":
        return scan_node in ("Seq Scan", "Bitmap Heap Scan")
    return True  # planner-default: whatever the planner chooses is the observation


def run(args):
    t_start = time.time()
    filters = json.loads((OUT_DIR / "filters.json").read_text(encoding="utf-8"))
    vectors, vec_sha = load_vectors()
    rng = random.Random(SEED)
    tables = TABLES[:]
    rng.shuffle(tables)
    schedule = []
    for t in tables:
        fl = filters[:]
        rng.shuffle(fl)
        for f in fl:
            vi = list(range(N_VECTORS))
            rng.shuffle(vi)
            for v in vi:
                arms = list(ARMS)
                rng.shuffle(arms)
                schedule.append((t, f["filter_id"], v, arms))
    if args.dry_run:
        schedule = [s for s in schedule if s[0] == "hm_clothes_100" and s[1] == "idx1" and s[2] in (0, 1)]
        results_path = OUT_DIR / "dryrun.jsonl"
    else:
        results_path = OUT_DIR / "results.jsonl"
    schedule_sha = hashlib.sha256(json.dumps(schedule).encode()).hexdigest()

    sweep = connect()
    truth = connect()
    with truth.cursor() as c:
        c.execute("SET enable_indexscan = off")
        c.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
        c.execute("SET jit = off")
    cur = sweep.cursor()
    cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
    pgvector_version = cur.fetchone()[0]
    cur.execute("SHOW server_version")
    pg_version = cur.fetchone()[0]

    used = ["src/phase_a_sweep/arm_comparison.py", "src/phase_a_sweep/explain_analyze_wrapper.py",
            "src/phase_a_sweep/recall_calculator.py", "src/database/connection.py", "PHASE_A_ARMS_PROTOCOL.md",
            str(OUT_DIR / "filters.json")]
    meta = {"git_commit": git("rev-parse", "HEAD"),
            "git_dirty_used_files": bool(git("status", "--porcelain", "--", *used[:5])),
            "pgvector_version": pgvector_version, "pg_version": pg_version, "python": sys.version.split()[0],
            "platform": platform.platform(), "seed": SEED, "k": K, "hnsw_ef_search": EF_SEARCH,
            "timed_repeats": TIMED_REPEATS, "warmups_per_point": 1, "n_vectors": N_VECTORS,
            "vectors_source": f"first {N_VECTORS} lines of {TESTS_FILE} (as run_phase_a_v2.py: limit_vectors=20)",
            "vectors_sha256": vec_sha, "statement_timeout_ms": STATEMENT_TIMEOUT_MS, "jit": "off (SET per arm)",
            "table_order": tables, "schedule_sha256": schedule_sha, "n_schedule_items": len(schedule),
            "file_sha256": {p: sha256_file(p) for p in used}, "arms": ARMS, "started": datetime.now(timezone.utc).isoformat(),
            "mode": "dry-run" if args.dry_run else "full"}
    (OUT_DIR / ("dryrun_meta.json" if args.dry_run else "run_meta.json")).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    done = set()
    if results_path.exists() and not args.dry_run:
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                done.add((d["table"], d["filter_id"], d["arm"], d["vector_idx"]))
    fmap = {f["filter_id"]: f for f in filters}
    warmed = set()
    combo_times = []
    out = open(results_path, "a" if not args.dry_run else "w", encoding="utf-8")
    for n_item, (table, fid, v_idx, arms) in enumerate(schedule, 1):
        t_combo = time.time()
        f = fmap[fid]
        where, params = f["where"], f["params"]
        qv = vectors[v_idx]
        if table not in warmed:   # per-table warm-up before any timing
            apply_arm(cur, "planner-default")
            cur.execute(f"SELECT id FROM {table} ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048) LIMIT {K}", (qv,))
            cur.fetchall()
            cur.execute(f"SELECT id FROM {table} WHERE {where} ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048) LIMIT {K}",
                        tuple(params) + (qv,))
            cur.fetchall()
            warmed.add(table)
        truth_ids, truth_err = None, None
        try:
            truth_ids = fetch_top_k_ids(truth, table, "embedding", where, params, qv, K, STATEMENT_TIMEOUT_MS)
        except Exception as e:
            truth_err = str(e)
        sql = f"SELECT id FROM {table} WHERE {where} ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048) LIMIT %s"
        for arm in arms:
            if (table, fid, arm, v_idx) in done:
                continue
            row = {"git_commit": meta["git_commit"], "pgvector_version": pgvector_version, "pg_version": pg_version,
                   "arm": arm, "table": table, "filter_id": fid, "filter": f["description"], "selectivity": f["selectivity"],
                   "vector_idx": v_idx, "k": K, "seed": SEED, "error": None, "recall_error": None}
            try:
                eff = apply_arm(cur, arm)
                row.update({"hnsw_ef_search": eff["hnsw.ef_search"], "hnsw_iterative_scan": eff["hnsw.iterative_scan"],
                            "hnsw_max_scan_tuples": eff["hnsw.max_scan_tuples"], "hnsw_scan_mem_multiplier": eff["hnsw.scan_mem_multiplier"],
                            "jit": eff["jit"], "enable_indexscan": eff["enable_indexscan"], "enable_seqscan": eff["enable_seqscan"],
                            "enable_bitmapscan": eff["enable_bitmapscan"], "enable_sort": eff["enable_sort"],
                            "statement_timeout": eff["statement_timeout"]})
                # recall + rows returned (a normal execution, not EXPLAIN)
                ids = fetch_top_k_ids(sweep, table, "embedding", where, params, qv, K, STATEMENT_TIMEOUT_MS)
                row["rows_returned"] = len(ids)
                if truth_ids is None:
                    row["recall"], row["recall_error"] = None, truth_err
                elif not truth_ids:
                    row["recall"] = 1.0
                else:
                    row["recall"] = len(ids & truth_ids) / len(truth_ids)
                row["truth_size"] = None if truth_ids is None else len(truth_ids)
                # one untimed warm-up, then TIMED_REPEATS timed EXPLAIN ANALYZE runs
                full_params = tuple(params) + (qv, K)
                run_explain_analyze(sweep, sql, full_params, STATEMENT_TIMEOUT_MS)
                runs = []
                for _ in range(TIMED_REPEATS):
                    ex = run_explain_analyze(sweep, sql, full_params, STATEMENT_TIMEOUT_MS)
                    m = parse_query_metrics(ex)
                    m["nodes"] = all_nodes(ex["Plan"])
                    runs.append(m)
                lat = [r["execution_time_ms"] for r in runs]
                mid = sorted(runs, key=lambda r: r["execution_time_ms"])[len(runs) // 2]
                row.update({"scan_node": mid["scan_strategy"], "index_used": mid["index_used"],
                            "plan_nodes": "/".join(n for n in mid["nodes"] if n), "rows_removed_by_filter": mid["rows_removed_by_filter"],
                            "latency_ms": statistics.median(lat), "latency_raw_ms": lat,
                            "scan_nodes_seen": sorted({r["scan_strategy"] for r in runs}),
                            "plan_as_intended": plan_as_intended(arm, mid["scan_strategy"], mid["index_used"])})
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            out.write(json.dumps(row) + "\n")
            out.flush()
        combo_times.append(time.time() - t_combo)
        if n_item % 10 == 0 or args.dry_run:
            el = (time.time() - t_start) / 60
            print(f"[{n_item}/{len(schedule)}] {table} {fid} v{v_idx}: {combo_times[-1]:.1f}s/combo, {el:.1f} min elapsed")
    out.close()
    sweep.close()
    truth.close()
    print(f"mean seconds per (table, filter, vector) combination: {statistics.mean(combo_times):.1f}")
    print(f"projected full-run hours at that rate (800 combos): {statistics.mean(combo_times) * 800 / 3600:.2f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--build-filters", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    if a.build_filters:
        build_filters()
    else:
        run(a)
