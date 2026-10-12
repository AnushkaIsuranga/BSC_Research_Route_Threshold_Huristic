import unittest.mock

import pytest

from src.phase_b_router import router as router_mod
from src.phase_b_router.router import (Deps, build_decision_matrix_graph, build_naive_graph, build_policy_v2_graph,
                                       validate_naive_route)
from src.phase_d_validation.llm_client import LLMResponse


class FakeClient:
    """Test double for an LLMClient (unit tests only; no runner uses it)."""
    paid = False

    def __init__(self, text, cost=0.0):
        self.text, self.cost, self.calls, self.spent_usd = text, cost, 0, 0.0

    def generate(self, system, user, *, max_output_tokens, json_mode=False):
        self.calls += 1
        return LLMResponse(self.text, 10, 5, 0, self.cost, 1.0, {"temperature": 0}, {})


def state(sel):
    return {"query_id": "A/2020/page_1.pdf-1", "ticker": "A", "year": "2020", "question": "q?",
            "gold_evidence_keys": ["text_1"], "estimated_selectivity": sel, "correlation_level": "t"}


def deps(answer="5", router=None):
    return Deps(conn=None, embed=lambda q: [0.0], router_client=router or FakeClient("{}"),
                answer_client=FakeClient(answer), k=6, router_max_tokens=64, answer_max_tokens=64)


@pytest.fixture
def patched_retrieve():
    with unittest.mock.patch.object(router_mod, "retrieve",
                                    side_effect=lambda conn, route, t, y, v, k: [("A/2020/page_1.pdf-1", "text_1", "c")]) as m:
        yield m


def test_validate_naive_route():
    ok, _ = validate_naive_route('{"route": "pre-filter", "reason": "small"}')
    assert ok["route"] == "pre-filter"
    for bad in ["nope", "[]", '{"route": "pre-filter"}', '{"route": "x", "reason": "r"}',
                '{"route": "post-filter", "reason": 3}', '{"route": "post-filter", "reason": "r", "extra": 1}']:
        data, err = validate_naive_route(bad)
        assert data is None and err, bad


def test_policy_v2_graph_routes(patched_retrieve):
    g = build_policy_v2_graph(deps())
    assert g.invoke(state(0.01))["chosen_route"] == "exact"
    out = g.invoke(state(0.5))
    assert out["chosen_route"] == "iterative-relaxed"
    assert out["raw_output"] == "5"
    assert out["retrieved_evidence_keys"] == ["A/2020/page_1.pdf-1::text_1"]


def test_decision_matrix_graph(patched_retrieve):
    th = {"t": {"recall_danger_zones": [], "latency_danger_zones": [], "margin": 0.01}}
    out = build_decision_matrix_graph(th, deps()).invoke(state(0.01))
    assert out["chosen_route"] == "pre-filter" and "cost_usd" in out


def test_naive_graph_valid_and_cost_parity(patched_retrieve):
    d = deps(router=FakeClient('{"route": "post-filter", "reason": "r"}', cost=0.5))
    d.answer_client.cost = 0.25
    out = build_naive_graph(d).invoke(state(0.01))
    assert out["chosen_route"] == "post-filter" and out["route_parse_failure"] is False
    assert out["cost_usd"] == pytest.approx(0.75)


def test_naive_graph_parse_failure_no_retry_no_default(patched_retrieve):
    d = deps(router=FakeClient("not json"))
    out = build_naive_graph(d).invoke(state(0.01))
    assert out["route_parse_failure"] is True
    assert d.router_client.calls == 1       # no silent retry
    assert d.answer_client.calls == 0       # no default route, no answer
    patched_retrieve.assert_not_called()


def test_unknown_route_raises():
    with pytest.raises(ValueError):
        router_mod.retrieve(unittest.mock.MagicMock(), "bogus", "A", "2020", [0.0], 6)


def test_runner_has_no_mock_or_fallback():
    import inspect
    from src.phase_d_validation import comparison_runner
    src = inspect.getsource(comparison_runner).lower()
    for bad in ("mockchatmodel", "get_openai_callback", "0.15", "random", "fallback"):
        assert bad not in src.replace("no mock, fallback or random behaviour", ""), bad
