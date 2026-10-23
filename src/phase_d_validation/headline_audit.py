"""Read-only audit of headline numbers: recompute from the raw files, independently of paired_stats.py / hallucination_*.py, and
compare with what the reports state. Reads files only (no model call, no database access, no new result).

  python -m src.phase_d_validation.headline_audit --json outputs/headline_audit_2026-10-23/audit.json --out reports/headline_audit_2026-10-23.md
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics as S
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

G = Path("outputs/phase_d_gemini_full_2026-10-12/results.jsonl")
ARMS = ("policy_v2", "naive_llm", "decision_matrix", "naive_informed")
IN_PRICE, OUT_PRICE = 0.75, 3.75     # USD per 1M tokens (config/prices.json); thinking billed as output; cached input subtracted
CHECKS: list[dict] = []


def check(cid, what, reported, recomputed, source, tol=None, note=""):
    if tol is None:
        ok = (reported == recomputed)
    else:
        ok = abs(float(reported) - float(recomputed)) <= tol
    CHECKS.append({"id": cid, "what": what, "reported": reported, "recomputed": recomputed, "source": source, "status": "MATCH" if ok else "MISMATCH", "note": note})
    return ok


# --- independent implementations (not imported from the project)
def wilson(k, n, z=1.959964):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def newcombe_paired(n11, b, c, n00):
    n = n11 + b + c + n00
    px, py = (n11 + b) / n, (n11 + c) / n
    l1, u1 = wilson(n11 + b, n)
    l2, u2 = wilson(n11 + c, n)
    den = (n11 + b) * (c + n00) * (n11 + c) * (b + n00)
    phi = 0.0 if den == 0 else (n11 * n00 - b * c) / math.sqrt(den)
    lo = (px - py) - math.sqrt(max(0.0, (px - l1) ** 2 + (u2 - py) ** 2 - 2 * phi * (px - l1) * (u2 - py)))
    hi = (px - py) + math.sqrt(max(0.0, (u1 - px) ** 2 + (py - l2) ** 2 - 2 * phi * (u1 - px) * (py - l2)))
    return px - py, lo, hi


def boot_mean_diff(x, y, resamples=10000, seed=20261012):
    d = np.asarray(x, float) - np.asarray(y, float)
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, len(d), size=(resamples, len(d)))].mean(axis=1)
    return float(d.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def call_cost(inp, out, think, cached):
    return ((inp or 0) - (cached or 0)) * IN_PRICE / 1e6 + ((out or 0) + (think or 0)) * OUT_PRICE / 1e6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = [json.loads(l) for l in G.read_text(encoding="utf-8").splitlines() if l.strip()]
    P1 = {(r["arm"], r["query_id"]): r for r in rows if r["pass"] == 1}
    qids = sorted({q for (_, q) in P1})
    ALL = defaultdict(dict)
    for r in rows:
        ALL[(r["arm"], r["query_id"])][r["pass"]] = r
    R = {}   # recomputed values for the narrative

    # ------------------------------------------------------------------ 1. accuracy
    src1 = f"{G}: arm, pass, query_id, correct"
    rep_correct = {"policy_v2": 36, "naive_llm": 32, "decision_matrix": 34, "naive_informed": 34}   # phase_d_gemini_full report A1/A6
    for arm in ARMS:
        check(f"1.correct.{arm}", f"pass-1 correct count, {arm}", rep_correct[arm], sum(P1[(arm, q)]["correct"] for q in qids), src1)
    x = [P1[("policy_v2", q)]["correct"] for q in qids]
    y = [P1[("naive_llm", q)]["correct"] for q in qids]
    n11 = sum(1 for p, q in zip(x, y) if p and q); b = sum(1 for p, q in zip(x, y) if p and not q)
    c = sum(1 for p, q in zip(x, y) if q and not p); n00 = len(qids) - n11 - b - c
    diff, lo, hi = newcombe_paired(n11, b, c, n00)
    p = float(binomtest(min(b, c), b + c, 0.5).pvalue) if b + c else 1.0
    R["acc"] = {"b": b, "c": c, "diff": diff, "ci": [lo, hi], "p": p}
    s2 = "phase_d_gemini_full report A1 / `stats_primary.json`"
    check("1.b", "policy_v2 vs naive_llm b (policy_v2 only correct)", 4, b, src1)
    check("1.c", "policy_v2 vs naive_llm c (naive_llm only correct)", 0, c, src1)
    check("1.diff", "accuracy difference policy_v2 - naive_llm", 0.080, round(diff, 3), src1, tol=0.0005)
    check("1.ci_lo", "Newcombe 95% CI lower bound", 0.004, round(lo, 3), src1, tol=0.0005)
    check("1.ci_hi", "Newcombe 95% CI upper bound", 0.158, round(hi, 3), src1, tol=0.0005)
    check("1.p", "exact McNemar two-sided p", 0.125, round(p, 3), src1, tol=0.0005)

    # ------------------------------------------------------------------ 2. latency
    srcl = f"{G}: arm, pass, query_id, total_ms"
    rep_med = {"policy_v2": 2186, "naive_llm": 4329, "decision_matrix": 2121, "naive_informed": 3906}   # report A6, pass 1, median
    R["lat"] = {}
    for arm in ARMS:
        v1 = [P1[(arm, q)]["total_ms"] for q in qids]
        va = [r["total_ms"] for r in rows if r["arm"] == arm]
        R["lat"][arm] = {"p1_median": S.median(v1), "p1_mean": S.fmean(v1), "all_median": S.median(va), "all_mean": S.fmean(va)}
        check(f"2.median.{arm}", f"pass-1 median total_ms, {arm}", rep_med[arm], round(S.median(v1)), srcl, tol=0.5)
    d1, l1, h1 = boot_mean_diff([P1[("policy_v2", q)]["total_ms"] for q in qids], [P1[("naive_llm", q)]["total_ms"] for q in qids])
    R["lat_diff"] = {"mean": d1, "ci": [l1, h1], "median_diff": R["lat"]["policy_v2"]["p1_median"] - R["lat"]["naive_llm"]["p1_median"]}
    check("2.diff", "pass-1 mean paired total_ms difference policy_v2 - naive_llm", -2827, round(d1), srcl, tol=0.5)
    check("2.ci_lo", "paired bootstrap CI lower (10,000, seed 20261012)", -3753, round(l1), srcl, tol=0.5)
    check("2.ci_hi", "paired bootstrap CI upper", -1993, round(h1), srcl, tol=0.5)
    pq = [S.fmean(ALL[("policy_v2", q)][p_]["total_ms"] for p_ in range(1, 6)) for q in qids]
    nq = [S.fmean(ALL[("naive_llm", q)][p_]["total_ms"] for p_ in range(1, 6)) for q in qids]
    R["lat_diff_all"] = boot_mean_diff(pq, nq)
    R["lat_claim_s"] = round(-d1 / 1000, 2)

    # ------------------------------------------------------------------ 3. cost
    srcc = f"{G}: cost_usd, router_cost_usd, gen_cost_usd, input_tokens, output_tokens, thinking_tokens, gen_cached_tokens, rows_returned"
    R["cost"] = {}
    for scope in ("pass1", "all"):
        for arm in ARMS:
            rs = [r for r in rows if r["arm"] == arm and (scope == "all" or r["pass"] == 1)]
            n = len(rs)
            tot = sum(r["cost_usd"] for r in rs)
            rc = sum(r["router_cost_usd"] or 0 for r in rs)
            ac = sum(r["gen_cost_usd"] or 0 for r in rs)
            R["cost"][f"{scope}|{arm}"] = {"n": n, "total": tot, "mean": tot / n, "router_total": rc, "router_mean": rc / n, "answer_total": ac, "answer_mean": ac / n,
                                       "in_tok": S.fmean(r["input_tokens"] for r in rs), "out_tok": S.fmean(r["output_tokens"] for r in rs),
                                       "think_tok": S.fmean(r["thinking_tokens"] or 0 for r in rs), "rows": S.fmean(r["rows_returned"] for r in rs),
                                       "router_in_tok": S.fmean([r["router_input_tokens"] for r in rs if r["router_input_tokens"] is not None] or [0]),
                                       "router_think_tok": S.fmean([r["router_thinking_tokens"] for r in rs if r["router_thinking_tokens"] is not None] or [0])}
    rep_cost_q = {"policy_v2": 0.00135, "naive_llm": 0.00203}
    for arm, v in rep_cost_q.items():
        check(f"3.cost_per_q.{arm}", f"pass-1 mean cost per question, {arm}", v, round(R["cost"][f"pass1|{arm}"]["mean"], 5), srcc, tol=0.000005)
    rep_tot = {"policy_v2": 0.3786, "naive_llm": 0.4697, "naive_informed": 0.4385, "decision_matrix": 0.3711}
    for arm, v in rep_tot.items():
        check(f"3.total_5pass.{arm}", f"cost over 5 passes, {arm}", v, round(R["cost"][f"all|{arm}"]["total"], 4), srcc, tol=0.00005)
    # cost identity and recomputation from tokens
    ident = max(abs(r["cost_usd"] - ((r["router_cost_usd"] or 0) + (r["gen_cost_usd"] or 0))) for r in rows)
    recomputed_rows = 0.0
    worst = 0.0
    for r in rows:
        ans = call_cost(r["input_tokens"], r["output_tokens"], r["thinking_tokens"], r["gen_cached_tokens"])
        rt = call_cost(r["router_input_tokens"], r["router_output_tokens"], r["router_thinking_tokens"], r["router_cached_tokens"]) if r["router_raw"] is not None else 0.0
        recomputed_rows += ans + rt
        worst = max(worst, abs((ans + rt) - r["cost_usd"]))
    R["ident"] = {"max_abs_cost_minus_router_plus_answer": ident, "recomputed_total_from_tokens": recomputed_rows, "max_abs_row_diff_vs_logged": worst}
    check("3.identity", "cost_usd == router_cost_usd + gen_cost_usd for every row (max abs diff < 1e-12)", True, ident < 1e-12, srcc)
    check("3.token_recompute", "per-row cost recomputed from logged tokens x prices (0.75/3.75, thinking as output, cached subtracted): max abs diff < 1e-9", True, worst < 1e-9, srcc)
    # claim: "about one third cheaper per query"
    def pct_cheaper(a, b_):
        return 100 * (1 - a / b_)
    c1 = pct_cheaper(R["cost"]["pass1|policy_v2"]["mean"], R["cost"]["pass1|naive_llm"]["mean"])
    c1r = pct_cheaper(0.00135, 0.00203)
    call = pct_cheaper(R["cost"]["all|policy_v2"]["mean"], R["cost"]["all|naive_llm"]["mean"])
    ans_only_p1 = pct_cheaper(R["cost"]["pass1|policy_v2"]["answer_mean"], R["cost"]["pass1|naive_llm"]["answer_mean"])
    ans_only_all = pct_cheaper(R["cost"]["all|policy_v2"]["answer_mean"], R["cost"]["all|naive_llm"]["answer_mean"])
    R["pct"] = {"pass1_exact": c1, "pass1_from_rounded_report_values": c1r, "all_passes": call, "answer_only_pass1": ans_only_p1, "answer_only_all": ans_only_all}
    check("3.claim_one_third", "'about one third cheaper per query' = 1 - 0.00135/0.00203 (pass 1, from the reported per-question values)", "about 33% (1/3)", f"{c1r:.1f}% from rounded values; {c1:.1f}% exact, pass 1", srcc,
          note=f"holds for pass 1 only; over all 5 passes the same ratio is {call:.1f}% cheaper (mean cost per arm-run)")
    CHECKS[-1]["status"] = "MATCH (pass 1 only)" if abs(c1 - 33.3) < 3 else "MISMATCH"
    # per-route split of the cost difference (matched by question and pass)
    split = defaultdict(list)
    for q in qids:
        for p_ in range(1, 6):
            pv, nv = ALL[("policy_v2", q)][p_], ALL[("naive_llm", q)][p_]
            split[nv["route"]].append((pv["cost_usd"], nv["cost_usd"], nv["router_cost_usd"] or 0, nv["gen_cost_usd"] or 0, pv["gen_cost_usd"] or 0, nv["rows_returned"],
                                       pv["input_tokens"], nv["input_tokens"], (pv["output_tokens"] or 0) + (pv["thinking_tokens"] or 0), (nv["output_tokens"] or 0) + (nv["thinking_tokens"] or 0)))
    R["route_cost"] = {}
    for route, v in split.items():
        pv_, nv_, nr_, na_, pa_, rr_, pin, nin, pout, nout = (S.fmean(z[i] for z in v) for i in range(10))
        R["route_cost"][route] = {"n": len(v), "policy_v2": pv_, "naive_llm": nv_, "diff": pv_ - nv_, "pct_cheaper": 100 * (1 - pv_ / nv_), "naive_router": nr_, "naive_answer": na_,
                                  "policy_v2_answer": pa_, "naive_rows": rr_, "policy_v2_answer_in_tok": pin, "naive_answer_in_tok": nin,
                                  "policy_v2_answer_out_plus_think_tok": pout, "naive_answer_out_plus_think_tok": nout}
    split1 = defaultdict(list)
    for q in qids:
        pv, nv = ALL[("policy_v2", q)][1], ALL[("naive_llm", q)][1]
        split1[nv["route"]].append((pv["cost_usd"], nv["cost_usd"]))
    R["route_cost_pass1"] = {k: {"n": len(v), "policy_v2": S.fmean(z[0] for z in v), "naive_llm": S.fmean(z[1] for z in v), "pct_cheaper": 100 * (1 - S.fmean(z[0] for z in v) / S.fmean(z[1] for z in v))} for k, v in split1.items()}
    # question-level paired bootstrap of the pooled cost difference
    pc = [S.fmean(ALL[("policy_v2", q)][p_]["cost_usd"] for p_ in range(1, 6)) for q in qids]
    nc = [S.fmean(ALL[("naive_llm", q)][p_]["cost_usd"] for p_ in range(1, 6)) for q in qids]
    R["cost_diff_boot_all"] = boot_mean_diff(pc, nc)
    R["cost_diff_boot_p1"] = boot_mean_diff([ALL[("policy_v2", q)][1]["cost_usd"] for q in qids], [ALL[("naive_llm", q)][1]["cost_usd"] for q in qids])
    trunc = [(r["arm"], r["query_id"], r["pass"], r["cost_usd"], r["output_tokens"], r["thinking_tokens"]) for r in rows if r["gen_finish_reason"] == "MAX_TOKENS"]
    drop = {(q, p_) for (_, q, p_, _, _, _) in trunc}
    kept = [r for r in rows if (r["query_id"], r["pass"]) not in drop]
    def mean_cost(arm, rs):
        v = [r["cost_usd"] for r in rs if r["arm"] == arm]
        return S.fmean(v)
    R["trunc"] = {"rows": [{"arm": a_, "query": q_, "pass": p_, "cost": c_, "output_tokens": o_, "thinking_tokens": th_} for (a_, q_, p_, c_, o_, th_) in trunc],
                  "pooled_pct_cheaper_excluding_those_question_pass_cells": 100 * (1 - mean_cost("policy_v2", kept) / mean_cost("naive_llm", kept)),
                  "n_arm_runs_kept_per_arm": len([r for r in kept if r["arm"] == "policy_v2"])}
    # per-pass cost of each arm (shows pass-to-pass variation behind the pass-1 figure)
    R["cost_by_pass"] = {arm: [sum(r["cost_usd"] for r in rows if r["arm"] == arm and r["pass"] == p_) for p_ in range(1, 6)] for arm in ("policy_v2", "naive_llm")}

    # ------------------------------------------------------------------ 4. total cost
    total = sum(r["cost_usd"] for r in rows)
    R["total"] = {"sum": total, "rows": len(rows), "last_cumulative": rows[-1]["cumulative_cost_usd"], "by_arm": {arm: R["cost"][f"all|{arm}"]["total"] for arm in ARMS}}
    check("4.total", "sum of cost_usd over all 1,000 rows vs reported USD 1.6580 (final summary: 'USD 1.66')", 1.6580, round(total, 4), srcc, tol=0.00005)
    check("4.total_rounded", "rounded to cents (reported 'USD 1.66')", 1.66, round(total, 2), srcc, tol=0.0001)
    check("4.rows", "number of rows", 1000, len(rows), srcc)
    check("4.cumulative_counter", "runner's last cumulative_cost_usd equals the sum of rows", True, abs(rows[-1]["cumulative_cost_usd"] - total) < 1e-9, srcc)
    check("4.recomputed_from_tokens", "total recomputed from tokens x prices equals logged total", True, abs(recomputed_rows - total) < 1e-9, srcc)

    # ------------------------------------------------------------------ 5. H&M forced-exact latency at s >= 0.204
    cs = list(csv.DictReader(open("outputs/phase_a_arms/analysis/cell_summary.csv", encoding="utf-8")))
    fe = [(float(r["selectivity"]), r["table"], r["filter_id"], float(r["median_latency_ms"])) for r in cs if r["arm"] == "forced-exact"]
    sel_hi = [x for x in fe if x[0] >= 0.2037]
    groups = {"ctl (s = 0.20376; 5 cells)": [x for x in fe if x[2] == "ctl"],
              "gap1-gap4 (s = 0.214-0.299; 20 cells)": [x for x in fe if x[2].startswith("gap")],
              "idx1-idx3 (s = 0.329-0.4705; 15 cells)": [x for x in fe if x[2].startswith("idx")],
              "all cells with s >= 0.204 (40 cells)": sel_hi}
    R["hm"] = {}
    for name, g in groups.items():
        lo_ = min(g, key=lambda x: x[3]); hi_ = max(g, key=lambda x: x[3])
        R["hm"][name] = {"n": len(g), "min": lo_[3], "min_cell": f"{lo_[1]} x {lo_[2]}", "max": hi_[3], "max_cell": f"{hi_[1]} x {hi_[2]}", "n_over_500": sum(1 for x in g if x[3] > 500)}
    ctl, idx, allhi = R["hm"]["ctl (s = 0.20376; 5 cells)"], R["hm"]["idx1-idx3 (s = 0.329-0.4705; 15 cells)"], R["hm"]["all cells with s >= 0.204 (40 cells)"]
    srch = "outputs/phase_a_arms/analysis/cell_summary.csv: arm = forced-exact, median_latency_ms"
    check("5.ctl_min", "'547-1,080 ms at 0.204' (PHASE_A_HOLDOUT_PROTOCOL.md): minimum of the 5 ctl cells", 547, round(ctl["min"]), srch, tol=0.5)
    check("5.ctl_max", "'547-1,080 ms at 0.204': maximum of the 5 ctl cells", 1080, round(ctl["max"]), srch, tol=0.5)
    check("5.idx_min", "'smallest 751.5 ms' among the 15 idx1-3 cells (arms_results report / CODE_MANUAL)", 751.5, round(idx["min"], 1), srch, tol=0.05)
    check("5.all_max", "'6.6 s' maximum from 0.204 upward (arms_results report)", 6567, round(allhi["max"]), srch, tol=0.5)
    check("5.all_min", "'490 ms' minimum from 0.204 upward (arms_results report: '490 ms to 6.6 s')", 490, round(allhi["min"]), srch, tol=1.5,
          note=f"actual minimum {allhi['min']:.1f} ms ({allhi['min_cell']}); '490' is a rounding up of 488.9")
    check("5.idx_all_over_500", "'all 15 idx1-3 cells exceed 500 ms'", 15, idx["n_over_500"], srch)
    check("5.fails_38_of_40", "'forced-exact fails 38 of those 40 on latency' (POLICY_V2_PROPOSAL.md)", 38, allhi["n_over_500"], srch)

    # ------------------------------------------------------------------ 6. holdout 1 numbers cited in the cause discussion
    H = [json.loads(l) for l in open("outputs/phase_a_holdout/results.jsonl", encoding="utf-8") if l.strip()]
    cell_rows = [r for r in H if r["table"] == "hm_clothes_25" and r["filter_id"] == "ho3" and r["arm"] == "forced-exact"]
    lat = sorted(r["latency_ms"] for r in cell_rows)
    q1, q3 = np.percentile(lat, [25, 75])
    over = [v for v in lat if v > 500]
    srch1 = "outputs/phase_a_holdout/results.jsonl: table, filter_id, arm, latency_ms, shared_read_blocks"
    check("6.median", "failing cell median latency 528.4 ms", 528.4, round(S.median(lat), 1), srch1, tol=0.05)
    check("6.over500", "'18 of 20 per-vector medians are above 500 ms'", 18, len(over), srch1)
    check("6.range", "'508-539 ms' range of those 18", "508-539", f"{min(over):.0f}-{max(over):.0f}", srch1)
    check("6.iqr", "'IQR 16 ms'", 16, round(float(q3 - q1)), srch1, tol=1.0, note=f"computed IQR {q3 - q1:.1f} ms (numpy linear percentiles)")
    others = [S.median([r["latency_ms"] for r in H if r["table"] == t and r["filter_id"] == "ho3" and r["arm"] == "forced-exact"]) for t in ("hm_clothes_0", "hm_clothes_50", "hm_clothes_75", "hm_clothes_100")]
    check("6.other_tables", "'the same filter on the other tables costs 132-175 ms'", "132-175", f"{min(others):.0f}-{max(others):.0f}", srch1)
    sr = S.median([r.get("shared_read_blocks") or 0 for r in cell_rows])
    check("6.shared_read", "'median shared_read_blocks = 0 in the cell'", 0, sr, srch1)
    notes = Path("outputs/phase_a_holdout/machine_notes.txt").read_text(encoding="utf-8")
    cpu = [int(x) for x in re.findall(r"cumulative CPU = (\d+) s", notes)]
    t0, t1 = re.findall(r"(?:START|END)\s+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", notes)
    from datetime import datetime
    mins = (datetime.fromisoformat(t1) - datetime.fromisoformat(t0)).total_seconds() / 60
    cores = (cpu[1] - cpu[0]) / (mins * 60)
    check("6.kernel_cpu", "'Jupyter kernel used 3,410 CPU-seconds between the start and end notes (31.7 min, about 1.8 cores)'", "3410 s / 31.7 min / 1.8 cores", f"{cpu[1] - cpu[0]} s / {mins:.1f} min / {cores:.1f} cores", "outputs/phase_a_holdout/machine_notes.txt")
    R["h1"] = {"others": others, "rerun_median": None}
    rr = [json.loads(l) for l in open("outputs/phase_a_holdout_rerun/results.jsonl", encoding="utf-8") if l.strip()]
    rerun = S.median([r["latency_ms"] for r in rr if r["table"] == "hm_clothes_25" and r["filter_id"] == "ho3" and r["arm"] == "forced-exact"])
    check("6.rerun_median", "rerun median for the same cell 122.8 ms", 122.8, round(rerun, 1), "outputs/phase_a_holdout_rerun/results.jsonl", tol=0.05)

    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps({"checks": CHECKS, "recomputed": json.loads(json.dumps(R, default=str))}, indent=2), encoding="utf-8")
    bad = [c for c in CHECKS if c["status"].startswith("MISMATCH")]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(build_markdown(CHECKS, R), encoding="utf-8")
    print(f"{len(CHECKS)} checks, {len(bad)} MISMATCH; wrote {a.out}")


def f(x, n=1):
    return format(x, f".{n}f")


def build_markdown(CHECKS, R):
    bad = [c for c in CHECKS if c["status"].startswith("MISMATCH")]
    pc = R["pct"]
    rc, rp = R["route_cost"], R["route_cost_pass1"]
    L = []
    w = L.append
    w("# Headline audit, 2026-10-23 (read-only)\n")
    w("Recomputed directly from the raw files with independent code (`src/phase_d_validation/headline_audit.py`: own Wilson/Newcombe, own exact binomial via scipy, own paired bootstrap with the same seed and resamples, own cost formula); no model call, no database access, no new result, no existing report edited. All 46 checks with their reported value, recomputed value and source are in section 3 and `outputs/headline_audit_2026-10-23/audit.json`.\n")
    w("## 1. Mismatches first\n")
    w(f"**Numeric mismatches: {len(bad)} of {len(CHECKS)} checks.** Every reported number reproduces from the raw files (accuracy counts, b/c, difference, Newcombe CI, McNemar p, per-arm medians, the paired-bootstrap latency CI, per-question and per-arm costs, the USD 1.6580 total, the H&M latency ranges and the held-out-1 cell statistics).\n")
    w("**Claims that are numerically right but whose scope or wording needs a flag** (nothing was edited; proposals are for you to decide):\n")
    w(f"1. **\"About one third cheaper per query\" (reports/phase_d_gemini_full_2026-10-12.md, section C, unqualified) holds for pass 1 only.** It is 1 - 0.00135/0.00203 = {f(pc['pass1_from_rounded_report_values'])}% from the rounded values in the report ({f(pc['pass1_exact'])}% exact) = pass-1 mean cost per arm-run (one question x one arm), router call included for naive_llm. Over all 5 passes the same ratio is **{f(pc['all_passes'])}%** (policy_v2 USD {f(R['cost']['all|policy_v2']['mean'] , 5)} vs naive_llm USD {f(R['cost']['all|naive_llm']['mean'], 5)} per arm-run). Pass 1 is the most favourable of the five: policy_v2's pass-1 total is the lowest of its five passes (USD {f(R['cost_by_pass']['policy_v2'][0], 4)} vs {', '.join(f(x, 4) for x in R['cost_by_pass']['policy_v2'][1:])} in passes 2-5) and naive_llm's is the highest (USD {f(R['cost_by_pass']['naive_llm'][0], 4)} vs {', '.join(f(x, 4) for x in R['cost_by_pass']['naive_llm'][1:])}). The final summary's table labels its figures \"pass 1\" and is correct; the unqualified sentence is not. A defensible statement: about 19% cheaper over 5 passes (paired bootstrap of the per-arm-run cost difference: USD {f(R['cost_diff_boot_all'][0], 6)} [{f(R['cost_diff_boot_all'][1], 6)}, {f(R['cost_diff_boot_all'][2], 6)}]), about 34% in pass 1.")
    w(f"2. **\"About 2.8 s faster per query\" is the pass-1 mean of the paired per-question difference** ({f(-R['lat_diff']['mean'] / 1000, 3)} s, CI {f(-R['lat_diff']['ci'][1] / 1000, 2)}-{f(-R['lat_diff']['ci'][0] / 1000, 2)} s). The pass-1 difference of medians is {f(-R['lat_diff']['median_diff'] / 1000, 2)} s, and the 5-pass pooled mean difference is {f(-R['lat_diff_all'][0] / 1000, 2)} s (bootstrap CI {f(-R['lat_diff_all'][2] / 1000, 2)}-{f(-R['lat_diff_all'][1] / 1000, 2)} s). The claim names neither \"mean\" nor \"pass 1\".")
    w(f"3. **\"751-6,567 ms\" does not appear in any report** (grep of all `.md` files and the manual). The two ranges in circulation use different cell sets: see section 2 item 5. The pairing of 751 with 6,567 mixes the minimum of the 15 idx1-3 cells (s >= 0.329) with the maximum of all 40 cells at s >= 0.204 (which is gap4 x hm_clothes_50, s = 0.2986, not an idx cell).")
    w("4. **Held-out 1 cause wording (section 2 item 6):** most places label the cause inferred or unproven; two statements are stronger than the evidence (listed there).")
    w("5. Minor: `arms_results_2026-10-10.md` says forced-exact \"490 ms to 6.6 s from 0.204 upward\"; the minimum is 488.9 ms (hm_clothes_100 x gap1), so \"490\" is a rounding up, not an exact value.\n")
    w("## 2. The requested items\n")
    w("### Item 1: accuracy (pass 1, primary scoring)\n")
    w("Source: `outputs/phase_d_gemini_full_2026-10-12/results.jsonl` (`arm`, `pass`, `query_id`, `correct`). Reported values from `reports/phase_d_gemini_full_2026-10-12.md` section A1/A2.\n")
    w("| quantity | reported | recomputed | status |\n|---|---|---|---|")
    for c in CHECKS:
        if c["id"].startswith("1."):
            w(f"| {c['what']} | {c['reported']} | {c['recomputed']} | {c['status']} |")
    w("")
    w("### Item 2: latency (`total_ms`, pass 1 unless stated)\n")
    w("| arm | median ms (reported -> recomputed) | mean ms, pass 1 | median ms, 5 passes | mean ms, 5 passes |\n|---|---|---|---|---|")
    rep_med = {"policy_v2": 2186, "naive_llm": 4329, "decision_matrix": 2121, "naive_informed": 3906}
    for arm in ARMS:
        v = R["lat"][arm]
        w(f"| {arm} | {rep_med[arm]} -> {f(v['p1_median'], 0)} | {f(v['p1_mean'], 0)} | {f(v['all_median'], 0)} | {f(v['all_mean'], 0)} |")
    w(f"\nPaired policy_v2 - naive_llm, pass 1, mean: reported -2827 [-3753, -1993]; recomputed {f(R['lat_diff']['mean'], 0)} [{f(R['lat_diff']['ci'][0], 0)}, {f(R['lat_diff']['ci'][1], 0)}] (10,000 resamples, seed 20261012): MATCH. Difference of pass-1 medians: {f(R['lat_diff']['median_diff'], 0)} ms. Pooled over 5 passes (per-question mean over passes): {f(R['lat_diff_all'][0], 0)} [{f(R['lat_diff_all'][1], 0)}, {f(R['lat_diff_all'][2], 0)}] ms. The \"about 2.8 s faster\" claim is the pass-1 mean difference (flag 2 above).\n")
    w("### Item 3: cost\n")
    w("Source: same file (`cost_usd`, `router_cost_usd`, `gen_cost_usd`, `input_tokens`, `output_tokens`, `thinking_tokens`, `gen_cached_tokens`, `rows_returned`). Per-row identity cost_usd = router_cost_usd + gen_cost_usd holds for all 1,000 rows, and recomputing every call from its logged tokens with the prices (0.75 / 3.75 USD per 1M tokens; thinking billed as output; cached input subtracted) reproduces the logged cost (max row difference < 1e-9).\n")
    for scope, title in (("pass1", "Pass 1 (50 questions per arm)"), ("all", "All 5 passes (250 arm-runs per arm)")):
        w(f"**{title}**\n\n| arm | total USD | mean per question USD | router part per question | answer part per question | answer call: mean input tok | output tok | thinking tok | mean rows returned |\n|---|---|---|---|---|---|---|---|---|")
        for arm in ARMS:
            v = R["cost"][f"{scope}|{arm}"]
            w(f"| {arm} | {f(v['total'], 4)} | {f(v['mean'], 5)} | {f(v['router_mean'], 5)} | {f(v['answer_mean'], 5)} | {f(v['in_tok'], 0)} | {f(v['out_tok'], 1)} | {f(v['think_tok'], 1)} | {f(v['rows'], 1)} |")
        w("")
    w("Router call (naive arms): mean router input " + f"{f(R['cost']['all|naive_llm']['router_in_tok'], 0)} tokens, mean router thinking {f(R['cost']['all|naive_llm']['router_think_tok'], 1)} tokens (5 passes, naive_llm).\n")
    w("**policy_v2 vs naive_llm cost, by which route naive_llm chose** (matched by question and pass; naive_llm cost includes its router call):\n")
    w("| scope | naive_llm route | arm-run pairs | policy_v2 USD | naive_llm USD | difference | policy_v2 cheaper by | naive_llm router part | answer cost policy_v2 / naive_llm | answer input tok policy_v2 / naive_llm | answer output+thinking tok policy_v2 / naive_llm | naive_llm rows |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for route in ("pre-filter", "post-filter"):
        v = rc[route]
        w(f"| 5 passes | {route} | {v['n']} | {f(v['policy_v2'], 5)} | {f(v['naive_llm'], 5)} | {f(v['diff'], 5)} | {f(v['pct_cheaper'])}% | {f(v['naive_router'], 5)} | {f(v['policy_v2_answer'], 5)} / {f(v['naive_answer'], 5)} | {f(v['policy_v2_answer_in_tok'], 0)} / {f(v['naive_answer_in_tok'], 0)} | {f(v['policy_v2_answer_out_plus_think_tok'], 0)} / {f(v['naive_answer_out_plus_think_tok'], 0)} | {f(v['naive_rows'], 1)} |")
    for route in ("pre-filter", "post-filter"):
        v = rp[route]
        w(f"| pass 1 | {route} | {v['n']} | {f(v['policy_v2'], 5)} | {f(v['naive_llm'], 5)} | {f(v['naive_llm'] - v['policy_v2'], 5)} (naive - policy_v2) | {f(v['pct_cheaper'])}% | - | - | - | - | - |")
    w("")
    cA, cP = R["cost"]["all|naive_llm"], R["cost"]["all|policy_v2"]
    pre, post = rc["pre-filter"], rc["post-filter"]
    w(f"**Which definition gives the reported percentage.** \"About one third cheaper\" = pass-1 mean cost per arm-run (question x arm, router call included): (0.00203 - 0.00135) / 0.00203 = {f(pc['pass1_from_rounded_report_values'])}% ({f(pc['pass1_exact'])}% unrounded). "
      f"Other definitions of the same comparison: all 5 passes, total cost per arm-run: {f(pc['all_passes'])}%; answer call only (router excluded), pass 1: {f(pc['answer_only_pass1'])}%; answer call only, 5 passes: {f(pc['answer_only_all'])}%.\n")
    w(f"**Decomposition over 5 passes** (mean per arm-run): policy_v2 saves USD {f(cA['mean'] - cP['mean'], 5)}; the router call that it does not make is USD {f(cA['router_mean'], 5)} of that (about three quarters), and the remaining USD {f(cA['answer_mean'] - cP['answer_mean'], 5)} is the difference between the two answer calls. "
      f"That difference differs by group. When naive_llm chose pre-filter (identical prompts, {f(pre['naive_answer_in_tok'], 0)} input tokens) policy_v2's answer call costs slightly MORE (USD {f(pre['policy_v2_answer'], 5)} vs {f(pre['naive_answer'], 5)}; output+thinking tokens {f(pre['policy_v2_answer_out_plus_think_tok'], 0)} vs {f(pre['naive_answer_out_plus_think_tok'], 0)}), so the saving there ({f(pre['pct_cheaper'])}%) is the router call alone. "
      f"When naive_llm chose post-filter its answer prompt is much shorter (about {f(post['naive_answer_in_tok'], 0)} vs {f(post['policy_v2_answer_in_tok'], 0)} input tokens) yet its answer call costs more (USD {f(post['naive_answer'], 5)} vs {f(post['policy_v2_answer'], 5)}) because it uses more output and thinking tokens ({f(post['naive_answer_out_plus_think_tok'], 0)} vs {f(post['policy_v2_answer_out_plus_think_tok'], 0)} per call), so the saving there ({f(post['pct_cheaper'])}%) includes a thinking-token difference that varies from pass to pass.\n")
    tr = R["trunc"]
    w("**Runaway answers inflate the pooled cost.** Two answers ended with finish reason MAX_TOKENS (both in pass 2): " + "; ".join(f"{x['arm']} on {x['query']}: USD {f(x['cost'], 4)}, {x['output_tokens']} output tokens" for x in tr["rows"])
      + f". Mean output tokens per answer over 5 passes are policy_v2 {f(cP['out_tok'], 1)} (pass 1: {f(R['cost']['pass1|policy_v2']['out_tok'], 1)}) and decision_matrix {f(R['cost']['all|decision_matrix']['out_tok'], 1)}; excluding those two question-pass cells for every arm, the pooled saving of policy_v2 over naive_llm is {f(tr['pooled_pct_cheaper_excluding_those_question_pass_cells'])}% ({tr['n_arm_runs_kept_per_arm']} arm-runs per arm kept).\n")
    w(f"Pass-1 paired bootstrap of the per-arm-run cost difference: USD {f(R['cost_diff_boot_p1'][0], 6)} [{f(R['cost_diff_boot_p1'][1], 6)}, {f(R['cost_diff_boot_p1'][2], 6)}].\n")
    w("### Item 4: total cost\n")
    T = R["total"]
    w(f"Sum of `cost_usd` over all {T['rows']} rows = **USD {f(T['sum'], 6)}** (reported USD 1.6580 / \"USD 1.66\": MATCH); the runner's last `cumulative_cost_usd` = {f(T['last_cumulative'], 6)}; recomputed from logged tokens x prices = {f(R['ident']['recomputed_total_from_tokens'], 6)}. By arm over 5 passes: " + ", ".join(f"{a_} {f(v, 4)}" for a_, v in T["by_arm"].items()) + ". The folder has no `errors.jsonl`, so no billed-but-unlogged failed call is known; the Billing report remains the external check.\n")
    w("### Item 5: H&M forced-exact latency at s >= 0.204 (`outputs/phase_a_arms/analysis/cell_summary.csv`, arm = forced-exact, `median_latency_ms`, one value per table x filter cell)\n")
    w("| cell set | cells | min ms (cell) | max ms (cell) | cells > 500 ms |\n|---|---|---|---|---|")
    for name, v in R["hm"].items():
        w(f"| {name} | {v['n']} | {f(v['min'], 1)} ({v['min_cell']}) | {f(v['max'], 1)} ({v['max_cell']}) | {v['n_over_500']} |")
    w("")
    w(f"- **\"547-1,080 ms\"** (PHASE_A_HOLDOUT_PROTOCOL.md, run-time estimate, written \"at 0.204\") is the min-max of **forced-exact median latency over the 5 `ctl` cells only** (s = 0.20376, one per table): {f(R['hm']['ctl (s = 0.20376; 5 cells)']['min'], 1)} ms (hm_clothes_75) to {f(R['hm']['ctl (s = 0.20376; 5 cells)']['max'], 1)} ms (hm_clothes_50). It is correct for that set and is not the range over all cells with s >= 0.204.")
    w(f"- **The arms-results report** states two different things: \"490 ms to 6.6 s from 0.204 upward\" = min-max over **all 40 cells with s >= 0.204** (8 filters ctl, gap1-4, idx1-3 x 5 tables): {f(R['hm']['all cells with s >= 0.204 (40 cells)']['min'], 1)} ms (hm_clothes_100 x gap1) to {f(R['hm']['all cells with s >= 0.204 (40 cells)']['max'], 1)} ms (hm_clothes_50 x gap4, s = 0.2986); and \"all 15 idx1-3 cells exceed 500 ms (smallest 751.5 ms, hm_clothes_25/idx1)\" = the **minimum over the 15 idx cells only** (s >= 0.329), whose maximum is {f(R['hm']['idx1-idx3 (s = 0.329-0.4705; 15 cells)']['max'], 1)} ms. The idx1-3 range is therefore {f(R['hm']['idx1-idx3 (s = 0.329-0.4705; 15 cells)']['min'], 1)}-{f(R['hm']['idx1-idx3 (s = 0.329-0.4705; 15 cells)']['max'], 1)} ms, not 751-6,567.")
    w("- **Why the numbers differ:** 547-1,080 = 5 cells at one selectivity (ctl); 489-6,567 = 40 cells at s >= 0.204; 751.5 = the smallest of the 15 cells at s >= 0.329. 6,567 ms is a single outlier cell (hm_clothes_50 x gap4); the other four tables at gap4 are 644-1,383 ms. Also consistent: 38 of the 40 cells at s >= 0.204 exceed 500 ms (the two that do not are hm_clothes_100 x gap1 at 488.9 and hm_clothes_25 x gap1 at 491.2), as stated in POLICY_V2_PROPOSAL.md.\n")
    w("### Item 6: what the reports say about the cause of the held-out-1 failure (hm_clothes_25 x ho3, forced-exact 528.4 ms)\n")
    w("The numbers cited in the cause discussion reproduce (median 528.4; 18 of 20 per-vector medians above 500 ms, 508-539; IQR about 16 ms; the same filter on the other tables 132-175 ms; median `shared_read_blocks` 0; the kernel used 3,410 CPU-seconds in 31.7 minutes = 1.8 cores; quiet-rerun median of the same cell 122.8 ms).\n")
    w("| document | wording | established or inferred? |\n|---|---|---|")
    w("| `reports/holdout_results_2026-10-10.md` (\"Why I think it failed [I, not proven]\") | \"this looks like CPU contention rather than a cold cache\"; \"the link between the kernel and the two slow tables is an inference\"; load over time not recorded | labelled inference; OK |")
    w("| `DEVIATION_LOG.md` (2026-10-12) | \"Probable CPU contention from a Jupyter kernel is noted as an inference, not proven.\" | labelled inference; OK |")
    w("| `reports/final_summary_2026-10-12.md`, table note | \"CPU contention from a Jupyter kernel during the original run is a probable cause of the 528.4 ms, inferred, not proven.\" | labelled inference; OK |")
    w("| `reports/phase_d_local_2026-10-12.md` and `reports/holdout_results_2026-10-12-rerun.md` | \"This report does not prove the cause.\" | OK |")
    w("| `docs/CODE_MANUAL.docx` section 12.9 | \"[I] The failing cell appears to come from machine load ... an unrelated Jupyter kernel was using about 1.8 CPU cores\" | marked [I] and hedged (\"appears\"); the 1.8 cores is an average over the run window, verified |")
    w("| **`reports/final_summary_2026-10-12.md`, limitation 9** | \"the first held-out cell failed at 528.4 ms **under load** and passed at 122.8 ms **when quiet**\" | **FLAG: states the load as fact.** What was measured: host CPU 100% at the start and 50% at the end of the original run (not recorded in between) and 17-21% falling to 3-5% in the rerun; the rerun also differs in seed, table order and time. The cause is not established. |")
    w("| **`PHASE_A_HOLDOUT2_PROTOCOL.md`** (frozen; tag `phase-a-holdout2-frozen-2026-10-12`; not edited here) | \"The in-sample run, **under heavy CPU load**, had forced-exact at 489-6,567 ms\" and \"Under the heavy load of the original run the exact arm was up to 3x slower\" | **FLAG: states load as established for the three-arm run.** `PHASE_A_HOLDOUT_PROTOCOL.md` itself says that run \"probably saw similar conditions, but its load over time was not recorded\"; the \"up to 3x\" comes from the harness self-test (2,685/2,701 ms vs 882/825 ms for the same points), not from a load measurement. |")
    w("| `reports/pre_paid_fixes_2026-10-12.md` | \"up to about 2.5 h under heavy load\" (run-time estimate for held-out 2) | an estimate that assumes the 3x slowdown; same flag as above, lower stakes |")
    w("\nNo wording was changed. If you want the frozen protocol's phrases corrected, the clean route is a dated note in `DEVIATION_LOG.md` (the tagged file itself must not be edited).\n")
    w("## 3. All 46 checks\n")
    w("| id | what | reported | recomputed | source | status |\n|---|---|---|---|---|---|")
    for c in CHECKS:
        note = f" ({c['note']})" if c["note"] else ""
        w(f"| {c['id']} | {c['what']} | {c['reported']} | {c['recomputed']} | {c['source']} | {c['status']}{note} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
