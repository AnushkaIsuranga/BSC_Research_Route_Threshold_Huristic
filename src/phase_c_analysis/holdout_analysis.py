"""Analysis of the policy_v2 held-out run (PHASE_A_HOLDOUT_PROTOCOL.md). Run only on the complete result file.

Reads outputs/phase_a_holdout/results.jsonl (never modifies it). Writes
  outputs/phase_a_holdout/analysis/cell_summary.csv, policy_cells.csv, hypotheses.json
  reports/holdout_results_<date>.md

Usage: python -m src.phase_c_analysis.holdout_analysis [--date 2026-10-10]
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.phase_b_router.policy import get_routing_decision
from src.phase_c_analysis.arm_analysis import LATENCY_SLA_MS, RECALL_SLA, TABLES, cell, cell_summary, fmt_ms, md_table

HO = Path("outputs/phase_a_holdout")
OUT = HO / "analysis"
T_FROZEN = 0.1                      # policy_v2 threshold, fixed by the protocol before any held-out query
ARMS = ["forced-exact", "forced-hnsw", "iterative-relaxed"]
SHORT = {"forced-exact": "FE", "forced-hnsw": "FH", "iterative-relaxed": "IR"}
N_VEC = 20
POLICIES = {"P1": "P1 v1 matrix (policy.py + phase_a_v1/thresholds.json)", "P4": "P4 always forced-exact", "P5": "P5 always forced-hnsw",
            "P6": "P6 always iterative-relaxed", "policy_v2": f"policy_v2 (forced-exact if s < {T_FROZEN} else iterative-relaxed)"}


def load():
    rows = [json.loads(ln) for ln in (HO / "results.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    df = pd.DataFrame(rows)
    rp = HO / "resumes.jsonl"
    resumes = [json.loads(ln) for ln in rp.read_text(encoding="utf-8").splitlines() if ln.strip()] if rp.exists() else []
    df["post_resume"] = (df["timestamp"] >= resumes[0]["resumed"]) if resumes else False
    df["valid"] = df["error"].isna() & df["recall"].notna() & df["latency_ms"].notna()
    filters = json.loads((HO / "filters.json").read_text(encoding="utf-8"))
    meta = json.loads((HO / "run_meta.json").read_text(encoding="utf-8"))
    return df, filters, meta, resumes


def policy_arm(policy, table, s):
    if policy == "P1":
        th = json.loads(Path("outputs/phase_a_v1/thresholds.json").read_text(encoding="utf-8"))
        return {"pre-filter": "forced-exact", "post-filter": "forced-hnsw"}[get_routing_decision(table, s, th)]
    if policy == "P4":
        return "forced-exact"
    if policy == "P5":
        return "forced-hnsw"
    if policy == "P6":
        return "iterative-relaxed"
    return "forced-exact" if s < T_FROZEN else "iterative-relaxed"


def evaluate(cs, filters):
    rows = []
    for p in POLICIES:
        for t in TABLES:
            for f in filters:
                fid, s = f["filter_id"], f["selectivity"]
                arm = policy_arm(p, t, s)
                c = cell(cs, t, fid, arm)
                complete = bool(c["n_valid"] == N_VEC)
                rec_ok = bool(c["n_valid"] > 0 and c["mean_recall"] >= RECALL_SLA - 1e-12)
                lat_ok = bool(c["n_valid"] > 0 and c["median_latency_ms"] <= LATENCY_SLA_MS)
                rows.append({"policy": p, "table": t, "filter_id": fid, "selectivity": s, "arm": arm, "n_valid": int(c["n_valid"]),
                             "mean_recall": c["mean_recall"], "median_latency_ms": c["median_latency_ms"], "recall_fail": not rec_ok,
                             "latency_fail": not lat_ok, "all_vectors_valid": complete, "pass": rec_ok and lat_ok and complete})
    return pd.DataFrame(rows)


def build_report(df, filters, meta, resumes, cs, ev, H, rep_date):
    sel = {f["filter_id"]: f["selectivity"] for f in filters}
    fids = [f["filter_id"] for f in filters]
    L = []
    w = L.append
    w(f"# policy_v2 held-out results — {rep_date}\n")
    w("**[V]** = computed by `src/phase_c_analysis/holdout_analysis.py` from `outputs/phase_a_holdout/results.jsonl`. **[I]** = interpretation. Protocol: `PHASE_A_HOLDOUT_PROTOCOL.md` (frozen in `fe06e9b`); `T = 0.1` was fixed before any held-out query and is not re-tuned here.\n")
    w("Provenance [V]: run commit `%s`, pgvector %s, PostgreSQL %s, seed %s, k=%s, ef_search=%s, server settings %s." % (
        meta["git_commit"][:7], meta["pgvector_version"], meta["pg_version"].split()[0], meta["seed"], meta["k"], meta["hnsw_ef_search"], json.dumps(meta["server_settings"])))
    w("")
    w("## 1. Headline: H7\n")
    w(f"**H7 — policy_v2 passes both SLAs in all 25 held-out cells: {'HOLDS' if H['H7']['holds'] else 'FAILS'}** ({H['H7']['n_pass']} of 25 cells pass). [V]\n")
    if H["H7"]["failing"]:
        rows = [[x.table, x.filter_id, f"{x.selectivity:.5f}", SHORT[x.arm], f"{x.mean_recall:.3f}", fmt_ms(x.median_latency_ms), x.n_valid,
                 ("recall " if x.recall_fail else "") + ("latency" if x.latency_fail else "") + ("" if x.all_vectors_valid else " invalid-vectors")] for x in H["H7"]["failing"].itertuples()]
        w("Failing cells (policy_v2):\n")
        w(md_table(["table", "filter", "sel", "arm used", "mean recall", "median ms", "valid vectors", "reason"], rows))
        w("")

    w("## 2. Completeness\n")
    exp = len(TABLES) * len(filters) * N_VEC * len(ARMS)
    keys = df.groupby(["table", "filter_id", "arm", "vector_idx"]).size()
    w(f"- Rows expected {exp}, written **{len(df)}**, unique keys {len(keys)}, max multiplicity {int(keys.max())}. [V]")
    w(f"- Rows with an error/timeout: **{int(df['error'].notna().sum())}**; rows without valid recall/latency: {int((~df['valid']).sum())}; `plan_as_intended == false`: **%d**. [V]" % int((df["plan_as_intended"] == False).sum()))  # noqa: E712
    n_post = int(df["post_resume"].sum())
    w(f"- Resumes: {len(resumes)}; rows written after a resume: **{n_post}**. [V]")
    w("- Vectors: 0-based line indices %s-%s of tests.jsonl; SHA-256 of the 20 lines `%s`. [V]" % (meta["vector_indices"][0], meta["vector_indices"][-1], meta["vectors_sha256"]))
    mn = HO / "machine_notes.txt"
    if mn.exists():
        w("- Machine notes recorded outside the run (kernel CPU seconds and host load at start/end): `outputs/phase_a_holdout/machine_notes.txt`:\n")
        w("```\n" + mn.read_text(encoding="utf-8").strip() + "\n```")
    w("")
    rows = [[a, len(df[df.arm == a]), int(df[df.arm == a]["error"].notna().sum()), int((df[df.arm == a]["plan_as_intended"] == False).sum()),  # noqa: E712
             ", ".join(f"{k}:{n}" for k, n in df[df.arm == a]["scan_node"].value_counts().items())] for a in ARMS]
    w(md_table(["arm", "rows", "errors", "plan_as_intended=false", "scan nodes"], rows))
    w("")

    w("## 3. Per-cell results (arm x table x filter)\n")
    w("Mean/min recall@10 over the 20 vectors; median rows returned; median latency (median of per-vector medians), IQR; scan nodes. CSV: `outputs/phase_a_holdout/analysis/cell_summary.csv`. [V]\n")
    for a in ARMS:
        w(f"### Arm: {a}\n")
        rows = []
        for t in TABLES:
            for f in fids:
                c = cell(cs, t, f, a)
                rows.append([t.replace("hm_clothes_", "T"), f, f"{sel[f]:.5f}", f"{c['mean_recall']:.3f}", f"{c['min_recall']:.2f}", f"{c['median_rows_returned']:.0f}",
                             fmt_ms(c["median_latency_ms"]), fmt_ms(c["latency_iqr_ms"]), c["scan_nodes"] + (f" (post-resume {c['n_post_resume_rows']})" if c["n_post_resume_rows"] else "")])
        w(md_table(["table", "filter", "sel", "mean rec", "min rec", "med rows", "med lat ms", "IQR ms", "scan nodes"], rows))
        w("")

    w("## 4. Policies on the 25 held-out cells\n")
    rows = []
    for p, lab in POLICIES.items():
        x = ev[ev.policy == p]
        rows.append([lab, f"**{int(x['pass'].sum())}** / 25", int(x.recall_fail.sum()), int(x.latency_fail.sum()), int((x.recall_fail & x.latency_fail).sum()), int((~x['all_vectors_valid']).sum())])
    w(md_table(["policy", "pass both SLAs", "recall fail", "latency fail", "both", "cells with invalid vectors"], rows))
    w("")
    rows = []
    for p in POLICIES:
        x = ev[ev.policy == p]
        rows.append([p] + [f"{int(x[x.table == t]['pass'].sum())}/5" for t in TABLES])
    w(md_table(["policy"] + TABLES, rows))
    w("")
    w("Route per held-out filter under each policy (policy_v2 and P1 vary only through selectivity and, for P1, the table tier) [V]:\n")
    rows = []
    for f in fids:
        x = ev[(ev.filter_id == f) & (ev.policy == "policy_v2")].iloc[0]
        p1 = ev[(ev.filter_id == f) & (ev.policy == "P1")]
        rows.append([f, f"{sel[f]:.5f}", SHORT[x.arm], "/".join(sorted({SHORT[a] for a in p1.arm}))])
    w(md_table(["filter", "sel", "policy_v2 arm", "P1 arm(s) over tables"], rows))
    w("")
    w("### Failing cells per policy\n")
    for p, lab in POLICIES.items():
        x = ev[(ev.policy == p) & (~ev["pass"])]
        w(f"**{lab}** — {len(x)} failing cell(s)")
        for f in fids:
            y = x[x.filter_id == f]
            if len(y):
                w(f"- {f} ({sel[f]:.5f}): " + ", ".join(f"{r.table.replace('hm_clothes_', 'T')}:{'RL' if r.recall_fail and r.latency_fail else 'R' if r.recall_fail else 'L' if r.latency_fail else 'INV'}({r.mean_recall:.2f}/{r.median_latency_ms:.0f}ms)" for r in y.itertuples()))
        if x.empty:
            w("- none")
        w("")

    w("## 5. Hypotheses H7-H9\n")
    w(f"**H7** policy_v2 passes all 25 held-out cells: **{'HOLDS' if H['H7']['holds'] else 'FAILS'}** ({H['H7']['n_pass']}/25). [V]\n")
    h8 = H["H8"]
    w(f"**H8** P6 (always iterative) fails recall in >= 1 held-out cell on hm_clothes_100 at s <= 0.03: **{'HOLDS' if h8['holds'] else 'FAILS'}**. Cells covered (hm_clothes_100, s <= 0.03): " + "; ".join(f"{f} (s={s:.5f}): iterative-relaxed mean recall {r:.3f}" for f, s, r in h8["cells"]) + ". [V]\n")
    h9 = H["H9"]
    w(f"**H9** policy_v2 passes more held-out cells than P1: **{'HOLDS' if h9['holds'] else 'FAILS'}** (policy_v2 {h9['v2']} vs P1 {h9['p1']} of 25). [V]\n")
    w(md_table(["H", "verdict"], [["H7", "holds" if H["H7"]["holds"] else "fails"], ["H8", "holds" if h8["holds"] else "fails"], ["H9", "holds" if h9["holds"] else "fails"]]))
    w("")

    w("## 6. Combined picture (in-sample and held-out kept separate)\n")
    w("In-sample = the 65 cells of the three-arm run (`reports/policy_evaluation_2026-10-10.md`; P1 and policy_v2 = P8 with T = 0.1 evaluated there; policy_v2's T was fitted on these cells). Held-out = the 25 cells above, tested once with T fixed in advance. The two sets are not independent samples of one population (same tables, same vector pool), so the combined row is a convenience, not an overall estimate. [V]\n")
    ins = pd.read_csv("outputs/phase_a_arms/analysis/policy_evaluation_cells.csv")
    mapping = {"P1": "P1", "P4": "P4", "P5": "P5", "P6": "P6", "policy_v2": "P8_0.1"}
    rows = []
    for p, lab in POLICIES.items():
        a = int(ins[ins.policy == mapping[p]]["pass"].sum())
        b = int(ev[ev.policy == p]["pass"].sum())
        rows.append([lab, f"{a} / 65 (in-sample)", f"{b} / 25 (held-out)", f"{a + b} / 90"])
    w(md_table(["policy", "in-sample", "held-out", "combined"], rows))
    w("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    a = ap.parse_args()
    df, filters, meta, resumes = load()
    exp = len(TABLES) * len(filters) * N_VEC * len(ARMS)
    if len(df) != exp:
        raise SystemExit(f"refusing to analyse partial data: {len(df)} of {exp} rows")
    sel = {f["filter_id"]: f["selectivity"] for f in filters}
    cs = cell_summary(df, sel)
    OUT.mkdir(parents=True, exist_ok=True)
    cs.to_csv(OUT / "cell_summary.csv", index=False)
    ev = evaluate(cs, filters)
    ev.to_csv(OUT / "policy_cells.csv", index=False)
    v2 = ev[ev.policy == "policy_v2"]
    h8_cells = [(r.filter_id, r.selectivity, cell(cs, "hm_clothes_100", r.filter_id, "iterative-relaxed")["mean_recall"])
                for r in v2[v2.table == "hm_clothes_100"].itertuples() if r.selectivity <= 0.03]
    H = {"H7": {"holds": bool(v2["pass"].all()), "n_pass": int(v2["pass"].sum()), "failing": v2[~v2["pass"]]},
         "H8": {"holds": any(r < RECALL_SLA - 1e-12 for *_, r in h8_cells), "cells": h8_cells},
         "H9": {"holds": int(v2["pass"].sum()) > int(ev[ev.policy == "P1"]["pass"].sum()), "v2": int(v2["pass"].sum()), "p1": int(ev[ev.policy == "P1"]["pass"].sum())}}
    (OUT / "hypotheses.json").write_text(json.dumps({k: {kk: (vv if not isinstance(vv, pd.DataFrame) else vv.to_dict("records")) for kk, vv in v.items()} for k, v in H.items()}, indent=2, default=str), encoding="utf-8")
    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/holdout_results_{a.date}.md").write_text(build_report(df, filters, meta, resumes, cs, ev, H, a.date), encoding="utf-8")
    print(f"wrote reports/holdout_results_{a.date}.md; H7 {'holds' if H['H7']['holds'] else 'FAILS'} ({H['H7']['n_pass']}/25); "
          f"H8 {'holds' if H['H8']['holds'] else 'fails'}; H9 {'holds' if H['H9']['holds'] else 'fails'}")


if __name__ == "__main__":
    main()
