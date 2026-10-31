"""Phase F question verification: number normalisation, company-name checks, scoring of independent answers, status rule."""

from src.phase_f_edgar import verify_questions as V


def test_first_number_normalises():
    n = V.first_number("$3.9 million")
    assert (n.raw, n.full, n.pct, n.span) == (3.9, 3.9e6, False, "$3.9 million")
    assert V.first_number("approximately $103,184,962").raw == 103184962
    assert V.first_number("(1,234)").raw == -1234
    assert V.first_number("$(5.0) million").full == -5e6
    p = V.first_number("25 percent")
    assert p.pct and p.raw == 25 and p.span == "25%"
    assert V.first_number("not answerable") is None


def test_number_in_text_raw_scaled_and_percent():
    assert V.number_in_text(V.first_number("$3.9 million"), "an increase of $3.9 million in 2019")
    assert V.number_in_text(V.first_number("$4.4 billion"), "goodwill of 4,400 million")
    assert V.number_in_text(V.first_number("$42,915 thousand"), "Impairment 42,915 12,000")
    assert V.number_in_text(V.first_number("9.70%"), "a base ROE of 9.7%")
    assert not V.number_in_text(V.first_number("12%"), "12 restaurants")
    assert not V.number_in_text(V.first_number("12"), "12% of sales")
    assert not V.number_in_text(V.first_number("$123"), "a loss of (123)")
    assert V.number_in_text(V.first_number("-$123"), "a loss of $(123)")


def test_like_patterns_cover_scaled_forms():
    pats = V.like_patterns(V.first_number("$3.9 million"))
    assert "%3.9%" in pats and "%3900%" in pats and "%3900000%" in pats
    assert "%.5%" in V.like_patterns(V.first_number("0.5"))


def test_company_core_and_match():
    assert V.core_name("Diebold Nixdorf, Incorporated") == ["diebold", "nixdorf"]
    assert V.core_name("The Cheesecake Factory Incorporated") == ["cheesecake", "factory"]
    assert V.name_in(V.core_name("People�s United Financial, Inc."), "People's United Financial reported")
    assert not V.name_in(V.core_name("Lear Corporation"), "Clear Channel")


def test_subsidiary_evidence():
    core = V.core_name("River Bank & Trust")
    assert V.subsidiary_evidence(core, ["The Company's wholly owned bank subsidiary, River Bank & Trust, operates 20 branches."])
    assert V.subsidiary_evidence(V.core_name("IBM Credit LLC"), ["IBM Credit LLC is a wholly-owned subsidiary of IBM."])
    assert V.subsidiary_evidence(core, ["the shareholders of River Bank & Trust became the wholly owned subsidiary of River Financial."])
    assert not V.subsidiary_evidence(V.core_name("Camden Property Trust"), ["Camden Property Trust and its subsidiaries own 170 properties."])
    assert not V.subsidiary_evidence(V.core_name("Unitil Corporation"), ["The following companies are wholly-owned subsidiaries of Unitil: x"])
    assert not V.subsidiary_evidence(V.core_name("J2 Global, Inc."), ["J2 Global, Inc., together with its subsidiaries, is a provider"])


def test_judge_verdict_uses_primary_rule():
    gold = V.first_number("$59.65 per Bbl")
    assert V.judge_verdict("$59.65 per barrel", gold)[0] == "Y"
    assert V.judge_verdict("not answerable", gold) == ("N", "", "not answerable")
    assert V.judge_verdict("about sixty dollars", gold)[0] == "N"
    assert V.judge_verdict(None, gold)[0] == "N"
    # Amendment 2 primary rule: scale word dropped without rescaling
    assert V.judge_verdict("$3,900,000", V.first_number("$3.9 million"))[0] == "N"
    assert V.judge_verdict("3.9 million dollars", V.first_number("$3.9 million"))[0] == "Y"


def _row(**kw):
    r = {"A_number_in_chunk": "Y", "B_agree": "N", "C_company_match": "Y", "C_subsidiary_flag": "N",
         "D_gold_in_top15_cik+year+section": "Y", "E_generic_fact": "N", "E_n_other_chunks": 0}
    r.update(kw)
    return r


def test_status_rule():
    assert V.failing_checks(_row()) == []
    assert V.failing_checks(_row(A_number_in_chunk="n/a", B_agree="Y")) == []
    assert V.failing_checks(_row(A_number_in_chunk="n/a")) == ["A/B (A=n/a, B=N)"]
    assert V.failing_checks(_row(C_subsidiary_flag="Y")) == ["C_subsidiary_flag"]
    assert V.failing_checks(_row(E_generic_fact="Y", E_n_other_chunks=7)) == ["E_generic_fact (7 chunks)"]
    assert V.failing_checks(_row(**{"D_gold_in_top15_cik+year+section": "N"})) == ["D_cik+year+section"]


def test_review_sheet_order_and_sample():
    from src.phase_f_edgar.review_sheet import order_rows
    checks = [{"qid": f"edgar_q{i:03d}", "status": "auto_pass", "A_number_in_chunk_any_type": "Y"} for i in range(1, 61)]
    for q in ("edgar_q005", "edgar_q033", "edgar_q057"):
        next(r for r in checks if r["qid"] == q)["status"] = "needs_review"
    next(r for r in checks if r["qid"] == "edgar_q020")["A_number_in_chunk_any_type"] = "N"
    next(r for r in checks if r["qid"] == "edgar_q020")["status"] = "needs_review"
    rows, sampled = order_rows(checks)
    assert len(sampled) == 10 and all(q not in sampled for q in ("edgar_q005", "edgar_q020", "edgar_q033", "edgar_q057"))
    assert [r["qid"] for r in rows[:3]] == ["edgar_q020", "edgar_q057", "edgar_q033"]
    assert len(rows) == 14 and rows == order_rows(checks)[0]
