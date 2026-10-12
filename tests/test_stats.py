import pytest

from src.phase_d_validation.paired_stats import (bootstrap_mean_diff, compare, mcnemar_exact, newcombe_paired_diff, wilson)


def test_mcnemar_known_values():
    assert mcnemar_exact(3, 1) == pytest.approx(0.625)
    assert mcnemar_exact(10, 0) == pytest.approx(2 * 0.5 ** 10)
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == pytest.approx(1.0)


def test_wilson_bounds():
    lo, hi = wilson(0, 50)
    assert lo == pytest.approx(0, abs=1e-9) and 0 < hi < 0.1
    assert wilson(50, 50)[1] == pytest.approx(1.0, abs=1e-9)


def test_newcombe_contains_diff_and_symmetric_when_equal():
    d, lo, hi = newcombe_paired_diff(8, 3, 1, 38)
    assert d == pytest.approx(0.04) and lo < d < hi
    d, lo, hi = newcombe_paired_diff(8, 2, 2, 38)
    assert d == 0 and lo == pytest.approx(-hi)


def test_bootstrap_fixed_seed_reproducible():
    x, y = [10, 12, 9, 15, 11, 14], [8, 9, 9, 10, 10, 9]
    assert bootstrap_mean_diff(x, y) == bootstrap_mean_diff(x, y)
    m, lo, hi = bootstrap_mean_diff(x, y)
    assert lo <= m <= hi and m == pytest.approx(sum(a - b for a, b in zip(x, y)) / 6)


def test_compare_counts():
    a = {str(i): {"correct": int(i < 6), "total_ms": 10.0} for i in range(10)}
    b = {str(i): {"correct": int(i in (0, 1, 8)), "total_ms": 5.0} for i in range(10)}
    r = compare(a, b)
    assert (r["both_correct"], r["b_X_only_correct"], r["c_Y_only_correct"], r["both_wrong"]) == (2, 4, 1, 3)
    assert r["mcnemar_exact_p_two_sided"] == pytest.approx(mcnemar_exact(4, 1))
    assert r["latency_total_ms_mean_diff_X_minus_Y"] == pytest.approx(5.0)


def test_margin_is_required(tmp_path):
    import subprocess, sys, json
    f = tmp_path / "r.jsonl"
    rows = []
    for arm in ("policy_v2", "naive_llm", "decision_matrix"):
        for i in range(10):
            rows.append({"pass": 1, "arm": arm, "query_id": str(i), "correct": int(i < 5), "total_ms": 10.0 + i, "retrieval_hit": 1,
                         "parse_failure": 0, "route_parse_failure": 0, "route": "x", "embed_ms": 1, "db_ms": 1, "router_ms": 1,
                         "generation_ms": 1, "input_tokens": 1, "output_tokens": 1, "thinking_tokens": 0, "router_input_tokens": None,
                         "router_output_tokens": None, "cost_usd": 0.0, "rows_returned": 6})
    f.write_text("\n".join(json.dumps(r) for r in rows))
    base = [sys.executable, "-m", "src.phase_d_validation.paired_stats", str(f), "--out", str(tmp_path / "o.json")]
    assert subprocess.run(base, capture_output=True).returncode != 0          # no --margin: refuses
    ok = subprocess.run(base + ["--margin", "0.1"], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    res = json.loads((tmp_path / "o.json").read_text())
    assert res["non_inferiority"]["policy_v2_vs_naive_llm"]["non_inferior"] is True
