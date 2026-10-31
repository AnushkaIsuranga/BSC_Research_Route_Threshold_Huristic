"""policy_v3.1 no-statistics rule (Amendment 11), against the running database (fails, not skips, if it is unreachable).

- fires on a JSONB expression filter without statistics (finqa_evidence_qwen3: metadata->>'ticker' / 'year');
- does not fire on plain columns with pg_stats rows (H&M, edgar_chunks), where the decision equals policy_v3's;
- when it fires the capped count decides and the trace says why.
"""

import pytest

from src.phase_e_router import policy_v3 as P
from src.phase_e_router import policy_v3_1 as V
from src.phase_e_router import retriever as R

T_HM = 0.07119177617441379


@pytest.fixture(scope="module")
def conn():
    c = R.connect()
    yield c
    c.close()


def finqa_cfg():
    return R.RouterConfig({"tables": ["finqa_evidence_qwen3"], "filter_columns": ["ticker", "year"],
                           "filter_expressions": {"ticker": "metadata->>'ticker'", "year": "metadata->>'year'"}})


def test_where_clause_substitutes_expressions_only():
    w, p = V.where_clause([["ticker", ["ADI"]], ["year", ["2011"]]], finqa_cfg())
    assert w == "metadata->>'ticker' = %s AND metadata->>'year' = %s" and p == ["ADI", "2011"]
    hm = R.RouterConfig.load()
    flt = [["product_type_name", ["Cap", "Blazer"]]]
    assert V.where_clause(flt, hm) == R.where_clause(flt, hm)


def test_rule_fires_on_jsonb_without_stats_and_uses_count(conn):
    tr = {}
    route = V.band_decision(conn, "finqa_evidence_qwen3", [["ticker", ["ADI"]], ["year", ["2011"]]], T_HM, finqa_cfg(), tr)
    assert tr[V.SKIP_FIELD] is True and tr["stats_missing"] == ["ticker", "year"]
    assert "s_est" not in tr and "estimate_ms" not in tr                      # the estimate is skipped
    assert tr["band"] == P.COUNT and tr["count_cap"] == P.count_cap(T_HM, tr["N"]) and tr["count"] == 52
    assert route == P.EXACT


def test_count_path_can_route_iterative(conn):
    tr = {}
    route = V.band_decision(conn, "finqa_evidence_qwen3", [["year", ["2011"]]], 0.001, finqa_cfg(), tr)
    assert tr[V.SKIP_FIELD] and tr["count"] == tr["count_cap"] and route == P.ITERATIVE


@pytest.mark.parametrize("table,flt", [("hm_clothes_100", [["product_type_name", ["Blazer"]]]),
                                       ("hm_clothes_0", [["perceived_colour_master_name", ["Blue", "Red"]]]),
                                       ("hm_clothes_50", [["graphical_appearance_name", ["Solid"]]])])
def test_rule_does_not_fire_on_plain_columns_with_stats(conn, table, flt):
    cfg = R.RouterConfig.load()
    tr_v31, tr_v3 = {}, {}
    route = V.band_decision(conn, table, flt, T_HM, cfg, tr_v31)
    assert tr_v31[V.SKIP_FIELD] is False and tr_v31["stats_missing"] == [] and "s_est" in tr_v31
    assert route == R._band_decision(conn, table, flt, T_HM, cfg, tr_v3)
    assert tr_v31["s_est"] == tr_v3["s_est"] and tr_v31["band"] == tr_v3["band"]


def test_retrieve_trace_on_edgar_plain_columns(conn):
    cfg = R.RouterConfig.load("config/router_edgar.json")
    cfg.T_default = T_HM
    R.configure_session(conn, cfg)
    with conn.cursor() as cur:
        cur.execute("SELECT embedding::text, cik, fiscal_year FROM edgar_chunks WHERE id = 1")
        qv, cik, fy = cur.fetchone()
    conn.commit()
    rows, tr = V.retrieve(qv, [["cik", [cik]], ["fiscal_year", [fy]]], 15, "router", cfg, conn=conn, table="edgar_chunks")
    assert tr["policy"] == "v3.1" and tr[V.SKIP_FIELD] is False and tr["decided"] == P.EXACT and rows[0][0] == 1
    rows2, tr2 = V.retrieve(qv, [["cik", [cik]]], 15, "always_exact", cfg, conn=conn, table="edgar_chunks")
    assert "policy" not in tr2 and tr2["decided"] == R.R_EXACT                # non-band modes: retriever unchanged


def test_missing_column_statistics_detected(conn):
    with conn.cursor() as cur:
        miss = V.missing_statistics(cur, "edgar_chunks", [{"name": "cik", "kind": "column", "sql": "cik"},
                                                          {"name": "text_hash", "kind": "column", "sql": "text_hash"},
                                                          {"name": "chunk_index", "kind": "column", "sql": "chunk_index"}])
    conn.commit()
    assert "cik" not in miss
