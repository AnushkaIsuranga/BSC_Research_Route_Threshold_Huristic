"""Phase E retriever (Amendment 9): executes routes on PostgreSQL/pgvector and records a trace.

retrieve(query_vector, filters, k, mode, config, conn=..., table=...) -> (rows, trace)

- filters: list of [column, [values]] (the `conditions` of the filters.json files); AND across columns, IN for >1 value.
- Every route runs in its own transaction with SET LOCAL; nothing is set at session level except jit and statement_timeout.
- No silent fallbacks: missing statistics, a missing T, an unknown mode or a missing LLM decision raise.

Imports only src (db settings) and policy_v3; never src.phase_a_sweep.logger or sweep_orchestrator.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_e_router import policy_v3 as P

EXACT, ITERATIVE = P.EXACT, P.ITERATIVE
# executable routes (SQL + settings)
R_EXACT, R_ITER, R_ITER_TUNED, R_HNSW, R_PLANNER_ITER, R_PROBE = ("exact", "iterative_default", "iterative_tuned", "hnsw",
                                                                  "planner_iterative", "probe")
MODES = ("router", "router_tuned", "router_no_guard", "router_always_count", "fixed_t_0_1", "local_probe",
         "router_plus_probe", "iterative_tuned", "default_hnsw", "planner_iterative", "retry_exact", "always_exact",
         "always_iterative", "llm_router")
LLM_ROUTES = {"pre-filter": R_EXACT, "post-filter": R_HNSW}   # Amendment 9 D5


class RetrieverError(RuntimeError):
    pass


@dataclass
class RouterConfig:
    raw: dict
    T_default: float | None = None
    T_tuned: float | None = None
    llm_routes: dict = field(default_factory=dict)   # filter key -> "pre-filter" / "post-filter" (decided offline)

    @classmethod
    def load(cls, path="config/router_hm.json", policy_path: str | None = None, require_policy=False) -> "RouterConfig":
        raw = json.loads((PROJECT_ROOT / path).read_text(encoding="utf-8"))
        cfg = cls(raw)
        pp = PROJECT_ROOT / (policy_path or raw["policy_file"])
        if pp.exists():
            pol = json.loads(pp.read_text(encoding="utf-8"))
            cfg.T_default, cfg.T_tuned = pol["T_default"], pol["T_tuned"]
        elif require_policy:
            raise RetrieverError(f"policy file {pp} not found")
        return cfg

    def __getitem__(self, key):
        return self.raw[key]


def connect():
    """Non-autocommit connection (routes use SET LOCAL inside a transaction); loads the pgvector library so hnsw.* GUCs
    are real settings, then sets jit and statement_timeout for the session."""
    conn = psycopg2.connect(**db_settings())
    with conn.cursor() as cur:
        cur.execute("SELECT '[1,2]'::vector <-> '[1,3]'::vector")
    conn.commit()
    return conn


def configure_session(conn, config: RouterConfig):
    with conn.cursor() as cur:
        cur.execute(f"SET jit = {config['jit']}")
        cur.execute(f"SET statement_timeout = {int(config['statement_timeout_ms'])}")
    conn.commit()


def vec_literal(v) -> str:
    return v if isinstance(v, str) else "[" + ",".join(map(str, v)) + "]"


def filter_key(filters) -> str:
    return json.dumps([[c, list(v)] for c, v in filters], sort_keys=False)


def where_clause(filters, config: RouterConfig):
    if not filters:
        raise RetrieverError("empty filter")
    allowed = set(config["filter_columns"])
    parts, params = [], []
    for col, values in filters:
        if col not in allowed:
            raise RetrieverError(f"column {col!r} not in config filter_columns")
        values = list(values)
        if not values:
            raise RetrieverError(f"no values for {col}")
        parts.append(f"{col} = %s" if len(values) == 1 else f"{col} IN ({', '.join(['%s'] * len(values))})")
        params.extend(values)
    return " AND ".join(parts), params


def _check_table(table, config):
    if table not in config["tables"]:
        raise RetrieverError(f"table {table!r} not in config tables")


def route_settings(route: str, config: RouterConfig) -> dict:
    ef = config["ef_search"]
    forced = {"enable_indexscan": "on", "enable_seqscan": "off", "enable_bitmapscan": "off", "enable_sort": "off"}
    if route == R_EXACT:
        return {"enable_indexscan": "off", "hnsw.iterative_scan": "off", "hnsw.ef_search": ef}
    if route in (R_ITER, R_ITER_TUNED):
        it = config["iterative_default" if route == R_ITER else "iterative_tuned"]
        return {**forced, "hnsw.iterative_scan": "relaxed_order", "hnsw.ef_search": ef,
                "hnsw.max_scan_tuples": it["max_scan_tuples"], "hnsw.scan_mem_multiplier": it["scan_mem_multiplier"]}
    if route == R_HNSW:
        return {**forced, "hnsw.iterative_scan": "off", "hnsw.ef_search": ef}
    if route == R_PLANNER_ITER:
        return {"hnsw.iterative_scan": "relaxed_order", "hnsw.ef_search": ef}
    if route == R_PROBE:
        return {**forced, "hnsw.iterative_scan": "off", "hnsw.ef_search": config["probe"]["ef_search"]}
    raise RetrieverError(f"unknown route {route!r}")


def route_sql(route: str, table: str, filters, k: int, qv: str, config: RouterConfig):
    """(sql, params) of a route. Iterative routes use the MATERIALIZED CTE re-sorted by distance (D6)."""
    _check_table(table, config)
    idc, ve, cast, op = config["id_column"], config["vector_expr"], config["query_cast"], config["distance_operator"]
    dist = f"{ve} {op} %s::{cast}"
    if route == R_PROBE:
        w, wp = where_clause(filters, config)
        return (f"SELECT {idc}, COALESCE(({w}), false) AS passes FROM {table} ORDER BY {dist} LIMIT %s",
                [*wp, qv, int(config["probe"]["m"])])
    w, wp = where_clause(filters, config)
    if route == R_EXACT:
        return (f"SELECT {idc}, {dist} AS d FROM {table} WHERE {w} ORDER BY d, {idc} LIMIT %s", [qv, *wp, k])
    if route == R_HNSW:
        return (f"SELECT {idc}, {dist} AS d FROM {table} WHERE {w} ORDER BY {dist} LIMIT %s", [qv, *wp, qv, k])
    if route in (R_ITER, R_ITER_TUNED, R_PLANNER_ITER):
        return (f"WITH c AS MATERIALIZED (SELECT {idc}, {dist} AS d FROM {table} WHERE {w} ORDER BY {dist} LIMIT %s) "
                f"SELECT {idc}, d FROM c ORDER BY d, {idc}", [qv, *wp, qv, k])
    raise RetrieverError(f"unknown route {route!r}")


def _set_local(cur, settings: dict):
    cur.execute(";".join(f"SET LOCAL {g} = '{v}'" for g, v in settings.items()))


def run_route(conn, route, table, filters, k, qv, config):
    """Execute one route in its own transaction. Returns (rows [(id, distance)], wall ms)."""
    sql, params = route_sql(route, table, filters, k, qv, config)
    t0 = time.perf_counter()
    try:
        with conn.cursor() as cur:
            _set_local(cur, route_settings(route, config))
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rows, (time.perf_counter() - t0) * 1000


def explain_route(conn, route, table, filters, k, qv, config, analyze=False):
    """Plain EXPLAIN (pre-flight) or EXPLAIN ANALYZE (timing) of a route under its settings. Returns the plan JSON."""
    sql, params = route_sql(route, table, filters, k, qv, config)
    opts = "ANALYZE, FORMAT JSON, BUFFERS, TIMING" if analyze else "FORMAT JSON"
    try:
        with conn.cursor() as cur:
            _set_local(cur, route_settings(route, config))
            cur.execute(f"EXPLAIN ({opts}) {sql}", params)
            plan = cur.fetchone()[0][0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return plan


def plan_nodes(plan: dict) -> list:
    out = [plan]
    for c in plan.get("Plans", []):
        out += plan_nodes(c)
    return out


def check_plan(route: str, plan_json: dict, config: RouterConfig) -> dict:
    """D6 pre-flight: exact = Seq/Bitmap Heap Scan and no HNSW index; iterative/hnsw/probe = Index Scan on *embedding_idx
    (a Sort above the CTE allowed); planner_iterative has no expectation."""
    nodes = plan_nodes(plan_json["Plan"])
    types = [n.get("Node Type") for n in nodes]
    suffix = config["hnsw_index_suffix"]
    hnsw = [n for n in nodes if n.get("Node Type") == "Index Scan" and (n.get("Index Name") or "").endswith(suffix)]
    if route == R_EXACT:
        ok = any(t in ("Seq Scan", "Bitmap Heap Scan") for t in types) and not hnsw
    elif route in (R_ITER, R_ITER_TUNED):
        cte = [n for n in nodes if n.get("Subplan Name", "").startswith("CTE")]
        ok = bool(cte) and any(n.get("Node Type") == "Index Scan" and (n.get("Index Name") or "").endswith(suffix)
                               for n in plan_nodes(cte[0])) and set(types) <= {"Sort", "CTE Scan", "Limit", "Index Scan"}
    elif route in (R_HNSW, R_PROBE):
        ok = bool(hnsw) and "Sort" not in types and not any(t in ("Seq Scan", "Bitmap Heap Scan") for t in types)
    elif route == R_PLANNER_ITER:
        ok = None
    else:
        raise RetrieverError(f"unknown route {route!r}")
    scan = next((n for n in nodes if n.get("Node Type") in ("Seq Scan", "Index Scan", "Bitmap Heap Scan", "Index Only Scan")), {})
    return {"route": route, "ok": ok, "plan_nodes": "/".join(types), "scan_node": scan.get("Node Type"),
            "index_used": scan.get("Index Name") or next((n.get("Index Name") for n in nodes if n.get("Index Name")), None)}


# ---------------------------------------------------------------- decision steps

def estimate(conn, table, filters, config):
    """(s_est, plan_rows, N, ms). Errors on missing statistics."""
    _check_table(table, config)
    w, wp = where_clause(filters, config)
    t0 = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT reltuples FROM pg_class WHERE oid = %s::regclass", (table,))
            r = cur.fetchone()
            cur.execute(f"EXPLAIN (FORMAT JSON) SELECT 1 FROM {table} WHERE {w}", wp)
            plan = cur.fetchone()[0][0]["Plan"]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    ms = (time.perf_counter() - t0) * 1000
    n = None if r is None else r[0]
    s_est = P.estimate_selectivity(plan.get("Plan Rows"), n)
    return s_est, plan.get("Plan Rows"), n, ms


def capped_count(conn, table, filters, cap, config):
    _check_table(table, config)
    w, wp = where_clause(filters, config)
    t0 = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM (SELECT 1 FROM {table} WHERE {w} LIMIT %s) x", [*wp, int(cap)])
            c = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return c, (time.perf_counter() - t0) * 1000


def probe(conn, table, filters, qv, config):
    """Unfiltered HNSW top-m; returns (p, m_returned, ms)."""
    rows, ms = run_route(conn, R_PROBE, table, filters, None, qv, config)
    return sum(1 for _, passes in rows if passes), len(rows), ms


def reltuples(conn, table):
    with conn.cursor() as cur:
        cur.execute("SELECT reltuples FROM pg_class WHERE oid = %s::regclass", (table,))
        r = cur.fetchone()[0]
    conn.commit()
    return r


# ---------------------------------------------------------------- retrieve

def _band_decision(conn, table, filters, T, config, trace, always_count=False):
    """Band rule (or count-only). Fills the trace; returns exact/iterative."""
    trace["T"] = T
    if always_count:
        n = reltuples(conn, table)
        if n is None or n == -1 or n <= 0:
            raise P.PolicyInputError(f"reltuples = {n}: no statistics")
        trace["N"] = n
        band = P.COUNT
    else:
        s_est, plan_rows, n, ms = estimate(conn, table, filters, config)
        trace.update({"s_est": s_est, "plan_rows": plan_rows, "N": n, "estimate_ms": ms})
        band = P.decide_band(s_est, T)
    trace["band"] = band
    if band != P.COUNT:
        return band
    cap = P.count_cap(T, trace["N"])
    c, ms = capped_count(conn, table, filters, cap, config)
    trace.update({"count": c, "count_cap": cap, "count_ms": ms})
    return P.decide_count(c, cap)


def _execute(conn, route, table, filters, k, qv, config, trace, guard: bool):
    rows, ms = run_route(conn, route, table, filters, k, qv, config)
    trace["routes_executed"].append(route)
    trace["route_ms"].append(ms)
    if guard and route != R_EXACT and len(rows) < k:
        trace["guard_triggered"] = True
        trace["guard_first_rows"] = len(rows)
        rows, ms = run_route(conn, R_EXACT, table, filters, k, qv, config)
        trace["routes_executed"].append(R_EXACT)
        trace["route_ms"].append(ms)
        trace["guard_added_ms"] = ms
    if route == R_EXACT or trace["guard_triggered"]:
        trace["filter_smaller_than_k"] = len(rows) < k
    return rows


def retrieve(query_vector, filters, k, mode, config: RouterConfig, *, conn, table):
    """Returns (rows, trace). rows = [(id, distance)] sorted by distance (ties by id on exact/iterative routes)."""
    if mode not in MODES:
        raise RetrieverError(f"unknown mode {mode!r}")
    qv = vec_literal(query_vector)
    trace: dict[str, Any] = {"mode": mode, "table": table, "k": k, "decided": None, "routes_executed": [], "route_ms": [],
                             "guard": False, "guard_triggered": False, "filter_smaller_than_k": None}
    t0 = time.perf_counter()

    def need(T, name):
        if T is None:
            raise RetrieverError(f"{name} is not set (calibration not loaded); mode {mode} cannot run")
        return T

    guard = mode not in ("router_no_guard", "default_hnsw", "planner_iterative", "always_exact", "always_iterative", "llm_router")
    trace["guard"] = guard
    if mode in ("router", "router_no_guard", "router_always_count", "fixed_t_0_1", "router_plus_probe"):
        T = config["fixed_T"] if mode == "fixed_t_0_1" else need(config.T_default, "T_default")
        decided = _band_decision(conn, table, filters, T, config, trace, always_count=mode == "router_always_count")
        if mode == "router_plus_probe":
            p, m, ms = probe(conn, table, filters, qv, config)
            trace.update({"probe_p": p, "probe_m": m, "probe_ms": ms, "router_route": decided})
            decided = P.combine_with_probe(decided, p, k)
        route = R_EXACT if decided == EXACT else R_ITER
    elif mode == "router_tuned":
        decided = _band_decision(conn, table, filters, need(config.T_tuned, "T_tuned"), config, trace)
        route = R_EXACT if decided == EXACT else R_ITER_TUNED
    elif mode == "local_probe":
        p, m, ms = probe(conn, table, filters, qv, config)
        trace.update({"probe_p": p, "probe_m": m, "probe_ms": ms})
        decided = P.local_probe_route(p, k)
        route = R_EXACT if decided == EXACT else R_ITER
    elif mode == "llm_router":
        key = filter_key(filters)
        if key not in config.llm_routes:
            raise RetrieverError(f"no LLM decision recorded for filter {key}")
        decided = config.llm_routes[key]
        if decided not in LLM_ROUTES:
            raise RetrieverError(f"LLM route {decided!r} not in the vocabulary")
        route = LLM_ROUTES[decided]
    else:
        route = {"iterative_tuned": R_ITER_TUNED, "default_hnsw": R_HNSW, "planner_iterative": R_PLANNER_ITER,
                 "retry_exact": R_HNSW, "always_exact": R_EXACT, "always_iterative": R_ITER}[mode]
        decided = route
    trace["decided"] = decided
    trace["plan_name"] = route
    rows = _execute(conn, route, table, filters, k, qv, config, trace, guard)
    trace["rows_returned"] = len(rows)
    trace["total_ms"] = (time.perf_counter() - t0) * 1000
    return rows, trace
