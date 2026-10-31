"""Read-only: the Phase E router's selectivity path and decision on the frozen 50 FinQA questions (finqa_evidence_qwen3),
plus a comparison of the two FinQA selectivity functions on all 1,147 test questions. No retrieval, no model calls, no
timed measurements. The session is read-only (SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY).

Estimate as in retriever.estimate(): EXPLAIN (FORMAT JSON) SELECT 1 FROM <table> WHERE <filter>, s_est = Plan Rows /
reltuples; band = policy_v3.decide_band(s_est, T); capped count (retriever.capped_count SQL shape) only in the count band.

  python -m src.phase_e_router.finqa_route_check
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.local_ollama_runner import estimate_selectivity as census_selectivity
from src.phase_e_router import policy_v3 as P
from src.phase_e_router.cells import git
from src.utils.finqa_utils import exact_selectivity, extract_ticker_year

TABLE = "finqa_evidence_qwen3"
WHERE = "metadata->>'ticker' = %s AND metadata->>'year' = %s"
OUT = PROJECT_ROOT / "outputs" / "finqa_router_v3_route_check_2026-10-31"


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    policy = json.loads((PROJECT_ROOT / "config/policy_v3_hm.json").read_text(encoding="utf-8"))
    T = policy["T_default"]
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    cur.execute("SELECT reltuples FROM pg_class WHERE oid = %s::regclass", (TABLE,))
    n = cur.fetchone()[0]
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    n_actual = cur.fetchone()[0]

    frozen_path = get_frozen_filepath()
    rows = []
    for q in load_finqa_subset(frozen_path):
        ticker, year = extract_ticker_year(q["id"])
        s_exact, match, total = exact_selectivity(conn, ticker, year)          # existing function (table finqa_evidence)
        cur.execute(f"SELECT count(*) FROM {TABLE} WHERE {WHERE}", (ticker, year))
        match_qwen3 = cur.fetchone()[0]
        cur.execute(f"EXPLAIN (FORMAT JSON) SELECT 1 FROM {TABLE} WHERE {WHERE}", (ticker, year))
        plan_rows = cur.fetchone()[0][0]["Plan"]["Plan Rows"]
        s_est = P.estimate_selectivity(plan_rows, n)
        band = P.decide_band(s_est, T)
        count = cap = None
        if band == P.COUNT:
            cap = P.count_cap(T, n)
            cur.execute(f"SELECT count(*) FROM (SELECT 1 FROM {TABLE} WHERE {WHERE} LIMIT %s) x", (ticker, year, int(cap)))
            count = cur.fetchone()[0]
            route = P.decide_count(count, cap)
        else:
            route = band
        rows.append({"query_id": q["id"], "ticker": ticker, "year": year, "matching_rows": match,
                     "matching_rows_qwen3": match_qwen3, "s_exact": s_exact, "plan_rows": plan_rows, "s_est": s_est,
                     "est_over_exact": s_est / s_exact, "band": band, "count_used": count is not None, "count": count,
                     "count_cap": cap, "route": route, "route_from_exact_s": P.decide_from_full_count(match, T, n)})

    with open(OUT / "route_check.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # (b) census function (returns 0 on no match) vs exact_selectivity (raises) on all test questions
    dataset = json.loads((PROJECT_ROOT / "data/raw/finqa_test.json").read_text(encoding="utf-8"))
    cur.execute("SELECT count(*) FROM finqa_evidence")
    corpus = cur.fetchone()[0]
    disagree, raised, n_q = [], [], 0
    for ex in dataset:
        n_q += 1
        ticker, year = extract_ticker_year(ex["id"])
        c = census_selectivity(conn, ticker, year, corpus)
        try:
            e = exact_selectivity(conn, ticker, year)[0]
        except RuntimeError as err:
            raised.append({"id": ex["id"], "census": c, "error": str(err)})
            continue
        if c != e:
            disagree.append({"id": ex["id"], "census": c, "exact": e})
    conn.close()

    meta = {"label": "read-only check, no paid calls, no timed measurements", "utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git("rev-parse", "HEAD"), "table": TABLE, "reltuples": n, "actual_rows": n_actual, "T": T,
            "T_source": "config/policy_v3_hm.json T_default", "band_edges": [T / 2, 2 * T], "count_cap": P.count_cap(T, n),
            "frozen_subset": frozen_path.as_posix(), "n_questions": len(rows),
            "routes": {r: sum(x["route"] == r for x in rows) for r in {x["route"] for x in rows}},
            "bands": {b: sum(x["band"] == b for x in rows) for b in {x["band"] for x in rows}},
            "plan_rows_distinct": sorted({x["plan_rows"] for x in rows}),
            "est_over_exact_min": min(x["est_over_exact"] for x in rows), "est_over_exact_max": max(x["est_over_exact"] for x in rows),
            "qwen3_counts_equal_finqa_evidence": all(x["matching_rows"] == x["matching_rows_qwen3"] for x in rows),
            "census_vs_exact": {"questions": n_q, "corpus_rows": corpus, "exact_raised": raised, "value_disagreements": disagree}}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items() if k != "census_vs_exact"}, indent=1))
    print("census_vs_exact:", n_q, "raised", len(raised), "disagree", len(disagree))


if __name__ == "__main__":
    main()
