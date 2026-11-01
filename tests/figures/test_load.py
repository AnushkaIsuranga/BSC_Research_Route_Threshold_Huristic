"""Anchor checks for src/figures/load.py on the committed result files. Each expected value is quoted from a report; if one
fails, the loader is reading the wrong file or column."""

import pytest

from src.figures import load as L
from src.figures.style import half_up


# ------------------------------------------------------------------ EDGAR

def test_edgar_retrieval_anchors():
    s = L.edgar_summary().set_index(["mode", "breadth"])
    # reports/phase_f_results_2026-11-01.md A2: "| router | 160 | 1.000 | 0.900 | 38.7 | 7 | exact 160 |"
    assert s.loc[("router", "all"), "recall15_ge_0.90"] == 160 and s.loc[("router", "all"), "n_pairs"] == 160
    # A2: "| default_hnsw | 34 | 0.538 | 0.781 | 9.1 | 106 | hnsw 160 |"
    assert s.loc[("default_hnsw", "all"), "recall15_ge_0.90"] == 34 and s.loc[("default_hnsw", "all"), "underfilled"] == 106
    assert round(s.loc[("router", "all"), "median_latency_ms"], 1) == 38.7


def test_edgar_answer_anchors():
    a = L.edgar_answers_by_mode().set_index(["mode", "breadth"])
    # A4: "router ... | 0.906 [0.838, 0.963]" and "default_hnsw | 0.800 [0.681, 0.906]"
    assert round(a.loc[("router", "all"), "correct"], 3) == 0.906 and a.loc[("router", "all"), "correct_ci"] == "[0.838, 0.963]"
    assert round(a.loc[("default_hnsw", "all"), "correct"], 3) == 0.800 and a.loc[("default_hnsw", "all"), "correct_ci"] == "[0.681, 0.906]"
    p = L.edgar_predictions()
    # A5 P3: "b = 19, c = 2; p = 0.00022"; P4: "0.019 vs 0.088"
    assert (p["P3"]["b_router_only"], p["P3"]["c_default_hnsw_only"]) == (19, 2) and round(p["P3"]["p_exact_mcnemar"], 5) == 0.00022
    assert half_up(p["P4"]["router_rate"]) == "0.019" and half_up(p["P4"]["default_hnsw_rate"]) == "0.088"


def test_edgar_calibration_anchors():
    # A1: "**T_default = T_tuned = 0.3787**"; 13 grid cells g00-g12; "Failing cells by T fall from 7 at g00 to 1 at both 0.3787 and 0.4709"
    assert round(L.edgar_config()["T_default"], 4) == 0.3787 and round(L.edgar_calibration()["T_default"]["T"], 4) == 0.3787
    assert len(L.edgar_cal_cells()) == 13
    f = L.edgar_failures_by_T()
    assert len(f) == 13 and f["failing_cells"].iloc[0] == 7 and f["failing_cells"].min() == 1
    assert [round(t, 4) for t in f.loc[f["failing_cells"] == 1, "T"]] == [0.3787, 0.4709]


def test_edgar_agreement_and_overhead_anchors():
    g = L.edgar_agreement()["all"]
    # A6: "**20 / 22 = 0.909**"; confusion wrong_in_context S 8, N 2, X 16; wrong_not_in_context N 12, X 2
    assert (g["agree"], g["n_scn"]) == (20, 22)
    assert g["confusion"]["wrong_in_context"] == {"S": 8, "C": 0, "N": 2, "X": 16}
    o = L.edgar_overhead().set_index("breadth")
    # B1: "| section | 6.4 | 3.8 | 8.4 (30 of 40) | 18.0 | 266.0 | 287.2 | 267.2 | +20.0 |"
    assert o.loc["section", "pairs_with_count"] == 30 and round(o.loc["section", "router_minus_always_exact_ms"], 1) == 20.0


# ------------------------------------------------------------------ H&M

def test_hm_calibration_anchors():
    c = L.hm_config()
    # reports/phase_e_calibration_hm_2026-10-30.md: "| pooled, default iterative | (0.0478, 0.1061] | **0.0712** |"
    pooled = c["calibration_default"]["pooled"]
    assert round(c["T_default"], 4) == 0.0712 and (round(pooled["lower"], 4), round(pooled["upper"], 4)) == (0.0478, 0.1061)


def test_hm_phase_e_pass_counts():
    # reports/phase_e_results_2026-10-31.md section 2 (in-sample /65, ho1 + ho2 /50)
    expected = {"router": (65, 50), "fixed_t_0_1": (65, 50), "oracle": (65, 50), "iterative_tuned": (59, 50), "always_iterative": (54, 49),
                "local_probe": (64, 46), "planner_iterative": (45, 30), "retry_exact": (45, 30), "always_exact": (25, 15),
                "default_hnsw": (11, 7)}
    df = L.hm_phase_e_pass_counts().set_index("mode")
    for mode, (ins, ho) in expected.items():
        assert (df.loc[mode, "in_sample"], df.loc[mode, "held_out"]) == (ins, ho), mode
    assert df.loc["llm_router", "held_out"] == 18                       # "| llm_router | - | 15/25 | 3/25 |"


def test_hm_route_map_and_switch():
    # reports/arms_results_2026-10-10.md: "Route counts over the 65 cells [V]: iterative-relaxed: 42, forced-exact: 12, forced-hnsw: 11"
    assert L.hm_route_map()["route"].value_counts().to_dict() == {"iterative-relaxed": 42, "forced-exact": 12, "forced-hnsw": 11}
    # same report: "The planner's switch from exact to HNSW lies between 0.2599 (gap3) and 0.2986 (gap4) on every table"
    lo, hi = L.hm_planner_switch()
    assert (round(lo, 4), round(hi, 4)) == (0.2599, 0.2986)


def test_hm_prior_rule_pass_counts():
    # reports/policy_evaluation_2026-10-10.md: "P1 matrix v1 ... | **29** / 65"; holdout_results_2026-10-10.md "| **21** / 25";
    # holdout2_results_2026-10-12.md "| P1 v1 matrix ... | 10/25 |"
    assert L.hm_v1_pass_counts() == {"in_sample": 29, "ho1": 21, "ho2": 10, "held_out": 31}
    # reports/amendment6_partb_2026-10-23.md: "| B4 Gan & Wang, recall/latency labels | 63 | 24 | 25 | 24 |"
    b = L.hm_partb_pass_counts().set_index("rule")
    assert tuple(b.loc["B4 Gan & Wang (recall/latency labels)", ["in_sample", "ho1", "ho2", "ho1_rerun"]]) == (63, 24, 25, 24)


# ------------------------------------------------------------------ FinQA

def test_finqa_anchors():
    s = L.finqa_stats()
    # reports/phase_d_gemini_full_2026-10-12.md: "**policy_v2 36/50 vs naive_llm 32/50; b = 4, c = 0, exact McNemar p = 0.125"
    assert (s["arms"]["policy_v2"]["correct"], s["arms"]["naive_llm"]["correct"]) == (36, 32)
    pr = s["pairs"]["policy_v2_vs_naive_llm"]
    assert (pr["b_X_only_correct"], pr["c_Y_only_correct"], pr["mcnemar_exact_p_two_sided"]) == (4, 0, 0.125)
    # reports/phase_d_always_hnsw_2026-10-31.md: "| always_hnsw | 24/50 (0.48) | 0.520 (130/250) | 0.464 |"
    a = L.finqa_always_hnsw()["arms"]["always_hnsw"]
    assert a["pass1_accuracy"] == 0.48 and a["accuracy"] == 0.52 and a["classes"]["correct"] == 130
    # the class counts file agrees with the pass-1 count above
    c = L.finqa_class_counts().query("arm == 'policy_v2' and `class` == 'correct'").set_index("pass")
    assert int(c.loc["1", "n"]) == 36


def test_prior_constants_from_code():
    p = L.prior_constants()
    assert (p["vbase"]["s"], p["milvus"]["s"]) == (0.18, 0.05)
    # reports/amendment6_partb_2026-10-23.md: "10000 / (2048/256) = **1,250"
    assert p["qdrant_hm"]["rows"] == 1250 and p["qdrant_finqa"]["rows"] == 2500 and p["qdrant_edgar"]["rows"] == 2500


def test_finqa_census_anchor():
    # FINQA_SELECTIVITY_CENSUS_PROTOCOL.md: "2. Run a read-only census over all 1,147 raw FinQA queries."
    # reports/finqa_router_v3_route_check_2026-10-31.md: "no FinQA question exceeds selectivity 0.0297"
    c = L.finqa_census()
    assert len(c) == 1147 and c.id.is_unique
    assert half_up(c.selectivity.max(), 4) == "0.0297"
    s = L.finqa_census_summary()
    assert s["query_count"] == 1147 and s["selectivity_max"] == pytest.approx(c.selectivity.max(), rel=1e-12) and s["corpus_size"] == 35862
