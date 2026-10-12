import json

import pytest

from src.phase_d_validation.llm_client import BudgetExceeded, CostGuard, LLMCallError, PaidLockError, make_client


def prices(tmp_path, verified=True, i=1.0, o=2.0):
    p = tmp_path / "prices.json"
    p.write_text(json.dumps({"gemini-3.8-flash": {"input_usd_per_1m": i, "output_usd_per_1m": o, "verified": verified},
                             "claude-sonnet-5-5": {"input_usd_per_1m": None, "output_usd_per_1m": None, "verified": False}}))
    return p


class FakeResp:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, body):
        self.body, self.calls = body, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json))
        return FakeResp(self.body)


def test_shipped_prices_are_locked():
    for m in ("claude-sonnet-5-5", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gpt-oss-120b"):
        with pytest.raises(PaidLockError):
            make_client(m, allow_paid=True, budget_usd=10, project="p")


def test_lock_requires_flag_budget_and_verified(tmp_path):
    with pytest.raises(PaidLockError, match="allow-paid"):
        CostGuard("gemini-3.8-flash", False, 10, prices(tmp_path))
    with pytest.raises(PaidLockError, match="budget"):
        CostGuard("gemini-3.8-flash", True, None, prices(tmp_path))
    with pytest.raises(PaidLockError, match="budget"):
        CostGuard("gemini-3.8-flash", True, 0, prices(tmp_path))
    with pytest.raises(PaidLockError, match="verified"):
        CostGuard("gemini-3.8-flash", True, 10, prices(tmp_path, verified=False))
    with pytest.raises(PaidLockError):
        CostGuard("gemini-3.8-flash", True, 10, prices(tmp_path, i=None))
    with pytest.raises(PaidLockError):
        CostGuard("missing-model", True, 10, prices(tmp_path))
    CostGuard("gemini-3.8-flash", True, 10, prices(tmp_path))


def test_cost_from_raw_usage_and_thinking_billed_as_output(tmp_path):
    body = {"candidates": [{"content": {"parts": [{"text": "42"}]}}],
            "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 10, "thoughtsTokenCount": 90}}
    sess = FakeSession(body)
    c = make_client("gemini-3.8-flash", allow_paid=True, budget_usd=1, prices_path=prices(tmp_path), project="p", session=sess)
    c._token = lambda: "t"
    r = c.generate("sys", "user", max_output_tokens=100)
    assert r.text == "42" and (r.input_tokens, r.output_tokens, r.thinking_tokens) == (1000, 10, 90)
    assert r.cost_usd == pytest.approx(1000 / 1e6 * 1.0 + 100 / 1e6 * 2.0)
    assert c.spent_usd == pytest.approx(r.cost_usd)
    url, payload = sess.calls[0]
    assert "locations/global" in url and url.endswith("gemini-3.8-flash:generateContent")
    assert payload["generationConfig"]["temperature"] == 0


def test_budget_abort_before_call(tmp_path):
    sess = FakeSession({})
    c = make_client("gemini-3.8-flash", allow_paid=True, budget_usd=0.0001, prices_path=prices(tmp_path, i=1000, o=1000),
                    project="p", session=sess)
    c._token = lambda: "t"
    with pytest.raises(BudgetExceeded):
        c.generate("s", "u" * 1000, max_output_tokens=500)
    assert sess.calls == []


def test_missing_usage_raises_not_zero_cost(tmp_path):
    body = {"candidates": [{"content": {"parts": [{"text": "1"}]}}], "usageMetadata": {}}
    c = make_client("gemini-3.8-flash", allow_paid=True, budget_usd=1, prices_path=prices(tmp_path), project="p",
                    session=FakeSession(body))
    c._token = lambda: "t"
    with pytest.raises(LLMCallError):
        c.generate("s", "u", max_output_tokens=10)


def test_ollama_needs_no_lock():
    c = make_client("qwen2.5:7b")
    assert c.backend == "ollama" and not c.paid and c.spent_usd == 0.0
