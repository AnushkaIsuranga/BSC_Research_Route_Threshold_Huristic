"""Task 4 (figures session, 2026-11-01): data tables from committed results only, as CSV and Markdown.

  python -m src.figures.make_tables

Each table carries its source files under it (Markdown) and in reports/tables_2026-11-01/SOURCES_TABLES.md. A value that no
committed result file holds is written as "not in a committed result file" with the reason; nothing is typed in by hand.
"""

from __future__ import annotations

import pandas as pd

from src.figures import load as L
from src.figures import style as S
from src.figures.make_figures import finqa_accuracy

NA = "not in a committed result file"
TABLES: list[tuple[str, str, list[str], str]] = []


def put(stem: str, title: str, df: pd.DataFrame, sources: list[str], note: str = ""):
    S.TAB_DIR.mkdir(parents=True, exist_ok=True)
    df = df.astype(object).where(df.notna(), None)
    df.to_csv(S.TAB_DIR / f"{stem}.csv", index=False, lineterminator="\n", encoding="utf-8")
    md = [f"# {title}", "", df.to_markdown(index=False, floatfmt="g", missingval="-"), "", "Source: " + ", ".join(f"`{s}`" for s in sources)]
    if note:
        md += ["", "Note: " + note]
    (S.TAB_DIR / f"{stem}.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    TABLES.append((stem, title, sources, note))


def r(x, n=4):
    return None if x is None else round(float(x), n)


# ------------------------------------------------------------------ T4.1

RUNBOOK = "docs/RUNBOOK_EDGAR.md"
AMENDMENT_11 = "docs/preregistration/PHASE_F_AMENDMENT_11.md"


def doc_quote(rel: str, needle: str) -> str:
    """The sentence fragment of a committed document that states a value (fails if the text is not there)."""
    text = L.path(rel).read_text(encoding="utf-8")
    assert needle in text, (rel, needle)
    return needle


def t4_1():
    fa, ec, st, ic = L.finqa_audit(), L.edgar_corpus(), L.edgar_stats(), L.edgar_index_checks()
    cen = L.finqa_census()
    q_texts = doc_quote(RUNBOOK, "158,308 chunks, 154,824 distinct texts")
    q_dim_a = doc_quote(AMENDMENT_11, "Qwen3-Embedding-8B 1024-d")
    q_dim_r = doc_quote(RUNBOOK, "`dimensions=1024`")
    idx = [i for i in ic["build"]["indexes"] if "hnsw" in i][0]
    rows = [
        {"corpus": "FinQA (finqa_evidence_qwen3)", "rows": fa["db_rows"], "unique texts": fa["db_unique"],
         "companies": f"{cen.ticker.nunique()} tickers among the {len(cen):,} test questions' filters (census)",
         "years": f"{cen.year.min()}-{cen.year.max()} among the test questions' filters (census)", "reltuples after VACUUM ANALYZE": NA,
         "gold resolution": f"{fa['unresolved_gold_pairs']} unresolved gold pairs", "zero vectors": fa["zero_vectors"],
         "dimension": fa["dimension"], "index / self-retrieval": f"self-retrieval {fa['self_retrieval']}"},
        {"corpus": "EDGAR (edgar_chunks)", "rows": ec["chunks_total"], "unique texts": "154,824 (from committed documentation)",
         "companies": ec["sampled_companies"], "years": "-".join([min(ec["chunks_by_year"]), max(ec["chunks_by_year"])]),
         "reltuples after VACUUM ANALYZE": int(float(st["after"]["reltuples"])), "gold resolution": "n/a (gold = chunk ids)",
         "zero vectors": ic["checks"]["zero_vectors"],
         "dimension": f"1024 (from committed documentation; {ic['checks']['dimension_mismatches']} dimension mismatches in the index checks)",
         "index / self-retrieval": idx.split(" USING ")[1] + f"; self-retrieval {ic['self_retrieval']['passed']}/{ic['self_retrieval']['of']}"},
    ]
    put("T4_1_corpus_audit", "Table 4.1 Database and corpus audit", pd.DataFrame(rows),
        ["outputs/embedding_build_2026-10-12/audit_finqa_evidence_qwen3.json", "outputs/edgar_chunks_2026-10-31/summary.json",
         "outputs/edgar_eval_preflight_2026-11-01/stats.json", "outputs/edgar_index_2026-10-31/checks.json",
         "outputs/finqa_selectivity_census/all_1147_selectivity.csv", RUNBOOK, AMENDMENT_11],
        f"From committed documentation, not from an output file: EDGAR unique texts, `{RUNBOOK}`: \"{q_texts}\"; EDGAR "
        f"dimension, `{AMENDMENT_11}` (tag phase-f-amendment-11-2026-11-01): \"{q_dim_a}\", and `{RUNBOOK}`: \"{q_dim_r}\". "
        "FinQA tickers and years are counted over the ticker-year filters of the 1,147 test questions in the committed census "
        "(every filter matches corpus rows); the distinct tickers and years of all 35,862 corpus rows are not in a committed file. "
        "FinQA reltuples was not recorded.")


# ------------------------------------------------------------------ T4.2

def t4_2():
    hm = L.hm_config()
    rows = []
    for var, key in (("default iterative", "calibration_default"), ("tuned iterative", "calibration_tuned")):
        cal = hm[key]
        for scope, d in [*sorted(cal["per_table"].items(), key=lambda kv: L.HM_TABLES.index(kv[0])), ("pooled", cal["pooled"])]:
            rows.append({"dataset": "H&M", "scope": scope, "iterative variant": var, "lower": r(d["lower"]), "upper (s_exact_max)": r(d["upper"]),
                         "s_iter_min": r(d["s_iter_min"]), "empty interval": d["empty"], "T": r(d["T"]), "rule": d["T_rule"]})
    ed = L.edgar_calibration()
    for var, key in (("default iterative", "T_default"), ("tuned iterative", "T_tuned")):
        d = ed[key]["per_table"]["edgar_chunks"]
        rows.append({"dataset": "EDGAR", "scope": "edgar_chunks (= pooled)", "iterative variant": var, "lower": r(d["lower"]),
                     "upper (s_exact_max)": r(d["upper"]), "s_iter_min": r(d["s_iter_min"]), "empty interval": d["empty"], "T": r(d["T"]),
                     "rule": d["T_rule"]})
    put("T4_2_calibrated_T", "Table 4.2 Calibrated threshold T and safe interval", pd.DataFrame(rows),
        ["config/policy_v3_hm.json", "outputs/edgar_calibration_2026-11-01/calibration.json"],
        "The deployed T is the pooled value (H&M 0.0712, EDGAR 0.3787). Empty cells: no s_iter_min / lower endpoint exists.")


# ------------------------------------------------------------------ T4.3

def t4_3():
    pe = L.hm_phase_e_pass_counts()
    rows = [{"mode / rule": S.name(m) + f" [{m}]", "session": "Phase E (Amendment 9)", "in-sample /65": pe.set_index("mode").loc[m, "in_sample"],
             "held-out 1 /25": pe.set_index("mode").loc[m, "ho1"], "held-out 2 /25": pe.set_index("mode").loc[m, "ho2"],
             "held-out /50": pe.set_index("mode").loc[m, "held_out"], "held-out 1 quiet re-run /25": None} for m in pe["mode"]]
    v1 = L.hm_v1_pass_counts()
    rows.append({"mode / rule": "v1 decision matrix [P1]", "session": "Phase A policy evaluation", "in-sample /65": v1["in_sample"],
                 "held-out 1 /25": v1["ho1"], "held-out 2 /25": v1["ho2"], "held-out /50": v1["held_out"], "held-out 1 quiet re-run /25": None})
    for _, b in L.hm_partb_pass_counts().iterrows():
        rows.append({"mode / rule": b["rule"], "session": "Phase A (Amendment 6 Part B)", "in-sample /65": b["in_sample"], "held-out 1 /25": b["ho1"],
                     "held-out 2 /25": b["ho2"], "held-out /50": b["held_out"], "held-out 1 quiet re-run /25": b["ho1_rerun"]})
    df = pd.DataFrame(rows)
    df["in-sample /65"] = df["in-sample /65"].astype("Int64")
    df["held-out 1 quiet re-run /25"] = df["held-out 1 quiet re-run /25"].astype("Int64")
    put("T4_3_hm_pass_counts", "Table 4.3 H&M pass counts per mode", df,
        ["outputs/phase_e_comparison_hm_2026-10-31/summary.json", "outputs/phase_a_amendment6_2026-10-23/partb_summary.json",
         "outputs/phase_a_arms/analysis/policy_evaluation_cells.csv", "outputs/phase_a_holdout/analysis/policy_cells.csv",
         "outputs/phase_a_holdout2/analysis/policy_cells.csv"],
        "Pass = mean recall@10 >= 0.90 and median latency <= 500 ms, all 20 vectors valid. Phase E and Phase A rows come from "
        "different measurement sessions. The LLM router was run on the held-out sets only.")


# ------------------------------------------------------------------ T4.4

def t4_4():
    s, ah = L.finqa_stats(), L.finqa_always_hnsw()
    c = L.finqa_class_counts()
    c["pass"] = c["pass"].astype(str)
    acc = finqa_accuracy().set_index(["arm", "estimate"])
    rows = []

    def wil(arm, p):
        if arm == "always_hnsw":
            x = acc.loc[(arm, "pass 1" if p == "1" else "pooled 5 passes")]
            return x["acc"], x["lo"], x["hi"], "recomputed (Amendment 5 Wilson)"
        x = c[(c.arm == arm) & (c["pass"] == p) & (c["class"] == "correct")].iloc[0]
        return x.rate, x.ci95_lo, x.ci95_hi, "saved"

    # paired results, stated as arm minus policy_v2 (sign flipped where the file stores policy_v2 minus arm)
    pairs = {"naive_llm": (s["pairs"]["policy_v2_vs_naive_llm"], s["pooled"]["policy_v2_vs_naive_llm"], -1),
             "naive_informed": (s["pairs"]["policy_v2_vs_naive_informed"], s["pooled"]["policy_v2_vs_naive_informed"], -1),
             "decision_matrix": (s["pairs"]["decision_matrix_vs_policy_v2"], s["pooled"]["decision_matrix_vs_policy_v2"], 1)}
    for arm in ("policy_v2", "naive_llm", "naive_informed", "decision_matrix", "always_hnsw"):
        a1, l1, h1, src1 = wil(arm, "1")
        ap, lp, hp, srcp = wil(arm, "all")
        rec = {"arm": S.name(arm) + f" [{arm}]", "pass-1 accuracy": r(a1, 3), "pass-1 95% CI": f"[{l1:.3f}, {h1:.3f}]",
               "pooled 5-pass accuracy": r(ap, 3), "pooled 95% CI": f"[{lp:.3f}, {hp:.3f}]", "CI source": src1}
        if arm in pairs:
            p1, pp, sg = pairs[arm]
            b, cc = (p1["b_X_only_correct"], p1["c_Y_only_correct"]) if sg == 1 else (p1["c_Y_only_correct"], p1["b_X_only_correct"])
            lo, hi = sorted(sg * x for x in p1["accuracy_diff_ci95"])
            plo, phi = sorted(sg * x for x in pp["pooled_diff_ci95"])
            rec.update({"b (arm only correct)": b, "c (policy_v2 only correct)": cc, "McNemar p (pass 1)": r(p1["mcnemar_exact_p_two_sided"], 5),
                        "diff vs policy_v2, pass 1 [Newcombe CI]": f"{sg * p1['accuracy_diff_X_minus_Y']:+.3f} [{lo:+.3f}, {hi:+.3f}]",
                        "diff vs policy_v2, pooled [bootstrap CI]": f"{sg * pp['pooled_diff_X_minus_Y']:+.3f} [{plo:+.3f}, {phi:+.3f}]"})
        elif arm == "always_hnsw":
            p1 = ah["comparisons"]["always_hnsw_vs_stored_policy_v2_pass1"]
            pp = ah["comparisons"]["always_hnsw_vs_stored_policy_v2_pooled"]
            rec.update({"b (arm only correct)": p1["b_X_only"], "c (policy_v2 only correct)": p1["c_Y_only"], "McNemar p (pass 1)": r(p1["mcnemar_exact_p"], 5),
                        "diff vs policy_v2, pass 1 [Newcombe CI]": f"{p1['diff']:+.3f} [{p1['ci95'][0]:+.3f}, {p1['ci95'][1]:+.3f}]",
                        "diff vs policy_v2, pooled [bootstrap CI]": f"{pp['pooled_diff_X_minus_Y']:+.3f} [{pp['pooled_diff_ci95'][0]:+.3f}, {pp['pooled_diff_ci95'][1]:+.3f}]"})
        rows.append(rec)
    put("T4_4_finqa_accuracy", "Table 4.4 FinQA accuracy per arm (Gemini 3.8 Flash, frozen 50 questions, 5 passes)", pd.DataFrame(rows),
        ["outputs/phase_d_gemini_full_2026-10-12/stats_primary.json", "outputs/hallucination_classification_2026-10-23/summary_counts_gemini_full.csv",
         "outputs/phase_d_always_hnsw_2026-10-31/analysis/summary.json", "outputs/phase_d_always_hnsw_2026-10-31/analysis/classes.csv"],
        "Differences are arm minus policy_v2; where the file stores policy_v2 minus arm, the sign of the estimate and interval was "
        f"flipped (no new estimate). Non-inferiority margin {s['non_inferiority']['margin']:.2f} (policy_v2 vs naive_llm). "
        "Filtered HNSW (always_hnsw) per-arm intervals are recomputed (see Fig 4.6 note). " + "policy_v2 routes all 50 FinQA questions "
        "exactly as the final router (policy_v3/v3.1), see `reports/finqa_router_v3_route_check_2026-10-31.md`.")


# ------------------------------------------------------------------ T4.5

def t4_5():
    s, a = L.finqa_stats(), L.headline_audit()["recomputed"]
    p = s["pairs"]["policy_v2_vs_naive_llm"]
    lat_all = a["lat_diff_all"]
    cost_p1, cost_all = a["cost_diff_boot_p1"], a["cost_diff_boot_all"]
    naive_all, v2_all = a["cost"]["all|naive_llm"], a["cost"]["all|policy_v2"]
    saving = naive_all["mean"] - v2_all["mean"]
    rows = [
        {"quantity": "latency, policy_v2 - naive_llm, pass 1 (mean of paired per-question differences, ms)", "estimate": r(p["latency_total_ms_mean_diff_X_minus_Y"], 1),
         "95% CI": f"[{p['latency_diff_ci95'][0]:.1f}, {p['latency_diff_ci95'][1]:.1f}]", "source": "stats_primary.json pairs"},
        {"quantity": "latency, policy_v2 - naive_llm, pooled 5 passes (ms)", "estimate": r(lat_all[0], 1), "95% CI": f"[{lat_all[1]:.1f}, {lat_all[2]:.1f}]",
         "source": "audit.json recomputed.lat_diff_all"},
        {"quantity": "latency, difference of pass-1 medians (ms)", "estimate": r(a["lat_diff"]["median_diff"], 1), "95% CI": "-", "source": "audit.json recomputed.lat_diff"},
        {"quantity": "cost per arm-run, policy_v2 - naive_llm, pass 1 (USD)", "estimate": r(cost_p1[0], 6), "95% CI": f"[{cost_p1[1]:.6f}, {cost_p1[2]:.6f}]",
         "source": "audit.json recomputed.cost_diff_boot_p1"},
        {"quantity": "cost per arm-run, policy_v2 - naive_llm, pooled 5 passes (USD)", "estimate": r(cost_all[0], 6), "95% CI": f"[{cost_all[1]:.6f}, {cost_all[2]:.6f}]",
         "source": "audit.json recomputed.cost_diff_boot_all"},
        {"quantity": "share cheaper, pass 1 (%)", "estimate": r(a["pct"]["pass1_exact"], 1), "95% CI": "-", "source": "audit.json recomputed.pct"},
        {"quantity": "share cheaper, 5 passes (%)", "estimate": r(a["pct"]["all_passes"], 1), "95% CI": "-", "source": "audit.json recomputed.pct"},
        {"quantity": "share cheaper, answer call only, 5 passes (%)", "estimate": r(a["pct"]["answer_only_all"], 1), "95% CI": "-", "source": "audit.json recomputed.pct"},
        {"quantity": "mean saving per arm-run, 5 passes (USD)", "estimate": r(saving, 6), "95% CI": "-", "source": "audit.json recomputed.cost (all|naive_llm - all|policy_v2)"},
        {"quantity": "  of which the skipped router call (USD)", "estimate": r(naive_all["router_mean"], 6), "95% CI": "-", "source": "audit.json recomputed.cost all|naive_llm router_mean"},
        {"quantity": "  share of the saving from the skipped router call (%)", "estimate": r(100 * naive_all["router_mean"] / saving, 1), "95% CI": "-",
         "source": "ratio of the two rows above"},
    ]
    put("T4_5_finqa_latency_cost", "Table 4.5 FinQA latency and cost, Router (policy_v2) vs LLM router (naive_llm)", pd.DataFrame(rows),
        ["outputs/phase_d_gemini_full_2026-10-12/stats_primary.json", "outputs/headline_audit_2026-10-23/audit.json"],
        "Negative differences mean policy_v2 is faster / cheaper. Bootstrap: paired over questions, 10,000 resamples (headline audit). "
        "The last row is a ratio of two committed values; reports/headline_audit_2026-10-23.md states it as 'about three quarters'.")


# ------------------------------------------------------------------ T4.6

def t4_6():
    sm = L.edgar_summary().query("breadth == 'all'").set_index("mode")
    an = L.edgar_answers_by_mode().query("breadth == 'all'").set_index("mode")
    rows = [{"mode": S.name(m) + f" [{m}]", "pairs recall@15 >= 0.90 /160": int(sm.loc[m, "recall15_ge_0.90"]), "mean recall@15": sm.loc[m, "mean_recall15"],
             "gold hit": sm.loc[m, "gold_hit_rate"], "median latency ms": sm.loc[m, "median_latency_ms"], "accuracy": an.loc[m, "correct"],
             "accuracy 95% CI": an.loc[m, "correct_ci"], "wrong_not_in_context": an.loc[m, "wrong_not_in_context"]} for m in S.EDGAR_MODES]
    put("T4_6_edgar_per_mode", "Table 4.6 EDGAR per mode (160 pairs, 1 answer pass)", pd.DataFrame(rows),
        ["outputs/edgar_retrieval_comparison_2026-11-01/summary_by_mode_breadth.csv", "outputs/edgar_analysis_2026-11-01/answers_by_mode_breadth.csv"],
        "Accuracy CI: cluster bootstrap over the 40 questions (10,000 resamples, seed 20261104).")


# ------------------------------------------------------------------ T4.7

def t4_7():
    fq = L.finqa_label_confusion()["tables"]["per_row"]["proxy_x_scn"]
    rows = [{"dataset": "FinQA (Amendment 5, 40 rows)", "automatic class": cls, **{lab: fq[cls]["cells"][lab]["n"] for lab in ("S", "C", "N")}, "X": "-"}
            for cls in ("wrong_grounded", "wrong_ungrounded")]
    ag = L.edgar_agreement()
    rows += [{"dataset": "EDGAR (Amendment 11, 40 rows)", "automatic class": cls, **{lab: ag["all"]["confusion"][cls][lab] for lab in ("S", "C", "N", "X")}}
             for cls in ("wrong_in_context", "wrong_not_in_context")]
    g = ag["all"]
    rows.append({"dataset": "EDGAR agreement (S/C/N rows)", "automatic class": f"{g['agree']}/{g['n_scn']} = {g['agreement']:.3f}",
                 "S": "-", "C": "-", "N": "-", "X": f"{g['n_x']} X rows excluded"})
    put("T4_7_label_validation", "Table 4.7 Label validation: automatic class vs checked S/C/N(/X) labels", pd.DataFrame(rows),
        ["outputs/hallucination_classification_2026-10-23/label_analysis/label_confusion.json", "outputs/edgar_analysis_exploratory_2026-11-01/agreement.json"],
        "S = number in the retrieved text; C = calculable from it; N = not supported; X (EDGAR only, added by the author, "
        "DEVIATION_LOG.md 2026-11-01) = refusal. FinQA proxy: wrong_ungrounded; EDGAR proxy: wrong_not_in_context. Labels drafted by the "
        "AI assistant and checked by the author.")


# ------------------------------------------------------------------ Appendix

def appendix():
    v = L.edgar_vecadvisor()
    v["unavailable_reason"] = v["unavailable_reason"].fillna("top candidate executed")
    put("TA_1_vecadvisor_decisions", "Table A.1 VecAdvisor decisions (160 pairs)",
        v.groupby(["unavailable_reason", "strategy"]).size().rename("pairs").reset_index(),
        ["outputs/edgar_retrieval_comparison_2026-11-01/vecadvisor_decisions.json"])
    d = L.edgar_llm_decisions()
    t = d.groupby("route", dropna=False).agg(pairs=("pair_id", "size"), median_latency_ms=("latency_ms", "median"), cost_usd=("cost_usd", "sum")).reset_index()
    t.loc[len(t)] = {"route": "parse errors / call errors", "pairs": int(d["parse_error"].notna().sum() + d["call_error"].notna().sum()),
                     "median_latency_ms": None, "cost_usd": None}
    put("TA_2_llm_router_decisions", "Table A.2 LLM-router decisions on EDGAR (Gemini 3.8 Flash, 160 pairs)", t,
        ["outputs/edgar_retrieval_comparison_2026-11-01/llm_decisions.json"])
    c = L.edgar_cost_log()
    t = c.groupby("step", sort=False).agg(calls=("cost_usd", "size"), cost_usd=("cost_usd", "sum")).reset_index()
    t.loc[len(t)] = {"step": "session total", "calls": int(t.calls.sum()), "cost_usd": c["running_total_usd"].iloc[-1]}
    pdc = L.edgar_pass_decision()
    for k, vv in pdc["projection_usd"].items():
        t.loc[len(t)] = {"step": f"projection, {k} pass(es) (pilot mean x {pdc['unique_prompts_per_pass']} prompts)", "calls": None, "cost_usd": vv}
    put("TA_3_edgar_cost", "Table A.3 EDGAR session cost per step and pass projection", t,
        ["outputs/edgar_cost_log_2026-11-01/cost_log.jsonl", "outputs/edgar_answers_2026-11-01/pass_decision.json"],
        f"Rule: {pdc['rule']}; chosen passes = {pdc['passes']}.")
    sc = L.edgar_scale_changes()
    t = sc.groupby(["answer_span", "gold_number", "class", "class_scale"]).agg(answers=("pair_id", "size"),
                                                                              pairs=("pair_id", lambda x: "; ".join(sorted(set(x))))).reset_index()
    put("TA_4_scale_changes", "Table A.4 EXPLORATORY: answers whose result changes under scale-aware matching (74 answers)", t,
        ["outputs/edgar_analysis_exploratory_2026-11-01/scale_changes.csv"])
    z = L.edgar_zero_passages()
    put("TA_5_zero_passages", "Table A.5 EXPLORATORY: pairs whose prompt held 0 passages", z[z.zero_passage_pairs > 0],
        ["outputs/edgar_analysis_exploratory_2026-11-01/zero_passages.csv"], "All other mode x breadth rows have 0 such pairs.")
    ls = L.edgar_label_sources()
    t = pd.DataFrame([x for x in ls["rows"] if x["wrong_source"] or x["wrong_year"] or "another company" in x["author_note"]])
    put("TA_6_wrong_source_year", "Table A.6 EXPLORATORY: wrong-source and wrong-year rows in the EDGAR label sample", t,
        ["outputs/edgar_analysis_exploratory_2026-11-01/label_error_sources.json"],
        f"S rows: {ls['S_rows']}; wrong source {ls['S_wrong_source']}; wrong year {ls['S_wrong_year']}.")


def main():
    for fn in (t4_1, t4_2, t4_3, t4_4, t4_5, t4_6, t4_7, appendix):
        fn()
    out = ["# Table sources, 2026-11-01", "", "| table | file | sources | note |", "|---|---|---|---|"]
    out += [f"| {t} | `{s}.csv` / `.md` | {', '.join(f'`{x}`' for x in src)} | {n} |" for s, t, src, n in TABLES]
    (S.TAB_DIR / "SOURCES_TABLES.md").write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(len(TABLES), "tables")


if __name__ == "__main__":
    main()
