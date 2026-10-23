import hashlib

import pytest

from src.phase_d_validation.make_labelling_sheet_v2 import NEW_COLUMN, add_column, drop_last_column, parse, serialise, verify

ROWS = [["sample_id", "question", "gold_answer", "model_answer", "retrieved_passages"],
        ["S001", "what is x, in millions?", "9.2%", "$ -61.1", "[1] a | b\n\n[2] \"quoted\", with comma"],
        ["S002", "q2", "307", "$39", "[1] text"]]


def test_add_column_keeps_everything_else_and_round_trips_bytes():
    v2 = add_column(ROWS)
    assert v2[0] == ROWS[0] + [NEW_COLUMN] and all(r[-1] == "" for r in v2[1:])
    assert drop_last_column(v2) == ROWS
    assert serialise(drop_last_column(v2)) == serialise(ROWS)
    sha = hashlib.sha256(serialise(ROWS)).hexdigest()
    assert all(verify(ROWS, v2, sha).values())
    # the text values a spreadsheet would reformat stay untouched
    assert v2[1][2] == "9.2%" and v2[1][3] == "$ -61.1"


def test_verify_detects_changes():
    v2 = add_column(ROWS)
    v2[1][2] = "9.20%"
    assert not verify(ROWS, v2)["every_original_field_identical"]
    v3 = add_column(ROWS)
    v3[1], v3[2] = v3[2], v3[1]
    assert not verify(ROWS, v3)["row_order_unchanged"]
    v4 = add_column(ROWS)
    v4[1][-1] = "Y"
    assert not verify(ROWS, v4)["new_column_empty"]
    assert not all(verify(ROWS, add_column(ROWS), "0" * 64).values())


def test_add_column_refuses_if_already_present():
    with pytest.raises(ValueError):
        add_column(add_column(ROWS))


def test_parse_serialise_round_trip_with_embedded_newlines_and_quotes():
    assert parse(serialise(ROWS)) == ROWS
