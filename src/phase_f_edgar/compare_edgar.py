"""Phase F Task 4 (Amendment 11 section 4): retrieval comparison on edgar_chunks, 160 pairs x 19 modes, k = 15.

  python -m src.phase_f_edgar.compare_edgar decide --allow-paid --out-dir outputs/edgar_retrieval_comparison_2026-11-01
  python -m src.phase_f_edgar.compare_edgar run --out-dir outputs/edgar_retrieval_comparison_2026-11-01
  python -m src.phase_f_edgar.compare_edgar analyze --out-dir outputs/edgar_retrieval_comparison_2026-11-01

decide (before the timed session): llm_router decisions (Gemini 3.8 Flash, NAIVE_INFORMED_ROUTER_SYSTEM verbatim, one call per
pair; paid, logged in the session cost log) and VecAdvisor recommend decisions (one per pair), both cached.
run: quiet-rule start (Addendum 2), pre-flight plain EXPLAIN (route shapes per pair), exact top-15 ground truth per pair, then per
(pair, mode) one normal execution (rows, recall@15/@10, gold hit, trace), one warm-up and 5 timed end-to-end wall-clock calls,
median, Addendum 1 early stop; order shuffled with random.Random(20261105); resumable.
analyze: per mode and breadth tables.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone

from src import PROJECT_ROOT
from src.phase_e_router import policy_v3_1 as V
from src.phase_e_router import retriever as R
from src.phase_e_router.cells import env_meta
from src.phase_f_edgar import session_tools as S
from src.phase_f_edgar import vecadvisor_adapter as VA

SEED = 20261105
K = 15
TIMED = 5
EARLY_STOP_MS = 1500.0
TABLE = "edgar_chunks"
CONFIG = "config/router_edgar.json"
POLICY_EDGAR = "config/policy_v3_1_edgar.json"
POLICY_HM = "config/policy_v3_1_hm.json"
EVAL = "outputs/edgar_eval_set_2026-11-01"
N_TOTAL = 158_308
BREADTHS = ("cik+year+section", "cik+year", "year+section", "section")
RETRIEVER_MODES = list(R.MODES)                                     # the 14 Amendment 9 modes
PRIOR = {"vbase": lambda s, n: s < 0.18, "milvus": lambda s, n: s <= 0.05, "qdrant": lambda s, n: n < 2500}
MODES = RETRIEVER_MODES + ["router_hmT", "vecadvisor", "vbase", "milvus", "qdrant"]
LLM_MODEL = "gemini-3.8-flash"
LLM_USER = "Metadata filter to be applied: {filter}\nQuestion: {question}"


def load_pairs():
    pairs = list(csv.DictReader(open(PROJECT_ROOT / EVAL / "pairs.csv", encoding="utf-8", newline="")))
    sel = {r["qid"]: r for r in csv.DictReader(open(PROJECT_ROOT / EVAL / "selected.csv", encoding="utf-8", newline=""))}
    for p in pairs:
        p["filters"] = json.loads(p["filter"])
        p["gold"] = json.loads(p["gold_ids"])
        p["question"] = sel[p["qid"]]["question"]
    if len(pairs) != 160:
        raise SystemExit(f"{len(pairs)} pairs, expected 160")
    return pairs


def configs():
    cfg = R.RouterConfig.load(CONFIG, require_policy=True)
    if cfg.T_default is None or cfg.T_tuned is None:
        raise SystemExit("edgar T not calibrated (config/policy_v3_1_edgar.json)")
    cfg_hm = R.RouterConfig.load(CONFIG, policy_path=POLICY_HM, require_policy=True)
    return cfg, cfg_hm


# ------------------------------------------------------------------ decisions (before the session)

def decide(a):
    from src.phase_b_router.router import NAIVE_INFORMED_ROUTER_SYSTEM, validate_naive_route
    from src.phase_d_validation.llm_client import load_generation_config, make_client
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    pairs, vecs = load_pairs(), S.load_question_vectors()
    llm_path, va_path = out / "llm_decisions.json", out / "vecadvisor_decisions.json"
    if not llm_path.exists():
        if not a.allow_paid:
            raise SystemExit("llm_router decisions are paid: needs --allow-paid")
        remaining = S.SESSION_CAP_USD - S.cost_spent()
        gcfg = load_generation_config()
        client = make_client(LLM_MODEL, allow_paid=True, budget_usd=min(a.budget_usd, remaining), config=gcfg)
        decisions = []
        for p in pairs:
            user = LLM_USER.format(filter=VA.filter_sql(p["filters"]), question=p["question"])
            rec = {"pair_id": p["pair_id"], "user_message": user}
            try:
                resp = client.generate(NAIVE_INFORMED_ROUTER_SYSTEM, user, max_output_tokens=gcfg["roles"]["router_max_output_tokens"],
                                       json_mode=True)
                data, err = validate_naive_route(resp.text)
                rec.update({"raw": resp.text, "route": data["route"] if data else None, "reason": data["reason"] if data else None,
                            "parse_error": err, "latency_ms": resp.latency_ms, "input_tokens": resp.input_tokens,
                            "output_tokens": resp.output_tokens, "thinking_tokens": resp.thinking_tokens, "cost_usd": resp.cost_usd,
                            "finish_reason": resp.finish_reason, "call_error": None})
            except Exception as e:                     # single attempt: a failed call is a route failure, recorded
                rec.update({"route": None, "call_error": f"{type(e).__name__}: {e}"[:500], "cost_usd": 0.0})
            S.cost_add("llm_router decision", rec["cost_usd"], {"pair_id": p["pair_id"]})
            decisions.append(rec)
            print(p["pair_id"], rec["route"], rec.get("parse_error") or rec.get("call_error") or "", flush=True)
        S.write_json(llm_path, {"model": LLM_MODEL, "system_prompt": NAIVE_INFORMED_ROUTER_SYSTEM,
                                "system_prompt_sha256": hashlib.sha256(NAIVE_INFORMED_ROUTER_SYSTEM.encode()).hexdigest(),
                                "user_template": LLM_USER, "total_cost_usd": sum(d["cost_usd"] for d in decisions),
                                "created_utc": datetime.now(timezone.utc).isoformat(), "decisions": decisions})
    if not va_path.exists():
        res = []
        for p in pairs:
            d = VA.decide(p["filters"], vecs[p["qid"]])
            res.append({"pair_id": p["pair_id"], **d})
            print(p["pair_id"], d["strategy"], d["unavailable_reason"] or "", f"{d['decision_ms']:.0f} ms", flush=True)
        S.write_json(va_path, {"vecadvisor": VA.VECADVISOR.relative_to(PROJECT_ROOT).as_posix(), "created_utc": datetime.now(timezone.utc).isoformat(),
                               "decisions": res})


def load_decisions(out):
    llm = {d["pair_id"]: d for d in json.loads((out / "llm_decisions.json").read_text(encoding="utf-8"))["decisions"]}
    va = {d["pair_id"]: d for d in json.loads((out / "vecadvisor_decisions.json").read_text(encoding="utf-8"))["decisions"]}
    return llm, va


# ------------------------------------------------------------------ one retrieval

def retrieve(conn, mode, p, qv, cfg, cfg_hm, llm, va):
    """(rows, trace) of one mode on one pair; end-to-end inside."""
    f = p["filters"]
    if mode in V.BAND_MODES:
        return V.retrieve(qv, f, K, mode, cfg, conn=conn, table=TABLE)
    if mode == "router_hmT":
        rows, tr = V.retrieve(qv, f, K, "router", cfg_hm, conn=conn, table=TABLE)
        tr["mode"] = "router_hmT"
        return rows, tr
    trace = {"mode": mode, "table": TABLE, "k": K, "decided": None, "routes_executed": [], "route_ms": [], "guard": False,
             "guard_triggered": False, "filter_smaller_than_k": None}
    t0 = time.perf_counter()
    if mode == "llm_router":
        d = llm[p["pair_id"]]
        if d["route"] not in R.LLM_ROUTES:
            trace.update({"route_failure": True, "decided": None, "rows_returned": 0, "total_ms": 0.0})
            return [], trace
        route = R.LLM_ROUTES[d["route"]]
        trace["decided"] = d["route"]
        rows = R._execute(conn, route, TABLE, f, K, R.vec_literal(qv), cfg, trace, False)
    elif mode == "vecadvisor":
        d = va[p["pair_id"]]
        rows, ms, shape = VA.execute(conn, d, TABLE, f, K, R.vec_literal(qv), cfg)
        trace.update({"decided": d["strategy"], "vecadvisor_params": d["params"], "vecadvisor_unavailable": d["unavailable"],
                      "vecadvisor_unavailable_reason": d["unavailable_reason"], "routes_executed": [shape], "route_ms": [ms],
                      "decision_ms_separate": d["decision_ms"]})
    elif mode in PRIOR:
        w, wp = R.where_clause(f, cfg)
        t1 = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {TABLE} WHERE {w}", wp)
            n = cur.fetchone()[0]
        conn.commit()
        s = n / N_TOTAL
        exact = PRIOR[mode](s, n)
        trace.update({"count_full": n, "s_exact": s, "count_ms": (time.perf_counter() - t1) * 1000,
                      "decided": R.EXACT if exact else R.ITERATIVE})
        rows = R._execute(conn, R.R_EXACT if exact else R.R_ITER, TABLE, f, K, R.vec_literal(qv), cfg, trace, False)
    else:
        return R.retrieve(qv, f, K, mode, cfg, conn=conn, table=TABLE)
    trace["rows_returned"] = len(rows)
    trace["total_ms"] = (time.perf_counter() - t0) * 1000
    return rows, trace


def small(tr):
    keep = ("decided", "band", "s_est", "plan_rows", "count", "count_cap", "count_full", "probe_p", "router_route", "routes_executed",
            "route_ms", "estimate_ms", "count_ms", "probe_ms", "stats_check_ms", V.SKIP_FIELD, "guard_triggered", "guard_added_ms",
            "rows_returned", "total_ms")
    return {k: tr[k] for k in keep if k in tr}


# ------------------------------------------------------------------ session

def run(a):
    out = PROJECT_ROOT / a.out_dir
    cfg, cfg_hm = configs()
    pairs, vecs = load_pairs(), S.load_question_vectors()
    llm, va = load_decisions(out)
    cfg.llm_routes = {}
    conn = R.connect()
    R.configure_session(conn, cfg)
    pmap = {p["pair_id"]: p for p in pairs}

    q = S.quiet_start(out)
    if not (out / "preflight.json").exists():
        checks = []
        for p in pairs:
            qv = R.vec_literal(vecs[p["qid"]])
            for route in (R.R_EXACT, R.R_ITER, R.R_ITER_TUNED, R.R_HNSW, R.R_PROBE, R.R_PLANNER_ITER):
                checks.append({"pair_id": p["pair_id"], **R.check_plan(route, R.explain_route(conn, route, TABLE, p["filters"], K, qv, cfg), cfg)})
            checks.append({"pair_id": p["pair_id"], "vecadvisor": va[p["pair_id"]]["strategy"],
                           **VA.explain(conn, va[p["pair_id"]], TABLE, p["filters"], K, qv, cfg)})
        failed = [c for c in checks if c["ok"] is False]
        S.write_json(out / ("preflight.json" if not failed else "preflight_failed.json"),
                     {"checked_utc": datetime.now(timezone.utc).isoformat(), "n_checks": len(checks), "n_failed": len(failed),
                      "failures": failed, "checks": checks})
        if failed:
            raise SystemExit(f"pre-flight failed: {failed[:3]}")
    gpath = out / "ground_truth.json"
    if gpath.exists():
        gt = json.loads(gpath.read_text(encoding="utf-8"))
    else:
        gt = {p["pair_id"]: S.exact_topk(conn, TABLE, p["filters"], K, R.vec_literal(vecs[p["qid"]]), cfg) for p in pairs}
        S.write_json(gpath, gt)

    rnd = random.Random(SEED)
    order = [p["pair_id"] for p in pairs]
    rnd.shuffle(order)
    items = []
    for pid in order:
        m = list(MODES)
        rnd.shuffle(m)
        items.extend((pid, mode) for mode in m)
    sched_sha = hashlib.sha256(json.dumps(items).encode()).hexdigest()
    results = out / "results.jsonl"
    done = set()
    if results.exists():
        for ln in results.read_text(encoding="utf-8").splitlines():
            d = json.loads(ln)
            done.add((d["pair_id"], d["mode"]))
    meta_path = out / "run_meta.json"
    if not meta_path.exists():
        S.write_json(meta_path, {**env_meta(conn), "amendment": "docs/preregistration/PHASE_F_AMENDMENT_11.md", "seed": SEED, "k": K,
                                 "timed_repeats": TIMED, "modes": MODES, "T_default": cfg.T_default, "T_tuned": cfg.T_tuned,
                                 "T_hm": cfg_hm.T_default, "schedule_sha256": sched_sha, "n_items": len(items), "quiet_check": q,
                                 "config": cfg.raw})
    else:
        with open(out / "resumes.jsonl", "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "already_done": len(done), "quiet_check": q,
                                 "schedule_sha256": sched_sha}, default=str) + "\n")
    loads = S.LoadLogger(out / f"host_load_{int(time.time())}.json")
    loads.sample("start")
    loads.start()
    p0 = pairs[0]
    retrieve(conn, "default_hnsw", p0, vecs[p0["qid"]], cfg, cfg_hm, llm, va)          # untimed warm-up
    retrieve(conn, "always_exact", p0, vecs[p0["qid"]], cfg, cfg_hm, llm, va)
    t_start, n_new = time.time(), 0
    with open(results, "a", encoding="utf-8", newline="\n") as fh:
        for i, (pid, mode) in enumerate(items):
            if (pid, mode) in done:
                continue
            p = pmap[pid]
            qv = vecs[p["qid"]]
            row = {"pair_id": pid, "qid": p["qid"], "breadth": p["breadth"], "selectivity": float(p["selectivity"]), "mode": mode,
                   "seed": SEED, "error": None}
            try:
                rows, tr = retrieve(conn, mode, p, qv, cfg, cfg_hm, llm, va)
                ids = [r_[0] for r_ in rows]
                truth = gt[pid]
                row.update({"rows_returned": len(ids), "recall15": S.recall_at(ids, truth, 15), "recall10": S.recall_at(ids, truth, 10),
                            "gold_hit": any(x in set(p["gold"]) for x in ids), "ids": ids,
                            "distances": [float(r_[1]) for r_ in rows], "trace": tr})
                if tr.get("route_failure"):
                    row.update({"latency_ms": None, "latency_raw_ms": [], "early_stop": False, "timed_traces": []})
                else:
                    retrieve(conn, mode, p, qv, cfg, cfg_hm, llm, va)                        # warm-up
                    walls, traces, early = [], [], False
                    for rep in range(TIMED):
                        t0 = time.perf_counter()
                        _, ttr = retrieve(conn, mode, p, qv, cfg, cfg_hm, llm, va)
                        walls.append((time.perf_counter() - t0) * 1000)
                        traces.append(small(ttr))
                        if rep == 1 and statistics.median(walls) > EARLY_STOP_MS:
                            early = True
                            break
                    row.update({"latency_ms": statistics.median(walls), "latency_raw_ms": walls, "early_stop": early,
                                "timed_traces": traces})
            except Exception as e:
                conn.rollback()
                row["error"] = repr(e)
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            n_new += 1
            if n_new % 200 == 0:
                print(f"{i + 1}/{len(items)} items, {n_new} new in {(time.time() - t_start) / 60:.1f} min", flush=True)
    loads.stop_evt.set()
    loads.sample("end")
    print(f"done: {n_new} new rows in {(time.time() - t_start) / 60:.1f} min")


# ------------------------------------------------------------------ analysis

def route_of(r) -> str:
    tr = r["trace"]
    if tr.get("route_failure"):
        return "route_failure"
    ex = tr.get("routes_executed") or []
    return "+".join(ex) if ex else str(tr.get("decided"))


def analyze(a):
    out = PROJECT_ROOT / a.out_dir
    rows = [json.loads(ln) for ln in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    by = {(r["pair_id"], r["mode"]): r for r in rows}
    errs = [r for r in rows if r["error"]]
    if len(by) != 160 * len(MODES) or errs:
        raise SystemExit(f"incomplete or invalid session: {len(by)}/{160 * len(MODES)} rows, {len(errs)} errors: {errs[:2]}")
    table, flat = [], []
    for mode in MODES:
        for b in ("all",) + BREADTHS:
            rs = [r for r in rows if r["mode"] == mode and (b == "all" or r["breadth"] == b)]
            lat = [r["latency_ms"] for r in rs if r["latency_ms"] is not None]
            routes = defaultdict(int)
            for r in rs:
                routes[route_of(r)] += 1
            table.append({"mode": mode, "breadth": b, "n_pairs": len(rs),
                          "recall15_ge_0.90": sum(1 for r in rs if (r["recall15"] or 0) >= 0.9),
                          "mean_recall15": round(statistics.fmean((r["recall15"] or 0) for r in rs), 4),
                          "mean_recall10": round(statistics.fmean((r["recall10"] or 0) for r in rs), 4),
                          "gold_hit_rate": round(sum(r["gold_hit"] for r in rs) / len(rs), 4),
                          "median_latency_ms": round(statistics.median(lat), 2) if lat else None,
                          "underfilled": sum(1 for r in rs if r["rows_returned"] < K),
                          "guard_fired": sum(1 for r in rs if r["trace"].get("guard_triggered")),
                          "early_stop": sum(1 for r in rs if r.get("early_stop")),
                          "route_failures": sum(1 for r in rs if r["trace"].get("route_failure")),
                          "vecadvisor_unavailable": sum(1 for r in rs if r["trace"].get("vecadvisor_unavailable")),
                          "estimate_skipped_no_stats": sum(1 for r in rs if r["trace"].get(V.SKIP_FIELD)),
                          "routes": json.dumps(dict(sorted(routes.items())))})
    for r in rows:
        flat.append({"pair_id": r["pair_id"], "qid": r["qid"], "breadth": r["breadth"], "selectivity": r["selectivity"], "mode": r["mode"],
                     "route": route_of(r), "decided": r["trace"].get("decided"), "band": r["trace"].get("band"),
                     "s_est": r["trace"].get("s_est"), "rows_returned": r["rows_returned"], "recall15": r["recall15"],
                     "recall10": r["recall10"], "gold_hit": r["gold_hit"], "guard_fired": r["trace"].get("guard_triggered"),
                     "latency_ms": r["latency_ms"], "early_stop": r.get("early_stop"),
                     "vecadvisor_unavailable": r["trace"].get("vecadvisor_unavailable"), "ids": json.dumps(r["ids"])})
    for name, data in (("summary_by_mode_breadth.csv", table), ("per_pair_mode.csv", flat)):
        with open(out / name, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(data)
    for t in table:
        if t["breadth"] == "all":
            print(t)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["decide", "run", "analyze"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--budget-usd", type=float, default=0.5)
    a = ap.parse_args()
    {"decide": decide, "run": run, "analyze": analyze}[a.cmd](a)
