"""Read-only timing of selectivity computation on finqa_evidence_qwen3 for the frozen 50 FinQA questions; no paid calls.

Two paths per question, each: 1 untimed warm-up, then 5 timed repetitions (client wall-clock, time.perf_counter, as
total_ms in comparison_runner):
  exact_selectivity  the two COUNT(*) statements of src.utils.finqa_utils.exact_selectivity (total rows, matching rows),
                     run against finqa_evidence_qwen3 (the function itself is hard-wired to finqa_evidence)
  router_v3          the Phase E decision path of retriever._band_decision: reltuples + EXPLAIN (FORMAT JSON) estimate,
                     band with T from config/policy_v3_hm.json, capped count only in the count band
Host CPU (processor counter and Win32 LoadPercentage) recorded at start and end; no quiet rule.

  python -m src.phase_e_router.finqa_selectivity_timing
"""

from __future__ import annotations

import csv
import json
import statistics
import time
from datetime import datetime, timezone

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_e_router import policy_v3 as P
from src.phase_e_router.cells import git, host_load
from src.utils.finqa_utils import extract_ticker_year

TABLE = "finqa_evidence_qwen3"
WHERE = "metadata->>'ticker' = %s AND metadata->>'year' = %s"
OUT = PROJECT_ROOT / "outputs" / "finqa_selectivity_timing_2026-10-31"
TIMED = 5


def exact_path(cur, ticker, year):
    cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
    total = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE {WHERE}", (ticker, year))
    return {"matching_rows": cur.fetchone()[0], "total_rows": total}


def router_path(cur, ticker, year, T):
    cur.execute("SELECT reltuples FROM pg_class WHERE oid = %s::regclass", (TABLE,))
    n = cur.fetchone()[0]
    cur.execute(f"EXPLAIN (FORMAT JSON) SELECT 1 FROM {TABLE} WHERE {WHERE}", (ticker, year))
    plan_rows = cur.fetchone()[0][0]["Plan"]["Plan Rows"]
    band = P.decide_band(P.estimate_selectivity(plan_rows, n), T)
    if band != P.COUNT:
        return {"route": band, "count_used": False}
    cap = P.count_cap(T, n)
    cur.execute(f"SELECT count(*) FROM (SELECT 1 FROM {TABLE} WHERE {WHERE} LIMIT %s) x", (ticker, year, int(cap)))
    return {"route": P.decide_count(cur.fetchone()[0], cap), "count_used": True}


def timed(fn, *args):
    out = fn(*args)                                   # warm-up (untimed)
    times = []
    for _ in range(TIMED):
        t0 = time.perf_counter()
        fn(*args)
        times.append((time.perf_counter() - t0) * 1000)
    return out, times


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    T = json.loads((PROJECT_ROOT / "config/policy_v3_hm.json").read_text(encoding="utf-8"))["T_default"]
    cpu_start = host_load()
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    rows = []
    frozen = get_frozen_filepath()
    for q in load_finqa_subset(frozen):
        ticker, year = extract_ticker_year(q["id"])
        ex, ex_t = timed(exact_path, cur, ticker, year)
        rt, rt_t = timed(router_path, cur, ticker, year, T)
        rows.append({"query_id": q["id"], "matching_rows": ex["matching_rows"], "route": rt["route"], "count_used": rt["count_used"],
                     "exact_median_ms": statistics.median(ex_t), "exact_max_ms": max(ex_t), "exact_raw_ms": ex_t,
                     "router_median_ms": statistics.median(rt_t), "router_max_ms": max(rt_t), "router_raw_ms": rt_t})
    conn.close()
    cpu_end = host_load()

    with open(OUT / "timing.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    def summary(key):
        med = [r[f"{key}_median_ms"] for r in rows]
        allv = sorted(v for r in rows for v in r[f"{key}_raw_ms"])
        return {"median_of_question_medians_ms": statistics.median(med),
                "p95_of_question_medians_ms": statistics.quantiles(med, n=20, method="inclusive")[18],
                "max_of_question_maxes_ms": max(r[f"{key}_max_ms"] for r in rows),
                "median_all_reps_ms": statistics.median(allv),
                "p95_all_reps_ms": statistics.quantiles(allv, n=20, method="inclusive")[18]}

    meta = {"label": "read-only timing, no paid calls, no quiet rule", "utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git("rev-parse", "HEAD"), "table": TABLE, "T": T, "frozen_subset": frozen.as_posix(),
            "n_questions": len(rows), "warmup": 1, "timed_repetitions": TIMED, "clock": "client wall-clock, time.perf_counter",
            "cpu_start": cpu_start, "cpu_end": cpu_end,
            "exact_selectivity": summary("exact"), "router_v3": summary("router"),
            "router_routes": {r: sum(x["route"] == r for x in rows) for r in {x["route"] for x in rows}},
            "router_count_used": sum(x["count_used"] for x in rows)}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("cpu_start", "cpu_end", "exact_selectivity", "router_v3", "router_routes",
                                           "router_count_used")}, indent=1))


if __name__ == "__main__":
    main()
