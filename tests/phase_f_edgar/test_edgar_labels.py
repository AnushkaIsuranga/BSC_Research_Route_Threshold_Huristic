"""Phase F Task 6 labels: join of the author's checked labels, proxy agreement and the exploratory re-score rules."""

import pytest

from src.phase_f_edgar import exploratory_edgar as EX
from src.phase_f_edgar import join_labels_edgar as J


def _orig(n=3):
    return [{"sample_id": f"L{i:02d}", "question": f"q{i}", "drafted_label": "S", "author_label": "", "author_note": ""} for i in range(1, n + 1)]


def _auth(labels, ids=None):
    ids = ids or [f"L{i:02d}" for i in range(1, len(labels) + 1)]
    return [{"sample_id": i, "question": "EXCEL CHANGED", "drafted_label": "?", "author_label": l, "author_note": f"note {i} "}
            for i, l in zip(ids, labels)]


def test_join_takes_only_label_columns_from_author():
    rows = J.join(_orig(), list(reversed(_auth(["S", "N ", "X"]))), n_rows=3)
    assert [r["sample_id"] for r in rows] == ["L01", "L02", "L03"]
    assert [r["author_label"] for r in rows] == ["S", "N", "X"] and rows[0]["author_note"] == "note L01"
    assert all(r["question"].startswith("q") and r["drafted_label"] == "S" for r in rows)


def test_join_stops_on_id_mismatch_or_bad_label():
    with pytest.raises(ValueError, match="sample_ids differ"):
        J.join(_orig(), _auth(["S", "S", "S"], ["L01", "L02", "L04"]), n_rows=3)
    with pytest.raises(ValueError, match="sample_ids differ"):
        J.join(_orig(), _auth(["S", "S"]), n_rows=3)
    with pytest.raises(ValueError, match="not in"):
        J.join(_orig(), _auth(["S", "Y", ""]), n_rows=3)


# ------------------------------------------------------------------ exploratory re-scores

def test_refusal_rule():
    for raw in ("I am sorry, but the provided evidence does not contain information about X during fiscal year 2018.",
                "Based on the provided evidence, there is no mention of the Infinity Note during fiscal year 2018.",
                'The provision "decreased by $1.2 million"; the exact amount is not explicitly stated.',
                "The exact amount for fiscal year 2018 is not contained in the supplied evidence."):
        assert EX.is_refusal(raw) and EX.refusal_class("wrong_in_context", raw) == "abstained"
    for raw in ("$42.9 million", "34,500,000", "approximately 12.5%", None, ""):
        assert not EX.is_refusal(raw)
    assert EX.refusal_class("correct", "It does not state it, but $5 million") == "correct"
    assert EX.refusal_class("wrong_not_in_context", "$5 million") == "wrong_not_in_context"


def test_scale_aware_matching():
    assert EX.scale_correct("34,500,000", "34.5 million")
    assert EX.scale_correct("$42.9 million", "$42,915 thousand")              # 42.9e6 vs 42.915e6: within 1 %
    assert not EX.scale_correct("$1.564 billion", "$1.6 billion")             # 2.3 % apart
    assert not EX.scale_correct("$13,060 thousand", "$13,060")                # scale applied on one side only
    assert EX.scale_correct("12.5%", "12.5%") and not EX.scale_correct(None, "1")
    assert EX.scale_class("abstained", None, "1", []) == "abstained"
    assert EX.scale_class("wrong_not_in_context", "34,500,000", "34.5 million", []) == "correct"
    assert EX.scale_class("correct", "$13,060 thousand", "$13,060", ["total $13,060 thousand"]) == "wrong_in_context"


def test_agreement_excludes_x():
    rows = [{"proxy_class": "wrong_not_in_context", "label": "N"}, {"proxy_class": "wrong_in_context", "label": "S"},
            {"proxy_class": "wrong_in_context", "label": "N"}, {"proxy_class": "wrong_in_context", "label": "X"}]
    a = EX.agreement(rows)
    assert a["n_scn"] == 3 and a["n_x"] == 1 and a["agree"] == 2 and a["agreement"] == 2 / 3
    assert a["confusion"]["wrong_in_context"] == {"S": 1, "C": 0, "N": 1, "X": 1}
    assert a["share_of_N_flagged_by_proxy"] == 0.5 and a["share_of_proxy_labelled_N"] == 1.0
