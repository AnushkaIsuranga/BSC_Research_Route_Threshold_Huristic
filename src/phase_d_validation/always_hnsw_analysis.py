"""Phase D Amendment 10 analysis: always_hnsw vs stored policy_v2 / naive_llm (frozen Gemini run), drift reference,
Amendment 5 proxy classes. Reads only; writes summary.json and classes.csv into the run folder's analysis/ subfolder.

  python -m src.phase_d_validation.always_hnsw_analysis
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from pathlib import Path

from src.phase_d_validation import paired_stats as PS
from src.phase_d_validation.hallucination_classify import CLASSES, classify_run

NEW = Path("outputs/phase_d_always_hnsw_2026-10-31")
STORED = Path("outputs/phase_d_gemini_full_2026-10-12/results.jsonl")
OUT = NEW / "analysis"
DRIFT_MAX_DISAGREE = 5
HIT = "retrieval_hit_passage"


def pass1_compare(x: dict, y: dict, key="correct") -> dict:
    ids = sorted(x)
    if set(x) != set(y):
        raise ValueError("arms do not cover the same questions")
    ids = [i for i in ids if x[i][key] is not None and y[i][key] is not None]
    a, b_ = [x[i][key] for i in ids], [y[i][key] for i in ids]
    n11 = sum(1 for p, q in zip(a, b_) if p and q)
    b = sum(1 for p, q in zip(a, b_) if p and not q)
    c = sum(1 for p, q in zip(a, b_) if q and not p)
    d, lo, hi = PS.newcombe_paired_diff(n11, b, c, len(ids) - n11 - b - c)
    return {"n": len(ids), "acc_X": (n11 + b) / len(ids), "acc_Y": (n11 + c) / len(ids), "b_X_only": b, "c_Y_only": c,
            "mcnemar_exact_p": PS.mcnemar_exact(b, c), "diff": d, "ci95": [lo, hi]}


def arm_stats(rows):
    cl = classify_run(rows, HIT)
    n = len(rows)
    rr = [r["rows_returned"] for r in rows]
    return {"n_rows": n, "accuracy": sum(r["correct"] for r in rows) / n,
            "accuracy_strict": (lambda v: sum(v) / len(v) if v else None)([r["correct_strict"] for r in rows if r.get("correct_strict") is not None]),
            "rows_returned": {"mean": statistics.fmean(rr), "median": statistics.median(rr), "min": min(rr), "max": max(rr),
                              "lt15": sum(1 for x in rr if x < 15), "eq0": sum(1 for x in rr if x == 0),
                              "hist": dict(sorted(Counter(rr).items()))},
            "gold_passage_hit_rate": sum(r[HIT] for r in rows) / n,
            "classes": {c: sum(1 for x in cl if x["class"] == c) for c in CLASSES},
            "correct_ungrounded": sum(x["correct_ungrounded"] for x in cl),
            "total_ms_median": statistics.median(r["total_ms"] for r in rows),
            "db_ms_median": statistics.median(r["db_ms"] for r in rows),
            "generation_ms_median": statistics.median(r["generation_ms"] for r in rows),
            "cost_usd": sum(r["cost_usd"] for r in rows)}, cl


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    new = PS.load(NEW / "results.jsonl")
    stored = PS.load(STORED)
    ah = [r for r in new if r["arm"] == "always_hnsw"]
    drift = [r for r in new if r["arm"] == "policy_v2"]
    if len(ah) != 250 or len(drift) != 50:
        raise SystemExit(f"incomplete run: always_hnsw {len(ah)}/250, policy_v2 {len(drift)}/50")
    sv2 = [r for r in stored if r["arm"] == "policy_v2"]
    snl = [r for r in stored if r["arm"] == "naive_llm"]

    by = lambda rows, p: {r["query_id"]: r for r in rows if r["pass"] == p}
    d1, s1 = by(drift, 1), by(sv2, 1)
    drift_cmp = {"same_correct": sum(d1[q]["correct"] == s1[q]["correct"] for q in d1),
                 "same_raw_answer": sum((d1[q]["raw_output"] or "").strip() == (s1[q]["raw_output"] or "").strip() for q in d1),
                 "same_parsed_answer": sum(PS.norm_answer(d1[q]) == PS.norm_answer(s1[q]) for q in d1),
                 "same_retrieved_ids": sum(d1[q]["retrieved_ids"] == s1[q]["retrieved_ids"] for q in d1),
                 "correct_new": sum(r["correct"] for r in drift), "correct_stored_pass1": sum(r["correct"] for r in sv2 if r["pass"] == 1),
                 "n": len(d1)}
    drift_cmp["disagree_correct"] = drift_cmp["n"] - drift_cmp["same_correct"]
    switched = drift_cmp["disagree_correct"] > DRIFT_MAX_DISAGREE
    ref_name = "drift_reference_policy_v2" if switched else "stored_policy_v2"
    ref_p1 = d1 if switched else s1

    a1 = by(ah, 1)
    comparisons = {
        f"always_hnsw_vs_{ref_name}_pass1": pass1_compare(a1, ref_p1),
        f"always_hnsw_vs_{ref_name}_pass1_strict": pass1_compare(a1, ref_p1, "correct_strict"),
        "always_hnsw_vs_stored_naive_llm_pass1": pass1_compare(a1, by(snl, 1)),
        "always_hnsw_vs_stored_naive_llm_pass1_strict": pass1_compare(a1, by(snl, 1), "correct_strict"),
        "always_hnsw_vs_stored_naive_llm_pooled": PS.pooled_compare(ah + snl, "always_hnsw", "naive_llm", [1, 2, 3, 4, 5]),
    }
    if not switched:
        comparisons["always_hnsw_vs_stored_policy_v2_pooled"] = PS.pooled_compare(ah + sv2, "always_hnsw", "policy_v2", [1, 2, 3, 4, 5])

    stats, all_cl = {}, []
    for name, rows in (("always_hnsw", ah), ("policy_v2_drift_reference", drift), ("policy_v2_stored", sv2), ("naive_llm_stored", snl)):
        s, cl = arm_stats(rows)
        s["pass1_accuracy"] = statistics.fmean(r["correct"] for r in rows if r["pass"] == 1)
        stats[name] = s
        all_cl += [{**x, "arm": name} for x in cl]
    stats["naive_llm_stored"]["routes"] = dict(Counter(r["route"] for r in snl))

    zero = sorted({r["query_id"] for r in ah if r["rows_returned"] == 0})
    zero_rows = [{"query_id": r["query_id"], "pass": r["pass"], "gold": r["gold_answer"], "answer": (r["raw_output"] or "").strip(),
                  "correct": r["correct"]} for r in sorted(ah, key=lambda r: (r["query_id"], r["pass"])) if r["rows_returned"] == 0]
    per_q_rows = {q: statistics.median(r["rows_returned"] for r in ah if r["query_id"] == q) for q in a1}
    summary = {"drift": {**drift_cmp, "switch_rule": f"> {DRIFT_MAX_DISAGREE} of 50 correctness labels differ",
                         "switched_to_drift_reference": switched, "reference_for_policy_v2": ref_name},
               "arms": stats, "comparisons": comparisons,
               "zero_row_questions": zero, "zero_row_answers": zero_rows,
               "questions_with_median_rows_lt15": sum(1 for v in per_q_rows.values() if v < 15),
               "always_hnsw_runs_consistency": PS.multi_pass_agreement(ah)["always_hnsw"],
               "cost_usd_total_run": sum(r["cost_usd"] for r in new)}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    with open(OUT / "classes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_cl[0]))
        w.writeheader()
        w.writerows(all_cl)
    print(json.dumps({k: v for k, v in summary.items() if k != "zero_row_answers"}, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
