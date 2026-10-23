from src.phase_d_validation.ragas_analysis import agreement, kappa, stage2


def test_kappa_known_values():
    assert kappa([(1, 1), (0, 0)]) == 1.0
    assert kappa([(1, 1)] * 4) is None                        # one class only: undefined
    # 2x2 [[a=20, b=5], [c=10, d=15]]: po = 0.7, pe = 0.5 -> 0.4
    pairs = [(1, 1)] * 20 + [(1, 0)] * 5 + [(0, 1)] * 10 + [(0, 0)] * 15
    assert abs(kappa(pairs) - 0.4) < 1e-12


def row(q, lab, status="ok", f=1.0, p=1, arm="policy_v2", sid="S"):
    return {"row": f"{p}|{arm}|{q}", "pass": p, "arm": arm, "query_id": q, "sample_id": sid, "label_scn": lab, "status": status, "faithfulness": f}


def test_agreement_excludes_errors_and_counts_by_scn():
    rows = [row("q1", "C", f=0.0), row("q1", "C", f=1.0), row("q2", "N", f=0.0), row("q3", "S", status="judge_error", f=None)]
    a = agreement(rows)
    assert a["per_row"]["n"] == 3 and a["per_row"]["excluded"] == {"judge_error": 1}
    assert a["per_row"]["by_scn"]["C"] == {"rows": 2, "judge_unsupported": 1, "judge_supported": 1}
    assert a["per_question"]["n"] == 2                      # q1 mean 0.5 -> supported, q2 unsupported
    assert a["per_question"]["accuracy"] == 1.0
    s = agreement(rows, sensitivity=True)
    assert s["per_row"]["n"] == 4


def test_stage2_no_context_zero_and_drop_labelled():
    rows = []
    for p in range(1, 6):
        for q in ("a", "b"):
            rows.append(row(q, None, f=1.0, p=p, arm="policy_v2", sid=None))
            rows.append(row(q, None, status="no_context" if q == "b" else "ok", f=0.0, p=p, arm="naive_llm", sid="S1" if (p, q) == (1, "a") else None))
            rows.append(row(q, None, f=1.0, p=p, arm="decision_matrix", sid=None))
            rows.append(row(q, None, f=1.0, p=p, arm="naive_informed", sid=None))
    r = stage2(rows, drop_labelled=False)
    assert r["per_arm"]["naive_llm"]["pooled"]["share_supported"] == 0.0
    assert r["paired_policy_v2_vs_naive_llm"]["pooled"]["pairs"] == 10
    assert r["paired_policy_v2_vs_naive_llm"]["pooled"]["diff_share_supported_policy_v2_minus_naive_llm"] == 1.0
    d = stage2(rows, drop_labelled=True)
    assert d["paired_policy_v2_vs_naive_llm"]["pooled"]["pairs"] == 9
    e = stage2(rows, drop_labelled=False, no_ctx="exclude")
    assert e["per_arm"]["naive_llm"]["pooled"]["n"] == 5
