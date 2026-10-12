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


def test_shipped_prices_other_models_locked_gemini_needs_flag_and_budget():
    for m in ("claude-sonnet-5-5", "gemini-3.5-flash-lite", "gpt-oss-120b"):
        with pytest.raises(PaidLockError):
            make_client(m, allow_paid=True, budget_usd=10, project="p")
    with pytest.raises(PaidLockError, match="allow-paid"):
        make_client("gemini-3.8-flash", allow_paid=False, budget_usd=10, genai_client=object())
    with pytest.raises(PaidLockError, match="budget"):
        make_client("gemini-3.8-flash", allow_paid=True, budget_usd=None, genai_client=object())
    make_client("gemini-3.8-flash", allow_paid=True, budget_usd=2, genai_client=object())


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


class _Name:
    def __init__(self, name):
        self.name = name


class _Usage:
    def __init__(self, prompt, cand, thoughts, cached=0, total=None, traffic="ON_DEMAND"):
        self.prompt_token_count, self.candidates_token_count, self.thoughts_token_count = prompt, cand, thoughts
        self.cached_content_token_count, self.total_token_count = cached, total or (prompt + cand + thoughts)
        self.traffic_type = _Name(traffic) if traffic else None


class _Cand:
    def __init__(self, reason):
        self.finish_reason = _Name(reason)


class _Resp:
    def __init__(self, text, usage, reason="STOP"):
        self.text, self.usage_metadata, self.candidates = text, usage, [_Cand(reason)]


class FakeGenai:
    def __init__(self, resp):
        self.resp, self.calls = resp, []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        return self.resp


def gemini(resp, tmp_path, i=0.75, o=3.75):
    fake = FakeGenai(resp)
    return make_client("gemini-3.8-flash", allow_paid=True, budget_usd=2, genai_client=fake), fake


def test_gemini_cost_formula_verified_usage_example():
    # Real Vertex call 2026-10-12: prompt 7 + candidates 1 + thoughts 44 = total 52, ON_DEMAND.
    u = _Usage(7, 1, 44)
    assert u.total_token_count == 52 == u.prompt_token_count + u.candidates_token_count + u.thoughts_token_count
    c, fake = gemini(_Resp("OK", u), None)
    r = c.generate("sys", "user", max_output_tokens=2048)
    expect = 7 * 0.75 / 1e6 + (1 + 44) * 3.75 / 1e6          # thinking billed at the output rate
    assert r.cost_usd == pytest.approx(expect)
    assert (r.input_tokens, r.output_tokens, r.thinking_tokens, r.cached_tokens) == (7, 1, 44, 0)
    assert r.finish_reason == "STOP" and r.traffic_type == "ON_DEMAND"
    assert c.spent_usd == pytest.approx(expect)
    conf = fake.calls[0][2]
    assert conf.temperature == 0 and conf.max_output_tokens == 2048 and conf.thinking_config.thinking_level.name == "LOW"


def test_gemini_cached_tokens_billed_at_zero_input():
    c, _ = gemini(_Resp("5", _Usage(1000, 10, 90, cached=400)), None)
    r = c.generate("s", "u", max_output_tokens=2048)
    assert r.cost_usd == pytest.approx((1000 - 400) * 0.75 / 1e6 + 100 * 3.75 / 1e6)


def test_gemini_truncation_is_recorded_not_retried():
    c, fake = gemini(_Resp("partial", _Usage(10, 2048, 0), reason="MAX_TOKENS"), None)
    r = c.generate("s", "u", max_output_tokens=2048)
    assert r.finish_reason == "MAX_TOKENS" and r.text == "partial" and len(fake.calls) == 1


def test_gemini_refuses_api_key_in_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    with pytest.raises(PaidLockError, match="Application Default"):
        make_client("gemini-3.8-flash", allow_paid=True, budget_usd=2)


def test_gemini_disallowed_thinking_level_raises(monkeypatch):
    from src.phase_d_validation.llm_client import load_generation_config
    cfg = load_generation_config()
    cfg["models"]["gemini-3.8-flash"]["thinking"] = {"thinking_level": "MINIMAL"}
    c = make_client("gemini-3.8-flash", allow_paid=True, budget_usd=2, genai_client=FakeGenai(_Resp("x", _Usage(1, 1, 0))), config=cfg)
    with pytest.raises(LLMCallError):
        c.generate("s", "u", max_output_tokens=10)


def test_price_validity_window_enforced(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"gemini-3.8-flash": {"input_usd_per_1m": 1, "output_usd_per_1m": 1, "verified": True, "valid_through": "2020-01-01"}}))
    with pytest.raises(PaidLockError, match="valid through"):
        CostGuard("gemini-3.8-flash", True, 2, p)


def test_budget_abort_before_call(tmp_path):
    fake = FakeGenai(_Resp("x", _Usage(1, 1, 0)))
    c = make_client("gemini-3.8-flash", allow_paid=True, budget_usd=0.000001, genai_client=fake)
    with pytest.raises(BudgetExceeded):
        c.generate("s", "u" * 1000, max_output_tokens=2048)
    assert fake.calls == []


def test_missing_usage_raises_not_zero_cost():
    c = make_client("gemini-3.8-flash", allow_paid=True, budget_usd=2, genai_client=FakeGenai(_Resp("1", None)))
    with pytest.raises(LLMCallError):
        c.generate("s", "u", max_output_tokens=10)


def test_ollama_needs_no_lock():
    c = make_client("qwen2.5:7b")
    assert c.backend == "ollama" and not c.paid and c.spent_usd == 0.0
