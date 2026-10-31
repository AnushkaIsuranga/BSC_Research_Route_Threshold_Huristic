"""Phase F company-name extraction from section 1 (cases taken from the 2026-10-31 spot checks)."""

import pytest

from src.phase_f_edgar.build_chunks import extract_name, majority_name, name_status


@pytest.mark.parametrize("text, name", [
    ("Item 1. Business Overview Allegion plc (\"Allegion,\" \"we,\" \"us\" or \"the Company\") is a leading", "Allegion plc"),
    ("ITEM 1. BUSINESS (a) General Development of the Business Colgate-Palmolive Company (together with its subsidiaries, "
     "“we,” \"us,\" the “Company”)", "Colgate-Palmolive Company"),
    ("Item 1.Business Corporate Profile Cousins Properties Incorporated (the “Registrant” or “Cousins”)",
     "Cousins Properties Incorporated"),
    ("ITEM 1. BUSINESS Overview Zion Oil and Gas, Inc., a Delaware corporation, is an oil and gas company", "Zion Oil and Gas, Inc."),
    ("Item 1. Business Overview MoSys, Inc., together with its subsidiaries (“MoSys,” the “Company,”)", "MoSys, Inc."),
    ("Item 1. BUSINESS All references in this report to “Corbus,” the “Company,” mean Corbus Pharmaceuticals "
     "Holdings, Inc. and its subsidiary", "Corbus Pharmaceuticals Holdings, Inc."),
    ("Item 1.Business Dover Motorsports, Inc. is a public holding company", "Dover Motorsports, Inc."),
    ("Item 1. Business Publix Super Markets, Inc. and its wholly owned subsidiaries (Company) are in the business",
     "Publix Super Markets, Inc."),
    ("Item 1. Business Overview We are a clinical-stage biopharmaceutical company.", None),
    ("Item 1. Business. Omitted. Item 1A.", None),
    ("", None),
])
def test_extract_name(text, name):
    assert extract_name(text) == name


def test_majority_rule():
    assert name_status({}) == "none_found"
    assert name_status({2018: "A Inc."}) == "single_year"
    assert name_status({2018: "A Inc.", 2019: "B Inc."}) == "conflict"
    found = {2018: "Command Center, Inc.", 2019: "HireQuest, Inc.", 2020: "HireQuest Inc"}
    assert name_status(found) == "agree" and majority_name(found) == "HireQuest Inc"
