"""Amendment 4 analysis of the Gemini scale-up run (one pass). Pre-registered; written before the run.

  python -m src.phase_d_validation.scaleup_analysis outputs/phase_d_gemini_scaleup_<date>/results.jsonl \
      --subset outputs/scaleup_confirmation_2026-10-13/confirmation_1075.csv --out outputs/phase_d_gemini_scaleup_<date>/analysis.json

Primary: policy_v2 vs naive_llm, primary scoring, Newcombe paired 95% CI, non-inferior iff lower bound > -0.10; exact McNemar.
Secondary: non-inferiority at 0.05; superiority iff two-sided exact McNemar p < 0.05 and policy_v2 ahead; the same pair by
evidence breadth (single / dual / multi; natural mix, no re-weighting); latency and cost differences by paired bootstrap
(10,000 resamples, seed 20261012); post-filter shares of naive_llm and naive_informed; policy_v2 vs naive_informed;
decision_matrix vs policy_v2 as the noise reference; strict-rule results. Every question of the subset must have exactly one
completed row per arm (otherwise the analysis refuses).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from src.phase_d_validation.paired_stats import arm_summary, bootstrap_mean_diff, compare

ARMS = ("decision_matrix", "policy_v2", "naive_llm", "naive_informed")
PAIRS = [("policy_v2", "naive_llm"), ("policy_v2", "naive_informed"), ("decision_matrix", "policy_v2"), ("decision_matrix", "naive_llm")]
MARGIN, MARGIN_SECONDARY, ALPHA = 0.10, 0.05, 0.05


def analyse(rows: list[dict], subset: list[dict], rule: str = "primary") -> dict:
    qids = [r["id"] for r in subset]
    breadth = {r["id"]: r["breadth"] for r in subset}
    by = {}
    for r in rows:
        key = (r["arm"], r["query_id"])
        if key in by:
            raise ValueError(f"duplicate row {key}")
        by[key] = r
    for a in ARMS:
        missing = [q for q in qids if (a, q) not in by]
        if missing:
            raise ValueError(f"arm {a}: {len(missing)} questions without a completed row (e.g. {missing[:3]})")
    excluded = []
    if rule == "strict":
        excluded = sorted({q for q in qids if any(by[(a, q)].get("strict_gold_unparseable") for a in ARMS)})
        for (a, q), r in by.items():
            r["correct"], r["parse_failure"] = r["correct_strict"], r["parse_failure_strict"]
    use = [q for q in qids if q not in set(excluded)]
    arms = {a: {q: by[(a, q)] for q in use} for a in ARMS}
    res = {"rule": rule, "n_questions": len(use), "strict_excluded": excluded,
           "arms": {a: arm_summary(arms[a]) for a in ARMS}, "pairs": {}, "strata": {}}
    for x, y in PAIRS:
        c = compare(arms[x], arms[y])
        lo = c["accuracy_diff_ci95"][0]
        cd, clo, chi = bootstrap_mean_diff([arms[x][q]["cost_usd"] or 0 for q in use], [arms[y][q]["cost_usd"] or 0 for q in use])
        c.update({"non_inferior_0_10": bool(lo > -MARGIN), "non_inferior_0_05": bool(lo > -MARGIN_SECONDARY),
                  "superior_mcnemar_p_lt_0_05": bool(c["mcnemar_exact_p_two_sided"] < ALPHA and c["accuracy_diff_X_minus_Y"] > 0),
                  "cost_usd_mean_diff_X_minus_Y": cd, "cost_diff_ci95": [clo, chi],
                  "latency_superior": bool(c["latency_diff_ci95"][1] < 0)})
        res["pairs"][f"{x}_vs_{y}"] = c
    for s in ("single", "dual", "multi"):
        qs = [q for q in use if breadth[q] == s]
        if qs:
            c = compare({q: arms["policy_v2"][q] for q in qs}, {q: arms["naive_llm"][q] for q in qs})
            res["strata"][s] = {k: c[k] for k in ("n", "b_X_only_correct", "c_Y_only_correct", "mcnemar_exact_p_two_sided",
                                                  "accuracy_X", "accuracy_Y", "accuracy_diff_X_minus_Y", "accuracy_diff_ci95")}
    res["post_filter_share"] = {a: sum(1 for q in use if arms[a][q]["route"] == "post-filter") / len(use) for a in ("naive_llm", "naive_informed")}
    res["primary"] = {"pair": "policy_v2_vs_naive_llm", "margin": MARGIN, **{k: res["pairs"]["policy_v2_vs_naive_llm"][k] for k in (
        "b_X_only_correct", "c_Y_only_correct", "mcnemar_exact_p_two_sided", "accuracy_X", "accuracy_Y", "accuracy_diff_X_minus_Y",
        "accuracy_diff_ci95", "non_inferior_0_10")}}
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--subset", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = [json.loads(l) for l in Path(a.results).read_text(encoding="utf-8").splitlines() if l.strip()]
    subset = list(csv.DictReader(open(a.subset, encoding="utf-8")))
    res = {"results": a.results, "subset": a.subset, "primary_rule": analyse([dict(r) for r in rows], subset, "primary"),
           "strict_rule": analyse([dict(r) for r in rows], subset, "strict")}
    Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    p = res["primary_rule"]["primary"]
    print(json.dumps(p, indent=2))


if __name__ == "__main__":
    main()
