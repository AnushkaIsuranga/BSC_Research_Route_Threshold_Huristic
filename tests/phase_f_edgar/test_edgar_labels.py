"""Phase F Task 6 labels: join of the author's checked labels to the drafted sheet."""

import pytest

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
