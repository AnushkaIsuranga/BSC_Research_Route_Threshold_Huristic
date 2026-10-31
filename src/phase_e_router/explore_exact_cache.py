"""Exploratory, not pre-registered (changes no T or verdict): forced-exact only on the in-sample cells at s = 0.0478 (lo4)
and 0.1061 (lo5), all five tables, vectors 0-19, no other route in the session. Tests whether tuned-iterative runs in the
mixed D2 session evicted the cache and slowed exact.

Per (table, filter, vector): one normal execution (rows, recall), one warm-up, 5 timed EXPLAIN (ANALYZE, BUFFERS)
Execution Times (median; Addendum 1 early stop kept), shared-buffer hits/reads of every timed repetition. Per table one
untimed exact query first (the calibration session also ran one unfiltered ANN query; omitted here, exact only).

  python -m src.phase_e_router.explore_exact_cache run
  python -m src.phase_e_router.explore_exact_cache analyze
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone

from src import PROJECT_ROOT
from src.phase_e_router import retriever as R
from src.phase_e_router.calibrate_v3 import OUT as CAL_OUT, STORED, LoadLogger
from src.phase_e_router.cells import env_meta, load_filters, load_ground_truth, load_vectors, quiet_check, recall, vector_indices

OUT = PROJECT_ROOT / "outputs" / "phase_e_exploratory_exact_cache_2026-10-31"
SEED = 20261101
K = 10
TIMED = 5
EARLY_STOP_MS = 1500.0
FILTERS = ["lo4", "lo5"]
BUF_KEYS = ("Shared Hit Blocks", "Shared Read Blocks")


def schedule(tables):
    rnd = random.Random(SEED)
    items = []
    t_order = list(tables)
    rnd.shuffle(t_order)
    for t in t_order:
        cells = [(fid, vi) for fid in FILTERS for vi in vector_indices("in_sample")]
        rnd.shuffle(cells)
        items.extend((t, fid, vi) for fid, vi in cells)
    return items


def run(args):
    OUT.mkdir(parents=True, exist_ok=True)
    results = OUT / "results.jsonl"
    if results.exists():
        raise SystemExit(f"{results} exists; the check is run once")
    cfg = R.RouterConfig.load()
    q = quiet_check()
    print("quiet check:", q, flush=True)
    if not q["quiet"]:
        (OUT / "quiet_check_refused.json").write_text(json.dumps(q, indent=1), encoding="utf-8")
        raise SystemExit("machine is not quiet (Amendment 9 Addendum 2): session not started")
    conn = R.connect()
    R.configure_session(conn, cfg)
    fmap = {f["filter_id"]: f for f in load_filters("in_sample")}
    vectors, vsha = load_vectors(20)
    gt = load_ground_truth()
    items = schedule(cfg["tables"])
    (OUT / "run_meta.json").write_text(json.dumps({**env_meta(conn), "label": "exploratory, not pre-registered", "seed": SEED,
                                                   "filters": FILTERS, "timed_repeats": TIMED, "route": R.R_EXACT,
                                                   "route_settings": R.route_settings(R.R_EXACT, cfg),
                                                   "vectors_sha256_lines_0_19": vsha, "n_items": len(items),
                                                   "quiet_check": q}, indent=1), encoding="utf-8")
    loads = LoadLogger(OUT / "host_load.json", every_s=60)
    loads.sample("start")
    loads.start()
    warmed = set()
    t0 = time.time()
    with open(results, "w", encoding="utf-8") as out:
        for table, fid, vi in items:
            qv, cond = R.vec_literal(vectors[vi]), fmap[fid]["conditions"]
            if table not in warmed:
                R.run_route(conn, R.R_EXACT, table, cond, K, qv, cfg)          # one filtered query (untimed)
                warmed.add(table)
                loads.sample(f"table_start {table}")
            row = {"table": table, "filter_id": fid, "selectivity": fmap[fid]["selectivity"], "vector_idx": vi, "error": None}
            try:
                rows, wall = R.run_route(conn, R.R_EXACT, table, cond, K, qv, cfg)
                ids = [r[0] for r in rows]
                row.update({"rows_returned": len(ids), "recall": recall(ids, gt[(table, fid, vi)]), "normal_wall_ms": round(wall, 3)})
                R.explain_route(conn, R.R_EXACT, table, cond, K, qv, cfg, analyze=True)        # warm-up
                times, bufs, plan, early = [], [], None, False
                for rep in range(TIMED):
                    plan = R.explain_route(conn, R.R_EXACT, table, cond, K, qv, cfg, analyze=True)
                    times.append(plan["Execution Time"])
                    bufs.append({k: plan["Plan"].get(k) for k in BUF_KEYS})
                    if rep == 1 and statistics.median(times) > EARLY_STOP_MS:
                        early = True
                        break
                chk = R.check_plan(R.R_EXACT, plan, cfg)
                row.update({"latency_ms": statistics.median(times), "latency_raw_ms": times, "buffers": bufs,
                            "early_stop": early, "plan_nodes": chk["plan_nodes"], "plan_as_intended": chk["ok"]})
            except Exception as e:
                conn.rollback()
                row["error"] = repr(e)
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            out.write(json.dumps(row) + "\n")
            out.flush()
    loads.stop_evt.set()
    loads.sample("end")
    print(f"done: {len(items)} rows in {(time.time() - t0) / 60:.1f} min")


def analyze(args):
    rows = [json.loads(ln) for ln in (OUT / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    bad = [r for r in rows if r["error"] or not r.get("plan_as_intended")]
    if bad or len(rows) != 200:
        raise SystemExit(f"incomplete or invalid: {len(rows)} rows, {len(bad)} errors/plan mismatches")
    cal = {}
    for ln in (CAL_OUT / "results.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(ln)
        if d["route"] == R.R_EXACT and d["filter_id"] in FILTERS:
            cal[(d["table"], d["filter_id"], d["vector_idx"])] = d["latency_ms"]
    stored = {}
    with open(PROJECT_ROOT / STORED["in_sample"], encoding="utf-8") as f:
        for ln in f:
            d = json.loads(ln)
            if d["arm"] == "forced-exact" and d["filter_id"] in FILTERS:
                stored[(d["table"], d["filter_id"], d["vector_idx"])] = d["latency_ms"]
    by_cell = defaultdict(list)
    for r in rows:
        by_cell[(r["table"], r["filter_id"])].append(r)
    out = []
    for (t, fid), rs in sorted(by_cell.items()):
        keys = [(t, fid, r["vector_idx"]) for r in rs]
        new = [r["latency_ms"] for r in rs]
        hits = [b["Shared Hit Blocks"] for r in rs for b in r["buffers"]]
        reads = [b["Shared Read Blocks"] for r in rs for b in r["buffers"]]
        out.append({"table": t, "filter_id": fid, "s": round(rs[0]["selectivity"], 4),
                    "exploratory_ms": round(statistics.median(new), 1),
                    "calibration_ms": round(statistics.median(cal[k] for k in keys), 1),
                    "stored_ms": round(statistics.median(stored[k] for k in keys), 1),
                    "vectors_faster_than_calibration": sum(1 for r, k in zip(rs, keys) if r["latency_ms"] < cal[k]),
                    "mean_recall": round(statistics.fmean(r["recall"] for r in rs), 4),
                    "median_shared_hit": statistics.median(hits), "median_shared_read": statistics.median(reads),
                    "hit_ratio": round(sum(hits) / (sum(hits) + sum(reads)), 4)})
    with open(OUT / "cell_comparison.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    for o in out:
        print(o)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "analyze"])
    a = ap.parse_args()
    {"run": run, "analyze": analyze}[a.cmd](a)
