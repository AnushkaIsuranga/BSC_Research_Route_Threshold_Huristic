from src.phase_c_analysis.amendment6_partb import B3_ROWS, EXACT, ITER, labels, score, threshold_rules


def cell(s, exact, iterative, n=20):
    return {"s": s, "rows": round(s * 105_100), "q": {v: {EXACT: exact, ITER: iterative} for v in range(n)}}


def test_threshold_rules_boundaries():
    r = threshold_rules()
    assert B3_ROWS == 1250
    assert r["policy_v2"](0.0999, 0) == EXACT and r["policy_v2"](0.1, 0) == ITER
    assert r["B1 VBASE (s < 0.18)"](0.1799, 0) == EXACT and r["B1 VBASE (s < 0.18)"](0.18, 0) == ITER
    assert r["B2 Milvus via NaviX (s <= 0.05)"](0.05, 0) == EXACT and r["B2 Milvus via NaviX (s <= 0.05)"](0.0501, 0) == ITER
    assert r["B3 Qdrant (rows < 1,250)"](0.5, 1249) == EXACT and r["B3 Qdrant (rows < 1,250)"](0.0, 1250) == ITER


def test_labels_ratio_and_sla():
    cells = {("t", "a"): cell(0.01, (1.0, 10.0), (0.5, 1.0)), ("t", "b"): cell(0.3, (1.0, 600.0), (0.95, 50.0))}
    _, y = labels(cells, "ratio")
    assert set(y[:20]) == {ITER} and set(y[20:]) == {ITER}     # 0.5/1 > 1/10: fast low-recall plan wins
    _, y = labels(cells, "sla")
    assert set(y[:20]) == {EXACT} and set(y[20:]) == {ITER}


def test_score_pass_fail_and_not_scored():
    cells = {("t", "a"): cell(0.05, (1.0, 600.0), (0.95, 5.0)), ("t", "b"): cell(0.2, (1.0, 10.0), (0.5, 5.0))}
    del cells[("t", "b")]["q"][3][ITER]
    out = {(r["filter_id"]): r for r in score(cells, threshold_rules()["policy_v2"])}
    assert out["a"]["status"] == "fail" and out["a"]["reason"] == "latency"
    assert out["b"]["status"] == "not scored"
