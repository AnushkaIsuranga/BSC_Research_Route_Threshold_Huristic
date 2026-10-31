"""Phase F evaluation Task 1: selection rule of docs/EDGAR_QUESTION_METHOD.md section 4."""

import random

import pytest

from src.phase_f_edgar.select_eval_set import residual_flag, select


def _data(n=60, calcs=(11, 44, 53)):
    cands = {f"q{i:03d}": {"drafted_answer": f"${i}.5 million", "type": "calculation" if i in calcs else "lookup"}
             for i in range(1, n + 1)}
    checks = {q: {"status": "auto_pass" if int(q[1:]) <= 30 else "needs_review"} for q in cands}
    return cands, checks


def test_eligibility_and_draw():
    cands, checks = _data()
    review = {"q005": {"decision": "drop"}, "q044": {"decision": "drop"}, "q053": {"decision": "keep"},
              "q040": {"decision": "fix", "corrected_answer": "$9 million", "corrected_type": "calculation"},
              "q041": {"decision": "keep"}}
    s = select(checks, review, cands, seed=20261101, n_target=20)
    assert "q005" not in s["eligible"] and "q044" not in s["eligible"]          # drop removes even auto_pass
    assert s["eligible"]["q040"] == {"answer": "$9 million", "type": "calculation", "basis": "author_fix"}
    assert s["calculations"] == ["q011", "q040", "q053"]
    assert set(s["calculations"]) <= set(s["selected"]) and len(s["selected"]) == 20 and s["shortfall"] == 0
    lookups = sorted(q for q, e in s["eligible"].items() if e["type"] == "lookup")
    assert s["lookups_drawn"] == sorted(random.Random(20261101).sample(lookups, 17))
    assert all(q not in s["eligible"] for q in ("q031", "q050"))               # needs_review without a keep


def test_shortfall_and_bad_decision():
    cands, checks = _data(n=10)
    s = select(checks, {}, cands, n_target=40)
    assert len(s["selected"]) == 10 and s["shortfall"] == 30
    with pytest.raises(ValueError):
        select(checks, {"q001": {"decision": "maybe"}}, cands)


def test_residual_flag():
    assert residual_flag("approximately 27%", "27%") == "qualifier"
    assert residual_flag("$59.65 per Bbl", "$59.65") == ""
    assert residual_flag("5,929 shares for 921 warrants", "5,929") == "more than one number"
