"""Deterministic FinQA answer scoring (no LLM judge).

Numbers: strip $ and thousands commas, "%" is removed and the value stays on the percent scale
("35.9%" == 35.9), "(123)" and "-123" are negative, "a/b" is a ratio. Match = relative
tolerance REL_TOL (1%) on the gold value, abs_tol 1e-9.
Booleans: gold "yes"/"no" (or true/false) matches the same boolean word, true==yes, false==no.
Anything else is unparseable: counted wrong and flagged parse_failure.

Two rules (Amendment 2):
  PRIMARY  = the Amendment 1 rule above plus: a trailing scale word (million, billion, thousand, mn, bn, m, k; case-insensitive,
             optional trailing period) is stripped WITHOUT rescaling: "$18.75 million" -> 18.75, "-$0.5 million" -> -0.5.
  STRICT   = the Amendment 1 rule only (such text is unparseable). Reported alongside.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

REL_TOL = 0.01
ABS_TOL = 1e-9
_NUM = r"\d+(?:\.\d+)?|\.\d+"
_SCALE = re.compile(r"^(.*[\d)])\s*(?:million|billion|thousand|mn|bn|m|k)\.?$", re.IGNORECASE)
_BOOL = {"yes": "yes", "true": "yes", "no": "no", "false": "no"}


class UnparseableNumber(ValueError):
    pass


def parse_financial_number(text: str, strip_scale: bool = False) -> float:
    if not isinstance(text, str):
        raise UnparseableNumber(f"not a string: {text!r}")
    if strip_scale:
        m = _SCALE.match(text.strip())
        if m:
            text = m.group(1)  # scale word dropped, value NOT rescaled
    s = text.strip().replace("−", "-").replace(",", "").replace(" ", "")
    s = s.rstrip(".") if re.search(r"\d\.$", s) else s
    s = s.replace("$", "")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if s[:1] in "+-" and s[:1]:
        neg, s = neg != (s[0] == "-"), s[1:]
    if s.endswith("%"):
        s = s[:-1]
    m = re.fullmatch(rf"({_NUM})/({_NUM})", s)
    if m:
        den = float(m.group(2))
        if den == 0:
            raise UnparseableNumber(f"division by zero in {text!r}")
        val = float(m.group(1)) / den
    elif re.fullmatch(_NUM, s):
        val = float(s)
    else:
        raise UnparseableNumber(f"cannot parse {text!r}")
    return -val if neg else val


@dataclass
class Score:
    correct: bool
    parse_failure: bool
    parsed: float | str | None


def _bool_word(text: str) -> str | None:
    return _BOOL.get(text.strip().lower().rstrip("."))


def score_answer(predicted: str, gold: str, rule: str = "primary") -> Score:
    if rule not in ("primary", "strict"):
        raise ValueError(f"unknown scoring rule {rule!r}")
    strip = rule == "primary"
    g_bool = _bool_word(gold)
    if g_bool is not None:
        p_bool = _bool_word(predicted or "")
        if p_bool is None:
            return Score(False, True, None)
        return Score(p_bool == g_bool, False, p_bool)
    g = parse_financial_number(gold, strip)  # gold must be parseable: a bad gold is a data error, not a model error
    try:
        p = parse_financial_number(predicted, strip)
    except UnparseableNumber:
        return Score(False, True, None)
    return Score(math.isclose(p, g, rel_tol=REL_TOL, abs_tol=ABS_TOL), False, p)
