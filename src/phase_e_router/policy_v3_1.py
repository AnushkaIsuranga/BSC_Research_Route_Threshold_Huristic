"""policy_v3.1 (Phase F, Amendment 11): policy_v3 (Amendment 9) unchanged except one rule.

No-statistics rule: before the planner estimate is used, every column or expression the filter references must have planner
statistics -- a pg_stats row for a plain column; for a JSONB / expression filter, an expression statistic of an extended
statistics object (pg_stats_ext_exprs) or the statistics of an expression index (pg_stats row of the index) on the same
expression. If any is missing, the estimate is skipped and the capped count `SELECT count(*) FROM (SELECT 1 ... LIMIT
floor(T*N)+1)` decides directly (count == cap -> iterative, else exact). The trace records
`estimate_skipped_no_stats` and the missing references. Everything else (band edges T/2 and 2T, the count, the guard, the
probe, routes and SQL) is policy_v3 / retriever.py as frozen; non-band modes are delegated to retriever.retrieve unchanged.

Filters reference config `filter_columns` (plain columns); a config may map a filter name to an SQL expression in
`filter_expressions` (e.g. {"ticker": "metadata->>'ticker'"}); the stats check then looks for statistics on that expression.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from src.phase_e_router import policy_v3 as P
from src.phase_e_router import retriever as R

SKIP_FIELD = "estimate_skipped_no_stats"
BAND_MODES = ("router", "router_no_guard", "fixed_t_0_1", "router_plus_probe", "router_tuned")


def _norm(expr: str) -> str:
    """Whitespace-free, lower-case form of a deparsed expression, outer parentheses removed."""
    s = re.sub(r"\s+", "", expr or "").lower()
    while s.startswith("(") and s.endswith(")") and _balanced(s[1:-1]):
        s = s[1:-1]
    return s


def _balanced(s: str) -> bool:
    depth = 0
    for ch in s:
        depth += ch == "("
        depth -= ch == ")"
        if depth < 0:
            return False
    return depth == 0


def refs_for(filters, config) -> list[dict]:
    """[{"name", "kind": column|expression, "sql"}] for the filter's references (order kept, duplicates dropped)."""
    exprs = config.raw.get("filter_expressions", {}) if hasattr(config, "raw") else config.get("filter_expressions", {})
    out, seen = [], set()
    for col, _ in filters:
        if col in seen:
            continue
        seen.add(col)
        out.append({"name": col, "kind": "expression", "sql": exprs[col]} if col in exprs else {"name": col, "kind": "column", "sql": col})
    return out


def missing_statistics(cur, table: str, refs: list[dict]) -> list[str]:
    """Names of the references without planner statistics (catalog reads only)."""
    missing = []
    for ref in refs:
        if ref["kind"] == "column":
            cur.execute("SELECT 1 FROM pg_stats WHERE schemaname = current_schema() AND tablename = %s AND attname = %s",
                        (table, ref["sql"]))
            if cur.fetchone() is None:
                missing.append(ref["name"])
            continue
        cur.execute(f"EXPLAIN (VERBOSE, FORMAT JSON) SELECT {ref['sql']} FROM {table} LIMIT 0")
        target = _norm(cur.fetchone()[0][0]["Plan"]["Output"][0])
        cur.execute("SELECT expr FROM pg_stats_ext_exprs WHERE schemaname = current_schema() AND tablename = %s", (table,))
        covered = any(_norm(e) == target for (e,) in cur.fetchall())
        if not covered:
            cur.execute("""SELECT ic.relname, pg_get_indexdef(i.indexrelid, k, true)
                           FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid
                           CROSS JOIN LATERAL generate_series(1, i.indnkeyatts) k
                           WHERE i.indrelid = %s::regclass AND i.indexprs IS NOT NULL""", (table,))
            for idx, col_def in cur.fetchall():
                if _norm(col_def) == target:
                    cur.execute("SELECT 1 FROM pg_stats WHERE schemaname = current_schema() AND tablename = %s", (idx,))
                    if cur.fetchone() is not None:
                        covered = True
                        break
        if not covered:
            missing.append(ref["name"])
    return missing


def decide(conn, table: str, where: str, params: list, refs: list[dict], T, trace: dict) -> str:
    """policy_v3.1 band decision for one filter (SQL shapes as retriever.estimate / capped_count). Fills the trace."""
    trace["T"] = T
    t0 = time.perf_counter()
    try:
        with conn.cursor() as cur:
            miss = missing_statistics(cur, table, refs)
            cur.execute("SELECT reltuples FROM pg_class WHERE oid = %s::regclass", (table,))
            r = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    n = None if r is None else r[0]
    trace.update({"stats_check_ms": (time.perf_counter() - t0) * 1000, SKIP_FIELD: bool(miss), "stats_missing": miss})
    if miss:
        if n is None or n == -1 or n <= 0:
            raise P.PolicyInputError(f"reltuples = {n}: no statistics")
        trace["N"] = n
        band = P.COUNT
    else:
        t1 = time.perf_counter()
        try:
            with conn.cursor() as cur:
                cur.execute(f"EXPLAIN (FORMAT JSON) SELECT 1 FROM {table} WHERE {where}", params)
                plan = cur.fetchone()[0][0]["Plan"]
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        s_est = P.estimate_selectivity(plan.get("Plan Rows"), n)
        trace.update({"s_est": s_est, "plan_rows": plan.get("Plan Rows"), "N": n, "estimate_ms": (time.perf_counter() - t1) * 1000})
        band = P.decide_band(s_est, T)
    trace["band"] = band
    if band != P.COUNT:
        return band
    cap = P.count_cap(T, trace["N"])
    t2 = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM (SELECT 1 FROM {table} WHERE {where} LIMIT %s) x", [*params, int(cap)])
            c = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    trace.update({"count": c, "count_cap": cap, "count_ms": (time.perf_counter() - t2) * 1000})
    return P.decide_count(c, cap)


def where_clause(filters, config):
    """retriever.where_clause, except that a name listed in config filter_expressions is written as its expression.
    For plain columns the output is identical to retriever.where_clause."""
    exprs = config.raw.get("filter_expressions", {})
    if not exprs:
        return R.where_clause(filters, config)
    w, wp = R.where_clause(filters, config)
    for name, sql in exprs.items():
        w = re.sub(rf"(?<![\w']){re.escape(name)}(?= (?:=|IN) )", lambda _: sql, w)
    return w, wp


def band_decision(conn, table, filters, T, config, trace) -> str:
    R._check_table(table, config)
    w, wp = where_clause(filters, config)
    return decide(conn, table, w, wp, refs_for(filters, config), T, trace)


def retrieve(query_vector, filters, k, mode, config: R.RouterConfig, *, conn, table):
    """retriever.retrieve with the v3.1 band decision; every other mode is retriever.retrieve unchanged."""
    if mode not in BAND_MODES:
        return R.retrieve(query_vector, filters, k, mode, config, conn=conn, table=table)
    qv = R.vec_literal(query_vector)
    trace: dict[str, Any] = {"mode": mode, "policy": "v3.1", "table": table, "k": k, "decided": None, "routes_executed": [],
                             "route_ms": [], "guard": mode != "router_no_guard", "guard_triggered": False,
                             "filter_smaller_than_k": None}
    t0 = time.perf_counter()

    def need(T, name):
        if T is None:
            raise R.RetrieverError(f"{name} is not set (calibration not loaded); mode {mode} cannot run")
        return T

    if mode == "router_tuned":
        decided = band_decision(conn, table, filters, need(config.T_tuned, "T_tuned"), config, trace)
        route = R.R_EXACT if decided == P.EXACT else R.R_ITER_TUNED
    else:
        T = config["fixed_T"] if mode == "fixed_t_0_1" else need(config.T_default, "T_default")
        decided = band_decision(conn, table, filters, T, config, trace)
        if mode == "router_plus_probe":
            p, m, ms = R.probe(conn, table, filters, qv, config)
            trace.update({"probe_p": p, "probe_m": m, "probe_ms": ms, "router_route": decided})
            decided = P.combine_with_probe(decided, p, k)
        route = R.R_EXACT if decided == P.EXACT else R.R_ITER
    trace["decided"] = decided
    trace["plan_name"] = route
    rows = R._execute(conn, route, table, filters, k, qv, config, trace, trace["guard"])
    trace["rows_returned"] = len(rows)
    trace["total_ms"] = (time.perf_counter() - t0) * 1000
    return rows, trace


def load_policy_T(path) -> dict:
    """T_default / T_tuned of a policy file (None while not calibrated)."""
    from src import PROJECT_ROOT
    d = json.loads((PROJECT_ROOT / path).read_text(encoding="utf-8"))
    return {"T_default": d.get("T_default"), "T_tuned": d.get("T_tuned")}
