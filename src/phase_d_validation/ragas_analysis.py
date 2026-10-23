"""Amendment 8 analysis (offline, no call): stage 1 agreement with the labels, stage 2 per-arm rates and paired comparison.

  .venv/Scripts/python -m src.phase_d_validation.ragas_analysis --stage 1 --dir outputs/ragas_judge_2026-10-23
  .venv/Scripts/python -m src.phase_d_validation.ragas_analysis --stage 2 --dir outputs/ragas_judge_2026-10-23

Supported = faithfulness >= 0.5. Rows without context: primary score 0 (unsupported), sensitivity excluded. no_statements and
judge_error rows: excluded (counted), sensitivity counted as unsupported. Kappa CIs: percentile bootstrap, 10,000 resamples,
seed 20261023 (rows, or questions for the per-question table); resamples with undefined kappa are counted and dropped.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from src.phase_d_validation.paired_stats import wilson

SEED, B, THRESH, GATE = 20261023, 10_000, 0.5, 0.4


def kappa(pairs: list[tuple[int, int]]) -> float | None:
    """Cohen's kappa for binary (reference, judge) pairs; None if undefined (expected agreement 1)."""
    n = len(pairs)
    if not n:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if abs(1 - pe) < 1e-12 else (po - pe) / (1 - pe)


def boot(units: list, stat, seed: int = SEED, b: int = B) -> dict:
    rng = random.Random(seed)
    vals, undefined = [], 0
    for _ in range(b):
        v = stat([units[rng.randrange(len(units))] for _ in units])
        if v is None:
            undefined += 1
        else:
            vals.append(v)
    vals.sort()
    if not vals:
        return {"ci95": [None, None], "undefined_resamples": undefined}
    return {"ci95": [vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]], "undefined_resamples": undefined}


def flat(units):
    return [p for u in units for p in u]


def judged(r: dict, sensitivity: bool = False):
    """1 = supported, 0 = unsupported, None = excluded."""
    if r["status"] == "ok":
        return int(r["faithfulness"] >= THRESH)
    return 0 if sensitivity else None


def agreement(rows: list[dict], sensitivity: bool = False) -> dict:
    ok = [r for r in rows if judged(r, sensitivity) is not None]
    excl = Counter(r["status"] for r in rows if judged(r, sensitivity) is None)
    ref = lambda r: int(r["label_scn"] in ("S", "C"))
    pairs = [(ref(r), judged(r, sensitivity)) for r in ok]
    acc_k = sum(1 for a, b in pairs if a == b)
    lo, hi = wilson(acc_k, len(pairs))
    per_row = {"n": len(pairs), "excluded": dict(excl), "accuracy": acc_k / len(pairs), "accuracy_ci95": [max(0, lo), min(1, hi)],
               "kappa": kappa(pairs), **{f"kappa_{k}": v for k, v in boot([[p] for p in pairs], lambda u: kappa(flat(u))).items()},
               "confusion": {f"label_{'supported' if a else 'unsupported'}__judge_{'supported' if b else 'unsupported'}": sum(1 for x in pairs if x == (a, b)) for a in (1, 0) for b in (1, 0)},
               "class_balance": {"N": sum(1 for r in ok if r["label_scn"] == "N"), "S_or_C": sum(1 for r in ok if r["label_scn"] != "N")},
               "by_scn": {s: {"rows": sum(1 for r in ok if r["label_scn"] == s), "judge_unsupported": sum(1 for r in ok if r["label_scn"] == s and judged(r, sensitivity) == 0),
                              "judge_supported": sum(1 for r in ok if r["label_scn"] == s and judged(r, sensitivity) == 1)} for s in ("S", "C", "N")}}
    byq = defaultdict(list)
    for r in ok:
        byq[r["query_id"]].append(r)
    qpairs = []
    for q, rs in sorted(byq.items()):
        labs = {ref(r) for r in rs}
        if len(labs) != 1:
            raise SystemExit(f"labels differ within question {q}")
        scores = [r["faithfulness"] if r["status"] == "ok" else 0.0 for r in rs]
        qpairs.append((labs.pop(), int(statistics.fmean(scores) >= THRESH)))
    qa = sum(1 for a, b in qpairs if a == b)
    qlo, qhi = wilson(qa, len(qpairs))
    per_q = {"n": len(qpairs), "accuracy": qa / len(qpairs), "accuracy_ci95": [max(0, qlo), min(1, qhi)], "kappa": kappa(qpairs),
             **{f"kappa_{k}": v for k, v in boot([[p] for p in qpairs], lambda u: kappa(flat(u))).items()},
             "class_balance": {"unsupported": sum(1 for a, _ in qpairs if a == 0), "supported": sum(1 for a, _ in qpairs if a == 1)},
             "confusion": {f"label_{'supported' if a else 'unsupported'}__judge_{'supported' if b else 'unsupported'}": sum(1 for x in qpairs if x == (a, b)) for a in (1, 0) for b in (1, 0)}}
    return {"per_row": per_row, "per_question": per_q}


def no_context_rows(inputs: list[dict]) -> list[dict]:
    return [{"row": f"{r['pass']}|{r['arm']}|{r['query_id']}", "pass": r["pass"], "arm": r["arm"], "query_id": r["query_id"],
             "sample_id": r["sample_id"], "label_scn": r["label_scn"], "status": "no_context", "faithfulness": 0.0} for r in inputs if not r["retrieved_contexts"]]


def value(r: dict, no_ctx: str, other: str):
    if r["status"] == "no_context":
        return None if no_ctx == "exclude" else 0
    if r["status"] == "ok":
        return int(r["faithfulness"] >= THRESH)
    return None if other == "exclude" else 0


def stage2(all_rows: list[dict], drop_labelled: bool, no_ctx: str = "zero", other: str = "exclude") -> dict:
    rows = [r for r in all_rows if not (drop_labelled and r["sample_id"])]
    arms = {}
    for arm in ("policy_v2", "naive_llm", "decision_matrix", "naive_informed"):
        for scope, sub in (("pooled", [r for r in rows if r["arm"] == arm]), ("pass1", [r for r in rows if r["arm"] == arm and r["pass"] == 1])):
            v = [value(r, no_ctx, other) for r in sub]
            vv = [x for x in v if x is not None]
            sc = [r["faithfulness"] for r in sub if r["status"] in ("ok", "no_context") and value(r, no_ctx, other) is not None]
            lo, hi = wilson(sum(vv), len(vv)) if vv else (None, None)
            arms.setdefault(arm, {})[scope] = {"n": len(vv), "excluded": len(v) - len(vv), "supported": sum(vv),
                                               "share_supported": sum(vv) / len(vv) if vv else None, "ci95": [lo, hi],
                                               "mean_faithfulness": statistics.fmean(sc) if sc else None}
    by = {(r["pass"], r["arm"], r["query_id"]): r for r in all_rows}
    paired = {}
    for scope, passes in (("pooled", range(1, 6)), ("pass1", [1])):
        pairs = defaultdict(list)
        dropped = 0
        for p in passes:
            for q in sorted({r["query_id"] for r in all_rows}):
                a, b = by[(p, "policy_v2", q)], by[(p, "naive_llm", q)]
                if drop_labelled and (a["sample_id"] or b["sample_id"]):
                    dropped += 1
                    continue
                va, vb = value(a, no_ctx, other), value(b, no_ctx, other)
                if va is None or vb is None:
                    dropped += 1
                    continue
                pairs[q].append((va, vb))
        units = list(pairs.values())
        diff = lambda u: (sum(a - b for a, b in flat(u)) / len(flat(u))) if flat(u) else None
        allp = flat(units)
        paired[scope] = {"pairs": len(allp), "dropped_pairs": dropped, "diff_share_supported_policy_v2_minus_naive_llm": diff(units),
                         **{f"diff_{k}": v for k, v in boot(units, diff).items()},
                         "discordant_v2_supported_naive_not": sum(1 for a, b in allp if a == 1 and b == 0),
                         "discordant_naive_supported_v2_not": sum(1 for a, b in allp if a == 0 and b == 1)}
    return {"per_arm": arms, "paired_policy_v2_vs_naive_llm": paired}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", type=int, choices=[1, 2], required=True)
    ap.add_argument("--dir", required=True)
    a = ap.parse_args()
    d = Path(a.dir)
    s1 = [json.loads(l) for l in open(d / "judged_stage1.jsonl", encoding="utf-8")]
    if a.stage == 1:
        res = {"primary": agreement(s1), "sensitivity_errors_as_unsupported": agreement(s1, sensitivity=True)}
        res["gate"] = {"rule": f"per-row kappa point estimate >= {GATE}", "kappa": res["primary"]["per_row"]["kappa"],
                       "stage2_runs": res["primary"]["per_row"]["kappa"] is not None and res["primary"]["per_row"]["kappa"] >= GATE}
        (d / "stage1_agreement.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    else:
        inputs = [json.loads(l) for l in open(d / "judge_inputs.jsonl", encoding="utf-8")]
        s2 = [json.loads(l) for l in open(d / "judged_stage2.jsonl", encoding="utf-8")]
        rows = s1 + s2 + no_context_rows(inputs)
        if len(rows) != 1000 or len({r["row"] for r in rows}) != 1000:
            raise SystemExit(f"stage 2 has {len(rows)} rows ({len({r['row'] for r in rows})} distinct), expected 1,000")
        res = {"status_counts": dict(Counter(r["status"] for r in rows)),
               "with_labelled_40": stage2(rows, False), "without_labelled_40": stage2(rows, True),
               "sensitivity_no_context_excluded": {"with_labelled_40": stage2(rows, False, no_ctx="exclude")},
               "sensitivity_errors_as_unsupported": {"with_labelled_40": stage2(rows, False, other="zero")}}
        (d / "stage2_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=1)[:6000])


if __name__ == "__main__":
    main()
