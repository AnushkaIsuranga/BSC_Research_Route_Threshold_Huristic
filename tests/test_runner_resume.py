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
