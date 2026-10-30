"""Amendment 9, Task 3: the quiet in-sample calibration session (D2) and the calibration procedure.

  python -m src.phase_e_router.calibrate_v3 run       # live session: exact, default iterative, tuned iterative, probe
  python -m src.phase_e_router.calibrate_v3 analyze   # guard derivation, pass status, calibrate twice -> config/policy_v3_hm.json

Session (per table x filter x vector x route; nested order shuffled with random.Random(20261030)): one normal execution
(rows, recall vs outputs/ground_truth_hm), one untimed warm-up, 5 timed EXPLAIN (ANALYZE) Execution Times, median.
Guard results are derived from the same session: if an iterative route returned < k rows, its rows/recall are the exact
route's for that vector and its latency = iterative median + exact median. Resumable (existing keys skipped).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

from src import PROJECT_ROOT
from src.phase_e_router import policy_v3 as P
from src.phase_e_router import retriever as R
from src.phase_e_router.cells import (env_meta, host_load, load_filters, load_ground_truth, load_vectors, quiet_check,
                                      recall, vector_indices)

OUT = PROJECT_ROOT / "outputs" / "phase_e_calibration_hm_2026-10-30"
SEED = 20261030
K = 10
TIMED = 5
ROUTES = [R.R_EXACT, R.R_ITER, R.R_ITER_TUNED, R.R_PROBE]
STORED = {"in_sample": "outputs/phase_a_arms/results.jsonl"}


def schedule(tables, filters, vectors):
    rnd = random.Random(SEED)
    items = []
    t_order = list(tables)
    rnd.shuffle(t_order)
    for t in t_order:
        f_order = [f["filter_id"] for f in filters]
        rnd.shuffle(f_order)
        for fid in f_order:
            v_order = list(vectors)
            rnd.shuffle(v_order)
            for vi in v_order:
                r_order = list(ROUTES)
                rnd.shuffle(r_order)
                items.extend((t, fid, vi, r) for r in r_order)
    return items


def preflight(conn, cfg, filters, qv0):
    checks = []
    for t in cfg["tables"]:
        for f in filters:
            for route in ROUTES:
                plan = R.explain_route(conn, route, t, f["conditions"], K, qv0, cfg)
                checks.append({"table": t, "filter_id": f["filter_id"], **R.check_plan(route, plan, cfg)})
    failed = [c for c in checks if c["ok"] is False]
    return {"checked_utc": datetime.now(timezone.utc).isoformat(), "vector_idx": 0, "n_checks": len(checks),
            "n_failed": len(failed), "all_passed": not failed, "failures": failed, "checks": checks}


class LoadLogger(threading.Thread):
    def __init__(self, path, every_s=300):
        super().__init__(daemon=True)
        self.path, self.every, self.stop_evt, self.samples = path, every_s, threading.Event(), []

    def sample(self, tag):
        try:
            s = host_load()
        except Exception as e:                                    # recorded, never silently dropped
            s = {"utc": datetime.now(timezone.utc).isoformat(), "error": repr(e)}
        s["tag"] = tag
        self.samples.append(s)
        self.path.write_text(json.dumps(self.samples, indent=1), encoding="utf-8")

    def run(self):
        while not self.stop_evt.wait(self.every):
            self.sample("periodic")


def run(args):
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = R.RouterConfig.load()
    q = quiet_check()
    print("quiet check:", q, flush=True)
    if not q["quiet"]:
        (OUT / "quiet_check_refused.json").write_text(json.dumps(q, indent=1), encoding="utf-8")
        raise SystemExit("machine is not quiet (Amendment 9): session not started")
    conn = R.connect()
    R.configure_session(conn, cfg)
    filters = load_filters("in_sample")
    fmap = {f["filter_id"]: f for f in filters}
    vectors, vsha = load_vectors(20)
    gt = load_ground_truth()
    pf = preflight(conn, cfg, filters, R.vec_literal(vectors[0]))
    if not pf["all_passed"]:
        (OUT / "preflight_failed.json").write_text(json.dumps(pf, indent=1), encoding="utf-8")
        raise SystemExit(f"pre-flight failed: {pf['failures'][:3]}")
    results = OUT / "results.jsonl"
    done = set()
    if results.exists():
        for ln in results.read_text(encoding="utf-8").splitlines():
            d = json.loads(ln)
            done.add((d["table"], d["filter_id"], d["vector_idx"], d["route"]))
    items = schedule(cfg["tables"], filters, vector_indices("in_sample"))
    sched_sha = hashlib.sha256(json.dumps(items).encode()).hexdigest()
    meta_path = OUT / "run_meta.json"
    if not meta_path.exists():
        (OUT / "preflight.json").write_text(json.dumps(pf, indent=1), encoding="utf-8")
        meta_path.write_text(json.dumps({**env_meta(conn), "seed": SEED, "k": K, "timed_repeats": TIMED, "routes": ROUTES,
                                         "route_settings": {r: R.route_settings(r, cfg) for r in ROUTES},
                                         "vectors_sha256_lines_0_19": vsha, "schedule_sha256": sched_sha,
                                         "n_items": len(items), "quiet_check": q, "config": cfg.raw}, indent=1), encoding="utf-8")
    else:
        with open(OUT / "resumes.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "already_done": len(done), "quiet_check": q,
                                "git_commit": env_meta(conn)["git_commit"], "schedule_sha256": sched_sha}) + "\n")
    loads = LoadLogger(OUT / "host_load.json" if not (OUT / "host_load.json").exists() else OUT / f"host_load_resume_{int(time.time())}.json")
    loads.sample("start")
    loads.start()
    warmed = set()
    t_start = time.time()
    n_new = 0
    with open(results, "a", encoding="utf-8") as out:
        for i, (table, fid, vi, route) in enumerate(items):
            if (table, fid, vi, route) in done:
                continue
            qv = R.vec_literal(vectors[vi])
            cond = fmap[fid]["conditions"]
            if table not in warmed:
                R.run_route(conn, R.R_PROBE, table, cond, K, qv, cfg)          # unfiltered ANN (untimed)
                R.run_route(conn, R.R_EXACT, table, cond, K, qv, cfg)          # one filtered query (untimed)
                warmed.add(table)
                loads.sample(f"table_start {table}")
            row = {"table": table, "filter_id": fid, "selectivity": fmap[fid]["selectivity"], "vector_idx": vi, "route": route,
                   "seed": SEED, "error": None}
            try:
                rows, wall = R.run_route(conn, route, table, cond, K, qv, cfg)
                if route == R.R_PROBE:
                    row.update({"probe_p": sum(1 for _, ok in rows if ok), "probe_m": len(rows)})
                else:
                    ids = [r[0] for r in rows]
                    row.update({"rows_returned": len(ids), "recall": recall(ids, gt[(table, fid, vi)]), "ids": ids})
                row["normal_wall_ms"] = round(wall, 3)
                R.explain_route(conn, route, table, cond, K, qv, cfg, analyze=True)                  # warm-up
                times, plan = [], None
                for _ in range(TIMED):
                    plan = R.explain_route(conn, route, table, cond, K, qv, cfg, analyze=True)
                    times.append(plan["Execution Time"])
                chk = R.check_plan(route, plan, cfg)
                row.update({"latency_ms": statistics.median(times), "latency_raw_ms": times, "plan_nodes": chk["plan_nodes"],
                            "scan_node": chk["scan_node"], "index_used": chk["index_used"], "plan_as_intended": chk["ok"]})
            except Exception as e:
                conn.rollback()
                row["error"] = repr(e)
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            out.write(json.dumps(row) + "\n")
            out.flush()
            n_new += 1
            if n_new % 200 == 0:
                el = time.time() - t_start
                print(f"{i + 1}/{len(items)} items, {n_new} new in {el / 60:.1f} min", flush=True)
    loads.stop_evt.set()
    loads.sample("end")
    print(f"done: {n_new} new rows in {(time.time() - t_start) / 60:.1f} min")


# ------------------------------------------------------------------ analysis

def _stored_cells():
    acc = defaultdict(list)
    with open(PROJECT_ROOT / STORED["in_sample"], encoding="utf-8") as f:
        for ln in f:
            d = json.loads(ln)
            if d["arm"] in ("forced-exact", "iterative-relaxed"):
                acc[(d["table"], d["filter_id"], d["arm"])].append(d)
    out = {}
    for key, rows in acc.items():
        out[key] = {"mean_recall": statistics.fmean(r["recall"] for r in rows),
                    "median_latency_ms": statistics.median(r["latency_ms"] for r in rows),
                    "underfill": sum(1 for r in rows if r["rows_returned"] < K)}
    return out


def per_vector(rows_by_key, table, fid, vi, variant):
    """(recall, latency, rows, guard_fired) for variant in exact / iter / iter_guard / tuned / tuned_guard."""
    ex = rows_by_key[(table, fid, vi, R.R_EXACT)]
    if variant == "exact":
        return ex["recall"], ex["latency_ms"], ex["rows_returned"], False
    it = rows_by_key[(table, fid, vi, R.R_ITER if variant.startswith("iter") else R.R_ITER_TUNED)]
    if variant in ("iter", "tuned") or it["rows_returned"] >= K:
        return it["recall"], it["latency_ms"], it["rows_returned"], False
    return ex["recall"], it["latency_ms"] + ex["latency_ms"], ex["rows_returned"], True


def analyze(args):
    cfg = R.RouterConfig.load()
    rows = [json.loads(ln) for ln in (OUT / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    errs = [r for r in rows if r["error"] or r.get("plan_as_intended") is False]
    by = {(r["table"], r["filter_id"], r["vector_idx"], r["route"]): r for r in rows}
    filters = load_filters("in_sample")
    expected = len(cfg["tables"]) * len(filters) * 20 * len(ROUTES)
    if len(by) != expected or errs:
        raise SystemExit(f"incomplete or invalid session: {len(by)}/{expected} rows, {len(errs)} errors/plan mismatches")
    stored = _stored_cells()
    variants = ["exact", "iter", "iter_guard", "tuned", "tuned_guard"]
    cells, csv_rows = [], []
    for t in cfg["tables"]:
        for f in filters:
            fid, s = f["filter_id"], f["selectivity"]
            rec = {"table": t, "filter_id": fid, "s": s}
            for v in variants:
                pv = [per_vector(by, t, fid, vi, v) for vi in vector_indices("in_sample")]
                res = P.cell_passes([p[0] for p in pv], [p[1] for p in pv], recall_target=cfg["recall_target"],
                                    latency_limit_ms=cfg["latency_limit_ms"])
                rec[v] = {**res, "underfill": sum(1 for p in pv if p[2] < K), "guard_fired": sum(1 for p in pv if p[3])}
            probes = [by[(t, fid, vi, R.R_PROBE)] for vi in vector_indices("in_sample")]
            rec["probe"] = {"p": [p["probe_p"] for p in probes], "n_p_below_k": sum(1 for p in probes if p["probe_p"] < K),
                            "median_latency_ms": statistics.median(p["latency_ms"] for p in probes)}
            rec["stored"] = {"exact": stored[(t, fid, "forced-exact")], "iter": stored[(t, fid, "iterative-relaxed")]}
            cells.append(rec)
            csv_rows.append({"table": t, "filter_id": fid, "s": round(s, 6),
                             **{f"{v}_recall": round(rec[v]["mean_recall"], 4) for v in variants},
                             **{f"{v}_ms": round(rec[v]["median_latency_ms"], 2) for v in variants},
                             **{f"{v}_pass": rec[v]["passed"] for v in variants},
                             "iter_underfill": rec["iter"]["underfill"], "tuned_underfill": rec["tuned"]["underfill"],
                             "stored_exact_ms": round(rec["stored"]["exact"]["median_latency_ms"], 2),
                             "stored_iter_ms": round(rec["stored"]["iter"]["median_latency_ms"], 2),
                             "stored_iter_recall": round(rec["stored"]["iter"]["mean_recall"], 4),
                             "stored_iter_underfill": rec["stored"]["iter"]["underfill"],
                             "probe_n_p_below_k": rec["probe"]["n_p_below_k"], "probe_ms": round(rec["probe"]["median_latency_ms"], 3)})
    cal = {}
    for name, it in (("T_default", "iter_guard"), ("T_tuned", "tuned_guard")):
        cal[name] = P.calibrate([{"table": c["table"], "s": c["s"], "exact_pass": c["exact"]["passed"],
                                  "iter_pass": c[it]["passed"]} for c in cells])
    with open(OUT / "cell_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
        w.writeheader()
        w.writerows(csv_rows)
    (OUT / "cells.json").write_text(json.dumps(cells, indent=1), encoding="utf-8")
    meta = json.loads((OUT / "run_meta.json").read_text(encoding="utf-8"))
    policy = {"T_default": cal["T_default"]["T"], "T_tuned": cal["T_tuned"]["T"], "R": cfg["recall_target"],
              "L_ms": cfg["latency_limit_ms"], "k": K, "ef_search": cfg["ef_search"],
              "grid": cal["T_default"]["grid"], "calibration_default": cal["T_default"], "calibration_tuned": cal["T_tuned"],
              "reference_H&M_interval": [0.0478, 0.2038],
              "inputs": {"session": str((OUT / "results.jsonl").relative_to(PROJECT_ROOT).as_posix()),
                         "session_git_commit": meta["git_commit"], "session_started_utc": meta["started_utc"],
                         "machine": {"platform": meta["platform"], "server_settings": meta["server_settings"],
                                     "pg_version": meta["pg_version"], "pgvector_version": meta["pgvector_version"]}},
              "calibrated_utc": datetime.now(timezone.utc).isoformat(), "amendment": "docs/preregistration/PHASE_E_AMENDMENT_9.md"}
    (PROJECT_ROOT / "config" / "policy_v3_hm.json").write_text(json.dumps(policy, indent=1), encoding="utf-8")
    for name in ("T_default", "T_tuned"):
        c = cal[name]
        print(f"{name}: pooled {c['pooled']} ")
        for t, v in c["per_table"].items():
            print(f"   {t}: ({v['lower']}, {v['upper']}] T={v['T']:.5f} empty={v['empty']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "analyze"])
    a = ap.parse_args()
    run(a) if a.cmd == "run" else analyze(a)
