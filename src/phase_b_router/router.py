"""LangGraph routing graphs for the FinQA validation (Phase D).

Three arms share the same retrieval and answer nodes; only the routing node differs:
  * Decision Matrix  -- original policy.py (route names pre-filter / post-filter / iterative-scan)
  * policy_v2        -- policy_v2.py       (route names exact / iterative-relaxed)
  * Naive LLM router -- structured JSON {"route": "pre-filter"|"post-filter", "reason": str}

Nothing here substitutes a default for a failure: database/LLM/embedding errors propagate. The one
non-exception outcome is a naive-router output that fails schema validation: it is recorded in the
state (route_parse_failure, router_raw) and the graph ends without retrieval or answer.
Every graph accumulates the same cost/token/latency fields in RouterState (parity).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, List, TypedDict

from langgraph.graph import END, StateGraph

from src.phase_b_router.policy import get_routing_decision
from src.phase_b_router.policy_v2 import get_routing_decision_v2

NAIVE_ROUTES = ("pre-filter", "post-filter")
NAIVE_ROUTER_SYSTEM = (
    "You are the router of a vector database. Decide how to apply a metadata filter (company ticker and "
    "fiscal year) to the vector search for the user's question. 'pre-filter' applies the filter first and "
    "searches only the matching rows; 'post-filter' searches the whole index first and applies the filter "
    "afterwards. Reply with JSON only, exactly: {\"route\": \"pre-filter\" or \"post-filter\", \"reason\": \"<one short sentence>\"}"
)
ANSWER_SYSTEM = (
    "You solve FinQA questions. Use only the supplied evidence. Return only the final numeric or boolean "
    "answer, with no explanation. Preserve percentages when the answer is a percentage."
)


class RouterState(TypedDict, total=False):
    query_id: str
    ticker: str
    year: str
    question: str
    gold_evidence_keys: List[str]
    estimated_selectivity: float
    correlation_level: str
    # routing
    chosen_route: str
    router_raw: str
    router_reason: str
    route_parse_failure: bool
    router_ms: float
    router_input_tokens: int
    router_output_tokens: int
    router_thinking_tokens: int
    # retrieval
    embed_ms: float
    db_ms: float
    retrieved_evidence_keys: List[str]
    retrieved_ids: List[int]
    retrieved_distances: List[float]
    rows_returned: int
    rows_fetched: int
    tie_truncated: bool
    distinct_dropped: int
    # generation
    raw_output: str
    generation_ms: float
    gen_input_tokens: int
    gen_output_tokens: int
    gen_thinking_tokens: int
    # cost parity
    cost_usd: float
    settings_used: dict


@dataclass
class Deps:
    conn: Any                              # psycopg2 connection, autocommit, pgvector registered
    embed: Callable[[str], list]           # question -> vector
    router_client: Any                     # LLMClient used by the naive router
    answer_client: Any                     # LLMClient used to answer
    k: int
    router_max_tokens: int
    answer_max_tokens: int
    table: str = "finqa_evidence"
    distinct: bool = False


def validate_naive_route(text: str) -> tuple[dict | None, str | None]:
    """Schema: object with exactly keys route (pre-filter|post-filter) and reason (str)."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, f"not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "JSON is not an object"
    if set(data) != {"route", "reason"}:
        return None, f"keys {sorted(data)} != ['reason', 'route']"
    if data["route"] not in NAIVE_ROUTES:
        return None, f"route {data['route']!r} not in {NAIVE_ROUTES}"
    if not isinstance(data["reason"], str):
        return None, "reason is not a string"
    return data, None


INDEX_FETCH_FACTOR = 2
DISTINCT_INDEX_FETCH_FACTOR = 10
DISTINCT_MIN_FETCH = 40  # = hnsw.ef_search: a non-iterative index scan never offers more candidates than this


def retrieve(conn, route: str, ticker: str, year: str, vector: list, k: int, table: str = "finqa_evidence",
             distinct: bool = False) -> dict:
    """Deterministic retrieval. Returns {rows, rows_fetched, tie_truncated, distinct_dropped};
    rows = (id, query_id, evidence_key, content, distance).

    Ties (identical embeddings are common: each passage appears on several pages) are broken by the unique row id.
    * exact (pre-filter): SQL ORDER BY distance, id (sequential scan + sort).
    * index routes (post-filter, iterative): adding ", id" to ORDER BY makes the planner abandon the HNSW index, so the
      index query keeps ORDER BY distance only, fetches INDEX_FETCH_FACTOR * k rows, and the (distance, id) sort + cut to k
      is done here. tie_truncated is True if the tie group at the k-th distance may extend past the fetched rows.
    distinct=True returns k DISTINCT passages (distinct md5(content)); the kept copy of a repeated passage is the one with
      the smallest (distance, id). Exact: SQL DISTINCT ON (md5(content)) over the whole filtered set, then ORDER BY
      distance, id LIMIT k. Index routes: over-fetch max(DISTINCT_MIN_FETCH, DISTINCT_INDEX_FETCH_FACTOR * k) rows
      (a non-iterative scan returns at most ef_search = 40 anyway, so post-filter can under-fill), drop repeats in Python,
      sort by (distance, id), cut to k; tie_truncated is set when the fetched rows ran out while distinct rows were still < k
      or the k-th tie group may continue.
    Unknown route raises.
    """
    import hashlib
    from psycopg2 import sql as psql
    base = ("SELECT id, query_id, evidence_key, content, embedding <-> %s::vector AS d FROM {tbl} "
            "WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s ORDER BY ")
    with conn.cursor() as cur:
        if route in ("pre-filter", "exact"):
            cur.execute("SET enable_indexscan = off; SET enable_seqscan = on;")
            cur.execute("SET hnsw.iterative_scan = off;")
            exact = True
        elif route == "post-filter":
            cur.execute("SET enable_indexscan = on; SET enable_seqscan = off;")
            cur.execute("SET hnsw.iterative_scan = off;")
            exact = False
        elif route in ("iterative-scan", "iterative-relaxed"):
            cur.execute("SET enable_indexscan = on; SET enable_seqscan = off;")
            cur.execute("SET hnsw.iterative_scan = 'relaxed_order';")
            exact = False
        else:
            raise ValueError(f"unknown route {route!r}")
        if exact and distinct:
            query = psql.SQL(
                "SELECT id, query_id, evidence_key, content, d FROM (SELECT DISTINCT ON (md5(content)) id, query_id, evidence_key, "
                "content, embedding <-> %s::vector AS d FROM {tbl} WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s "
                "ORDER BY md5(content), d, id) s ORDER BY d, id LIMIT %s").format(tbl=psql.Identifier(table))
            cur.execute(query, (vector, ticker, year, k))
            fetched = cur.fetchall()
            return {"rows": fetched, "rows_fetched": len(fetched), "tie_truncated": False, "distinct_dropped": 0}
        if exact:
            query = psql.SQL(base + "d, id LIMIT %s").format(tbl=psql.Identifier(table))
            limit = k
            cur.execute(query, (vector, ticker, year, limit))
        else:
            limit = max(DISTINCT_MIN_FETCH, DISTINCT_INDEX_FETCH_FACTOR * k) if distinct else INDEX_FETCH_FACTOR * k
            query = psql.SQL(base + "embedding <-> %s::vector LIMIT %s").format(tbl=psql.Identifier(table))
            cur.execute(query, (vector, ticker, year, vector, limit))
        fetched = cur.fetchall()
    fetched.sort(key=lambda r: (r[4], r[0]))
    dropped = 0
    if distinct:
        seen, kept = set(), []
        for r in fetched:
            h = hashlib.md5(r[3].encode()).hexdigest()
            if h in seen:
                dropped += 1
                continue
            seen.add(h)
            kept.append(r)
        rows = kept[:k]
        tie_truncated = len(fetched) == limit and (len(rows) < k or kept[-1][4] == rows[-1][4])
    else:
        rows = fetched[:k]
        tie_truncated = (not exact) and len(fetched) == limit and len(rows) == k and fetched[-1][4] == rows[-1][4]
    return {"rows": rows, "rows_fetched": len(fetched), "tie_truncated": tie_truncated, "distinct_dropped": dropped}


def make_execute_node(deps: Deps, route_label: str | None = None) -> Callable[[RouterState], dict]:
    def execute(state: RouterState) -> dict:
        route = route_label or state["chosen_route"]
        t0 = time.perf_counter()
        vector = deps.embed(state["question"])
        t1 = time.perf_counter()
        res = retrieve(deps.conn, route, state["ticker"], state["year"], vector, deps.k, deps.table, deps.distinct)
        t2 = time.perf_counter()
        rows = res["rows"]
        context = "\n".join(f"[{q}::{key}] {content}" for _, q, key, content, _ in rows)
        resp = deps.answer_client.generate(ANSWER_SYSTEM, f"Evidence:\n{context}\n\nQuestion: {state['question']}",
                                           max_output_tokens=deps.answer_max_tokens)
        return {
            "embed_ms": (t1 - t0) * 1000, "db_ms": (t2 - t1) * 1000,
            "retrieved_evidence_keys": [f"{q}::{key}" for _, q, key, _, _ in rows],
            "retrieved_ids": [r[0] for r in rows], "retrieved_distances": [r[4] for r in rows],
            "rows_returned": len(rows), "rows_fetched": res["rows_fetched"], "tie_truncated": res["tie_truncated"],
            "distinct_dropped": res.get("distinct_dropped", 0),
            "raw_output": resp.text, "generation_ms": resp.latency_ms,
            "gen_input_tokens": resp.input_tokens, "gen_output_tokens": resp.output_tokens,
            "gen_thinking_tokens": resp.thinking_tokens, "cost_usd": state.get("cost_usd", 0.0) + resp.cost_usd,
            "settings_used": {**state.get("settings_used", {}), "answer": resp.settings_used},
        }
    return execute


def _deterministic_graph(deps: Deps, decide: Callable[[RouterState], str], routes: dict[str, str]):
    def route_node(state: RouterState) -> dict:
        t0 = time.perf_counter()
        route = decide(state)
        return {"chosen_route": route, "router_ms": (time.perf_counter() - t0) * 1000, "route_parse_failure": False,
                "cost_usd": 0.0}

    g = StateGraph(RouterState)
    g.add_node("router", route_node)
    for node in set(routes.values()):
        g.add_node(node, make_execute_node(deps))
        g.add_edge(node, END)
    g.set_entry_point("router")
    g.add_conditional_edges("router", lambda s: s["chosen_route"], {r: r for r in routes})
    return g.compile()


def build_decision_matrix_graph(thresholds_dict: dict, deps: Deps):
    routes = {"pre-filter": "pre-filter", "post-filter": "post-filter", "iterative-scan": "iterative-scan"}
    return _deterministic_graph(
        deps, lambda s: get_routing_decision(s["correlation_level"], s["estimated_selectivity"], thresholds_dict), routes)


def build_policy_v2_graph(deps: Deps):
    routes = {"exact": "exact", "iterative-relaxed": "iterative-relaxed"}
    return _deterministic_graph(deps, lambda s: get_routing_decision_v2(s["estimated_selectivity"]), routes)


def build_naive_graph(deps: Deps):
    def route_node(state: RouterState) -> dict:
        resp = deps.router_client.generate(NAIVE_ROUTER_SYSTEM, f"Question: {state['question']}",
                                           max_output_tokens=deps.router_max_tokens, json_mode=True)
        data, err = validate_naive_route(resp.text)
        out = {"router_raw": resp.text, "router_ms": resp.latency_ms, "router_input_tokens": resp.input_tokens,
               "router_output_tokens": resp.output_tokens, "router_thinking_tokens": resp.thinking_tokens,
               "cost_usd": resp.cost_usd, "settings_used": {"router": resp.settings_used}}
        if data is None:
            return {**out, "chosen_route": "", "route_parse_failure": True, "router_reason": f"PARSE FAILURE: {err}"}
        return {**out, "chosen_route": data["route"], "route_parse_failure": False, "router_reason": data["reason"]}

    g = StateGraph(RouterState)
    g.add_node("router", route_node)
    for node in NAIVE_ROUTES:
        g.add_node(node, make_execute_node(deps))
        g.add_edge(node, END)
    g.set_entry_point("router")
    g.add_conditional_edges("router", lambda s: s["chosen_route"] if not s["route_parse_failure"] else "__end__",
                            {**{r: r for r in NAIVE_ROUTES}, "__end__": END})
    return g.compile()
