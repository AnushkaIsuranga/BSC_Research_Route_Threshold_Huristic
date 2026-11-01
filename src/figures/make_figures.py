"""Tasks 2-3 (figures session, 2026-11-01): main-text and appendix figures from committed results only.

  python -m src.figures.make_figures

Every plotted value comes from src.figures.load. Each figure's plotted values are also written to
reports/figures_2026-11-01/data/<stem>.csv (checked by src.figures.check_figures); captions go to CAPTIONS.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory

from src.figures import load as L
from src.figures import style as S
from src.figures.style import plt
from src.phase_d_validation.paired_stats import wilson

DATA_DIR = S.FIG_DIR / "data"
CAPTIONS: list[dict] = []
NOT_PRODUCED: list[tuple[str, str]] = [
    ("Fig 4.5 panel (b), H&M failing cells vs T", "the H&M calibration (`config/policy_v3_hm.json`) found a non-empty interval, so the "
     "empty-interval rule was never run and no `failures_by_T` was saved."),
]


def dump(stem: str, df: pd.DataFrame):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_DIR / f"{stem}.csv", index=False, lineterminator="\n", encoding="utf-8")


def caption(num: str, stem: str, text: str, sources: list[str], notes: str = ""):
    CAPTIONS.append({"num": num, "stem": stem, "text": text, "sources": sources, "notes": notes})


def tline(ax, x, label, color, ls="--", level=0, ha="center", **_):
    """Vertical threshold line, labelled above the plot area (level 1, 2 ... stack labels of nearby lines)."""
    ax.axvline(x, color=color, ls=ls, lw=1)
    ax.text(x, 1.01 + 0.075 * level, label, transform=ax.get_xaxis_transform(), color=color, ha=ha, va="bottom",
            fontsize=S.FONT, clip_on=False)


T_HM = L.hm_config()["T_default"]
T_ED = L.edgar_config()["T_default"]
FILTERED_HNSW_NOTE = ("\"Filtered HNSW (pgvector default)\" is pgvector's HNSW index scan with the filter applied after the scan "
                      "(`hnsw.iterative_scan = off`, ef_search 40); it is the FinQA arm `always_hnsw` and the EDGAR mode `default_hnsw`.")
POLICY_V2_NOTE = ("policy_v2 routes all 50 FinQA questions exactly as the final router (policy_v3/v3.1), see "
                  "`reports/finqa_router_v3_route_check_2026-10-31.md`.")


# ------------------------------------------------------------------ EDGAR mode groups (identical per-pair answer classes)

def answer_groups() -> list[list[str]]:
    a = L.edgar_answers_scored().query("`pass` == 1").sort_values("pair_id")
    sig = {m: tuple(g.sort_values("pair_id")["class"]) for m, g in a.groupby("mode")}
    groups: dict[tuple, list[str]] = {}
    for m in S.EDGAR_MODES:
        groups.setdefault(sig[m], []).append(m)
    return list(groups.values())


def group_label(members: list[str]) -> str:
    if "router" in members:
        assert sorted(members) == sorted(["router", "router_tuned", "router_no_guard", "router_always_count", "router_plus_probe",
                                          "always_exact", "llm_router"]), members
        return S.ROUTER_GROUP_LABEL
    return S.name(members[0]) + (f" (+{len(members) - 1} identical)" if len(members) > 1 else "")


def groups_note(groups) -> str:
    return "Mode groups with identical answer classes on all 160 pairs: " + "; ".join(
        f"{group_label(g)} = {', '.join(S.name(m) for m in g)}" for g in groups if len(g) > 1) + "."


# ------------------------------------------------------------------ Fig 4.1

def fig_4_1():
    stem = "fig4_1_selectivity_distributions"
    c = L.finqa_census()
    p = L.edgar_pairs()
    f, (a1, a2) = S.fig(15, nrows=2, sharex=True, gridspec_kw={"height_ratios": [1, 1.25]})
    bins = np.logspace(np.log10(min(c.selectivity.min(), p.selectivity.min())), 0, 46)
    a1.hist(c.selectivity, bins=bins, color="#555555", edgecolor="white", lw=0.4)
    a1.set_ylabel("FinQA questions")
    a1.set_title(f"(a) FinQA test set, {len(c):,} questions (corpus 35,862 rows)", fontsize=S.FONT, loc="left")
    rng = np.random.default_rng(0)                       # vertical jitter only (display)
    order = list(L.BREADTHS)
    for i, b in enumerate(order):
        s = p.loc[p.breadth == b, "selectivity"].to_numpy()
        a2.scatter(s, i + rng.uniform(-0.2, 0.2, len(s)), s=22, color="#333333", alpha=0.7, lw=0)
    a2.set_yticks(range(len(order)), [S.BREADTH_LABEL[b] for b in order])
    a2.set_ylim(-0.6, len(order) - 0.4)
    a2.set_title("(b) EDGAR, 160 evaluation pairs (corpus 158,308 rows)", fontsize=S.FONT, loc="left")
    a2.set_xscale("log")
    a2.set_xlabel("Exact filter selectivity = matching rows / corpus rows (log scale)")
    for ax in (a1, a2):
        ax.axvline(T_HM, color=S.T_HM_COLOUR, ls="--", lw=1)
    a2.axvline(T_ED, color=S.T_EDGAR_COLOUR, ls="--", lw=1)
    a1.text(T_HM, 0.97, f" H&M T = {T_HM:.4f}", transform=a1.get_xaxis_transform(), color=S.T_HM_COLOUR, ha="left", va="top")
    a2.text(T_ED, 0.5, f"EDGAR T = {T_ED:.4f} ", transform=a2.get_xaxis_transform(), color=S.T_EDGAR_COLOUR, ha="right", va="center",
            rotation=90)
    S.save(f, stem)
    dump(stem, pd.concat([c[["id", "selectivity"]].rename(columns={"id": "item"}).assign(panel="a FinQA census", breadth=""),
                          p[["pair_id", "selectivity", "breadth"]].rename(columns={"pair_id": "item"}).assign(panel="b EDGAR pairs")]))
    caption("4.1", stem, f"Filter selectivity distributions on one log axis. (a) FinQA: histogram of the exact ticker-year selectivity of "
            f"all {len(c):,} test questions (census, maximum {c.selectivity.max():.4f}). (b) EDGAR: the 160 evaluation pairs (40 questions x "
            "4 filter breadths), one point per pair (vertical jitter for display only). Dashed lines: calibrated thresholds "
            f"T = {T_HM:.4f} (H&M, both panels) and T = {T_ED:.4f} (EDGAR, panel b). Every FinQA question lies below T/2 of the H&M "
            "threshold, so a threshold router sends all of them to exact search.",
            ["outputs/finqa_selectivity_census/all_1147_selectivity.csv", "outputs/edgar_eval_set_2026-11-01/pairs.csv",
             "config/policy_v3_hm.json", "config/policy_v3_1_edgar.json"])


# ------------------------------------------------------------------ Fig 4.2

def fig_4_2():
    stem = "fig4_2_hm_recall_by_arm"
    c = L.hm_arms_cells()
    f, axes = S.fig(20, ncols=2, nrows=3, sharex=True, sharey=True)
    for ax, t in zip(axes.flat, L.HM_TABLES):
        d = c[c.table == t]
        for arm, (lab, col, mk) in S.ARMS.items():
            x = d[d.arm == arm].sort_values("selectivity")
            ax.plot(x.selectivity, x.mean_recall, color=col, marker=mk, ms=5, lw=1.3, label=lab)
        ax.axhline(0.9, color="#555555", ls=":", lw=1)
        ax.set_xscale("log")
        ax.set_title(S.HM_TABLE_LABEL[t].replace(" (", chr(10) + "("), fontsize=S.FONT, loc="left")
    f.supylabel("Mean recall@10 (20 vectors)", fontsize=S.FONT)
    for ax in (axes[2, 0], axes[1, 1]):
        ax.set_xlabel("Selectivity (log scale)")
    axes[1, 1].tick_params(labelbottom=True)
    leg = axes[2, 1]
    leg.axis("off")
    h = [Line2D([], [], color=c_, marker=m, lw=1, ms=4, label=lab) for lab, c_, m in S.ARMS.values()]
    h.append(Line2D([], [], color="#555555", ls=":", lw=1, label="recall = 0.90 (pass line)"))
    leg.legend(handles=h, loc="center left")
    S.save(f, stem)
    dump(stem, c[["table", "filter_id", "selectivity", "arm", "mean_recall", "median_latency_ms"]])
    caption("4.2", stem, "H&M three-arm run: mean recall@10 over 20 query vectors per (table, filter) cell against filter selectivity "
            "(log scale), one line per execution arm, 13 filters per table. Panels run from the least correlated table (hm_clothes_0) "
            "to the most correlated (hm_clothes_100: the filter attribute is most correlated with the embedding). Dotted line: "
            "recall 0.90, the pass line. Forced HNSW is the filtered HNSW scan (pgvector default). " + FILTERED_HNSW_NOTE,
            ["outputs/phase_a_arms/analysis/cell_summary.csv"])


# ------------------------------------------------------------------ Fig 4.3

def fig_4_3():
    stem = "fig4_3_exact_latency"
    h = L.hm_cal_cells()
    hm = h.groupby("s", as_index=False)[["exact_ms", "iter_guard_ms"]].median().assign(corpus="H&M (median of 5 tables)")
    e = L.edgar_cal_cells()[["s", "exact_ms", "iter_guard_ms"]].assign(corpus="EDGAR")
    L_ms = L.hm_config()["L_ms"]
    assert L_ms == L.edgar_config()["L_ms"]
    f, ax = S.fig(12)
    for d, col in ((hm, S.T_HM_COLOUR), (e, S.T_EDGAR_COLOUR)):
        ax.plot(d.s, d.exact_ms, color=col, marker="o", ms=5, lw=1.5)
        ax.plot(d.s, d.iter_guard_ms, color=col, marker="^", ms=5, lw=1.5, ls="--")
    ax.axhline(L_ms, color="#555555", ls=":", lw=1)
    ax.text(0.99, L_ms * 1.1, f"latency budget L = {L_ms} ms", transform=ax.get_yaxis_transform(), ha="right", fontsize=S.FONT, color="#555555")
    tline(ax, T_HM, f"H&M T = {T_HM:.4f} ", S.T_HM_COLOUR, ha="right")
    tline(ax, T_ED, f"EDGAR T = {T_ED:.4f} ", S.T_EDGAR_COLOUR, ha="right", level=1)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Grid selectivity (log scale)")
    ax.set_ylabel("Median latency, ms (log scale)")
    hdl = [Line2D([], [], color=S.T_HM_COLOUR, lw=1.2, label="H&M"), Line2D([], [], color=S.T_EDGAR_COLOUR, lw=1.2, label="EDGAR"),
           Line2D([], [], color="#333333", marker="o", lw=1.2, label="exact scan"),
           Line2D([], [], color="#333333", marker="^", ls="--", lw=1.2, label="iterative + guard")]
    f.legend(handles=hdl, loc="outside lower center", ncol=4)
    S.save(f, stem)
    dump(stem, pd.concat([hm, e]))
    caption("4.3", stem, "Calibration sessions: median latency (EXPLAIN ANALYZE execution time; median over 20 query vectors of the "
            "per-vector median of 5 timed runs) of the exact scan (solid) and the default iterative scan with guard (dashed) at each "
            "grid selectivity. H&M: the median over the five correlation tables of each cell's value (k = 10); EDGAR: one table "
            f"(k = 15). Both axes log scale. Dotted line: the {L_ms} ms latency budget of the pass rule. Vertical lines: calibrated "
            f"T = {T_HM:.4f} (H&M) and T = {T_ED:.4f} (EDGAR).",
            ["outputs/phase_e_calibration_hm_2026-10-30/cell_summary.csv", "outputs/edgar_calibration_2026-11-01/cell_summary.csv",
             "config/policy_v3_hm.json", "config/policy_v3_1_edgar.json"])


# ------------------------------------------------------------------ Fig 4.4

def fig_4_4():
    stem = "fig4_4_edgar_calibration_recall"
    c = L.edgar_cal_cells()
    f, ax = S.fig(12)
    rows = []
    for key, (lab, col, mk) in S.ROUTES.items():
        ax.plot(c.s, c[f"{key}_recall15"], color=col, lw=1, label=lab)
        ok = c[f"{key}_pass"].astype(str) == "True"
        ax.scatter(c.s[ok], c[f"{key}_recall15"][ok], color=col, marker=mk, s=40, zorder=3)
        ax.scatter(c.s[~ok], c[f"{key}_recall15"][~ok], facecolors="white", edgecolors=col, marker=mk, s=40, zorder=3)
        rows += [{"route": key, "s": s, "recall15": r, "passes": p} for s, r, p in zip(c.s, c[f"{key}_recall15"], ok)]
    ax.axhline(0.9, color="#555555", ls=":", lw=1)
    tline(ax, T_HM, f"T (H&M) = {T_HM:.4f} ", S.T_HM_COLOUR, ha="right")
    tline(ax, T_ED, f"T (EDGAR) = {T_ED:.4f} ", S.T_EDGAR_COLOUR, ha="right", level=1)
    ax.set_xscale("log")
    ax.set_xlabel("Grid selectivity (achieved; log scale)")
    ax.set_ylabel("Mean recall@15 (20 vectors)")
    h = [Line2D([], [], color=col, marker=mk, lw=1, label=lab) for lab, col, mk in S.ROUTES.values()]
    h += [Line2D([], [], color="#333333", marker="o", ls="", label="passes the rule"),
          Line2D([], [], color="#333333", marker="o", ls="", markerfacecolor="white", label="fails the rule")]
    f.legend(handles=h, loc="outside lower center", ncol=2)
    S.save(f, stem)
    dump(stem, pd.DataFrame(rows))
    caption("4.4", stem, "EDGAR calibration: mean recall@15 over the 20 calibration questions per grid cell (13 cik-set filters) and "
            "route. Filled markers: the route passes the Amendment 9 rule at that cell (mean recall@15 >= 0.90 and median latency "
            "<= 500 ms, all 20 vectors valid); open markers: it fails (recall or latency). Exact passes everywhere; the iterative "
            "routes fail at the largest cell (0.4709), so no safe interval exists and T comes from the empty-interval rule (Fig 4.5). "
            f"Vertical lines: T = {T_ED:.4f} (EDGAR) and T = {T_HM:.4f} (H&M). Dotted line: recall 0.90.",
            ["outputs/edgar_calibration_2026-11-01/cell_summary.csv", "config/policy_v3_1_edgar.json"])


# ------------------------------------------------------------------ Fig 4.5

def fig_4_5():
    stem = "fig4_5_edgar_failures_by_T"
    d = L.edgar_failures_by_T()
    f, ax = S.fig(9.5)
    ax.step(d["T"], d["failing_cells"], where="post", color=S.T_EDGAR_COLOUR, lw=1.3)
    ax.plot(d["T"], d["failing_cells"], "o", color=S.T_EDGAR_COLOUR, ms=4)
    tie = d[d.failing_cells == d.failing_cells.min()]
    ax.scatter(tie["T"], tie["failing_cells"], s=90, facecolors="none", edgecolors="#D55E00", lw=1.3, zorder=3)
    ax.annotate(f"tie at {tie['T'].iloc[0]:.4f} and {tie['T'].iloc[1]:.4f}\n(1 failing cell each)\nchosen: the smaller, T = {T_ED:.4f}",
                xy=(T_ED, 1), xytext=(0.012, 2.4), fontsize=S.FONT, arrowprops={"arrowstyle": "->", "lw": 0.8})
    ax.set_xscale("log")
    ax.set_xlabel("Candidate T = grid point (log scale)")
    ax.set_ylabel("Failing cells under\n\"exact if s < T, else iterative + guard\"")
    ax.set_yticks(range(0, int(d.failing_cells.max()) + 1))
    S.save(f, stem)
    dump(stem, d)
    caption("4.5", stem, "EDGAR empty-interval rule: number of the 13 grid cells that fail the pass rule when routing \"exact if s < T "
            "else iterative + guard\", for each grid point as candidate T (default iterative). Circled: the tie at 0.3787 and 0.4709 "
            f"(1 failing cell each), resolved to the smaller value as the rule states, T = {T_ED:.4f}.",
            ["outputs/edgar_calibration_2026-11-01/calibration.json"],
            "Panel skipped: (b) H&M, no failures_by_T saved because the H&M interval was not empty (see 'Not produced').")


# ------------------------------------------------------------------ Fig 4.6

def finqa_accuracy() -> pd.DataFrame:
    c = L.finqa_class_counts()
    c["pass"] = c["pass"].astype(str)
    rows = []
    for arm in ("policy_v2", "naive_llm"):
        for p, lab in (("1", "pass 1"), ("all", "pooled 5 passes")):
            r = c[(c.arm == arm) & (c["pass"] == p) & (c["class"] == "correct")].iloc[0]
            rows.append({"arm": arm, "estimate": lab, "k": int(r.n), "n": int(r["of"]), "acc": r.rate, "lo": r.ci95_lo, "hi": r.ci95_hi,
                         "ci_source": "saved (Wilson, summary_counts_gemini_full.csv)"})
    cl = L.finqa_always_hnsw_classes().query("arm == 'always_hnsw'")
    a = L.finqa_always_hnsw()["arms"]["always_hnsw"]
    for sub, lab, reported in ((cl[cl["pass"] == 1], "pass 1", a["pass1_accuracy"]), (cl, "pooled 5 passes", a["accuracy"])):
        k, n = int(sub.correct.sum()), len(sub)
        assert k / n == reported, (lab, k, n, reported)        # reproduces the reported 0.48 / 0.52 (24/50, 130/250)
        lo, hi = wilson(k, n)
        rows.append({"arm": "always_hnsw", "estimate": lab, "k": k, "n": n, "acc": k / n, "lo": lo, "hi": hi,
                     "ci_source": "recomputed (Amendment 5 Wilson, paired_stats.wilson)"})
    return pd.DataFrame(rows)


def edgar_group_rows(groups, ans_col="correct") -> pd.DataFrame:
    a = L.edgar_answers_by_mode().query("breadth == 'all'").set_index("mode")
    rows = []
    for g in groups:
        r = a.loc[g[0]]
        for m in g:                                         # identical members must carry identical values
            assert a.loc[m, ans_col] == r[ans_col], (m, g[0])
        rows.append({"group": group_label(g), "lead": g[0], "members": "|".join(g), "acc": r["correct"], "lo": r["correct_lo"],
                     "hi": r["correct_hi"], "correct_ci": r["correct_ci"]})
    return pd.DataFrame(rows)


def fig_4_6():
    stem = "fig4_6_accuracy"
    fq = finqa_accuracy()
    groups = answer_groups()
    ed = edgar_group_rows(groups).sort_values("acc")
    margin = L.finqa_stats()["non_inferiority"]["margin"]
    f, (a1, a2) = S.fig(17, nrows=2, gridspec_kw={"height_ratios": [3, 7]})
    arms = ["policy_v2", "naive_llm", "always_hnsw"]
    for i, arm in enumerate(arms):
        for j, (est, mk) in enumerate((("pass 1", "o"), ("pooled 5 passes", "s"))):
            r = fq[(fq.arm == arm) & (fq.estimate == est)].iloc[0]
            y = i + (0.15 if j == 0 else -0.15)
            a1.errorbar(r.acc, y, xerr=[[r.acc - r.lo], [r.hi - r.acc]], fmt=mk, color=S.colour(arm),
                        mfc=S.colour(arm) if j == 0 else "white", capsize=2, lw=1, ms=5)
    a1.set_yticks(range(len(arms)), [S.name(a).replace(" (pgvector default)", "\n(pgvector default)") for a in arms])
    a1.set_xlabel("Accuracy (95 % CI)")
    a1.set_xlim(0.3, 0.9)
    a1.text(0.0, 1.02, "(a) FinQA, Gemini 3.8 Flash, 50 questions", transform=a1.transAxes, fontsize=S.FONT)
    a1.legend(handles=[Line2D([], [], color="#333333", marker="o", ls="", label="pass 1"),
                       Line2D([], [], color="#333333", marker="s", mfc="white", ls="", label="pooled, 5 passes")],
              loc="lower left")
    for i, r in enumerate(ed.itertuples()):
        col, mk = S.colour(r.lead), S.marker(r.lead)
        a2.errorbar(r.acc, i, xerr=[[r.acc - r.lo], [r.hi - r.acc]], fmt=mk, color=col, capsize=2, lw=1, ms=5)
    a2.set_yticks(range(len(ed)), list(ed.group))
    a2.set_xlabel("Accuracy (95 % CI)")
    a2.set_xlim(0.6, 1.0)
    a2.text(0.0, 1.02, "(b) EDGAR, 40 questions x 4 breadths, 1 pass", transform=a2.transAxes, fontsize=S.FONT)
    S.save(f, stem)
    dump(stem, pd.concat([fq.assign(panel="a"), ed.rename(columns={"group": "arm"}).assign(panel="b", estimate="pass 1")]))
    caption("4.6", stem, "Answer accuracy with 95 % confidence intervals. (a) FinQA, frozen 50 questions, answer model Gemini 3.8 Flash, "
            "5 passes: filled circle = pass 1, open square = pooled over the 5 passes; intervals are Wilson intervals per arm and pass "
            "(pooled: over the 250 question-passes, not adjusted for repeated questions). The pre-registered FinQA non-inferiority "
            f"margin was -{margin:.2f} (on the router minus LLM-router difference, not shown here). (b) EDGAR, 160 question-filter "
            "pairs, 1 answer pass; intervals are the pre-registered cluster bootstrap over the 40 questions (10,000 resamples, seed "
            "20261104). " + POLICY_V2_NOTE + " " + FILTERED_HNSW_NOTE + " " + groups_note(groups),
            ["outputs/hallucination_classification_2026-10-23/summary_counts_gemini_full.csv",
             "outputs/phase_d_always_hnsw_2026-10-31/analysis/classes.csv", "outputs/phase_d_always_hnsw_2026-10-31/analysis/summary.json",
             "outputs/phase_d_gemini_full_2026-10-12/stats_primary.json", "outputs/edgar_analysis_2026-11-01/answers_by_mode_breadth.csv",
             "outputs/edgar_analysis_2026-11-01/answers_scored.csv"],
            "Recomputed: panel (a) Filtered HNSW intervals (pass 1: 24/50, pooled: 130/250) are not saved in any file; recomputed "
            "with the Amendment 5 per-arm Wilson method (`src/phase_d_validation/paired_stats.py` `wilson`, no seed), which reproduces "
            "the saved intervals of the other two arms exactly; the point estimates reproduce the reported 0.48 and 0.52.")


# ------------------------------------------------------------------ Fig 4.7

FQ_CLASSES = [("correct", "correct", "#0072B2"), ("wrong_grounded", "wrong, gold evidence retrieved", "#E69F00"),
              ("wrong_ungrounded", "wrong, gold evidence not retrieved", "#D55E00"),
              ("abstain_or_parse_fail", "abstained / unparseable", "#BBBBBB")]
ED_CLASSES = [("correct", "correct", "#0072B2"), ("wrong_in_context", "wrong, number in context", "#E69F00"),
              ("wrong_not_in_context", "wrong, number not in context", "#D55E00"), ("abstained", "abstained", "#BBBBBB")]


def stacked(ax, labels, shares: dict, classes, title):
    left = np.zeros(len(labels))
    for key, lab, col in classes:
        v = np.array(shares[key])
        ax.barh(range(len(labels)), v, left=left, color=col, edgecolor="white", lw=0.5, label=lab)
        left += v
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of answers")
    ax.annotate(title, (0.01, 1.03), xycoords=("figure fraction", "axes fraction"), fontsize=S.FONT)


def fig_4_7():
    stem = "fig4_7_error_classes"
    c = L.finqa_class_counts()
    c["pass"] = c["pass"].astype(str)
    allp = c[c["pass"] == "all"]
    arms = ["policy_v2", "naive_llm", "always_hnsw"]
    fq = {}
    for arm in arms[:2]:
        d = allp[allp.arm == arm].set_index("class")
        fq[arm] = {k: d.loc[k, "n"] / d.loc[k, "of"] for k, _, _ in FQ_CLASSES}
    ah = L.finqa_always_hnsw()["arms"]["always_hnsw"]
    fq["always_hnsw"] = {k: ah["classes"][k] / ah["n_rows"] for k, _, _ in FQ_CLASSES}
    groups = answer_groups()
    a = L.edgar_answers_by_mode().query("breadth == 'all'").set_index("mode")
    rr = L.edgar_refusal_by_mode().query("breadth == 'all'").set_index("mode")
    f, axes = S.fig(23, nrows=3, gridspec_kw={"height_ratios": [3, len(groups), len(groups)]})
    stacked(axes[0], [S.name(m) for m in arms], {k: [fq[m][k] for m in arms] for k, _, _ in FQ_CLASSES}, FQ_CLASSES,
            "(a) FinQA, pooled over 5 passes (250 answers per arm)")
    axes[0].legend(loc="upper left", bbox_to_anchor=(0.01, -0.42), bbox_transform=blended_transform_factory(f.transFigure, axes[0].transAxes), ncol=2)
    lead = [g[0] for g in groups]
    labels = [group_label(g) for g in groups]
    stacked(axes[1], labels, {k: [a.loc[m, k] for m in lead] for k, _, _ in ED_CLASSES}, ED_CLASSES,
            "(b) EDGAR, pre-registered classes (160 pairs, 1 pass)")
    ref = {"correct": "ref_accuracy", "wrong_in_context": "ref_wrong_in_context", "wrong_not_in_context": "ref_wrong_not_in_context",
           "abstained": "ref_abstained"}
    stacked(axes[2], labels, {k: [rr.loc[m, ref[k]] for m in lead] for k, _, _ in ED_CLASSES}, ED_CLASSES,
            "(c) EDGAR, EXPLORATORY: refusals re-scored as abstained")
    f.legend(*axes[2].get_legend_handles_labels(), loc="outside lower center", ncol=2)
    for ax in axes[1:]:
        ax.invert_yaxis()
    S.save(f, stem)
    rows = [{"panel": "a", "arm": m, **fq[m]} for m in arms]
    rows += [{"panel": "b", "arm": lab, **{k: a.loc[m, k] for k, _, _ in ED_CLASSES}} for m, lab in zip(lead, labels)]
    rows += [{"panel": "c", "arm": lab, **{k: rr.loc[m, ref[k]] for k, _, _ in ED_CLASSES}} for m, lab in zip(lead, labels)]
    dump(stem, pd.DataFrame(rows))
    caption("4.7", stem, "Answer classes. (a) FinQA (Amendment 5 classes, grounding = gold passage text retrieved), pooled over 5 "
            "passes: correct, wrong with the gold evidence in the prompt (wrong_grounded), wrong without it (wrong_ungrounded), "
            "abstained or unparseable. Filtered HNSW (Amendment 10) uses the same classes and grounding field. (b) EDGAR, the "
            "pre-registered classes of Amendment 11 (wrong in context = the answer's number appears in a retrieved passage). "
            "(c) EXPLORATORY, not pre-registered: the same answers with refusals (\"the evidence does not contain ...\") re-scored as "
            "abstained by the tested rule of `src/phase_f_edgar/exploratory_edgar.py`. " + POLICY_V2_NOTE + " " + groups_note(groups),
            ["outputs/hallucination_classification_2026-10-23/summary_counts_gemini_full.csv",
             "outputs/phase_d_always_hnsw_2026-10-31/analysis/summary.json", "outputs/edgar_analysis_2026-11-01/answers_by_mode_breadth.csv",
             "outputs/edgar_analysis_exploratory_2026-11-01/refusal_by_mode_breadth.csv"])


# ------------------------------------------------------------------ Fig 4.8

def fig_4_8():
    stem = "fig4_8_edgar_recall_vs_latency"
    s = L.edgar_summary().query("breadth == 'all'").set_index("mode").loc[S.EDGAR_MODES].reset_index()
    f, ax = S.fig(19)
    for r in s.itertuples():
        ax.scatter(r.median_latency_ms, r.mean_recall15, s=12 + 0.5 * r._4, color=S.colour(r.mode), marker=S.marker(r.mode),
                   edgecolors="black" if S.marker(r.mode) not in ("X", "P") else None, linewidths=0.3, zorder=3,
                   label=f"{S.name(r.mode)} ({r._4}/160)")
    ax.set_xscale("log")
    ax.set_xlabel("Median end-to-end latency per pair, ms (log scale)")
    ax.set_ylabel("Mean recall@15 (160 pairs)")
    f.legend(loc="outside lower center", ncol=2, title="mode (pairs with recall@15 >= 0.90)", markerscale=0.8)
    S.save(f, stem)
    dump(stem, s[["mode", "mean_recall15", "median_latency_ms", "recall15_ge_0.90", "underfilled"]])
    caption("4.8", stem, "EDGAR retrieval comparison, all 19 modes: mean recall@15 against median end-to-end latency of retrieve() "
            "(median over the 160 pairs of the per-pair median of 5 timed runs; LLM-router and VecAdvisor decision time excluded). "
            "Marker area grows with the number of pairs reaching recall@15 >= 0.90 (given in the legend). The seven modes that all "
            "chose exact search overlap at recall 1.0 and differ only in latency. " + FILTERED_HNSW_NOTE,
            ["outputs/edgar_retrieval_comparison_2026-11-01/summary_by_mode_breadth.csv"])


# ------------------------------------------------------------------ Fig 4.9

def fig_4_9():
    stem = "fig4_9_router_overhead"
    o = L.edgar_overhead().set_index("breadth").loc[list(L.BREADTHS)].reset_index()
    parts = [("median_stats_check_ms", "statistics check", "#CC79A7"), ("median_estimate_ms", "planner estimate", "#E69F00"),
             ("median_count_ms", "capped count (pairs that needed it)", "#D55E00"), ("median_route_ms", "exact route", "#0072B2")]
    f, axes = S.fig(11, ncols=2)
    for ax, bs in zip(axes, (L.BREADTHS[:2], L.BREADTHS[2:])):
        d = o[o.breadth.isin(bs)].reset_index(drop=True)
        y = np.arange(len(d)) * 1.0
        left = np.zeros(len(d))
        for col, lab, c_ in parts:
            v = d[col].fillna(0).to_numpy()
            ax.barh(y + 0.2, v, left=left, height=0.35, color=c_, label=lab)
            left += v
        ax.barh(y - 0.2, d["always_exact_median_latency_ms"], height=0.35, color="#000000", label="always exact (median)")
        ax.scatter(d["router_median_latency_ms"], y + 0.2, marker="|", s=120, color="#333333", zorder=3, label="router (median)")
        ax.set_yticks(y, [S.BREADTH_LABEL[b].replace(" + section", chr(10) + "+ section") for b in d.breadth])
        ax.invert_yaxis()
        ax.set_xlabel("Latency, ms")
    h, lab = axes[0].get_legend_handles_labels()
    f.legend(h, lab, loc="outside lower center", ncol=3)
    S.save(f, stem)
    dump(stem, o)
    caption("4.9", stem, "Why P5 failed: the router's per-query decision cost on EDGAR, by filter breadth (40 pairs each). Lower bar of each pair: "
            "median over pairs of each step's per-pair median over 5 timed runs (statistics check, planner estimate, capped count "
            "where the band needed one: 30 of 40 section pairs, none elsewhere), stacked with the exact route it then ran; the tick is "
            "the router's median end-to-end latency (the stacked medians do not add up to it exactly; about 1 ms is outside the "
            "steps). Upper bar: always-exact median latency. The router chose exact on all 160 pairs, so it paid 12-18 ms for the "
            "decision and then ran the same query; this is why P5 (router faster than always-exact at year+section and section) "
            "did not hold. Exploratory description from the route traces.",
            ["outputs/edgar_report_inputs_2026-11-01/decision_overhead.json"])


# ------------------------------------------------------------------ Fig 5.1

def fig_5_1():
    stem = "fig5_1_thresholds"
    hm = L.hm_config()
    pooled = hm["calibration_default"]["pooled"]
    pc = L.prior_constants()
    sw_lo, sw_hi = L.hm_planner_switch()
    cliff = hm["k"] / hm["ef_search"]
    rows = [("H&M router: safe interval and T", "band", pooled["lower"], pooled["upper"], T_HM, S.T_HM_COLOUR, "config/policy_v3_hm.json"),
            ("EDGAR router T (empty-interval rule)", "line", None, None, T_ED, S.T_EDGAR_COLOUR, "config/policy_v3_1_edgar.json"),
            ("VBASE: exact if s < 0.18", "line", None, None, pc["vbase"]["s"], S.colour("vbase"), pc["vbase"]["src"]),
            ("Milvus (via NaviX): exact if s <= 0.05", "line", None, None, pc["milvus"]["s"], S.colour("milvus"), pc["milvus"]["src"]),
            ("Qdrant, H&M (1,250 rows / 105,100)", "line", None, None, pc["qdrant_hm"]["s"], S.colour("qdrant"), pc["qdrant_hm"]["src"]),
            ("Qdrant, FinQA (2,500 rows / 35,862)", "line", None, None, pc["qdrant_finqa"]["s"], S.colour("qdrant"), pc["qdrant_finqa"]["src"]),
            ("Qdrant, EDGAR (2,500 rows / 158,308)", "line", None, None, pc["qdrant_edgar"]["s"], S.colour("qdrant"), pc["qdrant_edgar"]["src"]),
            ("H&M planner switch exact -> HNSW", "band", sw_lo, sw_hi, None, "#777777", "outputs/phase_a_arms/analysis/cell_summary.csv"),
            (f"Post-filter cliff k / ef_search = {hm['k']}/{hm['ef_search']}", "line", None, None, cliff, S.colour("default_hnsw"),
             "computed from k and ef_search in config/policy_v3_hm.json")]
    f, ax = S.fig(11)
    for i, (lab, kind, lo, hi, x, col, _) in enumerate(rows):
        y = len(rows) - 1 - i
        if kind == "band":
            ax.barh(y, hi - lo, left=lo, height=0.5, color=col, alpha=0.35, lw=0)
        if x is not None:
            ax.plot([x, x], [y - 0.3, y + 0.3], color=col, lw=2.2)
            ax.text(max(x, hi or x) * 1.12, y, f"{x:.4g}", va="center", fontsize=S.FONT, color=col)
        else:
            ax.text(lo / 1.08, y, f"{lo:.4f}-{hi:.4f}", va="center", ha="right", fontsize=S.FONT, color=col)
    ax.set_yticks(range(len(rows)), [r[0] for r in reversed(rows)])
    ax.set_xscale("log")
    ax.set_xlim(3e-3, 1)
    ax.set_xlabel("Filter selectivity (log scale)")
    ax.grid(axis="x", which="major", color="#DDDDDD", lw=0.5)
    S.save(f, stem)
    dump(stem, pd.DataFrame(rows, columns=["label", "kind", "lo", "hi", "x", "colour", "source"]))
    caption("5.1", stem, "Thresholds on one selectivity axis (log scale). Shaded: the H&M safe interval (0.0478, 0.1061] with the "
            f"calibrated T = {T_HM:.4f} (line), and the selectivity range in which the H&M planner switches from the exact bitmap "
            f"scan to the HNSW index scan ({sw_lo:.4f} = gap3, last all-exact cell; {sw_hi:.4f} = gap4, first all-HNSW cell, every "
            f"table). Lines: EDGAR T = {T_ED:.4f}; the prior-system rules as re-implemented in this repository (VBASE "
            f"{pc['vbase']['src']}; Milvus via NaviX {pc['milvus']['src']}); Qdrant's row limit 10,000 KB / vector size converted to a "
            "selectivity with each corpus' row count (H&M " + pc["qdrant_hm"]["src"] + "; FinQA " + pc["qdrant_finqa"]["src"] +
            "; EDGAR " + pc["qdrant_edgar"]["src"] + "); the post-filter cliff s = k / ef_search "
            f"= {hm['k']}/{hm['ef_search']} = {cliff:.2f} below which a post-filtered HNSW scan is expected to under-fill "
            "(Mandarapu & Kunkunuru, arXiv:2606.16341), computed from k and ef_search of `config/policy_v3_hm.json`, not measured.",
            ["config/policy_v3_hm.json", "config/policy_v3_1_edgar.json", "src/phase_c_analysis/amendment6_partb.py",
             "src/phase_d_validation/amendment7_step1.py", "src/phase_f_edgar/compare_edgar.py",
             "outputs/phase_a_arms/analysis/cell_summary.csv", "outputs/edgar_chunks_2026-10-31/summary.json"])


# ------------------------------------------------------------------ Appendix

def fig_a_1():
    stem = "figA_1_edgar_calibration_per_vector"
    r = L.edgar_cal_results()
    r = r[r.route.isin(["exact", "iterative_default", "iterative_tuned"]) & r.recall15.notna()]
    cells = r.groupby("filter_id")["selectivity"].first().sort_values()
    f, axes = S.fig(17, nrows=3, sharex=True, sharey=True)
    labs = {"exact": "Exact", "iterative_default": "Iterative (default)", "iterative_tuned": "Iterative, tuned"}
    cols = {"exact": "#555555", "iterative_default": "#E69F00", "iterative_tuned": "#DDCC77"}
    for ax, route in zip(axes, labs):
        d = [r[(r.route == route) & (r.filter_id == c)]["recall15"].to_numpy() for c in cells.index]
        bp = ax.boxplot(d, positions=range(len(cells)), widths=0.55, patch_artist=True, showfliers=True,
                        flierprops={"ms": 2.5, "marker": "o", "markerfacecolor": cols[route], "markeredgecolor": "none"},
                        medianprops={"color": "black"})
        for b in bp["boxes"]:
            b.set_facecolor(cols[route])
        ax.axhline(0.9, color="#555555", ls=":", lw=1)
        ax.set_ylabel("Recall@15")
        ax.set_title(labs[route], fontsize=S.FONT, loc="left")
    axes[-1].set_xticks(range(len(cells)), [f"{c} ({s:.2g})" for c, s in cells.items()], fontsize=S.FONT, rotation=45, ha="right")
    axes[-1].set_xlabel("Grid cell and achieved selectivity")
    S.save(f, stem)
    dump(stem, r.groupby(["route", "filter_id"])["recall15"].describe().reset_index())
    caption("A.1", stem, "EDGAR calibration, per-vector spread: recall@15 of each of the 20 calibration questions (normal execution) "
            "per grid cell, for the exact, default iterative and tuned iterative routes (box = quartiles, whiskers = 1.5 IQR, dots "
            "= outliers). Dotted line: 0.90. The guard variants are not stored per vector (they are derived per cell), so they are not "
            "shown.", ["outputs/edgar_calibration_2026-11-01/results.jsonl"], "Panels for iterative + guard and tuned + guard skipped: no "
            "per-vector values saved.")


def fig_a_2():
    stem = "figA_2_edgar_recall_heatmap"
    s = L.edgar_summary()
    cols = list(L.BREADTHS) + ["all"]
    m = s.pivot(index="mode", columns="breadth", values="mean_recall15").loc[S.EDGAR_MODES, cols]
    f, ax = S.fig(15)
    im = ax.imshow(m.to_numpy(), cmap="viridis", vmin=0.4, vmax=1.0, aspect="auto")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.iat[i, j]
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=S.FONT, color="black" if v > 0.75 else "white")
    ax.set_xticks(range(len(cols)), [S.BREADTH_LABEL[c].replace(" + ", chr(10) + "+ ") for c in cols])
    ax.set_yticks(range(len(m)), [S.name(x) for x in m.index])
    ax.spines[:].set_visible(False)
    cb = f.colorbar(im, ax=ax, fraction=0.03)
    cb.set_label("Mean recall@15")
    S.save(f, stem)
    dump(stem, m.reset_index())
    caption("A.2", stem, "EDGAR mean recall@15 by mode and filter breadth (40 pairs per breadth, 160 in 'all breadths').",
            ["outputs/edgar_retrieval_comparison_2026-11-01/summary_by_mode_breadth.csv"])


def fig_a_3():
    stem = "figA_3_edgar_latency_by_breadth"
    p = L.edgar_per_pair()
    modes = ["router", "always_exact", "router_hmT", "default_hnsw"]
    f, ax = S.fig(12)
    w = 0.18
    for j, m in enumerate(modes):
        d = [p[(p["mode"] == m) & (p.breadth == b)]["latency_ms"].to_numpy() for b in L.BREADTHS]
        pos = np.arange(len(L.BREADTHS)) + (j - 1.5) * w
        bp = ax.boxplot(d, positions=pos, widths=w * 0.85, patch_artist=True, showfliers=True,
                        flierprops={"ms": 2, "marker": S.marker(m), "markerfacecolor": S.colour(m), "markeredgecolor": "none"},
                        medianprops={"color": "white" if m in ("router", "always_exact") else "black"})
        for b in bp["boxes"]:
            b.set_facecolor(S.colour(m))
    ax.set_yscale("log")
    ax.set_xticks(range(len(L.BREADTHS)), [S.BREADTH_LABEL[b].replace(" + ", chr(10) + "+ ") for b in L.BREADTHS])
    ax.set_ylabel("Latency per pair, ms (log scale)")
    f.legend(handles=[Patch(color=S.colour(m), label=S.name(m)) for m in modes], loc="outside lower center", ncol=2)
    S.save(f, stem)
    dump(stem, p[p["mode"].isin(modes)].groupby(["mode", "breadth"])["latency_ms"].describe().reset_index())
    caption("A.3", stem, "EDGAR end-to-end latency per pair (median of 5 timed runs) by filter breadth for the router, always-exact, "
            "the router with the H&M threshold, and filtered HNSW; 40 pairs per box. " + FILTERED_HNSW_NOTE,
            ["outputs/edgar_retrieval_comparison_2026-11-01/per_pair_mode.csv"])


ROUTE_COLS = {"exact": "#000000", "iterative_default": "#E69F00", "iterative_tuned": "#DDCC77", "iterative_tuned+exact": "#999933",
              "planner_iterative": "#117733", "hnsw": "#D55E00", "hnsw+exact": "#882255", "route_failure": "#BBBBBB"}


def fig_a_4():
    stem = "figA_4_edgar_route_mix"
    s = L.edgar_summary()
    f, axes = S.fig(17, ncols=4, sharey=True)
    rows = []
    for ax, b in zip(axes, L.BREADTHS):
        d = s[s.breadth == b].set_index("mode").loc[S.EDGAR_MODES]
        left = np.zeros(len(d))
        for route, col in ROUTE_COLS.items():
            v = np.array([r.get(route, 0) for r in d.routes]) / d.n_pairs.to_numpy()
            ax.barh(range(len(d)), v, left=left, color=col, edgecolor="white", lw=0.3)
            left += v
            rows += [{"breadth": b, "mode": m, "route": route, "share": x} for m, x in zip(d.index, v) if x]
        assert np.allclose(left, 1.0), b
        ax.set_title(S.BREADTH_LABEL[b].replace(" + ", chr(10) + "+ "), fontsize=S.FONT)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Share of pairs")
    axes[0].set_yticks(range(len(S.EDGAR_MODES)), [S.name(m) for m in S.EDGAR_MODES])
    axes[0].invert_yaxis()
    present = sorted({r["route"] for r in rows}, key=list(ROUTE_COLS).index)
    f.legend(handles=[Patch(color=ROUTE_COLS[r], label=r) for r in present], loc="outside lower center", ncol=3)
    S.save(f, stem)
    dump(stem, pd.DataFrame(rows))
    caption("A.4", stem, "EDGAR route mix: share of the 40 pairs per breadth on which each mode executed each route (\"+exact\" = an "
            "exact re-run after the first route: guard or retry). The panel titles are the filter breadths.",
            ["outputs/edgar_retrieval_comparison_2026-11-01/summary_by_mode_breadth.csv"])


def fig_a_5():
    stem = "figA_5_router_hmT_per_pair"
    p = L.edgar_per_pair().query("mode == 'router_hmT'")
    f, ax = S.fig(11)
    for route, col in ROUTE_COLS.items():
        d = p[p.route == route]
        if len(d):
            ax.scatter(d.selectivity, d.recall15, s=26, color=col, label=f"{route} ({len(d)} pairs)", alpha=0.8, lw=0)
    ax.axhline(0.9, color="#555555", ls=":", lw=1)
    tline(ax, T_HM, f"H&M T = {T_HM:.4f}", S.T_HM_COLOUR, y=0.45)
    tline(ax, T_HM / 2, "T/2", S.T_HM_COLOUR, ls=":", level=1)
    ax.set_xscale("log")
    ax.set_xlabel("Exact selectivity of the pair's filter (log scale)")
    ax.set_ylabel("Recall@15")
    ax.legend(loc="lower left")
    S.save(f, stem)
    dump(stem, p[["pair_id", "breadth", "selectivity", "route", "recall15"]])
    caption("A.5", stem, f"EDGAR, router with the H&M threshold (T = {T_HM:.4f}): recall@15 of each of the 160 pairs against the "
            "filter's selectivity, coloured by the route taken. Pairs below T/2 go to exact; above 2T to iterative; in between the "
            "capped count decides. Dotted line: 0.90.", ["outputs/edgar_retrieval_comparison_2026-11-01/per_pair_mode.csv"])


def fig_a_6():
    stem = "figA_6_retrieval_vs_answer"
    a = L.edgar_answers_scored().query("`pass` == 1")
    groups = answer_groups()
    rows = []
    for g in groups:
        d = a[a["mode"] == g[0]]
        for hit in (True, False):
            x = d[d.gold_hit == hit]
            rows.append({"group": group_label(g), "lead": g[0], "gold_hit": hit, "n": len(x), "correct": int(x.correct.sum())})
    t = pd.DataFrame(rows)
    f, (a1, a2) = S.fig(16, nrows=2, gridspec_kw={"height_ratios": [2.2, 1]})
    y = np.arange(len(groups))
    for k, (hit, off, hatch) in enumerate(((True, 0.2, None), (False, -0.2, "///"))):
        d = t[t.gold_hit == hit].reset_index(drop=True)
        a1.barh(y + off, d.correct / d.n.replace(0, np.nan), height=0.38, color=[S.colour(m) for m in d.lead], hatch=hatch,
                edgecolor="white", lw=0.3)
        for i, r in d.iterrows():
            a1.text(1.01, y[i] + off, f"{r.correct}/{r.n}", va="center", fontsize=S.FONT)
    a1.set_yticks(y, [group_label(g) for g in groups])
    a1.invert_yaxis()
    a1.set_xlim(0, 1.15)
    a1.set_xlabel("Share correct")
    a1.legend(handles=[Patch(facecolor="#888888", label="gold chunk retrieved"),
                       Patch(facecolor="#888888", hatch="///", edgecolor="white", label="gold chunk not retrieved")],
              loc="upper center", bbox_to_anchor=(0.4, -0.22), ncol=2)
    d = a[a["mode"] == "default_hnsw"]
    rng = np.random.default_rng(0)
    for v, col in ((1, "#0072B2"), (0, "#D55E00")):
        x = d[d.correct == v]
        a2.scatter(x.recall15.fillna(0), v + rng.uniform(-0.15, 0.15, len(x)), s=10, color=col, alpha=0.7, lw=0)
    a2.set_yticks([0, 1], ["wrong / abstained", "correct"])
    a2.set_xlabel("Recall@15 (filtered HNSW), per pair")
    S.save(f, stem)
    dump(stem, t)
    caption("A.6", stem, "EDGAR retrieval against answer correctness (pass 1). Left: share of correct answers among pairs where the gold "
            "chunk was retrieved (solid) and where it was not (hatched), per mode group, with counts. Right: filtered HNSW, recall@15 "
            "of each pair against whether the answer was correct (vertical jitter for display). " + groups_note(groups),
            ["outputs/edgar_analysis_2026-11-01/answers_scored.csv"])


def fig_a_7():
    stem = "figA_7_default_hnsw_rows_vs_class"
    a = L.edgar_answers_scored().query("`pass` == 1 and mode == 'default_hnsw'")
    order = ["correct", "wrong_in_context", "wrong_not_in_context", "abstained"]
    f, ax = S.fig(10)
    rng = np.random.default_rng(0)
    for i, c in enumerate(order):
        x = a[a["class"] == c]
        col = np.where(x.rows_returned == 0, "#D55E00", np.where(x.rows_returned < 15, "#E69F00", "#0072B2"))
        ax.scatter(x.rows_returned + rng.uniform(-0.25, 0.25, len(x)), i + rng.uniform(-0.2, 0.2, len(x)), s=22, c=col, lw=0)
    ax.set_yticks(range(len(order)), [c.replace("_", " ") for c in order])
    ax.set_xlabel("Rows returned by filtered HNSW (k = 15)")
    f.legend(handles=[Patch(color="#D55E00", label="0 rows (empty prompt)"), Patch(color="#E69F00", label="1-14 rows (under-filled)"),
                       Patch(color="#0072B2", label="15 rows")], loc="outside lower center", ncol=3)
    S.save(f, stem)
    dump(stem, a.groupby(["class", "rows_returned"]).size().rename("pairs").reset_index())
    caption("A.7", stem, "EDGAR filtered HNSW (pgvector default): rows returned against the pre-registered answer class for the 160 "
            "pairs (pass 1; jitter for display). 0-row and under-filled prompts are highlighted. " + FILTERED_HNSW_NOTE,
            ["outputs/edgar_analysis_2026-11-01/answers_scored.csv"])


def fig_a_8():
    stem = "figA_8_accuracy_three_rules"
    groups = answer_groups()
    a = L.edgar_answers_by_mode().query("breadth == 'all'").set_index("mode")
    rr = L.edgar_refusal_by_mode().query("breadth == 'all'").set_index("mode")
    sc = L.edgar_scale_rescore()["accuracy_by_mode"]
    rows = [{"group": group_label(g), "lead": g[0], "primary": a.loc[g[0], "correct"], "scale_aware": sc[g[0]]["scale_aware"],
             "refusal_rule": rr.loc[g[0], "ref_accuracy"]} for g in groups]
    for r in rows:
        assert abs(r["primary"] - sc[r["lead"]]["primary"]) <= 5e-5     # answers_by_mode_breadth.csv rounds to 4 places
    t = pd.DataFrame(rows)
    f, ax = S.fig(11)
    marks = (("primary", "o", "pre-registered primary rule"), ("scale_aware", "s", "scale-aware matching"),
             ("refusal_rule", "^", "refusals as abstained"))
    for i, r in t.iterrows():
        ax.plot([min(r.primary, r.scale_aware), max(r.primary, r.scale_aware)], [i, i], color="#BBBBBB", lw=2, zorder=1)
        for k, mk, _ in marks:
            ax.scatter(r[k], i + {"primary": 0, "scale_aware": 0, "refusal_rule": 0.22}[k], marker=mk, s=45, zorder=3,
                       color=S.colour(r.lead), facecolors="white" if k != "primary" else S.colour(r.lead))
    ax.set_yticks(range(len(t)), t.group)
    ax.invert_yaxis()
    ax.set_xlabel("Accuracy (160 pairs, 1 pass)")
    f.legend(handles=[Line2D([], [], marker=mk, ls="", color="#333333", mfc="#333333" if k == "primary" else "white", label=lab)
                       for k, mk, lab in marks], loc="outside lower center", ncol=2)
    S.save(f, stem)
    dump(stem, t)
    caption("A.8", stem, "EXPLORATORY, not pre-registered: EDGAR accuracy per mode group under the pre-registered primary rule "
            "(filled circle), scale-aware matching (thousand/million/billion applied on both sides, same 1 % tolerance; open square) "
            "and the refusal rule (open triangle, offset; refusals were never correct, so accuracy equals the primary rule). "
            + groups_note(groups),
            ["outputs/edgar_analysis_2026-11-01/answers_by_mode_breadth.csv", "outputs/edgar_analysis_exploratory_2026-11-01/scale_rescore.json",
             "outputs/edgar_analysis_exploratory_2026-11-01/refusal_by_mode_breadth.csv"])


def fig_a_9():
    stem = "figA_9_hm_pass_counts"
    pe = L.hm_phase_e_pass_counts().set_index("mode")
    order = ["router", "router_tuned", "router_no_guard", "router_always_count", "router_plus_probe", "fixed_t_0_1", "oracle",
             "local_probe", "iterative_tuned", "always_iterative", "planner_iterative", "retry_exact", "always_exact", "default_hnsw",
             "llm_router"]
    rows = [{"key": m, "label": S.name(m), "in_sample": pe.loc[m, "in_sample"], "held_out": pe.loc[m, "held_out"], "session": "Phase E"}
            for m in order]
    v1 = L.hm_v1_pass_counts()
    rows.append({"key": "v1", "label": S.name("v1"), "in_sample": v1["in_sample"], "held_out": v1["held_out"], "session": "Phase A"})
    pb = L.hm_partb_pass_counts().set_index("rule")
    for key, rule in (("B1", "B1 VBASE (s < 0.18)"), ("B2", "B2 Milvus via NaviX (s <= 0.05)"), ("B3", "B3 Qdrant (rows < 1,250)"),
                      ("B4", "B4 Gan & Wang (recall/latency labels)"), ("B4b", "B4b Gan & Wang (SLA labels)")):
        rows.append({"key": key, "label": S.name(key), "in_sample": pb.loc[rule, "in_sample"], "held_out": pb.loc[rule, "held_out"],
                     "session": "Phase A (Amendment 6)"})
    t = pd.DataFrame(rows)
    f, ax = S.fig(17)
    y = np.arange(len(t))
    ins = t.in_sample.to_numpy(dtype=float)
    ax.barh(y - 0.2, np.nan_to_num(ins / 65), height=0.38, color=[S.colour(k) for k in t.key], label="in-sample (/65)")
    ax.barh(y + 0.2, t.held_out / 50, height=0.38, color=[S.colour(k) for k in t.key], hatch="///", edgecolor="white", lw=0.3,
            label="held-out (/50)")
    for i, r in t.iterrows():
        ax.text(1.01, i, ("-" if np.isnan(r.in_sample) else f"{int(r.in_sample)}/65") + f"  {int(r.held_out)}/50", va="center",
                fontsize=S.FONT)
    ax.axhline(len(order) - 0.5, color="#555555", lw=0.8)
    ax.set_yticks(y, t.label)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.25)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("Share of cells passing" + chr(10) + "(recall@10 >= 0.90 and median latency <= 500 ms)")
    f.legend(handles=[Patch(facecolor="#888888", label="in-sample (65 cells)"),
                       Patch(facecolor="#888888", hatch="///", edgecolor="white", label="held-out (50 cells)")],
              loc="outside lower center", ncol=2)
    S.save(f, stem)
    dump(stem, t)
    caption("A.9", stem, "H&M pass counts per mode: in-sample (65 cells: 13 filters x 5 tables) and held-out (50 cells: held-out sets 1 "
            "and 2, 25 each). Above the line: Phase E comparison session (Amendment 9; the LLM router was run on the held-out sets "
            "only). Below: the v1 decision matrix (Phase A policy evaluation and hold-out runs, held-out 1 = original run) and the "
            "prior-work rules B1-B4b re-scored on the Phase A measurements (Amendment 6 Part B, held-out 1 = original run; the quiet "
            "re-run is in Table 4.3). The two groups come from different measurement sessions. " + FILTERED_HNSW_NOTE,
            ["outputs/phase_e_comparison_hm_2026-10-31/summary.json", "outputs/phase_a_amendment6_2026-10-23/partb_summary.json",
             "outputs/phase_a_arms/analysis/policy_evaluation_cells.csv", "outputs/phase_a_holdout/analysis/policy_cells.csv",
             "outputs/phase_a_holdout2/analysis/policy_cells.csv"])


FIGURES = [fig_4_1, fig_4_2, fig_4_3, fig_4_4, fig_4_5, fig_4_6, fig_4_7, fig_4_8, fig_4_9, fig_5_1,
           fig_a_1, fig_a_2, fig_a_3, fig_a_4, fig_a_5, fig_a_6, fig_a_7, fig_a_8, fig_a_9]


def write_captions():
    out = ["# Figure captions (draft), 2026-11-01", "",
           "Every figure: PNG (300 dpi) and PDF in this folder; the plotted values are in `data/<file>.csv`. Generated by "
           "`src/figures/make_figures.py` from committed files only.", ""]
    for c in CAPTIONS:
        out += [f"## Figure {c['num']}: `{c['stem']}`", "", c["text"], "", "Sources: " + ", ".join(f"`{s}`" for s in c["sources"])]
        if c["notes"]:
            out += ["", "Note: " + c["notes"]]
        out.append("")
    out += ["## Not produced", ""] + [f"- **{a}**: {b}" for a, b in NOT_PRODUCED] + [""]
    (S.FIG_DIR / "CAPTIONS.md").write_text("\n".join(out), encoding="utf-8", newline="\n")


def main():
    for fn in FIGURES:
        fn()
        print("done", fn.__name__)
    write_captions()


if __name__ == "__main__":
    main()
