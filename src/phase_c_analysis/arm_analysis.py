"""Analysis of the H&M three-arm danger-zone run (PHASE_A_ARMS_PROTOCOL.md, Amendments 1 and 2).

Reads outputs/phase_a_arms/results.jsonl (never modifies it) and writes
  outputs/phase_a_arms/analysis/cell_summary.csv, route_map.csv, hypotheses.json,
  outputs/phase_a_arms/analysis/recall_vs_selectivity.png, latency_vs_selectivity.png
  reports/arms_results_<date>.md

Usage: python -m src.phase_c_analysis.arm_analysis [--date 2026-10-10]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

AA = Path("outputs/phase_a_arms")
OUT = AA / "analysis"
ARMS = ["planner-default", "forced-exact", "forced-hnsw", "iterative-relaxed", "iterative-strict"]
CAND = ["forced-exact", "forced-hnsw", "iterative-relaxed"]          # tie-break order, arms 2-4
TABLES = ["hm_clothes_0", "hm_clothes_25", "hm_clothes_50", "hm_clothes_75", "hm_clothes_100"]
ABBR = {"forced-exact": "FE", "forced-hnsw": "FH", "iterative-relaxed": "IR"}
RECALL_SLA, LATENCY_SLA_MS = 0.9, 500.0
N_VEC = 20
ORIGINAL_FILTERS = ["ctl", "gap1", "gap2", "gap3", "gap4", "idx1", "idx2", "idx3"]   # the 8 filters of the frozen protocol
V2_IDS = {"lo1": "f_000", "lo2": "f_006", "lo3": "f_016", "lo4": "f_028", "lo5": "f_037",
          "ctl": "f_040", "idx1": "f_041", "idx2": "f_042", "idx3": "f_043"}
# colours: reference palette, slots 1-5 in fixed order (validated: all pass, contrast WARN -> legend + markers + tables)
STYLE = {"forced-exact": ("#2a78d6", "o", "-"), "forced-hnsw": ("#eb6834", "s", "-"), "iterative-relaxed": ("#1baf7a", "^", "-"),
         "planner-default": ("#eda100", "D", "--"), "iterative-strict": ("#e87ba4", "v", "--")}
INK, INK2, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"


# ---------------------------------------------------------------- loading
def load():
    rows = [json.loads(ln) for ln in (AA / "results.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    df = pd.DataFrame(rows)
    df["row_idx"] = range(len(df))
    resumes = [json.loads(ln) for ln in (AA / "resumes.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    df["post_resume"] = df["timestamp"] >= resumes[0]["resumed"] if resumes else False
    df["valid"] = df["error"].isna() & df["recall"].notna() & df["latency_ms"].notna()
    filters = json.loads((AA / "filters.json").read_text(encoding="utf-8"))
    meta = json.loads((AA / "run_meta.json").read_text(encoding="utf-8"))
    return df, filters, meta, resumes


def fmt_ms(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x:.2f}" if x < 10 else f"{x:.1f}" if x < 1000 else f"{x:.0f}"


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------- (b) cell summary
def cell_summary(df, sel):
    recs = []
    for (t, f, a), x in df.groupby(["table", "filter_id", "arm"]):
        v = x[x["valid"]]
        lat = v["latency_ms"]
        recs.append({
            "table": t, "filter_id": f, "selectivity": sel[f], "arm": a, "n_rows": len(x), "n_valid": len(v),
            "mean_recall": v["recall"].mean() if len(v) else float("nan"),
            "min_recall": v["recall"].min() if len(v) else float("nan"),
            "frac_below_0.9": float((v["recall"] < RECALL_SLA - 1e-12).mean()) if len(v) else float("nan"),
            "median_rows_returned": v["rows_returned"].median() if len(v) else float("nan"),
            "min_rows_returned": v["rows_returned"].min() if len(v) else float("nan"),
            "median_latency_ms": lat.median() if len(v) else float("nan"),
            "latency_q25_ms": lat.quantile(0.25) if len(v) else float("nan"),
            "latency_q75_ms": lat.quantile(0.75) if len(v) else float("nan"),
            "latency_iqr_ms": (lat.quantile(0.75) - lat.quantile(0.25)) if len(v) else float("nan"),
            "scan_nodes": ", ".join(f"{k}:{n}" for k, n in x["scan_node"].value_counts().items()),
            "plan_as_intended_false": int((x["plan_as_intended"] == False).sum()),  # noqa: E712
            "n_post_resume_rows": int(x["post_resume"].sum()),
            "median_shared_read_blocks": v["shared_read_blocks"].median() if len(v) else float("nan"),
        })
    cs = pd.DataFrame(recs)
    cs["t_order"] = cs["table"].map({t: i for i, t in enumerate(TABLES)})
    cs = cs.sort_values(["arm", "t_order", "selectivity"]).drop(columns="t_order").reset_index(drop=True)
    return cs


def cell(cs, t, f, a):
    r = cs[(cs.table == t) & (cs.filter_id == f) & (cs.arm == a)]
    return r.iloc[0]


# ---------------------------------------------------------------- (c) hypotheses
def hypotheses(cs, filters):
    fids = [f["filter_id"] for f in filters]
    H = {}
    # H1
    per_t = {}
    for t in ("hm_clothes_75", "hm_clothes_100"):
        cells = [(f, cell(cs, t, f, "forced-hnsw")["mean_recall"]) for f in ("idx1", "idx2", "idx3")]
        per_t[t] = {"cells": cells, "any_below": any(r < RECALL_SLA for _, r in cells)}
    H["H1"] = {"holds": all(v["any_below"] for v in per_t.values()), "per_table": per_t}
    # H2 (all 65 cells, and the original 40)
    def fails(filter_list):
        out = []
        for t in TABLES:
            for f in filter_list:
                c = cell(cs, t, f, "iterative-relaxed")
                if c["n_valid"] < N_VEC or c["mean_recall"] < RECALL_SLA - 1e-12:
                    out.append((t, f, c["mean_recall"], int(c["n_valid"])))
        return out
    f65, f40 = fails(fids), fails(ORIGINAL_FILTERS)
    H["H2"] = {"holds_all_65": not f65, "failing_cells_65": f65, "holds_original_40": not f40, "failing_cells_40": f40}
    # H3
    h3 = [(t, f, cell(cs, t, f, "forced-exact")["median_latency_ms"]) for t in TABLES for f in ("idx1", "idx2", "idx3")]
    H["H3"] = {"holds": any(l > LATENCY_SLA_MS for *_, l in h3), "cells": h3, "n_over_500": sum(1 for *_, l in h3 if l > LATENCY_SLA_MS)}
    # H4
    h4 = []
    for t in TABLES:
        for f in ("idx1", "idx2", "idx3"):
            ir, fe = cell(cs, t, f, "iterative-relaxed")["median_latency_ms"], cell(cs, t, f, "forced-exact")["median_latency_ms"]
            h4.append((t, f, ir, fe, ir < fe))
    H["H4"] = {"holds": all(x[4] for x in h4), "n_true": sum(1 for x in h4 if x[4]), "cells": h4}
    # H5
    h5 = [(t, f, cell(cs, t, f, "forced-exact")["median_latency_ms"]) for t in TABLES for f in ("lo1", "lo2", "lo3")]
    H["H5"] = {"holds": all(l <= LATENCY_SLA_MS for *_, l in h5), "cells": h5,
               "exceptions": [x for x in h5 if x[2] > LATENCY_SLA_MS]}
    # H6
    h6 = []
    for t in TABLES:
        for f in ("lo1", "lo2"):
            c = cell(cs, t, f, "iterative-relaxed")
            h6.append((t, f, c["mean_recall"], c["median_rows_returned"], c["min_rows_returned"],
                       bool(c["mean_recall"] < RECALL_SLA - 1e-12 or c["median_rows_returned"] < 10)))
    H["H6"] = {"holds": any(x[5] for x in h6), "n_true": sum(1 for x in h6 if x[5]), "cells": h6}
    return H


# ---------------------------------------------------------------- (d) route map
def route_map(cs, filters):
    recs = []
    for t in TABLES:
        for f in filters:
            fid = f["filter_id"]
            cands = {a: cell(cs, t, fid, a) for a in CAND}
            ok = [a for a in CAND if cands[a]["n_valid"] == N_VEC and cands[a]["mean_recall"] >= RECALL_SLA - 1e-12]
            rec = {"table": t, "filter_id": fid, "selectivity": f["selectivity"]}
            if ok:
                best = min(ok, key=lambda a: (cands[a]["median_latency_ms"], CAND.index(a)))
                lat = cands[best]["median_latency_ms"]
                rec.update({"route": best, "route_latency_ms": lat, "route_recall": cands[best]["mean_recall"],
                            "status": "route" if lat <= LATENCY_SLA_MS else "no route meets both SLAs (latency)"})
            else:
                rec.update({"route": None, "route_latency_ms": None, "route_recall": None,
                            "status": "no route meets both SLAs (recall)"})
            if rec["status"] != "route":
                valid = [a for a in CAND if cands[a]["n_valid"] > 0]
                br = max(valid, key=lambda a: (cands[a]["mean_recall"], -CAND.index(a)))
                bl = min(valid, key=lambda a: (cands[a]["median_latency_ms"], CAND.index(a)))
                rec.update({"best_recall_arm": br, "best_recall": cands[br]["mean_recall"], "best_recall_latency_ms": cands[br]["median_latency_ms"],
                            "best_latency_arm": bl, "best_latency_ms": cands[bl]["median_latency_ms"], "best_latency_recall": cands[bl]["mean_recall"]})
            for a in CAND:
                rec[f"{ABBR[a]}_recall"] = cands[a]["mean_recall"]
                rec[f"{ABBR[a]}_latency_ms"] = cands[a]["median_latency_ms"]
            recs.append(rec)
    return pd.DataFrame(recs)


# ---------------------------------------------------------------- (e) consistency with Phase A v2
def v2_consistency(df):
    v2 = {}
    multi = 0
    for ln in (Path("outputs/phase_a_v2/sweep_results.jsonl")).read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not (ln.startswith("{") and ln.endswith("}")):
            continue
        d = json.loads(ln)
        v2.setdefault((d["filter_id"], d["table_name"], d["query_vector_idx"]), []).append(d["scan_strategy"])
    for k, v in v2.items():
        multi += len(set(v)) > 1
    pd_rows = df[df.arm == "planner-default"]
    recs = []
    for fid, v2id in V2_IDS.items():
        for t in TABLES:
            sub = pd_rows[(pd_rows.filter_id == fid) & (pd_rows.table == t)]
            match = sum(1 for _, r in sub.iterrows() if v2.get((v2id, t, r["vector_idx"]), [None])[0] == r["scan_node"])
            nov2 = sum(1 for _, r in sub.iterrows() if (v2id, t, r["vector_idx"]) not in v2)
            recs.append({"filter_id": fid, "v2_id": v2id, "table": t, "n": len(sub), "match": match, "no_v2_row": nov2,
                         "new_nodes": ", ".join(f"{k}:{n}" for k, n in sub["scan_node"].value_counts().items()),
                         "v2_nodes": ", ".join(f"{k}:{n}" for k, n in pd.Series([v2.get((v2id, t, vi), ['-'])[0] for vi in range(N_VEC)]).value_counts().items())})
    return pd.DataFrame(recs), multi


# ---------------------------------------------------------------- (g) figures
def figures(cs, filters):
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "text.color": INK, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE, "grid.color": GRID})
    for kind in ("recall", "latency"):
        fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.6), sharex=True, sharey=True)
        for ax, t in zip(axes.flat, TABLES):
            ax.grid(True, lw=0.6)
            for a in ARMS[::-1]:   # candidates drawn last (on top)
                s = cs[(cs.table == t) & (cs.arm == a)].sort_values("selectivity")
                col, mk, ls = STYLE[a]
                y = s["mean_recall"] if kind == "recall" else s["median_latency_ms"]
                ax.plot(s["selectivity"], y, color=col, marker=mk, ls=ls, lw=2, ms=5.5, mec=SURFACE, mew=1.0, label=a, zorder=3 if a in CAND else 2)
            ax.set_xscale("log")
            if kind == "recall":
                ax.axhline(RECALL_SLA, color=INK2, lw=1, ls=":")
                ax.set_ylim(-0.03, 1.06)
            else:
                ax.axhline(LATENCY_SLA_MS, color=INK2, lw=1, ls=":")
                ax.set_yscale("log")
            ax.set_title(t, loc="left", fontsize=10, color=INK)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
        for ax in axes[1]:
            ax.set_xlabel("selectivity (fraction of rows matching the filter, log scale)")
        for ax in axes[:, 0]:
            ax.set_ylabel("mean recall@10 (20 vectors)" if kind == "recall" else "median latency, ms (log)")
        leg_ax = axes.flat[5]
        leg_ax.axis("off")
        h, l = axes.flat[0].get_legend_handles_labels()
        order = [l.index(a) for a in ARMS]
        leg_ax.legend([h[i] for i in order], [l[i] for i in order], loc="upper left", frameon=False, fontsize=10, title="arm (solid = route candidates,\ndashed = reported only)")
        thr = "recall = 0.9" if kind == "recall" else "500 ms"
        leg_ax.text(0.0, 0.18, f"Dotted line: {thr}.\nOne point per filter (13 filters, selectivity 0.00012-0.47).\nTable view: cell_summary.csv.", transform=leg_ax.transAxes, fontsize=9, color=INK2, va="top")
        fig.suptitle(("Recall@10" if kind == "recall" else "Latency") + " vs selectivity, H&M tables, k=10, ef_search=40", x=0.01, ha="left", fontsize=12, color=INK)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(OUT / f"{kind}_vs_selectivity.png", dpi=150, facecolor=SURFACE)
        plt.close(fig)


# ---------------------------------------------------------------- report
def build_report(df, filters, meta, resumes, cs, H, rm, cons, multi_v2, report_date):
    sel = {f["filter_id"]: f["selectivity"] for f in filters}
    fids = [f["filter_id"] for f in filters]
    L = []
    w = L.append
    w(f"# H&M three-arm danger-zone run: results — {report_date}\n")
    w("**[V]** = computed from `outputs/phase_a_arms/results.jsonl` by `src/phase_c_analysis/arm_analysis.py`. **[I]** = my interpretation. "
      "The protocol (`PHASE_A_ARMS_PROTOCOL.md`, Amendments 1 and 2) was frozen before the run; the hypotheses and the decision rule are applied exactly as written there.\n")
    w("Provenance [V]: run commit `%s`, pgvector %s, PostgreSQL %s, seed %s, k=%s, ef_search=%s, `jit=off`, server settings %s. Result file contains one row per (table, filter, vector, arm)."
      % (meta["git_commit"][:7], meta["pgvector_version"], meta["pg_version"].split()[0], meta["seed"], meta["k"], meta["hnsw_ef_search"], json.dumps(meta["server_settings"])))
    w("")

    # (a)
    w("## (a) Completeness\n")
    exp = len(TABLES) * len(filters) * N_VEC * len(ARMS)
    keys = df.groupby(["table", "filter_id", "arm", "vector_idx"]).size()
    w(f"- Rows expected {exp}, written **{len(df)}**, unique (table, filter, arm, vector) keys {len(keys)}, max multiplicity {int(keys.max())}. [V]")
    w(f"- Rows with a non-null `error` (including statement timeouts): **{int(df['error'].notna().sum())}**; rows without a valid recall/latency: {int((~df['valid']).sum())}. [V]")
    w("- `plan_as_intended == false` rows: **%d**. The pre-flight (`preflight.json`, 260 arm 2-5 checks) had 0 failures. [V]" % int((df["plan_as_intended"] == False).sum()))  # noqa: E712
    w("")
    rows = []
    for a in ARMS:
        x = df[df.arm == a]
        rows.append([a, len(x), int(x["error"].notna().sum()), int((x["plan_as_intended"] == False).sum()),  # noqa: E712
                     ", ".join(f"{k}:{n}" for k, n in x["scan_node"].value_counts().items())])
    w(md_table(["arm", "rows", "errors/timeouts", "plan_as_intended=false", "scan nodes (all rows)"], rows))
    w("")
    n_post = int(df["post_resume"].sum())
    w(f"- **Crash and resume.** The run stopped once when a PostgreSQL backend exited with code 2 and the server did crash recovery (container never restarted, OOMKilled=false); the script stopped itself without recording a row and was resumed (`resumes.jsonl`: resumed 2026-10-10T09:35:22Z with 5609 rows present). "
      f"**{n_post} rows were written after the resume** (row_idx >= {len(df) - n_post}); they are flagged `post_resume` in the analysis. They fall in these (table, filter) cells: "
      + ", ".join(f"{t}/{f} ({int(n)})" for (t, f), n in df[df.post_resume].groupby(["table", "filter_id"]).size().items()) + ". [V]")
    w("- The shared buffers were cold after crash recovery [I]; rows around the resume point may include a cold-cache effect on latency (not on recall).")
    w("- The aborted first and second starts are **excluded**: `results_aborted_frozen_arms.jsonl` (42 rows, frozen arm settings, see Amendment 2) was not read by this analysis. [V]")
    w("")
    w("Cross-table spread of forced-exact median latency (ms) for the same filter, as a cache/noise indicator [V]:\n")
    rows = []
    for f in fids:
        rows.append([f, f"{sel[f]:.5f}"] + [fmt_ms(cell(cs, t, f, "forced-exact")["median_latency_ms"]) for t in TABLES])
    w(md_table(["filter", "selectivity"] + TABLES, rows))
    w("")

    # (b)
    w("## (b) Per (table, filter, arm) summary\n")
    w("Columns: mean/min recall@10 over the 20 vectors; fraction of vectors with recall < 0.9; median rows returned (of 10); median latency = median of the 20 per-vector medians (each the median of 5 timed `EXPLAIN ANALYZE` runs); IQR of latency over the 20 vectors; scan node counts. "
      "Full data with more columns: `outputs/phase_a_arms/analysis/cell_summary.csv`. [V]\n")
    for a in ARMS:
        w(f"### Arm: {a}\n")
        rows = []
        for t in TABLES:
            for f in fids:
                c = cell(cs, t, f, a)
                rows.append([t.replace("hm_clothes_", "T"), f, f"{sel[f]:.5f}", f"{c['mean_recall']:.3f}", f"{c['min_recall']:.2f}", f"{c['frac_below_0.9']:.2f}",
                             f"{c['median_rows_returned']:.0f}", fmt_ms(c["median_latency_ms"]), fmt_ms(c["latency_iqr_ms"]), c["scan_nodes"] + (f" (post-resume rows {c['n_post_resume_rows']})" if c["n_post_resume_rows"] else "")])
        w(md_table(["table", "filter", "sel", "mean rec", "min rec", "frac<0.9", "med rows", "med lat ms", "IQR ms", "scan nodes"], rows))
        w("")

    # (c)
    w("## (c) Hypotheses H1-H6 (operationalisations as written in the protocol)\n")
    h1 = H["H1"]
    w(f"**H1 — forced-hnsw mean recall@10 < 0.90 at >=1 index-scan point on hm_clothes_75 and on hm_clothes_100: {'HOLDS' if h1['holds'] else 'FAILS'}.** [V]")
    for t, v in h1["per_table"].items():
        w(f"- {t}: forced-hnsw mean recall at idx1/idx2/idx3 = " + " / ".join(f"{r:.3f}" for _, r in v["cells"]) + f" → {'at least one < 0.90' if v['any_below'] else 'none < 0.90'}.")
    w("")
    h2 = H["H2"]
    w(f"**H2 — iterative-relaxed mean recall@10 >= 0.90 at every point on every table: {'HOLDS' if h2['holds_all_65'] else 'FAILS'} over all 65 (table, filter) cells; {'HOLDS' if h2['holds_original_40'] else 'FAILS'} over the 40 cells of the 8 originally frozen filters.** [V]")
    if h2["failing_cells_65"]:
        w("Failing cells (table, filter, mean recall, valid vectors): " + "; ".join(f"{t}/{f} {r:.3f} (n={n})" for t, f, r, n in h2["failing_cells_65"]))
    else:
        w("No cell below 0.90; no cell with fewer than 20 valid vectors.")
    mn = cs[cs.arm == "iterative-relaxed"]["mean_recall"].min()
    w(f"Lowest iterative-relaxed cell mean recall: {mn:.3f}. Lowest single-vector recall over all iterative-relaxed cells: {cs[cs.arm == 'iterative-relaxed']['min_recall'].min():.2f}.\n")
    h3 = H["H3"]
    w(f"**H3 — forced-exact median latency > 500 ms at >= 0.329 on at least one table: {'HOLDS' if h3['holds'] else 'FAILS'}** ({h3['n_over_500']} of 15 (table, idx1-3) cells exceed 500 ms). [V]\n")
    rows = [[t, f, fmt_ms(l), "yes" if l > LATENCY_SLA_MS else "no"] for t, f, l in h3["cells"]]
    w(md_table(["table", "filter", "forced-exact median ms", "> 500"], rows))
    w("")
    h4 = H["H4"]
    w(f"**H4 — iterative-relaxed median latency < forced-exact median latency at >= 0.329: {'HOLDS' if h4['holds'] else 'FAILS'}** (true in {h4['n_true']} of 15 cells). [V]\n")
    rows = [[t, f, fmt_ms(ir), fmt_ms(fe), "yes" if ok else "NO"] for t, f, ir, fe, ok in h4["cells"]]
    w(md_table(["table", "filter", "iterative-relaxed ms", "forced-exact ms", "IR < FE"], rows))
    w("")
    h5 = H["H5"]
    w(f"**H5 — forced-exact median latency <= 500 ms in every (table, lo1..lo3) cell: {'HOLDS' if h5['holds'] else 'FAILS'}.** [V]")
    w("Cells: " + "; ".join(f"{t}/{f} {fmt_ms(l)} ms" for t, f, l in h5["cells"]))
    if h5["exceptions"]:
        w("Cells above 500 ms: " + "; ".join(f"{t}/{f} {fmt_ms(l)}" for t, f, l in h5["exceptions"]))
    w("")
    h6 = H["H6"]
    w(f"**H6 — iterative-relaxed mean recall < 0.90 OR median rows_returned < 10 in at least one (table, lo1..lo2) cell: {'HOLDS' if h6['holds'] else 'FAILS'}** ({h6['n_true']} of 10 cells). [V]\n")
    rows = [[t, f, f"{r:.3f}", f"{mr:.0f}", f"{mn_:.0f}", "yes" if ok else "no"] for t, f, r, mr, mn_, ok in h6["cells"]]
    w(md_table(["table", "filter", "mean recall", "median rows", "min rows (any vector)", "criterion met"], rows))
    w("")
    w(md_table(["H", "verdict"], [["H1", "holds" if h1["holds"] else "fails"], ["H2 (65 cells / original 40)", f"{'holds' if h2['holds_all_65'] else 'fails'} / {'holds' if h2['holds_original_40'] else 'fails'}"],
                                  ["H3", "holds" if h3["holds"] else "fails"], ["H4", "holds" if h4["holds"] else f"fails ({h4['n_true']}/15 cells)"],
                                  ["H5", "holds" if h5["holds"] else "fails"], ["H6", "holds" if h6["holds"] else "fails"]]))
    w("")

    # (d)
    w("## (d) Route map (Amendment 1 decision rule)\n")
    w("Rule [V, from the protocol]: per (table, filter) cell, the route is the arm among forced-exact (FE), forced-hnsw (FH) and iterative-relaxed (IR) with the lowest median latency whose mean recall@10 >= 0.90 (all 20 vectors valid; ties FE, FH, IR). "
      "If none qualifies, or the chosen arm's median latency > 500 ms, the cell is \"no route meets both SLAs\". planner-default and iterative-strict are reported but are not candidates. Cell text: route and its median latency in ms.\n")
    rows = []
    for f in fids:
        r = [f, f"{sel[f]:.5f}"]
        for t in TABLES:
            x = rm[(rm.table == t) & (rm.filter_id == f)].iloc[0]
            r.append(("**NONE** " + x["status"].split("(")[-1].rstrip(")") ) if x["status"] != "route" else f"{ABBR[x['route']]} {fmt_ms(x['route_latency_ms'])}")
        rows.append(r)
    w(md_table(["filter", "selectivity"] + TABLES, rows))
    w("")
    cnt = rm["route"].fillna("none").value_counts()
    w("Route counts over the 65 cells [V]: " + ", ".join(f"{k}: {v}" for k, v in cnt.items()) + f"; cells with status \"route\": {int((rm.status == 'route').sum())}.")
    none = rm[rm.status != "route"]
    if len(none):
        w("\n\"No route meets both SLAs\" cells, with the best recall and the best latency reported separately [V]:\n")
        rows = [[x.table, x.filter_id, f"{x.selectivity:.5f}", x.status, f"{ABBR[x.best_recall_arm]} {x.best_recall:.3f} @ {fmt_ms(x.best_recall_latency_ms)} ms",
                 f"{ABBR[x.best_latency_arm]} {fmt_ms(x.best_latency_ms)} ms @ recall {x.best_latency_recall:.3f}"] for x in none.itertuples()]
        w(md_table(["table", "filter", "sel", "reason", "best recall (arm, recall @ latency)", "best latency (arm, latency @ recall)"], rows))
    else:
        w("\nNo cell is a \"no route meets both SLAs\" cell. [V]")
    w("")

    # (e)
    w("## (e) Consistency check: planner-default vs Phase A v2 plan choices\n")
    w(f"Shared filters: lo1-lo5 = f_000, f_006, f_016, f_028, f_037; ctl = f_040; idx1-3 = f_041-f_043 (v2 `outputs/phase_a_v2/sweep_results.jsonl`, vectors 0-19, first row per key; v2 keys with more than one distinct strategy: {multi_v2}). A match means the same first scan node. [V]\n")
    tot, mt = int(cons["n"].sum()), int(cons["match"].sum())
    w(f"Overall: **{mt} of {tot}** (table, filter, vector) planner-default plan choices equal the v2 scan strategy.\n")
    rows = []
    for fid in V2_IDS:
        c = cons[cons.filter_id == fid]
        rows.append([fid, V2_IDS[fid], f"{sel[fid]:.5f}", f"{int(c['match'].sum())}/{int(c['n'].sum())}", "; ".join(f"{r.table.replace('hm_clothes_', 'T')}: {r.new_nodes}" for r in c.itertuples())])
    w(md_table(["filter", "v2 id", "sel", "matches", "new run planner-default scan nodes per table"], rows))
    mis = cons[cons["match"] < cons["n"]]
    if len(mis):
        w("\nMismatching (filter, table) groups [V]: " + "; ".join(f"{r.filter_id}/{r.table} ({r.match}/{r.n}; new {r.new_nodes}; v2 {r.v2_nodes})" for r in mis.itertuples()))
    w("")

    # (f)
    w("## (f) Gap points 0.204-0.329\n")
    gp = ["ctl", "gap1", "gap2", "gap3", "gap4", "idx1"]
    kind = {"ctl": "control (equality)", "gap1": "gap, equality", "gap2": "gap, IN list", "gap3": "gap, IN list", "gap4": "gap, IN list", "idx1": "index-scan point (equality)"}
    w("Per filter, aggregated over the 5 tables (mean of the cell mean recalls; median of the cell median latencies); planner-default plan share over 5 tables x 20 vectors = 100 queries. [V]\n")
    rows = []
    for f in gp:
        pdsub = df[(df.filter_id == f) & (df.arm == "planner-default")]
        share = (pdsub.scan_node == "Index Scan").mean()
        r = [f, kind[f], f"{sel[f]:.5f}", f"{share * 100:.0f}% HNSW Index Scan / {(1 - share) * 100:.0f}% other"]
        for a in ARMS:
            x = cs[(cs.filter_id == f) & (cs.arm == a)]
            r.append(f"{x['mean_recall'].mean():.3f} / {fmt_ms(x['median_latency_ms'].median())}")
        rows.append(r)
    w(md_table(["filter", "type", "sel", "planner-default plan"] + [f"{a} (recall / ms)" for a in ARMS], rows))
    w("")
    w("Per table, planner-default share of HNSW Index Scan (of 20 vectors) and forced-hnsw mean recall [V]:\n")
    rows = []
    for f in gp:
        r = [f]
        for t in TABLES:
            pdsub = df[(df.filter_id == f) & (df.arm == "planner-default") & (df.table == t)]
            r.append(f"{int((pdsub.scan_node == 'Index Scan').sum())}/20 · FH rec {cell(cs, t, f, 'forced-hnsw')['mean_recall']:.3f}")
        rows.append(r)
    w(md_table(["filter"] + TABLES, rows))
    w("")

    # (h)
    w("## (h) What this does NOT show\n")
    for s in [
        "H&M only: five categorical columns, 105,100 rows per table, halfvec(2048) cosine HNSW (m=16, ef_construction=64). Nothing here is evidence about FinQA (vector(768), L2, JSONB metadata) or about the Phase D router.",
        "Fixed k=10 and `hnsw.ef_search`=40; `hnsw.max_scan_tuples` at its default 20000 and `hnsw.scan_mem_multiplier`=1. Other values were not tested here.",
        "Single machine, single Docker PostgreSQL 16.14 / pgvector 0.8.3 instance with `shared_buffers`=128MB, `work_mem`=4MB (the Phase A defaults, deliberately unchanged); latency conclusions describe this configuration, and exact plans in particular may be faster with more memory.",
        "20 query vectors (the Phase A v2 vectors) per cell; cell means over 20 vectors carry sampling uncertainty that is not quantified here, and no significance tests were run.",
        "Equality and IN-list filters on one column (plus the 8 originally frozen filters); no numeric ranges, no multi-column filters, no filter correlated with the query.",
        "Latency is the PostgreSQL `Execution Time` of `EXPLAIN ANALYZE` (median of 5 timed runs after 1 warm-up), not end-to-end application latency. The run crashed once and resumed (see (a)); rows after the resume may carry a cold-cache effect.",
        "`jit` was off and plans were pre-checked; arms 3-5 use `enable_sort=off` (Amendment 2). Results for those arms describe forced-HNSW plans, not what the planner would choose by itself.",
        "The run does not evaluate the Decision Matrix (`policy.py`); it only measures candidate routes. Any change to `policy.py` is a separate step.",
    ]:
        w(f"- {s}")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    df, filters, meta, resumes = load()
    sel = {f["filter_id"]: f["selectivity"] for f in filters}
    cs = cell_summary(df, sel)
    cs.to_csv(OUT / "cell_summary.csv", index=False)
    H = hypotheses(cs, filters)
    rm = route_map(cs, filters)
    rm.to_csv(OUT / "route_map.csv", index=False)
    (OUT / "hypotheses.json").write_text(json.dumps(H, indent=2, default=lambda o: None if (isinstance(o, float) and math.isnan(o)) else bool(o) if hasattr(o, "item") and isinstance(o.item(), bool) else float(o) if hasattr(o, "item") else str(o)), encoding="utf-8")
    cons, multi = v2_consistency(df)
    figures(cs, filters)
    report = build_report(df, filters, meta, resumes, cs, H, rm, cons, multi, a.date)
    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/arms_results_{a.date}.md").write_text(report, encoding="utf-8")
    print(f"wrote reports/arms_results_{a.date}.md, {OUT}/cell_summary.csv, route_map.csv, hypotheses.json, 2 PNGs")


if __name__ == "__main__":
    main()
