"""Integration test (needs the local PostgreSQL finqa_evidence table): same query twice -> identical row order,
and ties on distance are ordered by id."""
import psycopg2
import pytest
from pgvector.psycopg2 import register_vector

from src import db_settings
from src.phase_b_router.router import retrieve

CASES = [("INTC", "2015", 7601), ("ABMD", "2007", 6271), ("ALXN", "2016", 917)]  # groups with exactly tied distances


@pytest.fixture(scope="module")
def conn():
    try:
        c = psycopg2.connect(**db_settings(), connect_timeout=3)
    except psycopg2.OperationalError:
        pytest.skip("PostgreSQL not available")
    c.autocommit = True
    register_vector(c)
    with c.cursor() as cur:
        cur.execute("SET hnsw.ef_search = 40")
    yield c
    c.close()


def vec(conn, row_id):
    with conn.cursor() as cur:
        cur.execute("SELECT embedding FROM finqa_evidence WHERE id = %s", (row_id,))
        return cur.fetchone()[0]


@pytest.mark.parametrize("route", ["exact", "pre-filter", "post-filter", "iterative-relaxed"])
@pytest.mark.parametrize("ticker,year,row_id", CASES)
def test_same_query_twice_identical_order(conn, route, ticker, year, row_id):
    v = vec(conn, row_id)
    a = retrieve(conn, route, ticker, year, v, 6)
    b = retrieve(conn, route, ticker, year, v, 6)
    assert [r[0] for r in a["rows"]] == [r[0] for r in b["rows"]]
    assert a["rows_fetched"] == b["rows_fetched"]
    keys = [(r[4], r[0]) for r in a["rows"]]
    assert keys == sorted(keys), "rows must be ordered by (distance, id)"
    assert len(a["rows"]) <= 6


def test_exact_route_has_ties_broken_by_id(conn):
    r = retrieve(conn, "exact", "INTC", "2015", vec(conn, 7601), 6)["rows"]
    top = [x for x in r if x[4] == r[0][4]]
    assert len(top) >= 2, "test data should contain tied distances"
    assert [x[0] for x in top] == sorted(x[0] for x in top)


def test_unknown_route_raises(conn):
    with pytest.raises(ValueError):
        retrieve(conn, "bogus", "INTC", "2015", vec(conn, 7601), 6)
