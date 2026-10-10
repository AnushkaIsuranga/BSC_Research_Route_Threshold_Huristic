"""Retrospective evaluation of routing policies on the 65 measured H&M cells.

Each policy picks one measured arm per (table, filter) cell; the cell passes if
mean recall@10 >= 0.90 (all 20 vectors valid) AND median latency <= 500 ms.
P1/P2 call the unmodified src/phase_b_router/policy.py with the Phase A v1 / v2
thresholds files. P7 and P8 are fitted on / explored with these same cells
(IN-SAMPLE).

Usage: python -m src.phase_c_analysis.policy_evaluation [--date 2026-10-10]
Writes outputs/phase_a_arms/analysis/policy_evaluation_cells.csv and
reports/policy_evaluation_<date>.md (the exploratory-diagnostic section is
appended separately by hand).
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.phase_b_router.policy import get_routing_decision
from src.phase_c_analysis.arm_analysis import (ABBR, LATENCY_SLA_MS, N_VEC, RECALL_SLA, TABLES, cell, cell_summary, load,
                                               md_table, route_map)

OUT = Path("outputs/phase_a_arms/analysis")
T_GRID = [0.001, 0.005, 0.01, 0.02, 0.05, 0.1]
POLICY_TO_ARM = {"pre-filter": "forced-exact", "post-filter": "forced-hnsw"}
SHORT = {"planner-default": "PD", "forced-exact": "FE", "forced-hnsw": "FH", "iterative-relaxed": "IR"}
LABELS = {
    "P1": "P1 matrix v1 (policy.py + phase_a_v1/thresholds.json, per-table tier; pre->FE, post->FH)",
    "P2": "P2 matrix v2 (policy.py + phase_a_v2/thresholds.json, per-table tier; pre->FE, post->FH)",
    "P3": "P3 planner-default (as measured)",
    "P4": "P4 always forced-exact",
    "P5": "P5 always forced-hnsw",
    "P6": "P6 always iterative-relaxed",
    "P7": "P7 route map of the amended decision rule [IN-SAMPLE: fitted on these cells]",
}
for _t in T_GRID:
    LABELS[f"P8_{_t}"] = f"P8 T={_t}: FE if selectivity < T else IR [IN-SAMPLE / exploratory]"


def evaluate(cs, filters):
    th1 = json.loads(Path("outputs/phase_a_v1/thresholds.json").read_text(encoding="utf-8"))
    th2 = json.loads(Path("outputs/phase_a_v2/thresholds.json").read_text(encoding="utf-8"))
    rm = route_map(cs, filters)
    rows = []

    def add(policy, t, f, s, arm):
        c = cell(cs, t, f, arm)
        rec_ok = bool(c["n_valid"] == N_VEC and c["mean_recall"] >= RECALL_SLA - 1e-12)
        lat_ok = bool(c["median_latency_ms"] <= LATENCY_SLA_MS)
        rows.append({"policy": policy, "table": t, "filter_id": f, "selectivity": s, "arm": arm,
                     "mean_recall": c["mean_recall"], "median_latency_ms": c["median_latency_ms"],
                     "recall_fail": not rec_ok, "latency_fail": not lat_ok, "pass": rec_ok and lat_ok})

    for t in TABLES:
        for fl in filters:
            f, s = fl["filter_id"], fl["selectivity"]
            add("P1", t, f, s, POLICY_TO_ARM[get_routing_decision(t, s, th1)])
            add("P2", t, f, s, POLICY_TO_ARM[get_routing_decision(t, s, th2)])
            add("P3", t, f, s, "planner-default")
            add("P4", t, f, s, "forced-exact")
            add("P5", t, f, s, "forced-hnsw")
            add("P6", t, f, s, "iterative-relaxed")
            r = rm[(rm.table == t) & (rm.filter_id == f)].iloc[0]
            # P7: the rule's route; if a cell had no route, fall back to its best-recall arm (not needed here)
            add("P7", t, f, s, r["route"] if r["route"] else r["best_recall_arm"])
            for T in T_GRID:
                add(f"P8_{T}", t, f, s, "forced-exact" if s < T else "iterative-relaxed")
    return pd.DataFrame(rows)


def build_report(ev, filters, rm, report_date):
    fids = [f["filter_id"] for f in filters]
    sel = {f["filter_id"]: f["selectivity"] for f in filters}
    L, w = [], None
    L = []
    w = L.append
    w(f"# Retrospective policy evaluation on the 65 H&M cells — {report_date}\n")
    w("**[V]** = computed by `src/phase_c_analysis/policy_evaluation.py` from `outputs/phase_a_arms/results.jsonl` (via `arm_analysis.py`). **[I]** = interpretation. "
      "A cell passes when the arm the policy picks there has mean recall@10 >= 0.90 over all 20 vectors AND median latency <= 500 ms (median of the 20 per-vector medians). "
      "\"Recall fail\" and \"latency fail\" count the cells failing that SLA (a cell failing both is counted in both columns and in \"both\").\n")
    w("**In-sample warning.** P7 and P8 were chosen or tuned using these same 65 cells; their scores describe fit, not out-of-sample performance. "
      "P1-P6 are fixed before looking (P1/P2 are the unmodified `policy.py` with existing threshold files). "
      "The 65 cells are 5 tables x 13 filters over the same 20 query vectors and one set of 105,100 rows per table, so they are not 65 independent trials.\n")

    w("## 1. Summary\n")
    rows = []
    for p, lab in LABELS.items():
        x = ev[ev.policy == p]
        rows.append([lab, f"**{int(x['pass'].sum())}** / 65", int(x.recall_fail.sum()), int(x.latency_fail.sum()), int((x.recall_fail & x.latency_fail).sum()), int((~x['pass']).sum())])
    w(md_table(["policy", "pass both SLAs", "recall fail", "latency fail", "both fail", "total fail"], rows))
    w("")
    w("Pass counts by table [V]:\n")
    rows = []
    for p, lab in LABELS.items():
        x = ev[ev.policy == p]
        rows.append([p] + [f"{int(x[x.table == t]['pass'].sum())}/13" for t in TABLES])
    w(md_table(["policy"] + TABLES, rows))
    w("")
    groups = {"lo1-lo2 (0.0001-0.001)": ["lo1", "lo2"], "lo3-lo5 (0.01-0.11)": ["lo3", "lo4", "lo5"], "ctl, gap1-gap3 (0.204-0.26)": ["ctl", "gap1", "gap2", "gap3"],
              "gap4, idx1-idx3 (0.299-0.47)": ["gap4", "idx1", "idx2", "idx3"]}
    w("Pass counts by selectivity region (cells per region = 5 tables x filters) [V]:\n")
    rows = []
    for p in LABELS:
        x = ev[ev.policy == p]
        rows.append([p] + [f"{int(x[x.filter_id.isin(g)]['pass'].sum())}/{5 * len(g)}" for g in groups.values()])
    w(md_table(["policy"] + list(groups), rows))
    w("")

    w("## 2. Routes per (table, filter)\n")
    for p in ("P1", "P2", "P7"):
        w(f"**{LABELS[p]}** — cell text: arm (✓ pass / R recall fail / L latency fail / RL both) [V]\n")
        rows = []
        for f in fids:
            r = [f, f"{sel[f]:.5f}"]
            for t in TABLES:
                c = ev[(ev.policy == p) & (ev.table == t) & (ev.filter_id == f)].iloc[0]
                flag = "✓" if c["pass"] else ("RL" if c.recall_fail and c.latency_fail else "R" if c.recall_fail else "L")
                r.append(f"{SHORT[c['arm']]} {flag}")
            rows.append(r)
        w(md_table(["filter", "sel"] + TABLES, rows))
        w("")
    w("P3 = planner-default in every cell; P4 = forced-exact; P5 = forced-hnsw; P6 = iterative-relaxed; P8 = forced-exact if selectivity < T else iterative-relaxed. "
      "The per-cell data for all policies (arm, recall, latency, flags) is in `outputs/phase_a_arms/analysis/policy_evaluation_cells.csv`.\n")

    w("## 3. Failing cells per policy\n")
    w("Format: filter (selectivity): tables with R = recall fail, L = latency fail, RL = both. [V]\n")
    for p, lab in LABELS.items():
        x = ev[(ev.policy == p) & (~ev['pass'])]
        w(f"**{lab}** — {len(x)} failing cell(s)")
        if x.empty:
            w("- none\n")
            continue
        for f in fids:
            y = x[x.filter_id == f]
            if len(y):
                parts = [f"{r.table.replace('hm_clothes_', 'T')}:{'RL' if r.recall_fail and r.latency_fail else 'R' if r.recall_fail else 'L'}"
                         f"({r.mean_recall:.2f}/{r.median_latency_ms:.0f}ms)" for r in y.itertuples()]
                w(f"- {f} ({sel[f]:.5f}): " + ", ".join(parts))
        w("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    a = ap.parse_args()
    df, filters, meta, resumes = load()
    sel = {f["filter_id"]: f["selectivity"] for f in filters}
    cs = cell_summary(df, sel)
    ev = evaluate(cs, filters)
    OUT.mkdir(parents=True, exist_ok=True)
    ev.to_csv(OUT / "policy_evaluation_cells.csv", index=False)
    rm = route_map(cs, filters)
    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/policy_evaluation_{a.date}.md").write_text(build_report(ev, filters, rm, a.date), encoding="utf-8")
    print(ev.groupby("policy")["pass"].sum().to_string())


if __name__ == "__main__":
    main()
