"""Task 5 (figures session, 2026-11-01): check every figure's plotted values and every table against anchor numbers and the
report sentences they illustrate; check the printed size of every PNG. Writes reports/figures_2026-11-01/CHECKS.md and exits
non-zero if any check fails.

  python -m src.figures.check_figures
"""

from __future__ import annotations

import math
import sys

import pandas as pd
from PIL import Image

from src.figures import style as S

D = S.FIG_DIR / "data"
T = S.TAB_DIR
ROWS: list[tuple] = []


def fig(stem):
    return pd.read_csv(D / f"{stem}.csv")


def tab(stem):
    return pd.read_csv(T / f"{stem}.csv")


def check(item, what, got, expected, source, tol=None):
    if tol is not None:
        ok = abs(float(got) - float(expected)) <= tol
    else:
        ok = got == expected
    ROWS.append((item, what, got, expected, source, "OK" if ok else "FAIL"))


def run():
    R_F = "reports/phase_f_results_2026-11-01.md"
    R_E = "reports/phase_e_results_2026-10-31.md"
    R_C = "reports/phase_e_calibration_hm_2026-10-30.md"
    R_A = "reports/arms_results_2026-10-10.md"
    R_G = "reports/phase_d_gemini_full_2026-10-12.md"
    R_H = "reports/phase_d_always_hnsw_2026-10-31.md"

    f = fig("fig4_1_selectivity_distributions")
    check("Fig 4.1", "EDGAR pairs plotted", len(f), 160, R_F + ' "160 pairs"')
    check("Fig 4.1", "pairs per breadth", sorted(f.groupby("breadth").size().unique().tolist()), [40], R_F + ' "40 / 40 at each breadth"')

    f = fig("fig4_2_hm_recall_by_arm")
    check("Fig 4.2", "cells x arms", len(f), 325, R_A + " (65 cells x 5 arms)")
    fh = f[f.arm == "forced-hnsw"]
    check("Fig 4.2", "forced-HNSW cells with mean recall >= 0.90", int((fh.mean_recall >= 0.9).sum()), 11, R_A + ' "mean recall >= 0.90 in only **11 of 65 cells**"')

    f = fig("fig4_3_exact_latency")
    e = f[f.corpus == "EDGAR"].sort_values("s")
    check("Fig 4.3", "EDGAR exact ms at g12 (half-up)", S.half_up(e.exact_ms.iloc[-1], 1), "336.5", R_F + ' A1 "| g12 | 0.4709 | 1.000 / 336.5"')
    check("Fig 4.3", "EDGAR exact ms at g00", round(e.exact_ms.iloc[0], 1), 0.2, R_F + ' A1 "| g00 | 0.00015 | 1.000 / 0.2"')

    f = fig("fig4_4_edgar_calibration_recall")
    check("Fig 4.4", "exact passes at all 13 cells", int(f[f.route == "exact"].passes.sum()), 13, R_F + ' "Exact passes at every grid point"')
    ig = f[f.route == "iter_guard"].sort_values("s")
    check("Fig 4.4", "iterative + guard fails at the largest cell", bool(ig.passes.iloc[-1]), False, R_F + ' "The iterative route fails at the largest grid point"')
    check("Fig 4.4", "iterative + guard recall at g12", round(ig.recall15.iloc[-1], 3), 0.887, R_F + ' A1 "| g12 | ... | 0.887 / 1.7"')

    f = fig("fig4_5_edgar_failures_by_T")
    check("Fig 4.5", "failing cells at the smallest T", int(f.failing_cells.iloc[0]), 7, R_F + ' "Failing cells by T fall from 7 at g00"')
    check("Fig 4.5", "candidates with 1 failing cell", [round(x, 4) for x in f[f.failing_cells == 1]["T"]], [0.3787, 0.4709], R_F + ' "to 1 at both 0.3787 and 0.4709"')

    f = fig("fig4_6_accuracy")
    a = f[f.panel == "a"].set_index(["arm", "estimate"])
    check("Fig 4.6a", "policy_v2 pass 1", a.loc[("policy_v2", "pass 1"), "acc"], 0.72, R_G + ' "policy_v2 36/50"', 1e-9)
    check("Fig 4.6a", "naive_llm pass 1", a.loc[("naive_llm", "pass 1"), "acc"], 0.64, R_G + ' "naive_llm 32/50"', 1e-9)
    check("Fig 4.6a", "always_hnsw pass 1 / pooled", (a.loc[("always_hnsw", "pass 1"), "acc"], a.loc[("always_hnsw", "pooled 5 passes"), "acc"]),
          (0.48, 0.52), R_H + ' "| always_hnsw | 24/50 (0.48) | 0.520 (130/250)"')
    check("Fig 4.6a", "policy_v2 pooled", a.loc[("policy_v2", "pooled 5 passes"), "acc"], 0.704, R_E + ' "pooled 0.520 vs 0.704"', 1e-9)
    b = f[f.panel == "b"].set_index("arm")
    check("Fig 4.6b", "router group accuracy and CI", (round(b.loc[S.ROUTER_GROUP_LABEL, "acc"], 4), b.loc[S.ROUTER_GROUP_LABEL, "correct_ci"]),
          (0.9062, "[0.838, 0.963]"), R_F + ' A4 "0.906 [0.838, 0.963]"')
    check("Fig 4.6b", "filtered HNSW accuracy and CI", (b.loc[S.name("default_hnsw"), "acc"], b.loc[S.name("default_hnsw"), "correct_ci"]),
          (0.8, "[0.681, 0.906]"), R_F + ' A4 "default_hnsw | 0.800 [0.681, 0.906]"')

    f = fig("fig4_7_error_classes").set_index(["panel", "arm"])
    check("Fig 4.7b", "router wrong_not_in_context (half-up)", S.half_up(f.loc[("b", S.ROUTER_GROUP_LABEL), "wrong_not_in_context"]), "0.019", R_F + ' P4 "0.019 vs 0.088"')
    check("Fig 4.7b", "filtered HNSW wrong_not_in_context (half-up)", S.half_up(f.loc[("b", S.name("default_hnsw")), "wrong_not_in_context"]), "0.088", R_F + ' P4 "0.019 vs 0.088"')
    check("Fig 4.7c", "filtered HNSW abstained / wnic, refusal rule", (f.loc[("c", S.name("default_hnsw")), "abstained"], f.loc[("c", S.name("default_hnsw")), "wrong_not_in_context"]),
          (0.0875, 0.075), R_F + ' B6 "0.013 -> 0.088" and "0.088 -> 0.075"')
    check("Fig 4.7a", "always_hnsw pooled correct share", f.loc[("a", "always_hnsw"), "correct"], 0.52, R_H + ' "0.520 (130/250)"', 1e-9)

    f = fig("fig4_8_edgar_recall_vs_latency").set_index("mode")
    check("Fig 4.8", "router pairs >= 0.90 / median ms", (int(f.loc["router", "recall15_ge_0.90"]), round(f.loc["router", "median_latency_ms"], 1)), (160, 38.7),
          R_F + ' A2 "| router | 160 | 1.000 | 0.900 | 38.7"')
    check("Fig 4.8", "default_hnsw pairs >= 0.90 / median ms / under-filled",
          (int(f.loc["default_hnsw", "recall15_ge_0.90"]), round(f.loc["default_hnsw", "median_latency_ms"], 1), int(f.loc["default_hnsw", "underfilled"])),
          (34, 9.1, 106), R_F + ' A2 "| default_hnsw | 34 | 0.538 | 0.781 | 9.1 | 106"')
    check("Fig 4.8", "modes plotted", len(f), 19, R_F + " A2 (19 modes)")

    f = fig("fig4_9_router_overhead").set_index("breadth")
    check("Fig 4.9", "section: pairs with capped count / router - always_exact", (int(f.loc["section", "pairs_with_count"]), round(f.loc["section", "router_minus_always_exact_ms"], 1)),
          (30, 20.0), R_F + ' B1 "| section | 6.4 | 3.8 | 8.4 (30 of 40) | 18.0 | 266.0 | 287.2 | 267.2 | +20.0 |"')
    check("Fig 4.9", "company+year+section router / always_exact median ms",
          (round(f.loc["cik+year+section", "router_median_latency_ms"], 1), round(f.loc["cik+year+section", "always_exact_median_latency_ms"], 1)), (22.1, 7.2),
          R_F + ' A2 "cik+year+section 22.1 vs 7.2"')

    f = fig("fig5_1_thresholds").set_index("label")
    hm = f.loc["H&M router: safe interval and T"]
    check("Fig 5.1", "H&M interval and T", (round(hm.lo, 4), round(hm.hi, 4), round(hm.x, 4)), (0.0478, 0.1061, 0.0712), R_C + ' "| pooled, default iterative | (0.0478, 0.1061] | **0.0712** |"')
    check("Fig 5.1", "planner switch", (round(f.loc["H&M planner switch exact -> HNSW", "lo"], 4), round(f.loc["H&M planner switch exact -> HNSW", "hi"], 4)), (0.2599, 0.2986),
          R_A + ' "between 0.2599 (gap3) and 0.2986 (gap4)"')
    check("Fig 5.1", "VBASE / Milvus / cliff", (f.loc["VBASE: exact if s < 0.18", "x"], f.loc["Milvus (via NaviX): exact if s <= 0.05", "x"],
                                                  f.loc["Post-filter cliff k / ef_search = 10/40", "x"]), (0.18, 0.05, 0.25), "src/phase_c_analysis/amendment6_partb.py:58-59; config/policy_v3_hm.json k, ef_search")
    check("Fig 5.1", "EDGAR T", round(f.loc["EDGAR router T (empty-interval rule)", "x"], 4), 0.3787, R_F + ' "T_default = T_tuned = 0.3787"')

    f = fig("figA_2_edgar_recall_heatmap").set_index("mode")
    check("Fig A.2", "default_hnsw all-breadth mean recall@15", round(f.loc["default_hnsw", "all"], 3), 0.538, R_F + ' A2 "0.538"')
    check("Fig A.2", "router all breadths", round(f.loc["router", "all"], 3), 1.0, R_F + ' A2 "1.000"')
    f = fig("figA_3_edgar_latency_by_breadth")
    check("Fig A.3", "pairs per box", sorted(f["count"].unique().tolist()), [40.0], "40 pairs per breadth")
    f = fig("figA_4_edgar_route_mix")
    hmT = f[(f["mode"] == "router_hmT") & (f.route == "iterative_default")].set_index("breadth")["share"]
    check("Fig A.4", "router_hmT iterative pairs year+section / section", (round(hmT["year+section"] * 40), round(hmT["section"] * 40)), (30, 38),
          R_F + ' A1 "router_hmT ... iterative 68 (year+section 30, section 38)"')
    f = fig("figA_5_router_hmT_per_pair")
    check("Fig A.5", "router_hmT routes", f.route.value_counts().to_dict(), {"exact": 92, "iterative_default": 68}, R_F + ' A1 "exact 92, iterative 68"')
    check("Fig A.5", "iterative pairs reaching 0.90", int(((f.route == "iterative_default") & (f.recall15 >= 0.9)).sum()), 39, R_F + ' B10 "39 reached recall@15 >= 0.90"')
    f = fig("figA_6_retrieval_vs_answer")
    r = f[f.lead == "router"].set_index("gold_hit")
    check("Fig A.6", "router gold hits / correct", (int(r.loc[True, "n"]), int(r.correct.sum())), (144, 145), R_F + ' A2 gold hit 0.900 (= 144/160); A5 "145 vs 128 correct"')
    f = fig("figA_7_default_hnsw_rows_vs_class")
    check("Fig A.7", "default_hnsw 0-row pairs", int(f[f.rows_returned == 0].pairs.sum()), 8, R_F + ' B8 "Only default_hnsw returned 0 rows, on 8 pairs"')
    check("Fig A.7", "0-row pairs correct", int(f[(f.rows_returned == 0) & (f["class"] == "correct")].pairs.sum()), 0, R_F + ' B8 "none was correct"')
    f = fig("figA_8_accuracy_three_rules").set_index("lead")
    check("Fig A.8", "scale-aware router / default_hnsw", (round(f.loc["router", "scale_aware"], 3), round(f.loc["default_hnsw", "scale_aware"], 3)), (0.894, 0.812),
          R_F + ' B7 "router accuracy goes from 0.906 to 0.894 and default_hnsw from 0.800 to 0.813" (0.8125 rounds to 0.813)')
    f = fig("figA_9_hm_pass_counts").set_index("key")
    for k, exp in {"router": (65, 50), "default_hnsw": (11, 7), "always_exact": (25, 15), "local_probe": (64, 46), "v1": (29, 31), "B4": (63, 49)}.items():
        check("Fig A.9", f"{k} in-sample / held-out", (int(f.loc[k, "in_sample"]), int(f.loc[k, "held_out"])), exp,
              R_E + " section 2 / reports/policy_evaluation_2026-10-10.md, holdout reports / reports/amendment6_partb_2026-10-23.md")

    # ---- tables
    t = tab("T4_2_calibrated_T")
    pooled = t[(t.scope == "pooled") & (t["iterative variant"] == "default iterative")].iloc[0]
    check("T4.2", "H&M pooled T / interval", (pooled["T"], pooled["lower"], pooled["upper (s_exact_max)"]), (0.0712, 0.0478, 0.1061), R_C)
    ed = t[(t.dataset == "EDGAR") & (t["iterative variant"] == "default iterative")].iloc[0]
    check("T4.2", "EDGAR T, empty interval", (ed["T"], bool(ed["empty interval"])), (0.3787, True), R_F + " A1")
    t = tab("T4_3_hm_pass_counts")
    check("T4.3", "rows (15 Phase E modes + v1 + policy_v2 + B1-B4b)", len(t), 22, "phase E summary.json (15) + v1 + partb_summary.json (6)")
    t = tab("T4_4_finqa_accuracy").set_index("arm")
    nl = t.loc["LLM router [naive_llm]"]
    check("T4.4", "naive_llm b, c, p, pass-1 diff", (int(nl["b (arm only correct)"]), int(nl["c (policy_v2 only correct)"]), nl["McNemar p (pass 1)"],
                                                       nl["diff vs policy_v2, pass 1 [Newcombe CI]"]),
          (0, 4, 0.125, "-0.080 [-0.158, -0.004]"), R_G + ' "b = 4, c = 0, exact McNemar p = 0.125; difference +0.080, 95% CI [+0.004, +0.158]" (sign: arm minus policy_v2)')
    ah = t.loc["Filtered HNSW (pgvector default) [always_hnsw]"]
    check("T4.4", "always_hnsw pooled diff", ah["diff vs policy_v2, pooled [bootstrap CI]"], "-0.184 [-0.288, -0.088]", R_E + ' "difference -0.184 [-0.288, -0.088]"')
    t = tab("T4_5_finqa_latency_cost").set_index("quantity")
    check("T4.5", "pass-1 latency difference (s)", round(t.loc[t.index[0], "estimate"] / 1000, 2), -2.83, 'reports/headline_audit_2026-10-23.md "2.827 s, CI 1.99-3.75 s"')
    check("T4.5", "share cheaper, 5 passes (%)", t.loc["share cheaper, 5 passes (%)", "estimate"], 19.4, 'reports/headline_audit_2026-10-23.md "**19.4%**"')
    check("T4.5", "router-call share of saving (%)", round(t.loc["  share of the saving from the skipped router call (%)", "estimate"]), 75,
          'reports/headline_audit_2026-10-23.md "USD 0.00027 of that (about three quarters)"', 2)
    t = tab("T4_6_edgar_per_mode").set_index("mode")
    check("T4.6", "router / default_hnsw pairs and accuracy", (int(t.loc["Router (policy_v3.1) [router]", "pairs recall@15 >= 0.90 /160"]),
                                                             int(t.loc["Filtered HNSW (pgvector default) [default_hnsw]", "pairs recall@15 >= 0.90 /160"]),
                                                             t.loc["Filtered HNSW (pgvector default) [default_hnsw]", "accuracy"]), (160, 34, 0.8), R_F + " A2, A4")
    t = tab("T4_7_label_validation")
    check("T4.7", "EDGAR agreement", t.iloc[-1]["automatic class"], "20/22 = 0.909", R_F + ' A6 "**20 / 22 = 0.909**"')
    fq = t[(t.dataset.str.startswith("FinQA")) & (t["automatic class"] == "wrong_ungrounded")].iloc[0]
    check("T4.7", "FinQA wrong_ungrounded rows labelled N", int(fq["N"]), 6, 'docs/preregistration/PHASE_D_AMENDMENT_10.md "of 20 sampled `wrong_ungrounded` rows only 6 were unsupported"')
    t = tab("TA_1_vecadvisor_decisions")
    check("TA.1", "VecAdvisor reasons", t.groupby("unavailable_reason").pairs.sum().to_dict(),
          {"invalid_parameter": 2, "requires_new_object": 47, "top candidate executed": 111}, R_F + ' B4 / DEVIATION_LOG "111 ... 47 ... 2"')
    t = tab("TA_3_edgar_cost").set_index("step")
    check("TA.3", "session total USD", round(t.loc["session total", "cost_usd"], 4), 1.4633, R_F + ' "Session spend: USD 1.4633"')
    t = tab("TA_4_scale_changes")
    check("TA.4", "scale-changed answers", int(t.answers.sum()), 74, R_F + ' B7 "74 answers change result"')

    # ---- printed size of every PNG (16 cm wide at 300 dpi: fonts print at their set size, >= 9 pt)
    for p in sorted(S.FIG_DIR.glob("*.png")):
        im = Image.open(p)
        w_cm = im.size[0] / 300 * 2.54
        check(p.name, "width at 300 dpi (cm)", round(w_cm, 1), 16.0, "A4 text width 16 cm; style.FONT = 9 pt", 0.05)


def main():
    run()
    fails = [r for r in ROWS if r[-1] != "OK"]
    out = ["# Figure and table checks, 2026-11-01", "", f"{len(ROWS)} checks, {len(fails)} failed. Generated by `src/figures/check_figures.py`.", "",
           "| item | check | plotted / tabled | expected | expected from | result |", "|---|---|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} | {e} | {g} |" for a, b, c, d, e, g in ROWS]
    out += ["", "## Visual check (done by opening every PNG)", "",
            "Each PNG was opened and checked for legibility, legend-colour match, clipping and axis units after the final layout "
            "(fixed 16 cm canvas, constrained layout, all text 9 pt). Issues found and fixed during the session: threshold labels "
            "overlapping data (moved above the axes), legends overlapping data or being clipped (moved below the plot as figure "
            "legends), overlapping tick labels (wrapped or rotated), panel titles running into neighbours (wrapped), text below 9 pt "
            "(raised to 9 pt), figures wider than 16 cm (fixed canvas). No remaining clipping or overlap was seen.", ""]
    (S.FIG_DIR / "CHECKS.md").write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"{len(ROWS)} checks, {len(fails)} failed")
    for r in fails:
        print("FAIL", r)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
