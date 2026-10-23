"""Amendment 7 Step 1 (FinQA, no LLM, no embedding call): routes each rule would choose on the frozen 50, vs policy_v2.

  .venv/Scripts/python -m src.phase_d_validation.amendment7_step1 --out-dir outputs/phase_d_amendment7_step1_2026-10-23

Embeddings: Qwen3-Embedding-8B, 1024-d, table finqa_evidence_qwen3; query vectors from the two Qwen3 caches only (SHA-256 checked,
every question must be present, every input-text hash verified). Selectivity: exact count of (ticker, year) rows on
finqa_evidence_qwen3 / its row count; every value must equal the recorded selectivity (frozen 50: Gemini full run; 1,075: the
confirmation file) or the run stops. Rules: policy_v2, B1, B2, B3 (from s / rows); A6 planner_iterative (plain EXPLAIN of the
index-route SQL with enable_* reset and hnsw.iterative_scan = relaxed_order); A8 fallback_hnsw (router.retrieve post-filter,
distinct, k = 15; exact if < 15 distinct rows); B4/B4b trained only on timed retrieval-only runs of the 1,075 confirmation
questions (exact vs iterative-relaxed; recall@15 against the exact distinct top-15 by passage text; latency = median of 5 timed
EXPLAIN ANALYZE after 1 warm-up). Year-only selectivity of the 50 is counted, not run. No retry: any error stops the run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import psycopg2

from src import db_settings
from src.phase_b_router.router import DISTINCT_INDEX_FETCH_FACTOR, DISTINCT_MIN_FETCH, retrieve
from src.phase_c_analysis.amendment6_partb import fit_mlp, boundary
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.utils.finqa_utils import extract_ticker_year

TABLE = "finqa_evidence_qwen3"
HNSW_INDEX = "finqa_evidence_qwen3_embedding_idx"
N_TOTAL, DIMS, K = 35_862, 1024, 15
SEED = 20261023
EXACT, ITER, HNSW = "exact", "iterative-relaxed", "forced-hnsw"
CACHE_50 = ("outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json", "930cadc0bdea177b0951a6891c227606cc47a3b4a1ce8c437563635f9be9ff23")
CACHE_1075 = ("outputs/embedding_build_2026-10-13/query_embeddings_qwen3_confirmation_1075.json", "c5215bea79bbd486b084d276a0bc2a5e1fb632a8e66a6ae3385f16d4bc7f36ea")
CONF_FILE = ("outputs/scaleup_confirmation_2026-10-13/confirmation_1075.csv", "aff43f1fb918e2d44dd1cdd934de2b8fccd4e64e2690fd5bd4e7f3d36d0704a3")
FROZEN_SEL = "outputs/phase_d_gemini_full_2026-10-12/results.csv"
PREFIX = "Instruct: Given a financial question, retrieve the report passages and table rows that answer it\nQuery: "
WHERE = "WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s"
INDEX_LIMIT = max(DISTINCT_MIN_FETCH, DISTINCT_INDEX_FETCH_FACTOR * K)        # 150, as retrieve(distinct=True)
SQL_INDEX = f"SELECT id, query_id, evidence_key, content, embedding <-> %s::vector AS d FROM {TABLE} {WHERE} ORDER BY embedding <-> %s::vector LIMIT {INDEX_LIMIT}"
SQL_EXACT = (f"SELECT id, query_id, evidence_key, content, d FROM (SELECT DISTINCT ON (md5(content)) id, query_id, evidence_key, content, "
             f"embedding <-> %s::vector AS d FROM {TABLE} {WHERE} ORDER BY md5(content), d, id) s ORDER BY d, id LIMIT {K}")
SESSION = {EXACT: "RESET ALL; SET enable_indexscan = off; SET enable_seqscan = on; SET hnsw.iterative_scan = off;",
           ITER: "RESET ALL; SET enable_indexscan = on; SET enable_seqscan = off; SET hnsw.iterative_scan = 'relaxed_order';",
           HNSW: "RESET ALL; SET enable_indexscan = on; SET enable_seqscan = off; SET hnsw.iterative_scan = off;",
           "planner_iterative": "RESET ALL; SET hnsw.iterative_scan = 'relaxed_order';"}


def sha256(p: str) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_cache(path: str, want_sha: str, questions: dict) -> dict:
    """questions: {query_id: question}. Returns {query_id: vector}; raises on any mismatch or missing question."""
    got = sha256(path)
    if got != want_sha:
        raise SystemExit(f"{path}: SHA-256 {got} != expected {want_sha}")
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d["model"] != "qwen/qwen3-embedding-8b" or d["dimension"] != DIMS:
        raise SystemExit(f"{path}: model {d['model']} / dimension {d['dimension']} is not Qwen3-Embedding-8B 1024-d")
    by = {x["query_id"]: x for x in d["queries"]}
    out = {}
    for qid, q in questions.items():
        x = by.get(qid)
        if x is None:
            raise SystemExit(f"{path}: no embedding for {qid}")
        if hashlib.sha256(x["input_text"].encode()).hexdigest() != x["input_sha256"] or x["input_text"] != PREFIX + q:
            raise SystemExit(f"{path}: input text / hash mismatch for {qid}")
        if len(x["vector"]) != DIMS:
            raise SystemExit(f"{path}: {qid} vector has {len(x['vector'])} dims")
        out[qid] = x["vector"]
    return out


def plan_nodes(plan: dict) -> list[dict]:
    out = [{"type": plan.get("Node Type"), "index": plan.get("Index Name")}]
    for p in plan.get("Plans", []):
        out += plan_nodes(p)
    return out


def explain(cur, sql: str, params: tuple, analyze: bool) -> dict:
    cur.execute(("EXPLAIN (ANALYZE, FORMAT JSON) " if analyze else "EXPLAIN (FORMAT JSON) ") + sql, params)
    return cur.fetchone()[0][0]


def is_hnsw(nodes: list[dict]) -> bool:
    return any(n["type"] == "Index Scan" and n["index"] == HNSW_INDEX for n in nodes)


def sql_for(route: str):
    return (SQL_EXACT, lambda v, t, y: (v, t, y)) if route == EXACT else (SQL_INDEX, lambda v, t, y: (v, t, y, v))


def timed(cur, route: str, vec, t, y) -> tuple[float, list[float], list[dict]]:
    cur.execute(SESSION[route])
    sql, par = sql_for(route)
    cur.execute(sql, par(vec, t, y))
    cur.fetchall()                                             # untimed warm-up
    raw, nodes = [], None
    for _ in range(5):
        e = explain(cur, sql, par(vec, t, y), analyze=True)
        raw.append(float(e["Execution Time"]))
        n = plan_nodes(e["Plan"])
        if nodes is None:
            nodes = n
        elif n != nodes:
            raise SystemExit(f"plan changed between timed runs ({route}, {t}/{y})")
    return statistics.median(raw), raw, nodes


class HostLoad:
    def __init__(self):
        self.samples, self._stop = [], threading.Event()

    def sample(self, event: str):
        top = sorted(((p.info["cpu_times"].user + p.info["cpu_times"].system if p.info["cpu_times"] else 0.0, p.info["name"])
                      for p in psutil.process_iter(["name", "cpu_times"])), reverse=True)[:5]
        self.samples.append({"event": event, "utc": datetime.now(timezone.utc).isoformat(),
                             "cpu_total_pct_3_samples": [psutil.cpu_percent(interval=1) for _ in range(3)],
                             "top5_cumulative_cpu_s": [{"name": n, "cpu_s": round(c, 1)} for c, n in top]})

    def start(self):
        self.sample("run_start")

        def loop():
            while not self._stop.wait(300):
                self.sample("every_5_min")
        self._t = threading.Thread(target=loop, daemon=True)
        self._t.start()

    def stop(self):
        self._stop.set()
        self.sample("run_end")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--smoke", type=int, default=None, help="train on only the first N shuffled questions (smoke test; never the reported run)")
    a = ap.parse_args()
    out = Path(a.out_dir)
    if out.exists():
        raise SystemExit(f"{out} exists; refusing to overwrite")
    if sha256(CONF_FILE[0]) != CONF_FILE[1]:
        raise SystemExit("confirmation file SHA-256 differs")
    frozen = load_finqa_subset(get_frozen_filepath())
    conf = list(csv.DictReader(open(CONF_FILE[0], encoding="utf-8", newline="")))
    if len(frozen) != 50 or len(conf) != 1075 or {q["id"] for q in frozen} & {q["id"] for q in conf}:
        raise SystemExit("question sets have the wrong size or overlap")
    vec50 = load_cache(*CACHE_50, {q["id"]: q["question"] for q in frozen})
    vec1075 = load_cache(*CACHE_1075, {q["id"]: q["question"] for q in conf})
    rec_sel = {r["query_id"]: float(r["selectivity"]) for r in csv.DictReader(open(FROZEN_SEL, encoding="utf-8")) if r["selectivity"]}
    rec_sel.update({q["id"]: float(q["selectivity"]) for q in conf})

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    if cur.fetchone()[0] != N_TOTAL:
        raise SystemExit(f"{TABLE} row count is not {N_TOTAL}")
    settings = {}
    for s in ("hnsw.ef_search", "hnsw.max_scan_tuples", "jit", "work_mem", "shared_buffers", "server_version"):
        cur.execute(f"SHOW {s}")
        settings[s] = cur.fetchone()[0]
    if settings["hnsw.ef_search"] != "40":
        raise SystemExit(f"hnsw.ef_search is {settings['hnsw.ef_search']}, not 40")
    out.mkdir(parents=True)
    load = HostLoad()
    load.start()
    t_start = time.perf_counter()
    try:
        # selectivity on finqa_evidence_qwen3, checked against the recorded values
        sel = {}
        for q in frozen + conf:
            t, y = extract_ticker_year(q["id"])
            cur.execute(f"SELECT count(*) FROM {TABLE} {WHERE}", (t, y))
            n = cur.fetchone()[0]
            if n == 0 or abs(n / N_TOTAL - rec_sel[q["id"]]) > 1e-12:
                raise SystemExit(f"{q['id']}: count {n} (s = {n / N_TOTAL}) differs from recorded s = {rec_sel[q['id']]}")
            sel[q["id"]] = {"ticker": t, "year": y, "rows": n, "s": n / N_TOTAL}

        # pre-flight plans (vector of the first frozen question)
        q0 = frozen[0]
        pf = {}
        for route in (EXACT, ITER, HNSW):
            cur.execute(SESSION[route])
            sql, par = sql_for(route)
            nodes = plan_nodes(explain(cur, sql, par(vec50[q0["id"]], sel[q0["id"]]["ticker"], sel[q0["id"]]["year"]), analyze=False)["Plan"])
            pf[route] = nodes
            if is_hnsw(nodes) == (route == EXACT):
                raise SystemExit(f"pre-flight: {route} plan {nodes} not as intended")
        (out / "preflight.json").write_text(json.dumps(pf, indent=2), encoding="utf-8")

        # frozen 50: A6 plan and A8 retrieval (+ year-only counts)
        frozen_rows = []
        for q in frozen:
            qid, v = q["id"], vec50[q["id"]]
            t, y, s, n = sel[qid]["ticker"], sel[qid]["year"], sel[qid]["s"], sel[qid]["rows"]
            cur.execute(SESSION["planner_iterative"])
            a6_nodes = plan_nodes(explain(cur, SQL_INDEX, (v, t, y, v), analyze=False)["Plan"])
            r8 = retrieve(conn, "post-filter", t, y, v, K, TABLE, distinct=True)
            cur.execute(f"SELECT count(*) FROM {TABLE} WHERE metadata->>'year' = %s", (y,))
            yr = cur.fetchone()[0]
            frozen_rows.append({"query_id": qid, "ticker": t, "year": y, "matched_rows": n, "s": s,
                                "policy_v2": EXACT if s < 0.1 else ITER, "B1": EXACT if s < 0.18 else ITER,
                                "B2": EXACT if s <= 0.05 else ITER, "B3": EXACT if n < 10000 / (DIMS / 256) else ITER,
                                "A6": ITER if is_hnsw(a6_nodes) else EXACT, "A6_plan": "/".join(f"{x['type']}{'(' + x['index'] + ')' if x['index'] else ''}" for x in a6_nodes),
                                "A8_hnsw_distinct_rows": len(r8["rows"]), "A8_fallback": len(r8["rows"]) < K,
                                "A8": EXACT if len(r8["rows"]) < K else HNSW, "year_only_rows": yr, "year_only_s": yr / N_TOTAL})

        # training: timed retrieval-only runs of the 1,075 (seeded order, seeded route order)
        rng = random.Random(SEED)
        order = conf[:]
        rng.shuffle(order)
        if a.smoke:
            order = order[:a.smoke]
        cur.execute(SESSION[EXACT])
        cur.execute(f"SELECT id FROM {TABLE} ORDER BY embedding <-> %s::vector LIMIT 1", (vec1075[order[0]["id"]],))
        cur.fetchall()                                        # per-table warm-up, untimed
        train = []
        for i, q in enumerate(order, 1):
            qid, v = q["id"], vec1075[q["id"]]
            t, y = sel[qid]["ticker"], sel[qid]["year"]
            truth = retrieve(conn, EXACT, t, y, v, K, TABLE, distinct=True)["rows"]
            truth_txt = {hashlib.md5(r[3].encode()).hexdigest() for r in truth}
            rec = {}
            routes = [EXACT, ITER]
            rng.shuffle(routes)
            row = {"query_id": qid, "s": sel[qid]["s"], "matched_rows": sel[qid]["rows"], "route_order": routes, "truth_size": len(truth)}
            for route in routes:
                got = retrieve(conn, route, t, y, v, K, TABLE, distinct=True)
                txt = {hashlib.md5(r[3].encode()).hexdigest() for r in got["rows"]}
                med, raw, nodes = timed(cur, route, v, t, y)
                if is_hnsw(nodes) == (route == EXACT):
                    raise SystemExit(f"{qid}: {route} timed plan not as intended: {nodes}")
                row[route] = {"recall15": len(txt & truth_txt) / len(truth_txt), "rows": len(got["rows"]), "rows_fetched": got["rows_fetched"],
                              "latency_ms": med, "latency_raw_ms": raw, "plan": "/".join(x["type"] for x in nodes)}
            train.append(row)
            if i % 100 == 0:
                print(f"{i}/1075 trained-query runs, {time.perf_counter() - t_start:.0f} s", flush=True)
    finally:
        load.stop()
        (out / "host_load.json").write_text(json.dumps(load.samples, indent=2), encoding="utf-8")

    with (out / "training_runs.jsonl").open("w", encoding="utf-8") as fh:
        for r in train:
            fh.write(json.dumps(r) + "\n")

    # B4 / B4b on the 1,075, predicted for the 50
    models = {}
    for name, kind in (("B4", "ratio"), ("B4b", "sla")):
        X, y = [], []
        for r in train:
            (re, le), (ri, li) = (r[EXACT]["recall15"], r[EXACT]["latency_ms"]), (r[ITER]["recall15"], r[ITER]["latency_ms"])
            if kind == "ratio":
                lab = EXACT if re / le >= ri / li else ITER
            else:
                ok = [(l, rt) for rt, rc, l in ((EXACT, re, le), (ITER, ri, li)) if rc >= 0.9 - 1e-12]
                lab = min(ok, key=lambda z: (z[0], z[1] != EXACT))[1] if ok else EXACT
            X.append(r["s"])
            y.append(lab)
        m, counts = fit_mlp(X, [{"exact": "forced-exact", ITER: ITER}[v] for v in y])
        models[name] = {"train_label_counts": counts, "n_train": len(y)}
        if m is None:
            for fr in frozen_rows:
                fr[name] = None
            models[name]["fitted"] = False
            continue
        models[name] |= {"fitted": True, "n_iter": int(m[-1].n_iter_), "boundary": boundary(m),
                         "train_accuracy": float((m.predict(np.array(X).reshape(-1, 1)) == np.array([{"exact": "forced-exact"}.get(v, v) for v in y])).mean())}
        pred = m.predict(np.array([[fr["s"]] for fr in frozen_rows]))
        for fr, p in zip(frozen_rows, pred):
            fr[name] = EXACT if p == "forced-exact" else ITER

    rules = ["B1", "B2", "B3", "A6", "A8", "B4", "B4b"]
    diff = {r: (None if any(fr[r] is None for fr in frozen_rows) else sum(1 for fr in frozen_rows if fr[r] != fr["policy_v2"])) for r in rules}
    with (out / "frozen50_routes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(frozen_rows[0]))
        w.writeheader()
        w.writerows(frozen_rows)
    ys = [fr["year_only_s"] for fr in frozen_rows]

    def stats(vals):
        return {"n": len(vals), "min": min(vals), "median": statistics.median(vals), "mean": statistics.fmean(vals), "max": max(vals)}
    tr = {rt: {"recall15": stats([r[rt]["recall15"] for r in train]), "latency_ms": stats([r[rt]["latency_ms"] for r in train]),
               "rows_lt_15": sum(1 for r in train if r[rt]["rows"] < K)} for rt in (EXACT, ITER)}
    summary = {"settings": settings | {"table": TABLE, "k_distinct": K, "seed": SEED, "index_route_limit": INDEX_LIMIT},
               "caches": {CACHE_50[0]: CACHE_50[1], CACHE_1075[0]: CACHE_1075[1]}, "confirmation_file": CONF_FILE,
               "selectivity_check": "all 1,125 counts on finqa_evidence_qwen3 equal the recorded selectivities",
               "policy_v2_routes": dict(Counter(fr["policy_v2"] for fr in frozen_rows)),
               "routes_per_rule": {r: dict(Counter(str(fr[r]) for fr in frozen_rows)) for r in rules},
               "differences_from_policy_v2": diff, "A8_fallbacks": sum(1 for fr in frozen_rows if fr["A8_fallback"]),
               "A6_plans": dict(Counter(fr["A6_plan"] for fr in frozen_rows)), "models": models, "training_summary": tr,
               "frozen_s": stats([fr["s"] for fr in frozen_rows]), "frozen_matched_rows_max": max(fr["matched_rows"] for fr in frozen_rows),
               "year_only": stats(ys) | {"n_above_0.1": sum(1 for v in ys if v > 0.1),
                                         "distinct_years": dict(sorted(Counter(fr["year"] for fr in frozen_rows).items())),
                                         "s_by_year": dict(sorted({fr["year"]: fr["year_only_s"] for fr in frozen_rows}.items()))},
               "elapsed_s": round(time.perf_counter() - t_start, 1),
               "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("differences_from_policy_v2", "A8_fallbacks", "A6_plans", "year_only", "elapsed_s")}, indent=1))


if __name__ == "__main__":
    main()
