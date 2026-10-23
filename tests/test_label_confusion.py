import pytest

from src.phase_d_validation.label_confusion import load_labels, note_counts, tables, verify_labelled_copy

ORIG = [["sample_id", "question", "gold_answer", "model_answer", "retrieved_passages"],
        ["S001", "q1", "9.2%", "$ -61.1", "[1] a"],
        ["S002", "q2", "307", "$39", "[1] b"]]


def chk(edit=None):
    edit = edit or {}
    c = [r + ["S", "Y"] for r in ORIG[1:]]
    c = [ORIG[0] + ["check", "gold_derivable"]] + c
    for (i, j), v in edit.items():
        c[i][j] = v
    return c


def test_verify_accepts_formatting_only_differences():
    c = chk({(1, 2): "9.20%", (1, 3): "($61.10)", (2, 3): "$39 "})
    r = verify_labelled_copy(c, ORIG)
    assert r["identical_columns"]["question"] == 2 and r["identical_columns"]["gold_answer"] == 1
    assert {x["sample_id"] for x in r["formatting_only_cells"]} == {"S001", "S002"} and len(r["formatting_only_cells"]) == 3


@pytest.mark.parametrize("edit", [{(1, 1): "other question"}, {(2, 4): "[1] changed"}, {(1, 2): "9.3%"}, {(2, 3): "$40"}, {(1, 0): "S009"}])
def test_verify_rejects_real_differences(edit):
    with pytest.raises(ValueError):
        verify_labelled_copy(chk(edit), ORIG)


def test_verify_rejects_row_count_or_header_change():
    with pytest.raises(ValueError):
        verify_labelled_copy(chk()[:-1], ORIG)
    bad = chk()
    bad[0][1] = "Question"
    with pytest.raises(ValueError):
        verify_labelled_copy(bad, ORIG)


def test_load_labels_accepts_lowercase_and_rejects_invalid():
    c = chk({(1, 5): " c ", (2, 6): "n"})
    lab = load_labels(c)
    assert lab["S001"] == {"scn": "C", "gd": "Y", "note": None} and lab["S002"]["gd"] == "N"
    for bad in ({(1, 5): "X"}, {(1, 5): ""}, {(2, 6): "maybe"}, {(2, 6): ""}):
        with pytest.raises(ValueError):
            load_labels(chk(bad))


def rows(spec):
    return [{"sample_id": f"S{i:03d}", "query_id": q, "arm": "a", "proxy": p, "scn": s, "gd": g, "note": None} for i, (q, p, s, g) in enumerate(spec, 1)]


def test_tables_per_row_and_per_distinct_question():
    r = rows([("q1", "wrong_ungrounded", "N", "N"), ("q1", "wrong_ungrounded", "C", "Y"), ("q2", "wrong_ungrounded", "N", "N"),
              ("q3", "wrong_grounded", "S", "Y"), ("q3", "wrong_grounded", "S", "Y"), ("q4", "wrong_grounded", "C", "N")])
    t = tables(r)
    wu = t["per_row"]["proxy_x_scn"]["wrong_ungrounded"]
    assert wu["rows"] == 3 and wu["cells"]["N"]["n"] == 2 and wu["cells"]["C"]["n"] == 1 and wu["cells"]["S"]["n"] == 0
    qu = t["per_question"]["proxy_x_scn"]["wrong_ungrounded"]
    assert qu["distinct_questions"] == 2 and qu["cells"]["N"]["n"] == 2 and qu["cells"]["C"]["n"] == 1      # q1 appears in two cells
    assert t["per_question"]["proxy_x_gold_derivable"]["wrong_grounded"]["cells"]["Y"]["n"] == 1
    sv = t["supported_vs_unsupported"]
    assert sv["per_row"]["wrong_ungrounded"]["unsupported_N"]["n"] == 2 and sv["per_row"]["wrong_grounded"]["supported_S_or_C"]["n"] == 3
    assert t["questions_with_mixed_labels_within_class"]["scn"] == 1 and t["questions_with_mixed_labels_within_class"]["question_class_pairs"] == 4
    lo, hi = wu["cells"]["N"]["ci95"]
    assert lo < 2 / 3 < hi


def test_note_counts_not_available_without_a_note_column_and_keyword_rules_with_one():
    assert note_counts(rows([("q1", "wrong_grounded", "S", "Y")]))["available"] is False
    r = rows([("q1", "wrong_grounded", "S", "Y"), ("q2", "wrong_ungrounded", "N", "N"), ("q3", "wrong_grounded", "C", "Y"), ("q4", "wrong_grounded", "S", "Y")])
    r[0]["note"], r[1]["note"], r[2]["note"], r[3]["note"] = "Rounding: 14.5 vs 14", "gold looks wrong", "count vs percentage mismatch", ""
    n = note_counts(r)
    assert n["available"] and n["rows_with_any_note"] == 3
    assert n["by_topic"]["rounding"]["rows"] == 1 and n["by_topic"]["suspected gold error"]["rows"] == 1 and n["by_topic"]["count vs percentage"]["rows"] == 1
    assert n["by_topic"]["scale"]["rows"] == 0
