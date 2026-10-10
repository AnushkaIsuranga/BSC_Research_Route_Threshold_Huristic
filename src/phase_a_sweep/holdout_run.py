"""Held-out run for policy_v2 (see PHASE_A_HOLDOUT_PROTOCOL.md).

Arms: forced-exact, forced-hnsw, iterative-relaxed with the exact Amendment-2 settings of
arm_comparison.py (reused: apply_arm, ARMS). Held-out filters ho1..ho5 and vectors = lines 21-40
of tests.jsonl (0-based indices 20-39). Measurement as in the main run: exact reference (cached per
filter/vector), 1 recall execution, 1 warm-up, 5 timed EXPLAIN ANALYZE; randomised order; pre-flight
plan check; resumable; run metadata written once.

Modes: --build-filters | (default) full run | --status | --selftest
  --selftest replays hm_clothes_100 x idx1 (a filter of the MAIN run, not held-out) for vectors 0 and 1
  into outputs/phase_a_holdout/selftest.jsonl so the harness can be checked against results.jsonl
  without running any held-out query.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.errors

from src.phase_a_sweep.arm_comparison import (ARMS, EF_SEARCH, K, STATEMENT_TIMEOUT_MS, TABLES, TIMED_REPEATS, all_nodes, apply_arm,
                                              connect, describe, git, plan_as_intended, sha256_file, where_for)
from src.phase_a_sweep.explain_analyze_wrapper import find_scan_node, parse_query_metrics, run_explain_analyze
from src.phase_a_sweep.recall_calculator import fetch_top_k_ids

OUT_DIR = Path("outputs/phase_a_holdout")
TESTS_FILE = Path("ann-filtering-benchmark-datasets/data/tests.jsonl")
VEC_FIRST, VEC_COUNT = 20, 20          # 0-based line index 20 = line 21 ... index 39 = line 40
SEED = 20261012
HO_ARMS = ["forced-exact", "forced-hnsw", "iterative-relaxed"]

HO_SPECS = [
    {"filter_id": "ho1", "target": 0.02, "conditions": [("garment_group_name", ["Shirts"])]},
    {"filter_id": "ho2", "target": 0.03, "conditions": [("perceived_colour_master_name", ["Yellow"])]},
    {"filter_id": "ho3", "target": 0.07, "conditions": [("garment_group_name", ["Under-, Nightwear"])]},
    {"filter_id": "ho4", "target": 0.15, "conditions": [("index_group_name", ["Divided"])]},
    {"filter_id": "ho5", "target": 0.18, "conditions": [("graphical_appearance_name", ["All over pattern", "Colour blocking"])]},
]


def load_vectors(first=VEC_FIRST, count=VEC_COUNT):
    lines = TESTS_FILE.read_text(encoding="utf-8").splitlines()
    chosen = lines[first:first + count]
    if len(chosen) < count:
        raise SystemExit(f"only {len(chosen)} vectors available at lines {first + 1}-{first + count}")
    vecs = [f"[{','.join(map(str, json.loads(ln)['query']))}]" for ln in chosen]
    return vecs, hashlib.sha256(("\n".join(chosen) + "\n").encode()).hexdigest(), list(range(first, first + count))


def build_filters():
    conn = connect()
    out = []
    with conn.cursor() as cur:
        for spec in HO_SPECS:
            where, params = where_for(spec["conditions"])
            per_table = {}
            for t in TABLES:
                cur.execute(f"SELECT COUNT(*) FROM {t} WHERE {where}", params)
                per_table[t] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM hm_clothes_100")
            total = cur.fetchone()[0]
            if len(set(per_table.values())) != 1:
                raise RuntimeError(f"{spec['filter_id']}: counts differ between tables {per_table}")
            n = per_table["hm_clothes_100"]
            out.append({"filter_id": spec["filter_id"], "target": spec["target"], "description": describe(spec["conditions"]),
                        "conditions": [[c, v] for c, v in spec["conditions"]], "where": where, "params": params, "matched_rows": n,
                        "total_rows": total, "selectivity": n / total, "per_table_matched_rows": per_table})
    conn.close()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "filters.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for f in out:
        print(f"{f['filter_id']} target {f['target']:.2f} sel={f['selectivity']:.5f} rows={f['matched_rows']} {f['description']}")


def preflight(cur, filters, vector):
    checks, fails = [], []
    for t in TABLES:
        for f in filters:
            sql = f"SELECT id FROM {t} WHERE {f['where']} ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048) LIMIT {K}"
            for arm in HO_ARMS:
                apply_arm(cur, arm)
                cur.execute("EXPLAIN (FORMAT JSON) " + sql, tuple(f["params"]) + (vector,))
                node = find_scan_node(cur.fetchone()[0][0]["Plan"])
                ok = plan_as_intended(arm, node.get("Node Type"), node.get("Index Name"))
                rec = {"table": t, "filter_id": f["filter_id"], "arm": arm, "scan_node": node.get("Node Type"), "index_used": node.get("Index Name"), "ok": ok}
                checks.append(rec)
                if not ok:
                    fails.append(rec)
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "git_commit": git("rev-parse", "HEAD"), "n_checks": len(checks),
            "n_failed": len(fails), "all_passed": not fails, "failures": fails, "checks": checks}


def run(selftest=False):
    t_start = time.time()
    if selftest:
        filters = [f for f in json.loads(Path("outputs/phase_a_arms/filters.json").read_text(encoding="utf-8")) if f["filter_id"] == "idx1"]
        vectors, vsha, vidx = load_vectors(0, 2)
        tables = ["hm_clothes_100"]
        results_path, meta_path = OUT_DIR / "selftest.jsonl", OUT_DIR / "selftest_meta.json"
    else:
        filters = json.loads((OUT_DIR / "filters.json").read_text(encoding="utf-8"))
        vectors, vsha, vidx = load_vectors()
        tables = TABLES[:]
        results_path, meta_path = OUT_DIR / "results.jsonl", OUT_DIR / "run_meta.json"
    rng = random.Random(SEED)
    rng.shuffle(tables)
    schedule = []
    for t in tables:
        fl = filters[:]
        rng.shuffle(fl)
        for f in fl:
            vi = list(range(len(vectors)))
            rng.shuffle(vi)
            for v in vi:
                arms = HO_ARMS[:]
                rng.shuffle(arms)
                schedule.append((t, f["filter_id"], v, arms))
    schedule_sha = hashlib.sha256(json.dumps(schedule).encode()).hexdigest()

    sweep, truth = connect(), connect()
    with truth.cursor() as c:
        c.execute("SET enable_indexscan = off")
        c.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
        c.execute("SET jit = off")
    cur = sweep.cursor()
    cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
    pgvector_version = cur.fetchone()[0]
    cur.execute("SHOW server_version")
    pg_version = cur.fetchone()[0]
    server = {}
    for g in ("shared_buffers", "work_mem", "effective_cache_size", "max_parallel_workers_per_gather", "random_page_cost"):
        cur.execute(f"SHOW {g}")
        server[g] = cur.fetchone()[0]

    resuming = meta_path.exists() and not selftest
    pf = preflight(cur, filters, vectors[0])
    print(f"pre-flight: {pf['n_checks']} checks, {pf['n_failed']} failed")
    if not pf["all_passed"]:
        for x in pf["failures"][:20]:
            print("  FAILED:", x["table"], x["filter_id"], x["arm"], x["scan_node"], x["index_used"])
        raise SystemExit("pre-flight plan check failed: aborting before any measured query")
    if not resuming:
        (OUT_DIR / ("selftest_preflight.json" if selftest else "preflight.json")).write_text(json.dumps(pf, indent=2), encoding="utf-8")

    used = ["src/phase_a_sweep/holdout_run.py", "src/phase_a_sweep/arm_comparison.py", "src/phase_a_sweep/explain_analyze_wrapper.py",
            "src/phase_a_sweep/recall_calculator.py", "src/database/connection.py", "PHASE_A_HOLDOUT_PROTOCOL.md"]
    meta = {"git_commit": git("rev-parse", "HEAD"), "git_dirty_used_files": bool(git("status", "--porcelain", "--", *used)),
            "server_settings": server, "pgvector_version": pgvector_version, "pg_version": pg_version, "python": sys.version.split()[0],
            "platform": platform.platform(), "seed": SEED, "k": K, "hnsw_ef_search": EF_SEARCH, "timed_repeats": TIMED_REPEATS,
            "warmups_per_point": 1, "arms": {a: ARMS[a] for a in HO_ARMS}, "vector_indices": vidx, "vectors_sha256": vsha,
            "vectors_source": f"0-based line indices {vidx[0]}-{vidx[-1]} of {TESTS_FILE}", "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
            "table_order": tables, "schedule_sha256": schedule_sha, "n_schedule_items": len(schedule),
            "file_sha256": {p: sha256_file(p) for p in used + ([str(OUT_DIR / "filters.json")] if not selftest else [])},
            "started": datetime.now(timezone.utc).isoformat(), "mode": "selftest" if selftest else "full"}
    if selftest:
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    elif resuming:
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        for key in ("schedule_sha256", "seed", "vectors_sha256"):
            if old[key] != meta[key]:
                raise SystemExit(f"resume refused: {key} differs from run_meta.json")
        changed = [p for p in old["file_sha256"] if old["file_sha256"][p] != meta["file_sha256"].get(p)]
        if changed:
            raise SystemExit(f"resume refused: changed since the run started: {changed}")
        n_present = sum(1 for ln in results_path.read_text(encoding="utf-8").splitlines() if ln.strip()) if results_path.exists() else 0
        with open(OUT_DIR / "resumes.jsonl", "a", encoding="utf-8") as rf:
            rf.write(json.dumps({"resumed": datetime.now(timezone.utc).isoformat(), "git_commit": meta["git_commit"],
                                 "git_dirty_used_files": meta["git_dirty_used_files"], "rows_already_present": n_present}) + "\n")
        meta = old
    else:
        if meta["git_dirty_used_files"]:
            raise SystemExit("refusing to start the full run: git_dirty_used_files is true (commit first)")
        if results_path.exists():
            raise SystemExit("refusing to start: results.jsonl exists but run_meta.json does not")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    done = set()
    if results_path.exists() and not selftest:
        for ln in results_path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                d = json.loads(ln)
                done.add((d["table"], d["filter_id"], d["arm"], d["vector_idx"]))
    fmap = {f["filter_id"]: f for f in filters}
    warmed, combo_times = set(), []
    out = open(results_path, "w" if selftest else "a", encoding="utf-8")
    for n_item, (table, fid, v_i, arms) in enumerate(schedule, 1):
        t_combo = time.time()
        f = fmap[fid]
        where, params, qv, v_idx = f["where"], f["params"], vectors[v_i], vidx[v_i]
        if table not in warmed:
            apply_arm(cur, "planner-default")
            cur.execute(f"SELECT id FROM {table} ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048) LIMIT {K}", (qv,))
            cur.fetchall()
            cur.execute(f"SELECT id FROM {table} WHERE {where} ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048) LIMIT {K}", tuple(params) + (qv,))
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
            row = {"holdout": not selftest, "git_commit": meta["git_commit"], "pgvector_version": pgvector_version, "pg_version": pg_version,
                   "arm": arm, "table": table, "filter_id": fid, "filter": f["description"], "selectivity": f["selectivity"],
                   "vector_idx": v_idx, "k": K, "seed": SEED, "error": None, "recall_error": None}
            try:
                eff = apply_arm(cur, arm)
                row.update({"hnsw_ef_search": eff["hnsw.ef_search"], "hnsw_iterative_scan": eff["hnsw.iterative_scan"],
                            "hnsw_max_scan_tuples": eff["hnsw.max_scan_tuples"], "hnsw_scan_mem_multiplier": eff["hnsw.scan_mem_multiplier"],
                            "jit": eff["jit"], "enable_indexscan": eff["enable_indexscan"], "enable_seqscan": eff["enable_seqscan"],
                            "enable_bitmapscan": eff["enable_bitmapscan"], "enable_sort": eff["enable_sort"], "statement_timeout": eff["statement_timeout"]})
                ids = fetch_top_k_ids(sweep, table, "embedding", where, params, qv, K, STATEMENT_TIMEOUT_MS)
                row["rows_returned"] = len(ids)
                if truth_ids is None:
                    row["recall"], row["recall_error"] = None, truth_err
                elif not truth_ids:
                    row["recall"] = 1.0
                else:
                    row["recall"] = len(ids & truth_ids) / len(truth_ids)
                row["truth_size"] = None if truth_ids is None else len(truth_ids)
                full_params = tuple(params) + (qv, K)
                run_explain_analyze(sweep, sql, full_params, STATEMENT_TIMEOUT_MS)
                runs = []
                for _ in range(TIMED_REPEATS):
                    ex = run_explain_analyze(sweep, sql, full_params, STATEMENT_TIMEOUT_MS)
                    m = parse_query_metrics(ex)
                    m["nodes"] = all_nodes(ex["Plan"])
                    m["shared_hit"], m["shared_read"] = ex["Plan"].get("Shared Hit Blocks"), ex["Plan"].get("Shared Read Blocks")
                    runs.append(m)
                lat = [r["execution_time_ms"] for r in runs]
                mid = sorted(runs, key=lambda r: r["execution_time_ms"])[len(runs) // 2]
                row.update({"scan_node": mid["scan_strategy"], "index_used": mid["index_used"], "plan_nodes": "/".join(n for n in mid["nodes"] if n),
                            "rows_removed_by_filter": mid["rows_removed_by_filter"], "shared_hit_blocks": mid["shared_hit"], "shared_read_blocks": mid["shared_read"],
                            "latency_ms": statistics.median(lat), "latency_raw_ms": lat, "scan_nodes_seen": sorted({r["scan_strategy"] for r in runs}),
                            "plan_as_intended": plan_as_intended(arm, mid["scan_strategy"], mid["index_used"])})
            except psycopg2.errors.QueryCanceled as e:
                row["error"] = f"{type(e).__name__}: {e}"
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                raise SystemExit(f"connection problem, stopping without recording this row: {type(e).__name__}: {e}")
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            out.write(json.dumps(row) + "\n")
            out.flush()
        combo_times.append(time.time() - t_combo)
        if n_item % 10 == 0 or selftest:
            print(f"[{n_item}/{len(schedule)}] {table} {fid} v{v_idx}: {combo_times[-1]:.1f}s/combo, {(time.time() - t_start) / 60:.1f} min elapsed")
    out.close()
    sweep.close()
    truth.close()
    print(f"mean seconds per combination: {statistics.mean(combo_times):.1f}")


def status():
    filters = json.loads((OUT_DIR / "filters.json").read_text(encoding="utf-8"))
    expected = len(TABLES) * len(filters) * VEC_COUNT * len(HO_ARMS)
    path = OUT_DIR / "results.jsonl"
    rows = errs = bad = 0
    first = last = None
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                d = json.loads(ln)
                rows += 1
                errs += 1 if d.get("error") else 0
                bad += 1 if d.get("plan_as_intended") is False else 0
                first, last = first or d["timestamp"], d["timestamp"]
    print(f"rows written: {rows} / {expected} ({100 * rows / expected:.1f}%); errors/timeouts: {errs}; plan_as_intended=false: {bad}")
    if rows > 1:
        el = (datetime.fromisoformat(last) - datetime.fromisoformat(first)).total_seconds()
        print(f"first {first}, last {last}; elapsed {el / 3600:.2f} h; rough ETA {el / rows * (expected - rows) / 3600:.2f} h more")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--build-filters", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.build_filters:
        build_filters()
    elif a.status:
        status()
    else:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        run(selftest=a.selftest)
