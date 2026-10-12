"""Paired statistics for the Phase D arm comparison (item 16).

Per pair of arms on the same queries (one chosen pass):
  * exact McNemar test (two-sided exact binomial on the discordant pairs; b = X correct & Y wrong,
    c = X wrong & Y correct; reports b, c and p)
  * 95% CI on the accuracy difference (X - Y): Newcombe's hybrid-score method 10 for paired
    proportions (Newcombe 1998, Stat Med 17:2635), built from Wilson score intervals
  * 95% CI on the latency difference (mean of per-query total_ms, X - Y): paired bootstrap over
    queries, percentile interval, fixed seed, BOOTSTRAP_RESAMPLES resamples
Also: --agreement compares two passes (same answer / same route per query and arm).

  python -m src.phase_d_validation.paired_stats outputs/<run>/results.jsonl --pass 1 --margin <M> --out outputs/<run>/stats_pass1.json

--margin is REQUIRED (the non-inferiority margin of Amendment 1; no default). Non-inferiority of X vs Y holds iff the lower
bound of the 95% CI of accuracy(X) - accuracy(Y) is above -MARGIN. Primary pair: policy_v2 vs naive_llm; decision_matrix vs
naive_llm is reported alongside. Superiority on latency: the paired-bootstrap CI of (X - Y) total_ms lies entirely below 0.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

TRUNCATED = {"MAX_TOKENS", "length", "max_tokens"}
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_SEED = 20261012
PAIRS = [("decision_matrix", "naive_llm"), ("policy_v2", "naive_llm"), ("decision_matrix", "policy_v2")]


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def mcnemar_exact(b: int, c: int) -> float:
    return 1.0 if b + c == 0 else float(binomtest(min(b, c), b + c, 0.5, alternative="two-sided").pvalue)


def newcombe_paired_diff(n11: int, b: int, c: int, n00: int) -> tuple[float, float, float]:
    n = n11 + b + c + n00
    px, py = (n11 + b) / n, (n11 + c) / n
    l1, u1 = wilson(n11 + b, n)
    l2, u2 = wilson(n11 + c, n)
    den = (n11 + b) * (c + n00) * (n11 + c) * (b + n00)
    phi = 0.0 if den == 0 else (n11 * n00 - b * c) / math.sqrt(den)
    lo = (px - py) - math.sqrt(max(0.0, (px - l1) ** 2 + (u2 - py) ** 2 - 2 * phi * (px - l1) * (u2 - py)))
    hi = (px - py) + math.sqrt(max(0.0, (u1 - px) ** 2 + (py - l2) ** 2 - 2 * phi * (u1 - px) * (py - l2)))
    return px - py, lo, hi


def bootstrap_mean_diff(x: list[float], y: list[float], resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED):
    d = np.asarray(x, float) - np.asarray(y, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(resamples, len(d)))
    means = d[idx].mean(axis=1)
    return float(d.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def by_arm(rows: list[dict], pass_no: int) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        if r["pass"] == pass_no:
            out.setdefault(r["arm"], {})[r["query_id"]] = r
    return out


def compare(a: dict[str, dict], b_: dict[str, dict]) -> dict:
    ids = sorted(set(a) & set(b_))
    if set(a) != set(b_):
        raise ValueError("arms do not cover the same queries")
    x = [a[i]["correct"] for i in ids]
    y = [b_[i]["correct"] for i in ids]
    n11 = sum(1 for p, q in zip(x, y) if p and q)
    b = sum(1 for p, q in zip(x, y) if p and not q)
    c = sum(1 for p, q in zip(x, y) if q and not p)
    n00 = len(ids) - n11 - b - c
    diff, lo, hi = newcombe_paired_diff(n11, b, c, n00)
    ld, llo, lhi = bootstrap_mean_diff([a[i]["total_ms"] for i in ids], [b_[i]["total_ms"] for i in ids])
    return {"n": len(ids), "both_correct": n11, "b_X_only_correct": b, "c_Y_only_correct": c, "both_wrong": n00,
            "mcnemar_exact_p_two_sided": mcnemar_exact(b, c),
            "accuracy_X": (n11 + b) / len(ids), "accuracy_Y": (n11 + c) / len(ids),
            "accuracy_diff_X_minus_Y": diff, "accuracy_diff_ci95": [lo, hi],
            "accuracy_diff_ci_method": "Newcombe hybrid-score (method 10) for paired proportions, Wilson-based",
            "latency_total_ms_mean_diff_X_minus_Y": ld, "latency_diff_ci95": [llo, lhi],
            "latency_ci_method": f"paired bootstrap over queries, percentile, {BOOTSTRAP_RESAMPLES} resamples, seed {BOOTSTRAP_SEED}"}


def arm_summary(arm_rows: dict[str, dict]) -> dict:
    rs = list(arm_rows.values())

    def q(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        s = sorted(vals)
        qs = statistics.quantiles(s, n=4, method="inclusive") if len(s) > 1 else [s[0]] * 3
        return {"median": statistics.median(s), "q1": qs[0], "q3": qs[2], "iqr": qs[2] - qs[0]}
    n = len(rs)
    hits = [r["retrieval_hit"] for r in rs if r["retrieval_hit"] is not None]
    return {"n": n, "accuracy": sum(r["correct"] for r in rs) / n, "correct": sum(r["correct"] for r in rs),
            "retrieval_hit_rate": (sum(hits) / len(hits)) if hits else None, "retrieval_hit_n": len(hits),
            "retrieval_hit_passage_rate": (lambda h: (sum(h) / len(h)) if h else None)([r["retrieval_hit_passage"] for r in rs if r.get("retrieval_hit_passage") is not None]),
            "rows_returned_by_route": {k: statistics.fmean([r["rows_returned"] for r in rs if str(r["route"]) == k and r.get("rows_returned") is not None])
                                       for k in sorted({str(r["route"]) for r in rs if r.get("rows_returned") is not None})},
            "cost_per_query_usd": sum(r["cost_usd"] or 0 for r in rs) / n,
            "truncations": sum(1 for r in rs for f in (r.get("gen_finish_reason"), r.get("router_finish_reason")) if f in TRUNCATED),
            "finish_reasons": dict(collections.Counter(str(f) for r in rs for f in (r.get("gen_finish_reason"), r.get("router_finish_reason")) if f)),
            "traffic_types": dict(collections.Counter(str(x) for r in rs for x in (r.get("traffic_types") or []))),
            "mean_thinking_tokens_per_call": (lambda v: statistics.fmean(v) if v else None)([x for r in rs for x in (r.get("thinking_tokens"), r.get("router_thinking_tokens")) if x is not None]),
            "parse_failures": sum(r["parse_failure"] for r in rs), "route_parse_failures": sum(r["route_parse_failure"] for r in rs),
            "routes": {k: sum(1 for r in rs if r["route"] == k) for k in sorted({str(r["route"]) for r in rs})},
            "latency_ms": {k: q([r[k] for r in rs]) for k in ("embed_ms", "db_ms", "router_ms", "generation_ms", "total_ms")},
            "tokens_mean": {k: (statistics.fmean([r[k] for r in rs if r[k] is not None]) if any(r[k] is not None for r in rs) else None)
                            for k in ("input_tokens", "output_tokens", "thinking_tokens", "router_input_tokens", "router_output_tokens")},
            "cost_usd_total": sum(r["cost_usd"] or 0 for r in rs)}


def norm_answer(r: dict) -> str:
    return str(r["parsed_answer"]) if r["parsed_answer"] is not None else f"RAW:{(r['raw_output'] or '').strip()}"


def agreement(rows: list[dict]) -> dict:
    p1, p2 = by_arm(rows, 1), by_arm(rows, 2)
    out = {}
    for arm in p1:
        ids = sorted(set(p1[arm]) & set(p2.get(arm, {})))
        out[arm] = {"n": len(ids),
                    "same_answer": sum(norm_answer(p1[arm][i]) == norm_answer(p2[arm][i]) for i in ids),
                    "same_route": sum(p1[arm][i]["route"] == p2[arm][i]["route"] for i in ids),
                    "same_correctness": sum(p1[arm][i]["correct"] == p2[arm][i]["correct"] for i in ids)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--pass", dest="pass_no", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--agreement", action="store_true")
    ap.add_argument("--margin", type=float, required=True, help="non-inferiority margin on the accuracy difference (e.g. 0.10); required")
    a = ap.parse_args()
    rows = load(Path(a.results))
    arms = by_arm(rows, a.pass_no)
    res = {"results_file": a.results, "pass": a.pass_no, "arms": {k: arm_summary(v) for k, v in arms.items()}, "pairs": {}}
    for x, y in PAIRS:
        if x in arms and y in arms:
            res["pairs"][f"{x}_vs_{y}"] = compare(arms[x], arms[y])
    if not 0 < a.margin < 1:
        raise SystemExit("--margin must be in (0, 1)")
    res["non_inferiority"] = {"margin": a.margin, "rule": "lower bound of the 95% CI of accuracy(X) - accuracy(Y) > -margin"}
    for k, v in res["pairs"].items():
        if k.endswith("_vs_naive_llm"):
            lo = v["accuracy_diff_ci95"][0]
            res["non_inferiority"][k] = {"ci_lower": lo, "non_inferior": bool(lo > -a.margin),
                                         "latency_superior": bool(v["latency_diff_ci95"][1] < 0), "primary": k.startswith("policy_v2")}
    if "decision_matrix" in arms and "policy_v2" in arms:
        ids = sorted(arms["decision_matrix"])
        dmap = {"pre-filter": "exact", "post-filter": "post-filter", "iterative-scan": "iterative-relaxed"}
        res["dm_vs_v2_route_identical"] = sum(dmap.get(arms["decision_matrix"][i]["route"]) == arms["policy_v2"][i]["route"] for i in ids)
        res["dm_vs_v2_route_n"] = len(ids)
    if a.agreement:
        res["pass_agreement"] = agreement(rows)
    Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
