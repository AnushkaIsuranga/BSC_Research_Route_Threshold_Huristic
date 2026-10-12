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


# ---- Amendment 3: pooled analysis over passes
def _rows(spec):
    """spec: {(arm, query, pass): correct}"""
    return [{"arm": a, "query_id": q, "pass": p, "correct": c, "parsed_answer": c, "raw_output": str(c), "route": "x"}
            for (a, q, p), c in spec.items()]


def test_pooled_compare_means_and_ci():
    from src.phase_d_validation.paired_stats import pooled_compare
    spec = {}
    for q in range(20):
        for p in range(1, 6):
            spec[("policy_v2", str(q), p)] = int(q < 10)              # mean 0.5
            spec[("naive_llm", str(q), p)] = int(q < 10 or (q < 12 and p <= 2))   # q10,q11 correct in 2/5 passes
    r = pooled_compare(_rows(spec), "policy_v2", "naive_llm", [1, 2, 3, 4, 5], margin=0.10)
    assert r["n_queries"] == 20
    assert r["mean_accuracy_X"] == pytest.approx(0.5)
    assert r["mean_accuracy_Y"] == pytest.approx(0.5 + 2 * 0.4 / 20)
    assert r["pooled_diff_X_minus_Y"] == pytest.approx(-0.04)
    lo, hi = r["pooled_diff_ci95"]
    assert lo <= -0.04 <= hi and hi <= 0 and r["non_inferior"] == (lo > -0.10)
    assert pooled_compare(_rows(spec), "policy_v2", "naive_llm", [1, 2, 3, 4, 5]) == {k: v for k, v in r.items() if k != "non_inferior"}


def test_pooled_identical_arms_zero_width():
    from src.phase_d_validation.paired_stats import pooled_compare
    spec = {(a, str(q), p): int((q + p) % 3 == 0) for a in ("decision_matrix", "policy_v2") for q in range(10) for p in range(1, 6)}
    r = pooled_compare(_rows(spec), "decision_matrix", "policy_v2", [1, 2, 3, 4, 5])
    assert r["pooled_diff_X_minus_Y"] == 0 and r["pooled_diff_ci95"] == [0.0, 0.0]


def test_pooled_refuses_missing_pass_or_duplicates():
    from src.phase_d_validation.paired_stats import pooled_compare
    spec = {(a, "q", p): 1 for a in ("policy_v2", "naive_llm") for p in range(1, 6)}
    rows = _rows(spec)
    with pytest.raises(ValueError, match="missing"):
        pooled_compare([r for r in rows if not (r["arm"] == "naive_llm" and r["pass"] == 3)], "policy_v2", "naive_llm", [1, 2, 3, 4, 5])
    with pytest.raises(ValueError, match="duplicate"):
        pooled_compare(rows + rows[:1], "policy_v2", "naive_llm", [1, 2, 3, 4, 5])


def test_multi_pass_agreement_counts():
    from src.phase_d_validation.paired_stats import multi_pass_agreement
    spec = {("policy_v2", "a", p): 1 for p in range(1, 6)}
    spec.update({("policy_v2", "b", p): int(p == 1) for p in range(1, 6)})
    r = multi_pass_agreement(_rows(spec))["policy_v2"]
    assert r["n_queries"] == 2 and r["same_answer_all_passes"] == 1 and r["same_correctness_all_passes"] == 1
    assert r["correct_per_pass"] == {"1": 2, "2": 1, "3": 1, "4": 1, "5": 1}
