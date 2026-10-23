"""Builds reports/hallucination_classification_<date>.md from the summaries written by hallucination_classify.py (read-only).

  python -m src.phase_d_validation.hallucination_report --dir outputs/hallucination_classification_2026-10-23 --out reports/hallucination_classification_2026-10-23.md
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

CLS = ("correct", "abstain_or_parse_fail", "wrong_ungrounded", "wrong_grounded")
RUNS = [("gemini_full", "Gemini 3.8 Flash full run (4 arms x 50 questions x 5 passes)", "retrieval_hit_passage"),
        ("local_v5", "local qwen2.5:7b v5 (4 arms x 50 x 5 passes)", "retrieval_hit_passage"),
        ("local_v4", "local qwen2.5:7b v4 (4 arms x 50 x 2 passes)", "retrieval_hit_passage"),
        ("local_v3", "local qwen2.5:7b v3 (3 arms x 50 x 2 passes)", "retrieval_hit_passage"),
        ("local_oct12_baseline", "local qwen2.5:7b 12 Oct baseline (nomic, k = 6, non-distinct; 3 arms x 50 x 2 passes)", "retrieval_hit (strict; the only field in its rows)")]
ARM_ORDER = ["policy_v2", "decision_matrix", "naive_llm", "naive_informed"]


def pct(x):
    return "-" if x is None else f"{100 * x:.1f}%"


def cell(r):
    return f"{r['n']}/{r['of']} ({pct(r['rate'])}; {pct(r['ci95'][0])}-{pct(r['ci95'][1])})"


def counts_tables(s, scope, label):
    arms = [a for a in ARM_ORDER if a in s["arms"]]
    t = {(r["arm"], r["class"]): r for r in s["counts"] if r["pass"] == scope}
    out = [f"**{label}** (count/rows (rate; Wilson 95% CI))\n", "| arm | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | correct_ungrounded (subset of correct) |", "|---|---|---|---|---|---|"]
    for a in arms:
        out.append(f"| {a} | " + " | ".join(cell(t[(a, c)]) for c in CLS + ("correct_ungrounded (subset of correct)",)) + " |")
    return out + [""]


def read_classified(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    D = Path(a.dir)
    S = {k: json.loads((D / f"summary_{k}.json").read_text(encoding="utf-8")) for k, _, _ in RUNS}
    w = []
    w.append("# Hallucination-oriented classification of wrong answers (Amendment 5), 2026-10-23\n")
    w.append("Pre-registered in `docs/preregistration/PHASE_D_AMENDMENT_5.md` (tag `phase-d-amendment-5-2026-10-23`, commit `0ac1bd2`, written and tagged before anything was computed). Existing outputs only: no model call, no API call (cost USD 0), no database write (the only database access is the read-only evidence `SELECT` for the labelling sheet). Primary results of Amendments 1-3 are not re-analysed. Each model is analysed separately.\n")
    w.append("**Naming.** `wrong_ungrounded` is called \"ungrounded wrong answer (hallucination proxy)\" below: a wrong, parsed answer where the gold evidence was not fully in the prompt. It is a proxy, not proof of fabrication; the word hallucination is not used for it until the blind manual sample (section 7) has been labelled.\n")
    w.append("**Grounding field (decision of the user, 2026-10-23).** `retrieval_hit_passage` (every gold row's text among the retrieved passage texts) for the Amendment 1+ runs; the strict page-id field `retrieval_hit` only for the 12 Oct baseline (its rows have no other field). The strict field is shown as a sensitivity table, \"strict page-id test, shown for transparency only\". No null grounding values were found in any run.\n")
    w.append("Classes in order: `correct`; `abstain_or_parse_fail` (wrong and no number parsed); `wrong_ungrounded` (wrong, parsed, grounding field 0); `wrong_grounded` (wrong, parsed, grounding field 1). `correct_ungrounded` = correct while the grounding field is 0.\n")
    for key, title, field in RUNS[:2]:
        s = S[key]
        w.append(f"## {title}\n\nGrounding field: {field}. {s['n_rows']} rows.\n")
        w += counts_tables(s, 1, "Pass 1")
        w += counts_tables(s, "all", f"Pooled over {len(s['passes'])} passes")
        w.append("**Paired comparison per question (secondary, pre-specified, descriptive; no margin, no multiplicity correction).** Pass 1: b = questions where the first arm has the class and the second does not; c = the reverse; exact McNemar p. Pooled: per-question mean class indicator over the passes, paired bootstrap (10,000 resamples, seed 20261012).\n")
        w.append("| comparison | class | pass 1 rates (x / y) | b | c | exact McNemar p | pooled rates (x / y) | pooled difference x - y [95% CI] |\n|---|---|---|---|---|---|---|---|")
        for name, p in s["paired"].items():
            for c, v in p["classes"].items():
                w.append(f"| {name.replace('_vs_', ' vs ')} | {c} | {pct(v['pass1']['rate_x'])} / {pct(v['pass1']['rate_y'])} | {v['pass1']['b_x_only']} | {v['pass1']['c_y_only']} | {v['pass1']['mcnemar_exact_p']:.3f} | {pct(v['pooled']['mean_rate_x'])} / {pct(v['pooled']['mean_rate_y'])} | {100 * v['pooled']['diff_x_minus_y']:+.1f} pp [{100 * v['pooled']['ci95'][0]:+.1f}, {100 * v['pooled']['ci95'][1]:+.1f}] |")
        w.append("")
        w.append("**Split by chosen route** (naive arms; all passes pooled):\n\n| arm | route | rows | correct | abstain_or_parse_fail | wrong_ungrounded | wrong_grounded | mean rows returned |\n|---|---|---|---|---|---|---|---|")
        for r in s["route_split"]:
            if r["scope"] == "all":
                w.append(f"| {r['arm']} | {r['route']} | {r['n']} | {r['correct']} | {r['abstain_or_parse_fail']} | {r['wrong_ungrounded']} ({pct(r['wrong_ungrounded'] / r['n'])}) | {r['wrong_grounded']} ({pct(r['wrong_grounded'] / r['n'])}) | {r['mean_rows_returned']:.1f} |")
        w.append("\n(Pass-1 route split: `summary_route_split_" + key + ".csv`.)\n")
    w.append("## Rows returned for ungrounded wrong answers, and 0-row cases\n")
    w.append("How many `wrong_ungrounded` rows had 0 rows returned (the post-filter route returned nothing, so the model answered with no evidence at all). All passes pooled, and pass 1 only.\n")
    w.append("| run | arm | wrong_ungrounded rows (all passes) | with 0 rows returned | rows returned: 0 / 1-3 / 4-7 / 8-14 / 15 | mean rows | pass 1: wrong_ungrounded | pass 1: with 0 rows |\n|---|---|---|---|---|---|---|---|")
    for key, title, field in RUNS:
        cl = read_classified(D / f"classified_rows_{key}.csv")
        for r in S[key]["rows_returned_wrong_ungrounded"]:
            p1 = [x for x in cl if x["arm"] == r["arm"] and x["pass"] == "1" and x["class"] == "wrong_ungrounded"]
            if r["n_with_rows_returned_logged"] == 0:
                w.append(f"| {key} | {r['arm']} | {r['n_wrong_ungrounded']} | not logged | not logged | not logged | {len(p1)} | not logged |")
                continue
            z1 = sum(1 for x in p1 if x["rows_returned"] == "0")
            w.append(f"| {key} | {r['arm']} | {r['n_wrong_ungrounded']} | {r['zero_row_cases']} | {r['rows_0']} / {r['rows_1-3']} / {r['rows_4-7']} / {r['rows_8-14']} / {r['rows_15+']} | {r['mean_rows']:.1f} | {len(p1)} | {z1} |")
    w.append("")
    w.append("## Other runs (pooled counts per arm; all passes)\n")
    for key, title, field in RUNS[2:]:
        s = S[key]
        w.append(f"**{title}**; grounding field: {field}.\n")
        w += counts_tables(s, "all", "Pooled over " + str(len(s["passes"])) + " passes")
        pv = s["paired"].get("policy_v2_vs_naive_llm")
        if pv:
            w.append("policy_v2 vs naive_llm, pass 1 (b = policy_v2 only, c = naive_llm only; exact McNemar p): " + "; ".join(f"{c}: b = {v['pass1']['b_x_only']}, c = {v['pass1']['c_y_only']}, p = {v['pass1']['mcnemar_exact_p']:.3f}; pooled diff {100 * v['pooled']['diff_x_minus_y']:+.1f} pp [{100 * v['pooled']['ci95'][0]:+.1f}, {100 * v['pooled']['ci95'][1]:+.1f}]" for c, v in pv["classes"].items()) + ".\n")
    w.append("## Sensitivity: the same class counts with the strict page-id test (shown for transparency only)\n")
    w.append("`wrong_ungrounded` and `correct_ungrounded` recomputed with the strict `retrieval_hit` (all passes pooled; rows per arm in parentheses). For the 12 Oct baseline the strict field is the grounding field, so its row is identical to the main table.\n")
    w.append("| run | arm | correct | wrong_ungrounded (passage level, main) | wrong_ungrounded (strict) | wrong_grounded (strict) | correct_ungrounded (passage level, main) | correct_ungrounded (strict) |\n|---|---|---|---|---|---|---|---|")
    for key, title, field in RUNS:
        s = S[key]
        main_t = {(r["arm"], r["class"]): r for r in s["counts"] if r["pass"] == "all"}
        sens = {(r["arm"], r["class"]): r for r in s["sensitivity_strict_page_id_test_for_transparency_only"] if r["pass"] == "all"}
        for a_ in [x for x in ARM_ORDER if x in s["arms"]]:
            w.append(f"| {key} | {a_} ({main_t[(a_, 'correct')]['of']}) | {main_t[(a_, 'correct')]['n']} | {main_t[(a_, 'wrong_ungrounded')]['n']} | {sens[(a_, 'wrong_ungrounded')]['n']} | {sens[(a_, 'wrong_grounded')]['n']} | {main_t[(a_, 'correct_ungrounded (subset of correct)')]['n']} | {sens[(a_, 'correct_ungrounded (subset of correct)')]['n']} |")
    w.append("")
    g, l5 = S["gemini_full"], S["local_v5"]
    gc = {(r["arm"], r["class"], r["pass"]): r for r in g["counts"]}
    gs = {(r["arm"], r["class"], r["pass"]): r for r in g["sensitivity_strict_page_id_test_for_transparency_only"]}
    lc = {(r["arm"], r["class"], r["pass"]): r for r in l5["counts"]}
    gp = g["paired"]["policy_v2_vs_naive_llm"]["classes"]
    gr = {(r["arm"], r["route"]): r for r in g["route_split"] if r["scope"] == "all"}
    gz = {r["arm"]: r for r in g["rows_returned_wrong_ungrounded"]}
    CU = "correct_ungrounded (subset of correct)"
    w.append("## What the data show (descriptive; the paired comparisons are secondary and uncorrected)\n")
    w.append(f"- **Gemini, ungrounded wrong answers (hallucination proxy):** {pct(gc[('policy_v2', 'wrong_ungrounded', 'all')]['rate'])} of policy_v2 rows against {pct(gc[('naive_llm', 'wrong_ungrounded', 'all')]['rate'])} of naive_llm rows over 5 passes (pass 1: {gc[('policy_v2', 'wrong_ungrounded', 1)]['n']}/50 against {gc[('naive_llm', 'wrong_ungrounded', 1)]['n']}/50; b = {gp['wrong_ungrounded']['pass1']['b_x_only']}, c = {gp['wrong_ungrounded']['pass1']['c_y_only']}, exact McNemar p = {gp['wrong_ungrounded']['pass1']['mcnemar_exact_p']:.3f}; pooled difference {100 * gp['wrong_ungrounded']['pooled']['diff_x_minus_y']:+.1f} pp, 95% CI [{100 * gp['wrong_ungrounded']['pooled']['ci95'][0]:+.1f}, {100 * gp['wrong_ungrounded']['pooled']['ci95'][1]:+.1f}]). Grounded wrong answers ({pct(gc[('policy_v2', 'wrong_grounded', 'all')]['rate'])} vs {pct(gc[('naive_llm', 'wrong_grounded', 'all')]['rate'])}) and abstain/parse-failure rows ({pct(gc[('policy_v2', 'abstain_or_parse_fail', 'all')]['rate'])} vs {pct(gc[('naive_llm', 'abstain_or_parse_fail', 'all')]['rate'])}) barely differ: the accuracy difference between these two arms sits almost entirely in the ungrounded class.")
    w.append(f"- **Where naive_llm's extra ungrounded answers come from:** its post-filter route returned few rows (mean {gr[('naive_llm', 'post-filter')]['mean_rows_returned']:.1f} against {gr[('naive_llm', 'pre-filter')]['mean_rows_returned']:.1f} on pre-filter) and had ungrounded wrong answers in {gr[('naive_llm', 'post-filter')]['wrong_ungrounded']}/{gr[('naive_llm', 'post-filter')]['n']} rows ({pct(gr[('naive_llm', 'post-filter')]['wrong_ungrounded'] / gr[('naive_llm', 'post-filter')]['n'])}) against {gr[('naive_llm', 'pre-filter')]['wrong_ungrounded']}/{gr[('naive_llm', 'pre-filter')]['n']} ({pct(gr[('naive_llm', 'pre-filter')]['wrong_ungrounded'] / gr[('naive_llm', 'pre-filter')]['n'])}) on pre-filter. Of its {gz['naive_llm']['n_wrong_ungrounded']} ungrounded wrong answers, **{gz['naive_llm']['zero_row_cases']} had 0 rows returned** (no evidence at all in the prompt, and a number was given), {gz['naive_llm']['rows_1-3']} had 1-3 rows, {gz['naive_llm']['rows_4-7']} 4-7, {gz['naive_llm']['rows_8-14']} 8-14 and {gz['naive_llm']['rows_15+']} the full 15. The ungrounded rows of every deterministic arm all had 15 rows: for them \"ungrounded\" means exact retrieval missed some gold evidence, not that routing failed.")
    w.append(f"- **The proxy is imprecise in both directions.** `correct_ungrounded` is {pct(gc[('policy_v2', CU, 'all')]['rate'])} of policy_v2 rows and {pct(gc[('naive_llm', CU, 'all')]['rate'])} of naive_llm rows: many correct answers were produced although not all gold evidence units were in the prompt (a partial set can suffice, or the number is derivable elsewhere). So `wrong_ungrounded` can contain answers that are derivable from other retrieved passages; this is why the manual sample (section 7) is needed before the word hallucination is used.")
    w.append(f"- **Strict page-id test (sensitivity, not used for conclusions).** With `retrieval_hit`, {gs[('naive_llm', CU, 'all')]['n']} of the {gc[('naive_llm', 'correct', 'all')]['n']} correct naive_llm answers (Gemini) would be labelled ungrounded, and `wrong_ungrounded` would rise from {gc[('naive_llm', 'wrong_ungrounded', 'all')]['n']} to {gs[('naive_llm', 'wrong_ungrounded', 'all')]['n']}. That is why the passage-level field is the grounding field.")
    w.append(f"- **Local qwen2.5:7b (v5) has a different profile:** the largest wrong class is wrong_grounded ({pct(lc[('policy_v2', 'wrong_grounded', 'all')]['rate'])} of policy_v2 rows, {pct(lc[('naive_llm', 'wrong_grounded', 'all')]['rate'])} of naive_llm rows) against ungrounded {pct(lc[('policy_v2', 'wrong_ungrounded', 'all')]['rate'])} and {pct(lc[('naive_llm', 'wrong_ungrounded', 'all')]['rate'])}; abstain/parse-failure {pct(lc[('policy_v2', 'abstain_or_parse_fail', 'all')]['rate'])} and {pct(lc[('naive_llm', 'abstain_or_parse_fail', 'all')]['rate'])}. Most local errors occur with the gold evidence in the prompt. The policy_v2 vs naive_llm differences in these classes are small; their pooled 95% CIs include 0 (wrong_ungrounded, wrong_grounded) or have 0 as the lower bound (abstain_or_parse_fail), table above.")
    w.append("- **12 Oct baseline:** classified with the strict field (only field available); its rows do not log `rows_returned`, so its row counts are shown as \"not logged\"; its ungrounded rates are not comparable with the other runs'.")
    w.append("- Models are never pooled; the five local/Gemini runs are separate analyses; v3, v4 and v5 share inputs (v4 pass 1 = v5 pass 1) and are not independent.\n")
    ls = S["gemini_full"]["label_sample"]
    w.append("## 7. Blind manual validation sample (not yet labelled)\n")
    w.append(f"Gemini full run, pass 1, all arms; seed {ls['seed']}; **{ls['n']} rows** ({ls['by_proxy_class'].get('wrong_ungrounded', 0)} `wrong_ungrounded`, {ls['by_proxy_class'].get('wrong_grounded', 0)} `wrong_grounded`; up to 20 of each, drawn at random and shuffled). `labelling_sheet.csv` has `sample_id`, `question`, `gold_answer`, `model_answer` (raw output) and the full text of every retrieved passage in prompt order; it does not contain the proxy class, the arm or the route. `labelling_key.csv` (separate) maps `sample_id` to query id, arm, pass and proxy class. Labels to be entered by the user: **S** = the answer number appears in the retrieved text; **C** = the answer can be calculated from numbers in the retrieved text; **N** = not supported by the retrieved text. The confusion table (proxy class vs human label, N = unsupported, S/C = supported) is **not** computed until the labels arrive.\n")
    Path(a.out).write_text("\n".join(w), encoding="utf-8")
    print(f"wrote {a.out} ({len(w)} blocks)")


if __name__ == "__main__":
    main()
