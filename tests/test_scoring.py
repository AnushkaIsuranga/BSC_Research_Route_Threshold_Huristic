import pytest

from src.phase_d_validation.scoring import UnparseableNumber, parse_financial_number, score_answer


@pytest.mark.parametrize("text,val", [
    ("18.75", 18.75), ("1,056.5", 1056.5), ("$5,000", 5000), ("35.9%", 35.9), ("-8.5%", -8.5),
    ("(123)", -123), ("($1,234.50)", -1234.5), ("(5.2%)", -5.2), ("-$5", -5), ("$-5", -5), ("3/4", 0.75),
    ("1/8", 0.125), ("  42 ", 42), ("−12", -12), ("0", 0), (".5", 0.5), ("12.", 12), ("+3", 3),
])
def test_parse(text, val):
    assert parse_financial_number(text) == pytest.approx(val)


@pytest.mark.parametrize("text", ["", "N/A", "abc", "1/0", "about 5", "5 million", "--5", "1.2.3", None])
def test_unparseable(text):
    with pytest.raises(UnparseableNumber):
        parse_financial_number(text)


def test_match_tolerance():
    assert score_answer("18.75", "18.8").correct
    assert not score_answer("18.0", "18.8").correct
    assert score_answer("0", "0").correct
    assert not score_answer("0.1", "0").correct


def test_percent_same_scale():
    assert score_answer("35.9%", "35.9%").correct
    assert score_answer("35.9", "35.9%").correct
    assert not score_answer("0.359", "35.9%").correct


def test_negative_forms():
    assert score_answer("(84)", "-84").correct
    assert not score_answer("84", "-84").correct


def test_ratio():
    assert score_answer("3/4", "0.75").correct


def test_boolean():
    assert score_answer("Yes", "yes").correct and score_answer("True", "yes").correct
    assert not score_answer("False", "yes").correct and not score_answer("False", "yes").parse_failure
    assert score_answer("no", "no").correct


def test_unparseable_prediction_is_wrong_and_flagged():
    s = score_answer("The information provided does not specify the total.", "3081")
    assert not s.correct and s.parse_failure and s.parsed is None
    s = score_answer("maybe", "yes")
    assert not s.correct and s.parse_failure


def test_parseable_wrong_is_not_parse_failure():
    s = score_answer("5", "6")
    assert not s.correct and not s.parse_failure
