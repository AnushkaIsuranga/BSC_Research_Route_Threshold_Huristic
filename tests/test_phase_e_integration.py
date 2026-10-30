"""Integration tests for src/phase_e_router/retriever.py against the running H&M database (Amendment 9).
They need the vector_db container; they fail (not skip) if it is unreachable."""

import json

import pytest

from src.phase_e_router import policy_v3 as P
from src.phase_e_router import retriever as R

TABLE = "hm_clothes_100"
LO1 = [["product_type_name", ["Cap"]]]                      # 13 rows: iterative under-fills (stored 18-20/20)
TINY = [["product_type_name", ["Bumbag"]]]                  # 1 row
FILTERS = [LO1, [["product_type_name", ["Blazer"]]], [["garment_group_name", ["Shoes"]]],
           [["product_type_name", ["Trousers"]]], [["perceived_colour_master_name", ["Blue", "Red"]]],
           [["graphical_appearance_name", ["Solid"]]]]


@pytest.fixture(scope="module")
def ctx():
    cfg = R.RouterConfig.load()
    cfg.T_default, cfg.T_tuned = 0.1, 0.1           # tests do not depend on the calibrated values
    conn = R.connect()
    R.configure_session(conn, cfg)
    with open("ann-filtering-benchmark-datasets/data/tests.jsonl") as f:
        qv = json.loads(f.readline())["query"]
    yield cfg, conn, qv
    conn.close()


@pytest.mark.parametrize("route", [R.R_EXACT, R.R_ITER, R.R_ITER_TUNED, R.R_HNSW, R.R_PROBE])
@pytest.mark.parametrize("flt", [LO1, FILTERS[4], FILTERS[5]])
def test_preflight_plan_per_route(ctx, route, flt):
    cfg, conn, qv = ctx
    plan = R.explain_route(conn, route, TABLE, flt, 10, R.vec_literal(qv), cfg)
    chk = R.check_plan(route, plan, cfg)
    assert chk["ok"], chk


def test_iterative_plan_has_sort_above_cte(ctx):
    cfg, conn, qv = ctx
    chk = R.check_plan(R.R_ITER, R.explain_route(conn, R.R_ITER, TABLE, LO1, 10, R.vec_literal(qv), cfg), cfg)
    assert chk["plan_nodes"].startswith("Sort") and "CTE Scan" in chk["plan_nodes"]


def test_guard_triggers_on_lo1(ctx):
    cfg, conn, qv = ctx
    rows, tr = R.retrieve(qv, LO1, 10, "always_iterative", cfg, conn=conn, table="hm_clothes_0")
    assert len(rows) < 10                                   # unguarded iterative under-fills here
    rows, tr = R.retrieve(qv, LO1, 10, "retry_exact", cfg, conn=conn, table="hm_clothes_0")
    assert tr["guard_triggered"] and tr["routes_executed"] == [R.R_HNSW, R.R_EXACT] and len(rows) == 10
    assert tr["filter_smaller_than_k"] is False


def test_guard_on_iterative_route_of_router(ctx):
    cfg, conn, qv = ctx
    old = cfg.T_default
    cfg.T_default = 0.00001                                 # forces the router to iterative on lo1
    try:
        rows, tr = R.retrieve(qv, LO1, 10, "router", cfg, conn=conn, table="hm_clothes_0")
    finally:
        cfg.T_default = old
    assert tr["decided"] == P.ITERATIVE and tr["guard_triggered"] and len(rows) == 10


def test_filter_smaller_than_k_flag(ctx):
    cfg, conn, qv = ctx
    rows, tr = R.retrieve(qv, TINY, 10, "retry_exact", cfg, conn=conn, table=TABLE)
    assert len(rows) == 1 and tr["guard_triggered"] and tr["filter_smaller_than_k"] is True


@pytest.mark.parametrize("T", [0.0005, 0.01, 0.05, 0.1, 0.2])
def test_capped_count_matches_full_count(ctx, T):
    cfg, conn, _ = ctx
    n = R.reltuples(conn, TABLE)
    for flt in FILTERS:
        cap = P.count_cap(T, n)
        c, _ = R.capped_count(conn, TABLE, flt, cap, cfg)
        w, wp = R.where_clause(flt, cfg)
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {TABLE} WHERE {w}", wp)
            full = cur.fetchone()[0]
        conn.commit()
        assert P.decide_count(c, cap) == P.decide_from_full_count(full, T, n), (flt, T, c, full)


@pytest.mark.parametrize("flt", FILTERS)
def test_probe_returns_m_rows_and_direct_count(ctx, flt):
    cfg, conn, qv = ctx
    rows, _ = R.run_route(conn, R.R_PROBE, TABLE, flt, None, R.vec_literal(qv), cfg)
    assert len(rows) == cfg["probe"]["m"]
    p = sum(1 for _, ok in rows if ok)
    w, wp = R.where_clause(flt, cfg)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TABLE} WHERE id = ANY(%s) AND {w}", [[i for i, _ in rows], *wp])
        direct = cur.fetchone()[0]
    conn.commit()
    assert p == direct
    p2, m2, _ = R.probe(conn, TABLE, flt, R.vec_literal(qv), cfg)
    assert (p2, m2) == (p, cfg["probe"]["m"])


def test_missing_T_raises(ctx):
    cfg, conn, qv = ctx
    old = cfg.T_default
    cfg.T_default = None
    try:
        with pytest.raises(R.RetrieverError):
            R.retrieve(qv, LO1, 10, "router", cfg, conn=conn, table=TABLE)
    finally:
        cfg.T_default = old


def test_unknown_column_and_mode_raise(ctx):
    cfg, conn, qv = ctx
    with pytest.raises(R.RetrieverError):
        R.retrieve(qv, [["embedding", ["x"]]], 10, "always_exact", cfg, conn=conn, table=TABLE)
    with pytest.raises(R.RetrieverError):
        R.retrieve(qv, LO1, 10, "vecadvisor", cfg, conn=conn, table=TABLE)
    with pytest.raises(R.RetrieverError):
        R.retrieve(qv, LO1, 10, "llm_router", cfg, conn=conn, table=TABLE)   # no recorded LLM decision


def test_exact_route_is_ground_truth_order(ctx):
    cfg, conn, qv = ctx
    rows, tr = R.retrieve(qv, FILTERS[1], 10, "always_exact", cfg, conn=conn, table=TABLE)
    d = [r[1] for r in rows]
    assert d == sorted(d) and len(rows) == 10 and tr["routes_executed"] == [R.R_EXACT]
