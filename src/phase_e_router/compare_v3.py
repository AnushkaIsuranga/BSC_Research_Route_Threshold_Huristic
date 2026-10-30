"""Amendment 9, Task 4: live comparison of all modes (retrieval only).

  python -m src.phase_e_router.compare_v3 llm --allow-paid --budget-usd 5   # llm_router decisions, one per held-out filter
  python -m src.phase_e_router.compare_v3 run [--sets ho1 ho2 in_sample]     # live session
  python -m src.phase_e_router.compare_v3 analyze

Per (cell, vector, mode): one normal retrieve() (rows, recall, trace), one warm-up, 5 timed retrieve() calls; latency =
end-to-end wall-clock median (estimate, count, probe, guard included). Sets in the order ho1, ho2, in_sample; within a set
tables, filters, vectors and modes shuffled with random.Random(20261031). llm_router runs on held-out cells only and only
from recorded decisions. Resumable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from src import PROJECT_ROOT
from src.phase_e_router import policy_v3 as P
from src.phase_e_router import retriever as R
from src.phase_e_router.calibrate_v3 import LoadLogger
from src.phase_e_router.cells import (SETS, env_meta, load_filters, load_ground_truth, load_vectors, quiet_check, recall,
                                      vector_indices)

OUT = PROJECT_ROOT / "outputs" / "phase_e_comparison_hm_2026-10-31"
SEED = 20261031
K = 10
TIMED = 5
SET_ORDER = ["ho1", "ho2", "in_sample"]
MODES = [m for m in R.MODES if m != "llm_router"]
ORACLE_CANDIDATES = ["always_exact", "always_iterative", "iterative_tuned", "default_hnsw", "retry_exact", "planner_iterative"]
LLM_MODEL = "gemini-3.8-flash"
LLM_USER = "Metadata filter to be applied: {filter}\nQuestion: find the 10 catalogue items most similar to the query item."
STORED_REF = {"ho1_original": "outputs/phase_a_holdout/results.jsonl", "ho1_rerun": "outputs/phase_a_holdout_rerun/results.jsonl",
              "ho2": "outputs/phase_a_holdout2/results.jsonl", "in_sample": "outputs/phase_a_arms/results.jsonl"}
STORED_ARM_TO_MODE = {"forced-exact": "always_exact", "forced-hnsw": "default_hnsw", "iterative-relaxed": "always_iterative"}


def describe(conditions) -> str:
    return " AND ".join(f"{c} = {v[0]!r}" if len(v) == 1 else f"{c} IN ({', '.join(repr(x) for x in v)})" for c, v in conditions)


# ------------------------------------------------------------------ llm decisions

def llm(args):
    from src.phase_b_router.router import NAIVE_INFORMED_ROUTER_SYSTEM, validate_naive_route
    from src.phase_d_validation.llm_client import load_generation_config, make_client
    out_path = OUT / "llm_decisions.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists; decisions are recorded once")
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_generation_config()
    client = make_client(LLM_MODEL, allow_paid=args.allow_paid, budget_usd=args.budget_usd, config=cfg)
    decisions = []
    for set_name in ("ho1", "ho2"):
        for f in load_filters(set_name):
            user = LLM_USER.format(filter=describe(f["conditions"]))
            resp = client.generate(NAIVE_INFORMED_ROUTER_SYSTEM, user, max_output_tokens=cfg["roles"]["router_max_output_tokens"],
                                   json_mode=True)
            data, err = validate_naive_route(resp.text)
            decisions.append({"set": set_name, "filter_id": f["filter_id"], "filter_key": R.filter_key(f["conditions"]),
                              "user_message": user, "raw": resp.text, "route": data["route"] if data else None,
                              "reason": data["reason"] if data else None, "parse_error": err, "latency_ms": resp.latency_ms,
                              "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens,
                              "thinking_tokens": resp.thinking_tokens, "cost_usd": resp.cost_usd,
                              "finish_reason": resp.finish_reason, "settings_used": resp.settings_used})
            print(f["filter_id"], decisions[-1]["route"], err or "", f"${resp.cost_usd:.5f}", flush=True)
    out_path.write_text(json.dumps({"model": LLM_MODEL, "system_prompt": NAIVE_INFORMED_ROUTER_SYSTEM,
                                    "system_prompt_sha256": hashlib.sha256(NAIVE_INFORMED_ROUTER_SYSTEM.encode()).hexdigest(),
                                    "budget_usd": args.budget_usd, "total_cost_usd": sum(d["cost_usd"] for d in decisions),
                                    "created_utc": datetime.now(timezone.utc).isoformat(), "decisions": decisions}, indent=1),
                        encoding="utf-8")


def load_llm_routes():
    p = OUT / "llm_decisions.json"
    if not p.exists():
        return None
    return {d["filter_key"]: d["route"] for d in json.loads(p.read_text(encoding="utf-8"))["decisions"]}


# ------------------------------------------------------------------ live session

def schedule(cfg, sets, llm_available):
    rnd = random.Random(SEED)
    items = []
    for set_name in sets:
        filters = load_filters(set_name)
        modes = MODES + (["llm_router"] if llm_available and set_name != "in_sample" else [])
        t_order = list(cfg["tables"])
        rnd.shuffle(t_order)
        for t in t_order:
            f_order = [f["filter_id"] for f in filters]
            rnd.shuffle(f_order)
            for fid in f_order:
                v_order = vector_indices(set_name)
                rnd.shuffle(v_order)
                for vi in v_order:
                    m_order = list(modes)
                    rnd.shuffle(m_order)
                    items.extend((set_name, t, fid, vi, m) for m in m_order)
    return items


def preflight(conn, cfg, sets, qv):
    checks = []
    for set_name in sets:
        for f in load_filters(set_name):
            for t in cfg["tables"]:
                for route in (R.R_EXACT, R.R_ITER, R.R_ITER_TUNED, R.R_HNSW, R.R_PROBE, R.R_PLANNER_ITER):
                    plan = R.explain_route(conn, route, t, f["conditions"], K, qv, cfg)
                    checks.append({"set": set_name, "table": t, "filter_id": f["filter_id"], **R.check_plan(route, plan, cfg)})
    failed = [c for c in checks if c["ok"] is False]
    return {"checked_utc": datetime.now(timezone.utc).isoformat(), "n_checks": len(checks), "n_failed": len(failed),
            "all_passed": not failed, "failures": failed, "checks": checks}


def _trace_small(tr):
    keep = ("decided", "band", "s_est", "plan_rows", "count", "count_cap", "probe_p", "router_route", "routes_executed",
            "route_ms", "estimate_ms", "count_ms", "probe_ms", "guard_triggered", "guard_added_ms", "rows_returned", "total_ms")
    return {k: tr[k] for k in keep if k in tr}


def run(args):
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = R.RouterConfig.load(require_policy=True)
    llm_routes = load_llm_routes()
    if llm_routes is not None:
        cfg.llm_routes = {k: v for k, v in llm_routes.items() if v is not None}
    q = quiet_check()
    print("quiet check:", q, flush=True)
    if not q["quiet"]:
        (OUT / f"quiet_check_refused_{int(time.time())}.json").write_text(json.dumps(q, indent=1), encoding="utf-8")
        raise SystemExit("machine is not quiet (Amendment 9): session not started")
    conn = R.connect()
    R.configure_session(conn, cfg)
    vectors, vsha = load_vectors(60)
    gt = load_ground_truth()
    sets = [s for s in SET_ORDER if s in args.sets]
    pf = preflight(conn, cfg, sets, R.vec_literal(vectors[0]))
    if not pf["all_passed"]:
        (OUT / "preflight_failed.json").write_text(json.dumps(pf, indent=1), encoding="utf-8")
        raise SystemExit(f"pre-flight failed: {pf['failures'][:3]}")
    fmaps = {s: {f["filter_id"]: f for f in load_filters(s)} for s in sets}
    items = schedule(cfg, sets, llm_routes is not None)
    results = OUT / "results.jsonl"
    done = set()
    if results.exists():
        for ln in results.read_text(encoding="utf-8").splitlines():
            d = json.loads(ln)
            done.add((d["set"], d["table"], d["filter_id"], d["vector_idx"], d["mode"]))
    sched_sha = hashlib.sha256(json.dumps(items).encode()).hexdigest()
    meta_path = OUT / "run_meta.json"
    if not meta_path.exists():
        (OUT / "preflight.json").write_text(json.dumps(pf, indent=1), encoding="utf-8")
        meta_path.write_text(json.dumps({**env_meta(conn), "seed": SEED, "k": K, "timed_repeats": TIMED, "sets": sets,
                                         "modes": MODES, "llm_router": llm_routes is not None, "T_default": cfg.T_default,
                                         "T_tuned": cfg.T_tuned, "vectors_sha256_lines_0_59": vsha, "schedule_sha256": sched_sha,
                                         "n_items": len(items), "quiet_check": q, "config": cfg.raw}, indent=1), encoding="utf-8")
    else:
        with open(OUT / "resumes.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "already_done": len(done), "quiet_check": q,
                                "sets": sets, "git_commit": env_meta(conn)["git_commit"], "schedule_sha256": sched_sha}) + "\n")
    loads = LoadLogger(OUT / f"host_load_{int(time.time())}.json")
    loads.sample("start")
    loads.start()
    warmed, t_start, n_new = set(), time.time(), 0
    with open(results, "a", encoding="utf-8") as out:
        for i, (set_name, table, fid, vi, mode) in enumerate(items):
            if (set_name, table, fid, vi, mode) in done:
                continue
            cond = fmaps[set_name][fid]["conditions"]
            qv = vectors[vi]
            if (set_name, table) not in warmed:
                R.retrieve(qv, cond, K, "default_hnsw", cfg, conn=conn, table=table)
                R.retrieve(qv, cond, K, "always_exact", cfg, conn=conn, table=table)
                warmed.add((set_name, table))
                loads.sample(f"table_start {set_name} {table}")
            row = {"set": set_name, "table": table, "filter_id": fid, "selectivity": fmaps[set_name][fid]["selectivity"],
                   "vector_idx": vi, "mode": mode, "seed": SEED, "error": None}
            try:
                rows, tr = R.retrieve(qv, cond, K, mode, cfg, conn=conn, table=table)
                ids = [r[0] for r in rows]
                row.update({"rows_returned": len(ids), "recall": recall(ids, gt[(table, fid, vi)]), "ids": ids, "trace": tr})
                R.retrieve(qv, cond, K, mode, cfg, conn=conn, table=table)                 # warm-up
                walls, traces = [], []
                for _ in range(TIMED):
                    t0 = time.perf_counter()
                    _, ttr = R.retrieve(qv, cond, K, mode, cfg, conn=conn, table=table)
                    walls.append((time.perf_counter() - t0) * 1000)
                    traces.append(_trace_small(ttr))
                row.update({"latency_ms": statistics.median(walls), "latency_raw_ms": walls, "timed_traces": traces})
            except Exception as e:
                conn.rollback()
                row["error"] = repr(e)
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            out.write(json.dumps(row) + "\n")
            out.flush()
            n_new += 1
            if n_new % 500 == 0:
                print(f"{i + 1}/{len(items)} items, {n_new} new in {(time.time() - t_start) / 60:.1f} min", flush=True)
    loads.stop_evt.set()
    loads.sample("end")
    print(f"done: {n_new} new rows in {(time.time() - t_start) / 60:.1f} min")


# ------------------------------------------------------------------ analysis

def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _p95(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return xs[min(len(xs) - 1, max(0, int(round(0.95 * len(xs) + 0.5)) - 1))]   # nearest-rank


def _stored_reference(cfg):
    out = {}
    for name, path in STORED_REF.items():
        acc = defaultdict(lambda: {"recalls": [], "lat": []})
        with open(PROJECT_ROOT / path, encoding="utf-8") as f:
            for ln in f:
                d = json.loads(ln)
                mode = STORED_ARM_TO_MODE.get(d["arm"])
                if mode:
                    a = acc[(d["table"], d["filter_id"], mode)]
                    a["recalls"].append(d["recall"] if not d["error"] else None)
                    a["lat"].append(d["latency_ms"] if not d["error"] else None)
        out[name] = {k: P.cell_passes(v["recalls"], v["lat"])["passed"] for k, v in acc.items()}
    return out


def analyze(args):
    cfg = R.RouterConfig.load(require_policy=True)
    rows = [json.loads(ln) for ln in (OUT / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    by_cell = defaultdict(list)
    for r in rows:
        by_cell[(r["set"], r["table"], r["filter_id"], r["mode"])].append(r)
    T = cfg.T_default
    cell_rows = []
    for (s, t, fid, mode), rs in sorted(by_cell.items()):
        rs.sort(key=lambda r: r["vector_idx"])
        ok = [r for r in rs if not r["error"]]
        res = P.cell_passes([r["recall"] if not r["error"] else None for r in rs],
                            [r["latency_ms"] if not r["error"] else None for r in rs])
        timed = [tt for r in ok for tt in r["timed_traces"]]
        guard = [r["trace"].get("guard_triggered") for r in ok]
        cell_rows.append({
            "set": s, "table": t, "filter_id": fid, "selectivity": rs[0]["selectivity"], "mode": mode, "n": len(rs),
            "errors": len(rs) - len(ok), "passed": res["passed"], "reason": res["reason"], "mean_recall": res["mean_recall"],
            "full_k_rate": sum(1 for r in ok if r["rows_returned"] >= K) / len(rs),
            "median_ms": res["median_latency_ms"], "p95_ms": _p95([x for r in ok for x in r["latency_raw_ms"]]),
            "estimate_ms": _med([tt.get("estimate_ms") for tt in timed]), "count_ms": _med([tt.get("count_ms") for tt in timed]),
            "probe_ms": _med([tt.get("probe_ms") for tt in timed]),
            "guard_rate": sum(1 for g in guard if g) / len(rs), "guard_added_ms": _med([tt.get("guard_added_ms") for tt in timed]),
            "in_band": sum(1 for r in ok if r["trace"].get("band") == "count"),
            "decided": dict(sorted(Counter(r["trace"]["decided"] for r in ok).items())),
            "probe_p_below_k": sum(1 for r in ok if r["trace"].get("probe_p") is not None and r["trace"]["probe_p"] < K),
        })
    # oracle per cell
    idx = {(c["set"], c["table"], c["filter_id"], c["mode"]): c for c in cell_rows}
    for (s, t, fid) in sorted({(c["set"], c["table"], c["filter_id"]) for c in cell_rows}):
        cands = [idx[(s, t, fid, m)] for m in ORACLE_CANDIDATES if (s, t, fid, m) in idx and idx[(s, t, fid, m)]["passed"]]
        best = min(cands, key=lambda c: c["median_ms"]) if cands else None
        cell_rows.append({"set": s, "table": t, "filter_id": fid, "selectivity": idx[(s, t, fid, "always_exact")]["selectivity"],
                          "mode": "oracle", "passed": best is not None, "reason": None if best else "no passing candidate",
                          "oracle_choice": best["mode"] if best else None, "median_ms": best["median_ms"] if best else None,
                          "mean_recall": best["mean_recall"] if best else None})
    with open(OUT / "cell_summary.csv", "w", newline="", encoding="utf-8") as f:
        fields = sorted({k for c in cell_rows for k in c}, key=lambda k: list(cell_rows[0]).index(k) if k in cell_rows[0] else 99)
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(cell_rows)
    # pass counts
    stored = _stored_reference(cfg)
    counts = defaultdict(dict)
    for c in cell_rows:
        counts[c["mode"]].setdefault(c["set"], [0, 0])
        counts[c["mode"]][c["set"]][0] += bool(c["passed"])
        counts[c["mode"]][c["set"]][1] += 1
    ref = {}
    for m in STORED_ARM_TO_MODE.values():
        ref[m] = {name: sum(1 for (t, fid, mm), p in stored[name].items() if mm == m and p) for name in stored}
    # H5: estimate-only vs exact count, per (set, table, filter) from the router mode's normal traces
    h5 = []
    for (s, t, fid, mode), rs in sorted(by_cell.items()):
        if mode != "router":
            continue
        r0 = next(r for r in rs if not r["error"])
        s_true = r0["selectivity"]
        s_est, n = r0["trace"]["s_est"], r0["trace"]["N"]
        est_route = P.EXACT if s_est < T else P.ITERATIVE
        cnt_route = P.decide_from_full_count(round(s_true * n), T, n)
        h5.append({"set": s, "table": t, "filter_id": fid, "s": s_true, "s_est": s_est, "band": P.decide_band(s_est, T),
                   "est_route": est_route, "count_route": cnt_route, "match": est_route == cnt_route,
                   "router_route": r0["trace"]["decided"]})
    # H7: per-query route differences local_probe vs router
    diffs = []
    rmap = {(r["set"], r["table"], r["filter_id"], r["vector_idx"]): r for r in rows if r["mode"] == "router" and not r["error"]}
    for r in rows:
        if r["mode"] != "local_probe" or r["error"]:
            continue
        g = rmap.get((r["set"], r["table"], r["filter_id"], r["vector_idx"]))
        if g and g["trace"]["decided"] != r["trace"]["decided"]:
            diffs.append({"set": r["set"], "table": r["table"], "filter_id": r["filter_id"], "vector_idx": r["vector_idx"],
                          "s": r["selectivity"], "router": g["trace"]["decided"], "local_probe": r["trace"]["decided"],
                          "probe_p": r["trace"]["probe_p"], "router_recall": g["recall"], "probe_recall": r["recall"],
                          "router_ms": g["latency_ms"], "probe_mode_ms": r["latency_ms"]})
    summary = {"T_default": T, "T_tuned": cfg.T_tuned,
               "pass_counts": {m: {s: f"{v[0]}/{v[1]}" for s, v in d.items()} for m, d in sorted(counts.items())},
               "stored_reference_pass_counts": ref, "h5": h5, "h5_mismatches": [x for x in h5 if not x["match"]],
               "h7_route_differences": diffs,
               "failing_cells": [{k: c.get(k) for k in ("set", "table", "filter_id", "selectivity", "mode", "reason", "mean_recall", "median_ms")}
                                 for c in cell_rows if not c["passed"]]}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for m, d in sorted(counts.items()):
        print(f"{m:22s} " + "  ".join(f"{s}={v[0]}/{v[1]}" for s, v in sorted(d.items())))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["llm", "run", "analyze"])
    ap.add_argument("--sets", nargs="+", default=SET_ORDER, choices=SET_ORDER)
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--budget-usd", type=float, default=None)
    a = ap.parse_args()
    {"llm": llm, "run": run, "analyze": analyze}[a.cmd](a)
