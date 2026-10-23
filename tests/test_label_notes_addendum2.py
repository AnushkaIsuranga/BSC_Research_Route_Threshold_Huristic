import pytest

from src.phase_d_validation.label_notes_addendum2 import a1_tables, join_and_check, note_counts, topics

USED = [{"sample_id": "S001", "query_id": "q1", "arm": "a", "proxy": "wrong_grounded", "scn": "C", "gd": "Y", "note": ""},
        {"sample_id": "S002", "query_id": "q1", "arm": "a", "proxy": "wrong_ungrounded", "scn": "N", "gd": "N", "note": ""},
        {"sample_id": "S003", "query_id": "q2", "arm": "a", "proxy": "wrong_grounded", "scn": "S", "gd": "Y", "note": ""}]


def lab(**edit):
    rows = [{"sample_id": u["sample_id"], "gold_answer": "x", "check": u["scn"], "gold_derivable": u["gd"], "note": ""} for u in USED]
    for sid, (col, v) in edit.items():
        next(r for r in rows if r["sample_id"] == sid)[col] = v
    return rows


def test_join_ignores_other_columns_and_attaches_notes():
    rows = join_and_check(lab(S001=("gold_answer", "9.20%"), S003=("note", "rounding: off by 0.2")), ["S001", "S002", "S003"], USED)
    assert [r["note"] for r in rows] == ["", "", "rounding: off by 0.2"]


@pytest.mark.parametrize("edit", [{"S002": ("check", "C")}, {"S001": ("gold_derivable", "N")}, {"S003": ("sample_id", "S009")}])
def test_join_stops_on_label_or_id_difference(edit):
    with pytest.raises(ValueError):
        join_and_check(lab(**edit), ["S001", "S002", "S003"], USED)


def test_topics_and_counts():
    assert topics("possible gold error: question asks for 2010") == ["suspected gold error"]
    assert topics('question asks "how many"; 1692 is a valid count, gold expects a percentage') == ["count vs percentage"]
    assert topics("scale; answered in millions") == ["scale"]
    assert topics("question wording ambiguous") == []
    rows = join_and_check(lab(S001=("note", "rounding"), S002=("note", "rounding too"), S003=("note", "ambiguous")), ["S001", "S002", "S003"], USED)
    n = note_counts(rows)
    assert n["by_topic"]["rounding"]["rows"] == 2 and n["by_topic"]["rounding"]["distinct_questions"] == 1
    assert n["by_topic"]["rounding"]["rows_by_proxy_class"] == {"wrong_ungrounded": 1, "wrong_grounded": 1}
    assert n["by_topic"]["other note only"]["sample_ids"] == ["S003"] and n["by_topic"]["no note"]["rows"] == 0


def test_a1_tables_copies_block_verbatim():
    rep = "intro\n## Per row (40 rows)\n\n| t | 1 |\n\n## Per distinct question (17 questions)\n\n| t | 2 |\n\nWithin a proxy class, questions with rows ...\n"
    b = a1_tables(rep)
    assert "| t | 1 |" in b and "| t | 2 |" in b and "Within" not in b and "model-drafted labels verified by the author" in b
