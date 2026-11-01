"""Phase F Tasks 4-6 helpers (no database, no paid call): session cost log, VecAdvisor adapter choice and settings, comparison
mode list and prior-system rules, answer prompt building and reuse, answer classification and cluster bootstrap."""

import json

import pytest

from src.phase_e_router import retriever as R
from src.phase_f_edgar import analyze_edgar as AN
from src.phase_f_edgar import answer_edgar as AE
from src.phase_f_edgar import compare_edgar as CMP
from src.phase_f_edgar import session_tools as S
from src.phase_f_edgar import vecadvisor_adapter as VA


# ------------------------------------------------------------------ session cost log

def test_cost_log_running_total_and_cap(tmp_path):
    log = str(tmp_path / "cost.jsonl")
    assert S.cost_spent(log) == 0.0
    assert S.cost_add("a", 1.25, {"x": 1}, path=log) == pytest.approx(1.25)
    assert S.cost_add("b", 2.5, path=log) == pytest.approx(3.75)
    assert S.cost_spent(log) == pytest.approx(3.75)
    lines = (tmp_path / "cost.jsonl").read_bytes()
    assert b"\r\n" not in lines
    first = json.loads(lines.decode().splitlines()[0])
    assert first["step"] == "a" and first["x"] == 1 and first["running_total_usd"] == pytest.approx(1.25)
    with pytest.raises(SystemExit, match="exceeds"):
        S.cost_add("c", 2.26, path=log)
    assert S.cost_spent(log) == pytest.approx(6.01)               # the call that passed the cap is still logged


# ------------------------------------------------------------------ VecAdvisor adapter

def test_filter_sql_literals():
    f = [["cik", ["0000320193"]], ["fiscal_year", [2023]], ["section", ["7", "7A"]]]
    assert VA.filter_sql(f) == "cik = '0000320193' AND fiscal_year = 2023 AND section IN ('7', '7A')"
    assert VA.filter_sql([["section", ["O'Brien"]]]) == "section = 'O''Brien'"


def _cand(strategy, ef=None, new_object=None, hint=""):
    return {"strategy": strategy, "plan": {"ef_search": ef, "requires_new_object": new_object, "sql_hint": hint}}


def test_choose_top_ranked_without_new_object():
    rep = {"recommendation": {"decision": {"recommended_strategy": "iterative_relaxed"},
                              "ranked": [_cand("iterative_relaxed", 80, hint="SET hnsw.max_scan_tuples = 40000;"), _cand("exact")]}}
    c = VA.choose(rep)
    assert c["strategy"] == "iterative_relaxed" and c["params"] == {"ef_search": 80, "max_scan_tuples": 40000}
    assert c["unavailable"] is False and c["unavailable_reason"] is None


def test_choose_skips_new_object_and_errors_fall_back_to_exact():
    rep = {"recommendation": {"decision": {"recommended_strategy": "partial"},
                              "ranked": [_cand("partial", new_object="partial index"), _cand("postfilter", 500), _cand("exact")]}}
    c = VA.choose(rep)
    assert c["strategy"] == "postfilter" and c["params"]["ef_search"] == 500
    assert c["unavailable"] is True and c["unavailable_reason"] == "requires_new_object" and c["top_ranked"] == "partial"
    for c in (VA.choose(None, "exit 2: boom"), VA.choose({"recommendation": {"ranked": []}}),
              VA.choose({"ranked": [_cand("partial", new_object="x")]})):
        assert c["strategy"] == "exact" and c["unavailable"] is True and c["unavailable_reason"] == "error"
    with pytest.raises(ValueError):
        VA.choose({"ranked": [_cand("iterative_strict")]})            # an index strategy without its ef_search


def test_choose_skips_ef_search_above_pgvector_range():
    rep = {"recommendation": {"decision": {"recommended_strategy": "partial"},
                              "ranked": [_cand("partial", 40, new_object="partial index"), _cand("postfilter", 1500),
                                         _cand("iterative_relaxed", 40, hint="SET hnsw.max_scan_tuples = 20000;"), _cand("exact")]}}
    c = VA.choose(rep)
    assert c["strategy"] == "iterative_relaxed" and c["params"] == {"ef_search": 40, "max_scan_tuples": 20000}
    assert c["unavailable"] is True and c["unavailable_reason"] == "invalid_parameter"
    assert [(s["strategy"], s["reason"]) for s in c["skipped"]] == [("partial", "requires_new_object"), ("postfilter", "invalid_parameter")]
    c = VA.choose({"ranked": [_cand("postfilter", 1001), _cand("exact")]})
    assert c["strategy"] == "exact" and c["unavailable_reason"] == "invalid_parameter"
    assert VA.choose({"ranked": [_cand("postfilter", 1000)]})["strategy"] == "postfilter"     # 1000 is in range


def test_strategy_settings_shapes():
    cfg = R.RouterConfig.load(CMP.CONFIG)
    route, s = VA.strategy_settings({"strategy": "iterative_strict", "params": {"ef_search": 60, "max_scan_tuples": None}}, cfg)
    assert route == R.R_ITER and s["hnsw.iterative_scan"] == "strict_order" and s["hnsw.ef_search"] == 60
    assert "hnsw.max_scan_tuples" not in s
    route, s = VA.strategy_settings({"strategy": "postfilter", "params": {"ef_search": 500}}, cfg)
    assert route == R.R_HNSW and s["hnsw.iterative_scan"] == "off" and s["hnsw.ef_search"] == 500
    assert VA.strategy_settings({"strategy": "exact", "params": {}}, cfg)[0] == R.R_EXACT
    with pytest.raises(ValueError):
        VA.strategy_settings({"strategy": "partial", "params": {}}, cfg)


# ------------------------------------------------------------------ comparison

def test_modes_and_prior_rules():
    assert len(CMP.MODES) == 19 and len(set(CMP.MODES)) == 19
    assert CMP.MODES[:14] == list(R.MODES) and "oracle" not in CMP.MODES
    assert CMP.PRIOR["vbase"](0.179, 0) and not CMP.PRIOR["vbase"](0.18, 0)
    assert CMP.PRIOR["milvus"](0.05, 0) and not CMP.PRIOR["milvus"](0.0501, 0)
    assert CMP.PRIOR["qdrant"](0.9, 2499) and not CMP.PRIOR["qdrant"](0.0, 2500)


def test_route_of_and_small():
    assert CMP.route_of({"trace": {"route_failure": True}}) == "route_failure"
    assert CMP.route_of({"trace": {"routes_executed": ["iterative_default", "exact"]}}) == "iterative_default+exact"
    assert CMP.route_of({"trace": {"routes_executed": [], "decided": "exact"}}) == "exact"
    assert CMP.small({"decided": "exact", "total_ms": 3.0, "sql": "SELECT"}) == {"decided": "exact", "total_ms": 3.0}


# ------------------------------------------------------------------ answer prompts

def _meta(i, h, name="Apple Inc."):
    return {"cik": "0000320193", "company_name": name, "fiscal_year": 2023, "section": "7", "text": f"text {i}", "text_hash": h}


def test_passage_line_prefix():
    assert AE.passage_line(_meta(1, "a"), "x") == "[Apple Inc. | FY 2023 | Item 7] x"
    assert AE.passage_line(_meta(1, "a", name=None), "x") == "[CIK 0000320193 | FY 2023 | Item 7] x"


def test_build_prompts_dedup_and_reuse():
    meta = {1: _meta(1, "h1"), 2: _meta(2, "h1"), 3: _meta(3, "h3")}            # 1 and 2 share a text
    res = [{"pair_id": "P1", "qid": "q1", "breadth": "section", "mode": "router", "ids": [1, 2, 3]},
           {"pair_id": "P1", "qid": "q1", "breadth": "section", "mode": "always_exact", "ids": [1, 3]},
           {"pair_id": "P1", "qid": "q1", "breadth": "section", "mode": "default_hnsw", "ids": [3, 1]}]
    prompts, reuse = AE.build_prompts(res, meta, {"q1": "What was revenue?"})
    assert len(prompts) == 2                                          # router and always_exact reduce to [1, 3]
    assert reuse[("P1", "router")] == reuse[("P1", "always_exact")] != reuse[("P1", "default_hnsw")]
    p = next(x for x in prompts if x["prompt_id"] == reuse[("P1", "router")])
    assert p["passage_ids"] == [1, 3] and p["n_rows"] == 2 and p["n_distinct"] == 2 and sorted(p["modes"]) == ["always_exact", "router"]
    assert p["user"] == "Evidence:\n[Apple Inc. | FY 2023 | Item 7] text 1\n[Apple Inc. | FY 2023 | Item 7] text 3\n\nQuestion: What was revenue?"


# ------------------------------------------------------------------ analysis

def test_classify_classes():
    passages = ["Net sales were $383,285 million in 2023."]
    assert AN.classify(None, "383285", passages)[0] == "abstained"
    assert AN.classify("Not answerable from the evidence.", "383285", passages)[0] == "abstained"
    assert AN.classify("No figure given.", "383285", passages)[0] == "abstained"
    assert AN.classify("383,285 million", "383285", passages) == ("correct", "383,285 million")   # scale word stripped, no rescale
    assert AN.classify("383,285", "394328", passages)[0] == "wrong_in_context"
    assert AN.classify("12,345", "394328", passages)[0] == "wrong_not_in_context"


def test_cluster_boot_reproducible_and_brackets_mean():
    per_q = {f"q{i}": [float(i % 2)] for i in range(40)}
    mean = lambda gs: sum(v for g in gs for v in g) / sum(len(g) for g in gs)
    a, b = AN.cluster_boot(per_q, mean, n=500), AN.cluster_boot(per_q, mean, n=500)
    assert a == b and a[0] < 0.5 < a[1]
    assert AN.cluster_boot({"q": [1.0]}, mean, n=50) == (1.0, 1.0)
