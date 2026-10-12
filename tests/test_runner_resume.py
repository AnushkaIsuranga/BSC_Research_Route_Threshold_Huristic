"""Amendment 4 runner additions: resume state, error-rate and projected-cost abort rules, refusal without --resume."""
import json
import subprocess
import sys

import pytest

from src.phase_d_validation.comparison_runner import error_rule, load_resume_state, projected_cost


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


def test_error_rule_two_percent_of_first_100_questions_x_4_arms():
    window = [f"q{i}" for i in range(100)]
    errs = [{"query_id": f"q{i}"} for i in range(8)]
    assert error_rule(errs, window, 4, 0.02) == {"errors_in_window": 8, "allowed": 8.0, "triggered": False}
    assert error_rule(errs + [{"query_id": "q50"}], window, 4, 0.02)["triggered"] is True
    assert error_rule(errs + [{"query_id": "q150"}], window, 4, 0.02)["triggered"] is False   # outside the window


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
