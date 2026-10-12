"""Amendment 4 runner additions: resume state, error-rate and projected-cost abort rules, refusal without --resume."""
import json
import subprocess
import sys

import pytest

from src.phase_d_validation.comparison_runner import error_kind, error_rule, load_resume_state, projected_cost


def _write(p, rows):
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_load_resume_state_counts_rows_errors_and_cost(tmp_path):
    _write(tmp_path / "results.jsonl", [{"pass": 1, "query_id": "a", "arm": "policy_v2", "cost_usd": 0.001},
                                        {"pass": 1, "query_id": "a", "arm": "naive_llm", "cost_usd": 0.002}])
    _write(tmp_path / "errors.jsonl", [{"pass": 1, "query_id": "b", "arm": "naive_llm", "cost_usd": 0.0005}])
    s = load_resume_state(tmp_path)
    assert s["done"] == {(1, "a", "policy_v2"), (1, "a", "naive_llm")} and s["n_results"] == 2
    assert len(s["errors"]) == 1 and s["prior_spent"] == pytest.approx(0.0035)


def test_load_resume_state_refuses_duplicates(tmp_path):
    r = {"pass": 1, "query_id": "a", "arm": "policy_v2", "cost_usd": 0}
    _write(tmp_path / "results.jsonl", [r, r])
    with pytest.raises(RuntimeError, match="duplicate"):
        load_resume_state(tmp_path)


def test_load_resume_state_empty_folder(tmp_path):
    s = load_resume_state(tmp_path)
    assert s == {"done": set(), "n_results": 0, "errors": [], "prior_spent": 0.0}


def test_error_rule_fixed_allowance_of_8_rows_regardless_of_run_size():
    for n_questions in (10, 100):                       # a 10-question smoke test uses the same fixed allowance as 100 questions
        window = [f"q{i}" for i in range(n_questions)]
        errs = [{"query_id": f"q{i}", "error": "ValueError: boom"} for i in range(8)]
        assert error_rule(errs, window) == {"errors_counted": 8, "rate_limit_429_not_counted": 0, "allowed": 8, "triggered": False}
        assert error_rule(errs + [{"query_id": "q9", "error": "KeyError: x"}], window)["triggered"] is True
    window = [f"q{i}" for i in range(100)]
    assert error_rule([{"query_id": "q150", "error": "x"}] * 20, window)["triggered"] is False   # outside the first 100 questions


def test_429_is_not_counted_toward_the_abort_rule():
    window = [f"q{i}" for i in range(10)]
    e429 = {"query_id": "q1", "error": "LLMCallError: vertex_gemini/x: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {}}"}
    r = error_rule([e429] * 50, window)
    assert r["triggered"] is False and r["errors_counted"] == 0 and r["rate_limit_429_not_counted"] == 50
    assert error_kind(e429["error"]) == "rate_limit_429" and error_kind("RuntimeError: 429 words only") == "other"
    assert error_rule([e429] * 50 + [{"query_id": "q2", "error": "ValueError: x"}] * 9, window)["triggered"] is True


def test_projected_cost():
    assert projected_cost(0.5, 100, 4300) == pytest.approx(21.5)
    assert projected_cost(0.0, 0, 4300) is None


def test_runner_refuses_non_empty_folder_without_resume(tmp_path):
    (tmp_path / "results.jsonl").write_text("{}\n")
    cmd = [sys.executable, "-m", "src.phase_d_validation.comparison_runner", "--model", "qwen2.5:7b", "--arms", "v2",
           "--table", "t", "--query-embeddings", "live", "--k", "15", "--distinct", "--output-dir", str(tmp_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode != 0 and "--resume" in r.stderr
    r = subprocess.run(cmd + ["--resume"], capture_output=True, text=True)
    assert r.returncode != 0 and "run_meta.json not found" in r.stderr


def test_strict_label_absent_when_gold_has_scale_word():
    from src.phase_d_validation.comparison_runner import build_record
    base = {"ticker": "A", "year": "2020", "raw_output": "13.4", "route_parse_failure": False, "chosen_route": "exact"}
    row = {"id": "A/2020/page_1.pdf-1", "answer": "$ 13.4 million"}
    rec = build_record("r", 1, "v2", row, {"text_1"}, 0.001, dict(base), 1.0, "m", "m", None, ["v2"], [])
    assert rec["correct"] == 1 and rec["correct_strict"] is None and rec["strict_gold_unparseable"] == 1
    # route-parse failure of a naive arm on the same question: still flagged (gold-only decision)
    rec2 = build_record("r", 1, "naive", row, {"text_1"}, 0.001, dict(base, route_parse_failure=True, raw_output=None), 1.0, "m", "m",
                        None, ["naive"], [])
    assert rec2["strict_gold_unparseable"] == 1 and rec2["correct_strict"] is None and rec2["correct"] == 0
    row_ok = {"id": "A/2020/page_1.pdf-1", "answer": "13.4"}
    rec3 = build_record("r", 1, "v2", row_ok, {"text_1"}, 0.001, dict(base, raw_output="$13.4 million"), 1.0, "m", "m", None, ["v2"], [])
    assert rec3["correct"] == 1 and rec3["correct_strict"] == 0 and rec3["strict_gold_unparseable"] == 0


def test_paired_stats_strict_drops_strict_unscorable_questions(tmp_path):
    rows = []
    for arm in ("policy_v2", "naive_llm"):
        for q in ("a", "b", "c"):
            rows.append({"pass": 1, "arm": arm, "query_id": q, "correct": 1, "correct_strict": None if q == "c" else 1,
                         "parse_failure": 0, "parse_failure_strict": 0, "strict_gold_unparseable": int(q == "c"),
                         "total_ms": 1.0, "retrieval_hit": 1, "route_parse_failure": 0, "route": "x", "embed_ms": 1, "db_ms": 1,
                         "router_ms": 1, "generation_ms": 1, "input_tokens": 1, "output_tokens": 1, "thinking_tokens": 0,
                         "router_input_tokens": None, "router_output_tokens": None, "cost_usd": 0.0, "rows_returned": 1})
    f = tmp_path / "r.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "o.json"
    r = subprocess.run([sys.executable, "-m", "src.phase_d_validation.paired_stats", str(f), "--margin", "0.1", "--rule", "strict",
                        "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    res = json.loads(out.read_text())
    assert res["strict_excluded_queries"] == ["c"] and res["pairs"]["policy_v2_vs_naive_llm"]["n"] == 2


def test_scaleup_analysis_primary_strata_and_refusal():
    from src.phase_d_validation.scaleup_analysis import analyse
    subset = [{"id": f"q{i}", "breadth": "single" if i < 6 else "multi"} for i in range(10)]
    rows = []
    for a in ("decision_matrix", "policy_v2", "naive_llm", "naive_informed"):
        for i in range(10):
            ok = int(i < 6) if a != "naive_llm" else int(i < 5)
            rows.append({"arm": a, "query_id": f"q{i}", "correct": ok, "correct_strict": ok, "parse_failure": 0, "parse_failure_strict": 0,
                         "strict_gold_unparseable": 0, "route": "post-filter" if (a == "naive_llm" and i % 2) else "exact",
                         "total_ms": 10.0 if a.startswith("naive") else 5.0, "cost_usd": 0.002 if a.startswith("naive") else 0.001,
                         "retrieval_hit": 1, "route_parse_failure": 0, "embed_ms": 0, "db_ms": 1, "router_ms": 1, "generation_ms": 1,
                         "input_tokens": 1, "output_tokens": 1, "thinking_tokens": 0, "router_input_tokens": None,
                         "router_output_tokens": None, "rows_returned": 15})
    r = analyse([dict(x) for x in rows], subset)
    p = r["pairs"]["policy_v2_vs_naive_llm"]
    assert (p["b_X_only_correct"], p["c_Y_only_correct"]) == (1, 0)
    assert p["cost_usd_mean_diff_X_minus_Y"] == pytest.approx(-0.001) and p["latency_superior"]
    assert r["strata"]["single"]["n"] == 6 and r["strata"]["multi"]["n"] == 4
    assert r["post_filter_share"]["naive_llm"] == 0.5
    with pytest.raises(ValueError, match="without a completed row"):
        analyse([x for x in rows if not (x["arm"] == "naive_llm" and x["query_id"] == "q3")], subset)


# ---------------- Amendment 4 addendum 1: pacing, single attempt, 429 stops the run but is resumable
class _FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_pacer_enforces_minimum_spacing_between_call_starts():
    from src.phase_d_validation.llm_client import Pacer
    c = _FakeClock()
    p = Pacer(15, clock=c.now, sleep=c.sleep)                       # 15 calls/min -> 4.0 s spacing
    assert p.min_interval_s == 4.0
    starts = []
    for work in (1.0, 5.0, 0.5, 0.5):                              # call durations
        p.wait()
        starts.append(c.t)
        c.t += work
    # call 2 starts 4.0 s after call 1 (1.0 s of work + 3.0 s wait); call 3 starts right after the 5 s call 2 (no wait);
    # call 4 waits until 4.0 s after call 3 started
    assert starts == [0.0, 4.0, 9.0, 13.0]
    assert c.slept == [3.0, 3.5]
    assert all(b - a >= 4.0 - 1e-9 for a, b in zip(starts, starts[1:]))
    assert p.describe()["max_calls_per_minute"] == 15 and p.n_calls == 4


def test_pacer_is_applied_before_every_call_and_shared_by_router_and_answer_clients():
    from src.phase_d_validation.llm_client import LLMClient, Pacer

    class Fake(LLMClient):
        backend = "fake"

        def _call(self, system, user, max_out, json_mode):
            return "x", 1, 1, 0, {}, {}
    c = _FakeClock()
    pacer = Pacer(30, clock=c.now, sleep=c.sleep)                   # 2.0 s
    a, b = Fake("a", {}), Fake("b", {})
    a.pacer = b.pacer = pacer
    a.generate("s", "u", max_output_tokens=1)
    b.generate("s", "u", max_output_tokens=1)
    a.generate("s", "u", max_output_tokens=1)
    assert c.slept == [2.0, 2.0] and pacer.n_calls == 3
    d = Fake("d", {})
    d.generate("s", "u", max_output_tokens=1)                       # no pacer: no waiting
    assert c.slept == [2.0, 2.0]


def test_gemini_client_is_built_with_a_single_attempt(monkeypatch):
    import google.genai as genai
    from src.phase_d_validation.llm_client import VertexGeminiBackend, load_generation_config
    seen = {}

    class Spy:
        def __init__(self, **kw):
            seen.update(kw)
    monkeypatch.setattr(genai, "Client", Spy)
    for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_generation_config()["models"]["gemini-3.8-flash"]
    VertexGeminiBackend("gemini-3.8-flash", cfg, guard=object())
    assert seen["vertexai"] is True and seen["location"] == "global"
    assert seen["http_options"].retry_options.attempts == 1


def test_one_http_attempt_per_call_with_the_real_client_and_a_429():
    """Real google-genai client (no network: the transport call is replaced); a 429 must reach the caller after ONE attempt."""
    import time
    from google import genai
    from google.genai import errors, types
    from src.phase_d_validation.llm_client import VertexGeminiBackend
    try:
        client = genai.Client(vertexai=True, project="bsc-research-project-511410", location="global", http_options=VertexGeminiBackend.http_options())
    except Exception as exc:  # no Application Default Credentials on this machine
        pytest.skip(f"cannot build a Vertex client here: {type(exc).__name__}")
    calls = {"n": 0}

    def fake_request_once(http_request, stream=False):
        calls["n"] += 1
        raise errors.ClientError(429, {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}})
    client._api_client._request_once = fake_request_once
    t0 = time.time()
    with pytest.raises(errors.ClientError):
        client.models.generate_content(model="gemini-3.8-flash", contents="x", config=types.GenerateContentConfig(max_output_tokens=8))
    assert calls["n"] == 1 and time.time() - t0 < 5
    # contrast: asking for the library's own retrying behaviour makes several attempts, so the test can tell the difference
    retrying = genai.Client(vertexai=True, project="bsc-research-project-511410", location="global",
                            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=3, initial_delay=0.01, max_delay=0.02)))
    calls["n"] = 0
    retrying._api_client._request_once = fake_request_once
    with pytest.raises(errors.ClientError):
        retrying.models.generate_content(model="gemini-3.8-flash", contents="x")
    assert calls["n"] == 3


def test_429_stops_the_run_is_logged_not_counted_and_resumable(tmp_path, monkeypatch):
    """Integration (real DB, cached query embeddings, fake LLM client): a 429 on the 2nd call stops the run immediately even with
    --abort-error-rows 0, is written to errors.jsonl with error_kind, and --resume completes the missing rows without a retry."""
    import psycopg2

    from src import db_settings
    from src.phase_d_validation import comparison_runner as cr
    from src.phase_d_validation.llm_client import LLMCallError, LLMClient, LLMResponse
    try:
        psycopg2.connect(**db_settings(), connect_timeout=3).close()
    except psycopg2.OperationalError:
        pytest.skip("PostgreSQL not available")

    class Fake(LLMClient):
        backend = "fake"

        def __init__(self, fail_on=None):
            super().__init__("fake", {}, None)
            self.calls, self.fail_on = 0, fail_on

        def generate(self, system, user, *, max_output_tokens, json_mode=False):
            self.calls += 1
            if self.pacer is not None:
                self.pacer.wait()
            if self.calls == self.fail_on:
                raise LLMCallError("fake/m: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429}}")
            return LLMResponse("1", 1, 1, 0, 0.0, 1.0, {}, {}, "STOP")
    out = tmp_path / "run"
    base = ["--model", "qwen2.5:7b", "--arms", "v2", "--limit", "3", "--table", "finqa_evidence_qwen3", "--k", "15", "--distinct",
            "--query-embeddings", "outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json", "--output-dir", str(out),
            "--abort-error-rows", "0", "--max-calls-per-minute", "6000"]
    import argparse
    import sys

    def run_main(extra, fake):
        monkeypatch.setattr(cr, "make_client", lambda *a, **k: fake)
        monkeypatch.setattr(cr, "ollama_digest", lambda *a, **k: {"digest": "x"})
        monkeypatch.setattr(sys, "argv", ["prog"] + base + extra)
        cr.main()
    with pytest.raises(RuntimeError, match="429 rate limit.*resume manually with --resume"):
        run_main([], Fake(fail_on=2))
    errs = [json.loads(l) for l in (out / "errors.jsonl").read_text().splitlines()]
    done = [json.loads(l) for l in (out / "results.jsonl").read_text().splitlines()]
    assert len(done) == 1 and len(errs) == 1 and errs[0]["error_kind"] == "rate_limit_429" and errs[0]["error_traceback"]
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["pacing"]["max_calls_per_minute"] == 6000 and meta["abort_rules"]["error_rows_allowed_in_first_100_questions"] == 0
    f2 = Fake()
    run_main(["--resume"], f2)
    done = [json.loads(l) for l in (out / "results.jsonl").read_text().splitlines()]
    assert len(done) == 3 and len({(r["pass"], r["query_id"], r["arm"]) for r in done}) == 3 and f2.calls == 2   # only the 2 missing rows ran
    assert (out / "resumes.jsonl").exists()
