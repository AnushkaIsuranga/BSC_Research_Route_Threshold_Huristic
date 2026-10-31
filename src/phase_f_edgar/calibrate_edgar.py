"""Phase F Task 3 (Amendment 11 section 3): calibration of policy_v3.1 on edgar_chunks. No paid call.

  python -m src.phase_f_edgar.calibrate_edgar run --out-dir outputs/edgar_calibration_2026-11-01
  python -m src.phase_f_edgar.calibrate_edgar analyze --out-dir outputs/edgar_calibration_2026-11-01

run: grid filters (cik IN sets, random.Random(20261102), recorded), quiet-rule start check (Addendum 2; three refusals 5 min
apart stop), pre-flight plain EXPLAIN of every cell x route, exact top-15 ground truth per (cell, vector), then the D2 session:
per (cell, vector, route) one normal execution (rows, recall@15, recall@10), one warm-up, 5 timed EXPLAIN (ANALYZE) Execution
Times, median, Addendum 1 early stop; routes exact, default iterative, tuned iterative, probe; order shuffled with
random.Random(20261102). Resumable (existing keys skipped).
analyze: guard derivation (as Amendment 9: iterative < k rows -> exact rows, latency iterative + exact), pass rule with
recall@15, policy_v3.calibrate() twice (default / tuned) -> config/policy_v3_1_edgar.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import time
from datetime import datetime, timezone

from src import PROJECT_ROOT
from src.phase_e_router import policy_v3 as P
from src.phase_e_router import retriever as R
from src.phase_e_router.cells import env_meta
from src.phase_f_edgar import session_tools as S

SEED = 20261102
K = 15
TIMED = 5
EARLY_STOP_MS = 1500.0      # Addendum 1: 3 x L; median of the first 2 timed repetitions
ROUTES = [R.R_EXACT, R.R_ITER, R.R_ITER_TUNED, R.R_PROBE]
TABLE = "edgar_chunks"
CONFIG = "config/router_edgar.json"
POLICY = "config/policy_v3_1_edgar.json"
HM_POLICY = "config/policy_v3_hm.json"
CALIB_QUERIES = "outputs/edgar_eval_set_2026-11-01/calibration_queries.csv"


def build_grid_filters(cik_rows: dict, grid: list, n_total: int, seed: int = SEED) -> list[dict]:
    """One cik IN (...) filter per grid point. CIKs sorted, shuffled once per grid point with one generator (grid order), then
    walked in that order, adding a CIK whenever it brings the matched row count closer to s x n_total."""
    rng = random.Random(seed)
    ciks = sorted(cik_rows)
    out = []
    for i, s in enumerate(grid):
        order = list(ciks)
        rng.shuffle(order)
        target, chosen, total = s * n_total, [], 0
        for c in order:
            if abs(total + cik_rows[c] - target) < abs(total - target):
                chosen.append(c)
                total += cik_rows[c]
        if not chosen:
            raise SystemExit(f"grid point {s}: no CIK set found")
        out.append({"filter_id": f"g{i:02d}", "grid_s": s, "target_rows": target, "matched_rows": total, "selectivity": total / n_total,
                    "n_ciks": len(chosen), "conditions": [["cik", sorted(chosen)]]})
    return out


def per_vector(by, fid, qid, variant):
    """(recall15, latency, rows, guard_fired, recall10) for exact / iter / iter_guard / tuned / tuned_guard (Amendment 9 D2)."""
    ex = by[(fid, qid, R.R_EXACT)]
    if variant == "exact":
        return ex["recall15"], ex["latency_ms"], ex["rows_returned"], False, ex["recall10"]
    it = by[(fid, qid, R.R_ITER if variant.startswith("iter") else R.R_ITER_TUNED)]
    if variant in ("iter", "tuned") or it["rows_returned"] >= K:
        return it["recall15"], it["latency_ms"], it["rows_returned"], False, it["recall10"]
    return ex["recall15"], it["latency_ms"] + ex["latency_ms"], ex["rows_returned"], True, ex["recall10"]


def early_flag(by, fid, qid, variant) -> bool:
    ex = by[(fid, qid, R.R_EXACT)]
    if variant == "exact":
        return bool(ex.get("early_stop"))
    it = by[(fid, qid, R.R_ITER if variant.startswith("iter") else R.R_ITER_TUNED)]
    fired = variant.endswith("guard") and it["rows_returned"] < K
    return bool(it.get("early_stop")) or (fired and bool(ex.get("early_stop")))


def run(a):
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    cfg = R.RouterConfig.load(CONFIG)
    if cfg["k"] != K:
        raise SystemExit("config k differs from 15")
    qids = [r["qid"] for r in csv.DictReader(open(PROJECT_ROOT / CALIB_QUERIES, encoding="utf-8", newline=""))]
    if len(qids) != 20:
        raise SystemExit(f"{len(qids)} calibration questions, expected 20")
    vecs = S.load_question_vectors()
    conn = R.connect()
    R.configure_session(conn, cfg)

    fpath = out / "grid_filters.json"
    if fpath.exists():
        filters = json.loads(fpath.read_text(encoding="utf-8"))
    else:
        grid = json.loads((PROJECT_ROOT / HM_POLICY).read_text(encoding="utf-8"))["grid"]
        with conn.cursor() as cur:
            cur.execute(f"SELECT cik, count(*) FROM {TABLE} GROUP BY cik")
            cik_rows = dict(cur.fetchall())
            cur.execute(f"SELECT count(*) FROM {TABLE}")
            (n_total,) = cur.fetchone()
        conn.commit()
        filters = build_grid_filters(cik_rows, grid, n_total)
        for f in filters:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {TABLE} WHERE cik = ANY(%s)", (f["conditions"][0][1],))
                if cur.fetchone()[0] != f["matched_rows"]:
                    raise SystemExit(f"{f['filter_id']}: matched rows differ on recount")
            conn.commit()
        S.write_json(fpath, filters)
    fmap = {f["filter_id"]: f for f in filters}
    for f in filters:
        print(f"{f['filter_id']}: grid {f['grid_s']:.6f} achieved {f['selectivity']:.6f} ({f['matched_rows']} rows, {f['n_ciks']} CIKs)")

    q = S.quiet_start(out)
    qv0 = R.vec_literal(vecs[qids[0]])
    if not (out / "preflight.json").exists():
        checks = []
        for f in filters:
            for route in ROUTES:
                plan = R.explain_route(conn, route, TABLE, f["conditions"], K, qv0, cfg)
                checks.append({"filter_id": f["filter_id"], **R.check_plan(route, plan, cfg)})
        failed = [c for c in checks if c["ok"] is False]
        S.write_json(out / ("preflight.json" if not failed else "preflight_failed.json"),
                     {"checked_utc": datetime.now(timezone.utc).isoformat(), "n_checks": len(checks), "n_failed": len(failed),
                      "failures": failed, "checks": checks})
        if failed:
            raise SystemExit(f"pre-flight failed: {failed[:3]}")

    gpath = out / "ground_truth.json"
    if gpath.exists():
        gt = {tuple(k.split("|")): v for k, v in json.loads(gpath.read_text(encoding="utf-8")).items()}
    else:
        gt = {(f["filter_id"], qid): S.exact_topk(conn, TABLE, f["conditions"], K, R.vec_literal(vecs[qid]), cfg)
              for f in filters for qid in qids}
        S.write_json(gpath, {f"{a_}|{b_}": v for (a_, b_), v in gt.items()})

    rnd = random.Random(SEED)
    items = []
    f_order = [f["filter_id"] for f in filters]
    rnd.shuffle(f_order)
    for fid in f_order:
        v_order = list(qids)
        rnd.shuffle(v_order)
        for qid in v_order:
            r_order = list(ROUTES)
            rnd.shuffle(r_order)
            items.extend((fid, qid, r) for r in r_order)
    sched_sha = hashlib.sha256(json.dumps(items).encode()).hexdigest()
    results = out / "results.jsonl"
    done = set()
    if results.exists():
        for ln in results.read_text(encoding="utf-8").splitlines():
            d = json.loads(ln)
            done.add((d["filter_id"], d["qid"], d["route"]))
    meta_path = out / "run_meta.json"
    if not meta_path.exists():
        S.write_json(meta_path, {**env_meta(conn), "amendment": "docs/preregistration/PHASE_F_AMENDMENT_11.md", "seed": SEED, "k": K,
                                 "timed_repeats": TIMED, "routes": ROUTES, "route_settings": {r: R.route_settings(r, cfg) for r in ROUTES},
                                 "calibration_qids": qids, "schedule_sha256": sched_sha, "n_items": len(items), "quiet_check": q,
                                 "config": cfg.raw})
    else:
        with open(out / "resumes.jsonl", "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "already_done": len(done), "quiet_check": q,
                                 "schedule_sha256": sched_sha}, default=str) + "\n")
    loads = S.LoadLogger(out / f"host_load_{int(time.time())}.json")
    loads.sample("start")
    loads.start()
    R.run_route(conn, R.R_PROBE, TABLE, filters[0]["conditions"], K, qv0, cfg)        # untimed table warm-up
    R.run_route(conn, R.R_EXACT, TABLE, filters[0]["conditions"], K, qv0, cfg)
    t_start, n_new = time.time(), 0
    with open(results, "a", encoding="utf-8", newline="\n") as fh:
        for i, (fid, qid, route) in enumerate(items):
            if (fid, qid, route) in done:
                continue
            cond, qv = fmap[fid]["conditions"], R.vec_literal(vecs[qid])
            row = {"filter_id": fid, "selectivity": fmap[fid]["selectivity"], "qid": qid, "route": route, "seed": SEED, "error": None}
            try:
                rows, wall = R.run_route(conn, route, TABLE, cond, K, qv, cfg)
                if route == R.R_PROBE:
                    row.update({"probe_p": sum(1 for _, ok in rows if ok), "probe_m": len(rows)})
                else:
                    ids = [r_[0] for r_ in rows]
                    truth = gt[(fid, qid)]
                    row.update({"rows_returned": len(ids), "recall15": S.recall_at(ids, truth, 15), "recall10": S.recall_at(ids, truth, 10),
                                "ids": ids})
                row["normal_wall_ms"] = round(wall, 3)
                R.explain_route(conn, route, TABLE, cond, K, qv, cfg, analyze=True)                       # warm-up
                times, plan, early = [], None, False
                for rep in range(TIMED):
                    plan = R.explain_route(conn, route, TABLE, cond, K, qv, cfg, analyze=True)
                    times.append(plan["Execution Time"])
                    if rep == 1 and statistics.median(times) > EARLY_STOP_MS:          # Addendum 1
                        early = True
                        break
                chk = R.check_plan(route, plan, cfg)
                row.update({"latency_ms": statistics.median(times), "latency_raw_ms": times, "early_stop": early,
                            "plan_nodes": chk["plan_nodes"], "scan_node": chk["scan_node"], "index_used": chk["index_used"],
                            "plan_as_intended": chk["ok"]})
            except Exception as e:
                conn.rollback()
                row["error"] = repr(e)
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            n_new += 1
            if n_new % 100 == 0:
                print(f"{i + 1}/{len(items)} items, {n_new} new in {(time.time() - t_start) / 60:.1f} min", flush=True)
    loads.stop_evt.set()
    loads.sample("end")
    print(f"done: {n_new} new rows in {(time.time() - t_start) / 60:.1f} min")


def analyze(a):
    out = PROJECT_ROOT / a.out_dir
    cfg = R.RouterConfig.load(CONFIG)
    filters = json.loads((out / "grid_filters.json").read_text(encoding="utf-8"))
    qids = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))["calibration_qids"]
    rows = [json.loads(ln) for ln in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    errs = [r for r in rows if r["error"] or r.get("plan_as_intended") is False]
    by = {(r["filter_id"], r["qid"], r["route"]): r for r in rows}
    expected = len(filters) * len(qids) * len(ROUTES)
    if len(by) != expected or errs:
        raise SystemExit(f"incomplete or invalid session: {len(by)}/{expected} rows, {len(errs)} errors/plan mismatches: {errs[:2]}")
    variants = ["exact", "iter", "iter_guard", "tuned", "tuned_guard"]
    cells, csv_rows = [], []
    for f in filters:
        fid, s = f["filter_id"], f["selectivity"]
        rec = {"table": TABLE, "filter_id": fid, "s": s, "grid_s": f["grid_s"]}
        for v in variants:
            pv = [per_vector(by, fid, qid, v) for qid in qids]
            res = P.cell_passes([p[0] for p in pv], [p[1] for p in pv], recall_target=cfg["recall_target"],
                                latency_limit_ms=cfg["latency_limit_ms"])
            rec[v] = {**res, "mean_recall10": statistics.fmean(p[4] for p in pv), "underfill": sum(1 for p in pv if p[2] < K),
                      "guard_fired": sum(1 for p in pv if p[3]), "early_stop_vectors": sum(early_flag(by, fid, qid, v) for qid in qids)}
        probes = [by[(fid, qid, R.R_PROBE)] for qid in qids]
        rec["probe"] = {"n_p_below_k": sum(1 for p in probes if p["probe_p"] < K),
                        "median_latency_ms": statistics.median(p["latency_ms"] for p in probes)}
        cells.append(rec)
        csv_rows.append({"filter_id": fid, "grid_s": round(f["grid_s"], 6), "s": round(s, 6), "matched_rows": f["matched_rows"],
                         "n_ciks": f["n_ciks"], **{f"{v}_recall15": round(rec[v]["mean_recall"], 4) for v in variants},
                         **{f"{v}_recall10": round(rec[v]["mean_recall10"], 4) for v in variants},
                         **{f"{v}_ms": round(rec[v]["median_latency_ms"], 2) for v in variants},
                         **{f"{v}_pass": rec[v]["passed"] for v in variants},
                         **{f"{v}_early_stop": rec[v]["early_stop_vectors"] for v in variants},
                         "iter_underfill": rec["iter"]["underfill"], "tuned_underfill": rec["tuned"]["underfill"],
                         "iter_guard_fired": rec["iter_guard"]["guard_fired"], "tuned_guard_fired": rec["tuned_guard"]["guard_fired"],
                         "probe_n_p_below_k": rec["probe"]["n_p_below_k"], "probe_ms": round(rec["probe"]["median_latency_ms"], 3)})
    cal = {}
    for name, it in (("T_default", "iter_guard"), ("T_tuned", "tuned_guard")):
        cal[name] = P.calibrate([{"table": TABLE, "s": c["s"], "exact_pass": c["exact"]["passed"], "iter_pass": c[it]["passed"]}
                                 for c in cells])
    with open(out / "cell_summary.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(csv_rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(csv_rows)
    S.write_json(out / "cells.json", cells)
    plans = {"exact_routes_without_hnsw": sum(1 for r in rows if r["route"] == R.R_EXACT and r["plan_as_intended"]),
             "iterative_routes_on_hnsw": sum(1 for r in rows if r["route"] in (R.R_ITER, R.R_ITER_TUNED) and r["plan_as_intended"]),
             "probe_routes_on_hnsw": sum(1 for r in rows if r["route"] == R.R_PROBE and r["plan_as_intended"]),
             "plan_mismatches": sum(1 for r in rows if r.get("plan_as_intended") is False),
             "index_used_by_route": {rt: sorted({str(r["index_used"]) for r in rows if r["route"] == rt}) for rt in ROUTES},
             "scan_nodes_by_route": {rt: sorted({str(r["scan_node"]) for r in rows if r["route"] == rt}) for rt in ROUTES}}
    S.write_json(out / "plan_checks.json", plans)
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    policy = {"_note": "policy_v3.1 on edgar_chunks, calibrated under Amendment 11 section 3 (src.phase_f_edgar.calibrate_edgar).",
              "T_default": cal["T_default"]["T"], "T_tuned": cal["T_tuned"]["T"], "R": cfg["recall_target"], "L_ms": cfg["latency_limit_ms"],
              "k": K, "recall_metric": "recall@15", "ef_search": cfg["ef_search"], "grid_hm": [f["grid_s"] for f in filters],
              "grid_achieved": cal["T_default"]["grid"], "calibration_default": cal["T_default"], "calibration_tuned": cal["T_tuned"],
              "T_hm": json.loads((PROJECT_ROOT / HM_POLICY).read_text(encoding="utf-8"))["T_default"],
              "inputs": {"session": (out / "results.jsonl").relative_to(PROJECT_ROOT).as_posix(), "session_git_commit": meta["git_commit"],
                         "session_started_utc": meta["started_utc"]},
              "calibrated_utc": datetime.now(timezone.utc).isoformat(), "amendment": "docs/preregistration/PHASE_F_AMENDMENT_11.md"}
    (PROJECT_ROOT / POLICY).write_text(json.dumps(policy, indent=1) + "\n", encoding="utf-8", newline="\n")
    S.write_json(out / "calibration.json", cal)
    for name in ("T_default", "T_tuned"):
        c = cal[name]["pooled"]
        print(f"{name}: interval ({c['lower']}, {c['upper']}] empty={c['empty']} T={c['T']} ({c['T_rule']})")
    print(json.dumps(plans, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "analyze"])
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    run(a) if a.cmd == "run" else analyze(a)
