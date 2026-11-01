"""VecAdvisor 0.1.0a6 adapter (Amendment 11 section 4). Amendment 9 defines none (D4: VecAdvisor was not scored on H&M).

decide(): per pair, `vecadvisor recommend --table edgar_chunks --vector embedding --query <filter literals> --q-vectors <the pair's
question vector> --limit 15 --ef-search 40` (read-only, no DDL; run from .venv-vecadvisor). The executed strategy is the
top-ranked candidate; if it requires a new database object (partial / partition index) the pair is `vecadvisor_unavailable`
(requires_new_object) and the next-ranked candidate without a new object runs (VecAdvisor's own ranking); a candidate whose
ef_search is outside pgvector's range (1 .. 1000) is skipped the same way (invalid_parameter; DEVIATION_LOG.md 2026-11-01); if recommend errors
or gives no usable candidate, the pair is `vecadvisor_unavailable` (error) and exact runs ("exact is the recall-safe fallback").
execute(): runs a strategy with VecAdvisor's own parameters, no guard, SQL shapes of retriever.py (iterative = MATERIALIZED CTE).
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from src import PROJECT_ROOT, db_settings
from src.phase_e_router import retriever as R

VECADVISOR = PROJECT_ROOT / ".venv-vecadvisor/Scripts/vecadvisor.exe"
EXEC_STRATEGIES = ("exact", "iterative_relaxed", "iterative_strict", "postfilter")
EF_SEARCH_MAX = 1000                                     # pgvector 0.8.3 hnsw.ef_search range 1 .. 1000
FORCED = {"enable_indexscan": "on", "enable_seqscan": "off", "enable_bitmapscan": "off", "enable_sort": "off"}


def filter_sql(filters) -> str:
    """Literal predicate for VecAdvisor's --query (values from edgar_chunks; quotes doubled)."""
    parts = []
    for col, vals in filters:
        lit = [str(int(v)) if col == "fiscal_year" else "'" + str(v).replace("'", "''") + "'" for v in vals]
        parts.append(f"{col} = {lit[0]}" if len(lit) == 1 else f"{col} IN ({', '.join(lit)})")
    return " AND ".join(parts)


def choose(report: dict | None, error: str | None = None) -> dict:
    """Strategy to execute from a recommend report (pure)."""
    if report is None or error:
        return {"strategy": "exact", "params": {}, "unavailable": True, "unavailable_reason": "error", "detail": (error or "")[:500],
                "recommended": None}
    ranked = report.get("recommendation", {}).get("ranked") or report.get("ranked") or []
    rec = report.get("recommendation", {}).get("decision", {}).get("recommended_strategy")
    if not ranked:
        return {"strategy": "exact", "params": {}, "unavailable": True, "unavailable_reason": "error", "detail": "no ranked candidates",
                "recommended": rec}
    top = ranked[0]
    skipped, pick = [], None
    for c in ranked:
        plan = c.get("plan") or {}
        if plan.get("requires_new_object"):
            skipped.append({"strategy": c["strategy"], "reason": "requires_new_object", "detail": plan["requires_new_object"]})
        elif (plan.get("ef_search") or 0) > EF_SEARCH_MAX:      # deviation log 2026-11-01: outside pgvector's range, same as new object
            skipped.append({"strategy": c["strategy"], "reason": "invalid_parameter", "detail": f"ef_search {plan['ef_search']}"})
        elif c["strategy"] in EXEC_STRATEGIES:
            pick = c
            break
    if pick is None:
        return {"strategy": "exact", "params": {}, "unavailable": True, "unavailable_reason": "error",
                "detail": "no ranked candidate that can run without a new object", "recommended": rec, "skipped": skipped}
    plan = pick.get("plan") or {}
    hint = plan.get("sql_hint") or ""
    m = re.search(r"hnsw\.max_scan_tuples\s*=\s*(\d+)", hint)
    params = {"ef_search": plan.get("ef_search"), "max_scan_tuples": int(m.group(1)) if m else None}
    reasons = {s["reason"] for s in skipped}
    reason = None if pick is top else ("invalid_parameter" if "invalid_parameter" in reasons else "requires_new_object")
    out = {"strategy": pick["strategy"], "params": params, "recommended": rec, "top_ranked": top["strategy"],
           "unavailable": pick is not top, "unavailable_reason": reason,
           "detail": (top.get("plan") or {}).get("requires_new_object") if pick is not top else None, "skipped": skipped}
    if pick["strategy"] != "exact" and not params["ef_search"]:
        raise ValueError(f"strategy {pick['strategy']} without ef_search: {plan}")
    return out


def decide(filters, query_vector, table="edgar_chunks", k=15, ef_search=40) -> dict:
    """Run recommend once; returns the choice plus the redacted report and the wall time."""
    s = db_settings()
    dsn = f"postgresql://{s['user']}:{s['password']}@{s['host']}:{s['port']}/{s['dbname']}"
    with tempfile.TemporaryDirectory() as td:
        qf = Path(td) / "q.jsonl"
        qf.write_text(json.dumps(list(query_vector)) + "\n", encoding="utf-8")
        t0 = time.perf_counter()
        r = subprocess.run([str(VECADVISOR), "recommend", "--dsn", dsn, "--table", table, "--vector", "embedding",
                            "--query", filter_sql(filters), "--q-vectors", str(qf), "--limit", str(k), "--ef-search", str(ef_search)],
                           capture_output=True, text=True, encoding="utf-8")
        ms = (time.perf_counter() - t0) * 1000
    redact = lambda t: (t or "").replace(dsn, "postgresql://***").replace(s["password"], "***")
    report, err = None, None
    if r.returncode != 0:
        err = f"exit {r.returncode}: {redact(r.stderr)[-800:]}"
    else:
        try:
            report = json.loads(r.stdout)
        except json.JSONDecodeError as e:
            err = f"unparseable output: {e}"
    ch = choose(report, err)
    if report is not None:
        report = json.loads(redact(json.dumps(report)))
    return {**ch, "decision_ms": ms, "report": report}


def strategy_settings(choice: dict, config) -> tuple[str, dict]:
    """(retriever route whose SQL shape is used, SET LOCAL settings)."""
    st, p = choice["strategy"], choice["params"]
    if st == "exact":
        return R.R_EXACT, R.route_settings(R.R_EXACT, config)
    if st in ("iterative_relaxed", "iterative_strict"):
        s = {**FORCED, "hnsw.iterative_scan": "relaxed_order" if st == "iterative_relaxed" else "strict_order",
             "hnsw.ef_search": p["ef_search"]}
        if p.get("max_scan_tuples"):
            s["hnsw.max_scan_tuples"] = p["max_scan_tuples"]
        return R.R_ITER, s
    if st == "postfilter":
        return R.R_HNSW, {**FORCED, "hnsw.iterative_scan": "off", "hnsw.ef_search": p["ef_search"]}
    raise ValueError(f"unknown strategy {st!r}")


def execute(conn, choice, table, filters, k, qv, config):
    """Run the chosen strategy in its own transaction. Returns (rows, wall ms, route shape)."""
    route, settings = strategy_settings(choice, config)
    sql, params = R.route_sql(route, table, filters, k, qv, config)
    t0 = time.perf_counter()
    try:
        with conn.cursor() as cur:
            R._set_local(cur, settings)
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rows, (time.perf_counter() - t0) * 1000, route


def explain(conn, choice, table, filters, k, qv, config) -> dict:
    route, settings = strategy_settings(choice, config)
    sql, params = R.route_sql(route, table, filters, k, qv, config)
    try:
        with conn.cursor() as cur:
            R._set_local(cur, settings)
            cur.execute(f"EXPLAIN (FORMAT JSON) {sql}", params)
            plan = cur.fetchone()[0][0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return R.check_plan(route, plan, config)
