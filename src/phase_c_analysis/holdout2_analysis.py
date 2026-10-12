"""Analysis of the second held-out run (PHASE_A_HOLDOUT2_PROTOCOL.md). Run only on the complete result file.

Reuses the cell/policy machinery of holdout_analysis.py (module paths redirected to outputs/phase_a_holdout2) and evaluates
H10 (policy_v2 passes all 25 cells), H11 per filter (P1 fails >= 1 cell, with failure mode), H12 (P4 fails latency in every
cell with s >= 0.30; h2a/h2b reported as exploratory) plus per-policy pass counts.
Writes outputs/phase_a_holdout2/analysis/*.csv|json and reports/holdout2_results_<date>.md.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.phase_c_analysis import holdout_analysis as A
from src.phase_c_analysis.arm_analysis import LATENCY_SLA_MS, RECALL_SLA, TABLES, cell, cell_summary

HO = Path("outputs/phase_a_holdout2")
EXPLORATORY = {"h2a", "h2b"}
CONFIRMATORY_MIN_S = 0.30


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    a = ap.parse_args()
    A.HO, A.OUT = HO, HO / "analysis"
    df, filters, meta, resumes = A.load()
    exp = len(TABLES) * len(filters) * 20 * len(A.ARMS)
    if len(df) != exp:
        raise SystemExit(f"refusing to analyse partial data: {len(df)} of {exp} rows")
    sel = {f["filter_id"]: f["selectivity"] for f in filters}
    cs = cell_summary(df, sel)
    A.OUT.mkdir(parents=True, exist_ok=True)
    cs.to_csv(A.OUT / "cell_summary.csv", index=False)
    ev = A.evaluate(cs, filters)
    ev.to_csv(A.OUT / "policy_cells.csv", index=False)

    def mode(r):
        why = []
        if not r.all_vectors_valid:
            why.append("invalid vectors")
        if r.recall_fail:
            why.append(f"recall {r.mean_recall:.3f}")
        if r.latency_fail:
            why.append(f"latency {r.median_latency_ms:.0f} ms")
        return ", ".join(why)

    counts = {p: int(ev[ev.policy == p]["pass"].sum()) for p in A.POLICIES}
    conf = ev[~ev.filter_id.isin(EXPLORATORY)]
    counts_conf = {p: int(conf[conf.policy == p]["pass"].sum()) for p in A.POLICIES}
    v2 = ev[ev.policy == "policy_v2"]
    H10 = {"holds": bool(v2["pass"].all()), "n_pass": int(v2["pass"].sum()), "failing": [(r.table, r.filter_id, r.arm, mode(r)) for r in v2[~v2["pass"]].itertuples()]}
    p1 = ev[ev.policy == "P1"]
    H11 = {}
    for fid in [f["filter_id"] for f in filters]:
        sub = p1[p1.filter_id == fid]
        fails = sub[~sub["pass"]]
        H11[fid] = {"holds": bool(len(fails) >= 1), "n_fail": int(len(fails)), "exploratory": fid in EXPLORATORY,
                    "routes": {r.table: r.arm for r in sub.itertuples()}, "failing": [(r.table, r.arm, mode(r)) for r in fails.itertuples()]}
    p4 = ev[ev.policy == "P4"]
    big = p4[p4.selectivity >= CONFIRMATORY_MIN_S]
    H12 = {"holds": bool(big["latency_fail"].all()), "n_cells": int(len(big)), "n_latency_fail": int(big["latency_fail"].sum()),
           "not_failing": [(r.table, r.filter_id, round(r.median_latency_ms, 1)) for r in big.itertuples() if not r.latency_fail],
           "exploratory_cells": [(r.table, r.filter_id, round(r.median_latency_ms, 1), bool(r.latency_fail)) for r in p4[p4.selectivity < CONFIRMATORY_MIN_S].itertuples()]}
    out = {"policy_pass_counts_25": counts, "policy_pass_counts_confirmatory_15": counts_conf, "H10": H10, "H11": H11, "H12": H12}
    (A.OUT / "hypotheses.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    w = []
    w.append(f"# Second held-out results (policy_v2, selectivity 0.23-0.45), {a.date}\n")
    w.append("Computed by `src/phase_c_analysis/holdout2_analysis.py` from `outputs/phase_a_holdout2/results.jsonl` (1,500 rows). Protocol: `PHASE_A_HOLDOUT2_PROTOCOL.md` (tag `phase-a-holdout2-frozen-2026-10-12`). SLAs: mean recall@10 >= 0.90 and median latency <= 500 ms. A cell with any invalid vector counts as not passing.\n")
    w.append(f"Run: seed {meta['seed']}, table order {meta['table_order']}, commit `{meta['git_commit'][:7]}`, started {meta['started']}.\n")
    w.append("## Hypotheses\n")
    w.append(f"- **H10 (primary) policy_v2 passes all 25 cells: {'HOLDS' if H10['holds'] else 'FAILS'}** ({H10['n_pass']}/25)." + ("" if H10['holds'] else " Failing cells: " + "; ".join(f"{t} x {f} ({arm}): {m}" for t, f, arm, m in H10['failing'])))
    w.append("- **H11 per filter (P1 fails >= 1 of its 5 cells):**")
    for fid, h in H11.items():
        w.append(f"  - {fid} ({sel[fid]:.4f}){' [exploratory]' if h['exploratory'] else ''}: {'HOLDS' if h['holds'] else 'FAILS'}, {h['n_fail']}/5 cells fail; P1 routes {h['routes']}; failing: " + ("; ".join(f"{t} ({arm}): {m}" for t, arm, m in h['failing']) or "none"))
    w.append(f"- **H12 P4 fails latency in all {H12['n_cells']} cells with s >= 0.30: {'HOLDS' if H12['holds'] else 'FAILS'}** ({H12['n_latency_fail']}/{H12['n_cells']} fail)." + ("" if H12['holds'] else " Cells not failing: " + "; ".join(f"{t} x {f} ({ms} ms)" for t, f, ms in H12['not_failing'])))
    w.append("  - Exploratory (s < 0.30, no pass/fail claim): " + "; ".join(f"{t} x {f}: {ms} ms ({'fails' if fl else 'passes'} latency)" for t, f, ms, fl in H12['exploratory_cells']) + "\n")
    w.append("## Policy pass counts\n\n| policy | cells passed of 25 | of the 15 confirmatory cells (h2c-h2e) |\n|---|---|---|")
    for p in A.POLICIES:
        w.append(f"| {A.POLICIES[p]} | {counts[p]}/25 | {counts_conf[p]}/15 |")
    w.append("\n## Per-cell results (all policies' arms; mean recall@10, median latency ms)\n")
    for fid in [f["filter_id"] for f in filters]:
        w.append(f"**{fid}** (s = {sel[fid]:.5f}){' - exploratory' if fid in EXPLORATORY else ''}\n\n| table | forced-exact | forced-hnsw | iterative-relaxed | policy_v2 | P1 arm / pass |\n|---|---|---|---|---|---|")
        for t in TABLES:
            cells = {arm: cell(cs, t, fid, arm) for arm in A.ARMS}
            f = lambda c: f"{c['mean_recall']:.3f} / {c['median_latency_ms']:.1f}"
            p1r = p1[(p1.table == t) & (p1.filter_id == fid)].iloc[0]
            v2r = v2[(v2.table == t) & (v2.filter_id == fid)].iloc[0]
            w.append(f"| {t} | {f(cells['forced-exact'])} | {f(cells['forced-hnsw'])} | {f(cells['iterative-relaxed'])} | {'pass' if v2r['pass'] else 'FAIL'} ({v2r.arm}) | {p1r.arm}: {'pass' if p1r['pass'] else 'FAIL ' + mode(p1r)} |")
        w.append("")
    hl = HO / "host_load.json"
    if hl.exists():
        w.append("## Host load\n\n" + "; ".join(f"{s['event']} {s['utc'][11:19]}Z cpu% {[round(x) for x in s['cpu_total_pct_3_samples']]}" for s in json.loads(hl.read_text())['samples']) + "\n")
    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/holdout2_results_{a.date}.md").write_text("\n".join(w), encoding="utf-8")
    print(f"wrote reports/holdout2_results_{a.date}.md; H10 {'holds' if H10['holds'] else 'FAILS'} ({H10['n_pass']}/25); H12 {'holds' if H12['holds'] else 'FAILS'}; "
          f"H11 " + ", ".join(f"{k}:{'holds' if v['holds'] else 'FAILS'}" for k, v in H11.items()) + f"; pass counts {counts}")


if __name__ == "__main__":
    main()
