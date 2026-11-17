"""Phase H (Amendment 13, Section 6): Frozen confirmatory and descriptive analysis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import PROJECT_ROOT
from src.phase_e_router.policy_v3 import cell_passes
from src.phase_h_efsweep import EF_VALUES

HM_FILTERS_PATH = "outputs/phase_a_arms/filters.json"
EDGAR_CAL_FILTERS_PATH = "outputs/edgar_calibration_2026-11-01/grid_filters.json"
EDGAR_EVAL_PAIRS_PATH = "outputs/edgar_eval_set_2026-11-01/pairs.csv"
POLICY_HM_PATH = "config/policy_v3_hm.json"
POLICY_EDGAR_PATH = "config/policy_v3_1_edgar.json"
ROUTER_HM_PATH = "config/router_hm.json"


def guard_main_path(results_path: Path, allow_main: bool) -> None:
    """Refuse to read any path under a main-run output directory unless --main is explicitly passed."""
    norm = results_path.resolve().as_posix().lower()
    if not allow_main and ("ef_sweep_main" in norm or "/main" in norm or "main_" in norm):
        raise RuntimeError(f"Refusing to read main-run path {results_path} without --main")


def exact_mcnemar_two_sided(n_01: int, n_10: int) -> float:
    """Exact two-sided McNemar p-value via binomial test (p = 1.0 when n_01 + n_10 == 0)."""
    n_disc = n_01 + n_10
    if n_disc == 0:
        return 1.0
    return float(binomtest(min(n_01, n_10), n_disc, 0.5, alternative="two-sided").pvalue)


def holm_step_down(tests: list[dict[str, Any]], alpha: float = 0.05) -> list[dict[str, Any]]:
    """Apply step-down Holm-Bonferroni at alpha across tests with 'p_value' key.

    A test at a larger threshold is rejected ONLY if all tests ranked before it are also rejected.
    """
    m = len(tests)
    ordered = sorted(range(m), key=lambda i: tests[i]["p_value"])
    out = [dict(t) for t in tests]
    stopped = False
    for rank_idx, orig_idx in enumerate(ordered):
        thr = alpha / (m - rank_idx)
        p = out[orig_idx]["p_value"]
        if not stopped and p <= thr:
            rejected = True
        else:
            rejected = False
            stopped = True
        out[orig_idx]["holm_rank"] = rank_idx + 1
        out[orig_idx]["holm_threshold"] = thr
        out[orig_idx]["rejected"] = rejected
    return out


def compute_s_pass(cell_selectivities_and_recall_pass: list[tuple[float, bool]]) -> float | None:
    """Lowest selectivity s* such that every grid cell with selectivity >= s* passes recall-only."""
    if not cell_selectivities_and_recall_pass:
        return None
    ordered = sorted(cell_selectivities_and_recall_pass, key=lambda x: x[0])
    # Walk from highest selectivity downward; stop at the first failure.
    s_pass: float | None = None
    for s, ok in reversed(ordered):
        if ok:
            s_pass = s
        else:
            break
    return s_pass


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        if not fieldnames:
            return
        w = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_analysis(
    results_path: Path,
    out_dir: Path,
    explain_path: Path | None = None,
    allow_main: bool = False,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Run Section 6 confirmatory and descriptive analysis deterministically."""
    guard_main_path(results_path, allow_main=allow_main)
    if not results_path.exists():
        raise FileNotFoundError(f"results.jsonl not found: {results_path}")

    if explain_path is None:
        cand = results_path.parent / "explain_results.jsonl"
        explain_path = cand if cand.exists() else None
    elif not explain_path.exists():
        raise FileNotFoundError(f"explain_results.jsonl not found: {explain_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Record SHA-256 of every input file used
    input_files: list[Path] = [
        results_path,
        root / HM_FILTERS_PATH,
        root / EDGAR_CAL_FILTERS_PATH,
        root / EDGAR_EVAL_PAIRS_PATH,
        root / POLICY_HM_PATH,
        root / POLICY_EDGAR_PATH,
        root / ROUTER_HM_PATH,
    ]
    if explain_path is not None:
        input_files.append(explain_path)

    checksums = {
        p.as_posix(): {"sha256": _sha256(p), "bytes": p.stat().st_size}
        for p in input_files
    }
    (out_dir / "analysis_inputs.json").write_text(json.dumps(checksums, indent=1), encoding="utf-8", newline="\n")

    t_hm = float(json.loads((root / POLICY_HM_PATH).read_text(encoding="utf-8"))["T_default"])
    t_edgar = float(json.loads((root / POLICY_EDGAR_PATH).read_text(encoding="utf-8"))["T_default"])
    t_hm_sens = float(json.loads((root / ROUTER_HM_PATH).read_text(encoding="utf-8"))["fixed_T"])

    rows = [json.loads(ln) for ln in results_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    explain_rows = (
        [json.loads(ln) for ln in explain_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if explain_path is not None
        else []
    )

    # Group primary cell vectors: (dataset, table, cell_id, selectivity, arm, ef_search) -> list[row]
    cell_groups: dict[tuple[str, str, str, float, str, int | None], list[dict[str, Any]]] = defaultdict(list)
    eval_rows: list[dict[str, Any]] = []
    for r in rows:
        if r["dataset"] in ("hm", "edgar_cal"):
            key = (r["dataset"], r["table"], r["cell_id"], float(r["selectivity"]), r["arm"], r["ef_search"])
            cell_groups[key].append(r)
        elif r["dataset"] == "edgar_eval":
            eval_rows.append(r)

    # 1. Cell-level evaluation using frozen cell_passes()
    cell_summary: list[dict[str, Any]] = []
    cell_lookup: dict[tuple[str, str, str, str, int | None], dict[str, Any]] = {}
    for (ds, tbl, cid, sel, arm, ef), grp in sorted(cell_groups.items()):
        recalls = [r["recall"] if r.get("valid") else None for r in grp]
        lats = [
            (r["median_latency_ms"] if r.get("median_latency_ms") is not None else statistics.median(r["rep_latencies_ms"]))
            if r.get("valid") and r.get("rep_latencies_ms")
            else None
            for r in grp
        ]
        cp = cell_passes(recalls, lats, n_expected=20, recall_target=0.90, latency_limit_ms=500.0)
        recall_only = bool(cp["valid"] and cp["mean_recall"] is not None and cp["mean_recall"] >= 0.90)
        latency_only = bool(cp["valid"] and cp["median_latency_ms"] is not None and cp["median_latency_ms"] <= 500.0)
        rec = {
            "dataset": ds,
            "table": tbl,
            "cell_id": cid,
            "selectivity": sel,
            "arm": arm,
            "ef_search": ef if ef is not None else "none",
            "n_vectors": len(grp),
            "valid": cp["valid"],
            "passed": cp["passed"],
            "recall_only_pass": recall_only,
            "latency_only_pass": latency_only,
            "mean_recall": cp["mean_recall"],
            "median_latency_ms": cp["median_latency_ms"],
            "reason": cp["reason"],
            "n_early_stopped": sum(1 for r in grp if r.get("early_stopped")),
        }
        cell_summary.append(rec)
        cell_lookup[(ds, tbl, cid, arm, ef)] = rec

    _write_csv(out_dir / "cell_summary.csv", cell_summary)

    # 2. Confirmatory: 4 exact two-sided McNemar tests (ef=400 vs ef=40) + Holm step-down
    mcnemar_raw: list[dict[str, Any]] = []
    for ds in ("hm", "edgar_cal"):
        for arm in ("default_hnsw", "always_iterative"):
            units = sorted({(r["table"], r["cell_id"]) for r in cell_summary if r["dataset"] == ds})
            n_01 = n_10 = n_11 = n_00 = 0
            for tbl, cid in units:
                c40 = cell_lookup.get((ds, tbl, cid, arm, 40))
                c400 = cell_lookup.get((ds, tbl, cid, arm, 400))
                p40 = bool(c40 and c40["passed"])
                p400 = bool(c400 and c400["passed"])
                if not p40 and p400:
                    n_01 += 1
                elif p40 and not p400:
                    n_10 += 1
                elif p40 and p400:
                    n_11 += 1
                else:
                    n_00 += 1
            pval = exact_mcnemar_two_sided(n_01, n_10)
            mcnemar_raw.append({
                "hypothesis": f"{ds}_{arm}",
                "dataset": ds,
                "arm": arm,
                "n_cells": len(units),
                "pass_40": n_11 + n_10,
                "pass_400": n_11 + n_01,
                "n_01_gain": n_01,
                "n_10_loss": n_10,
                "n_11": n_11,
                "n_00": n_00,
                "p_value": pval,
            })

    mcnemar_holm = holm_step_down(mcnemar_raw, alpha=0.05)
    _write_csv(out_dir / "confirmatory_mcnemar.csv", mcnemar_holm)

    # 3. Pass-rule decomposition & smallest ef reaching pass rule
    decomp_rows: list[dict[str, Any]] = []
    for ds in ("hm", "edgar_cal"):
        for arm in ("always_exact", "default_hnsw", "always_iterative"):
            efs = [None] if arm == "always_exact" else list(EF_VALUES)
            for ef in efs:
                ef_key = "none" if ef is None else ef
                sub = [r for r in cell_summary if r["dataset"] == ds and r["arm"] == arm and r["ef_search"] == ef_key]
                decomp_rows.append({
                    "dataset": ds,
                    "arm": arm,
                    "ef_search": ef_key,
                    "n_cells": len(sub),
                    "n_pass": sum(1 for r in sub if r["passed"]),
                    "n_recall_only_pass": sum(1 for r in sub if r["recall_only_pass"]),
                    "n_latency_only_pass": sum(1 for r in sub if r["latency_only_pass"]),
                })
    _write_csv(out_dir / "pass_decomposition.csv", decomp_rows)

    smallest_ef_rows: list[dict[str, Any]] = []
    for ds in ("hm", "edgar_cal"):
        for arm in ("default_hnsw", "always_iterative"):
            units = sorted({(r["table"], r["cell_id"], r["selectivity"]) for r in cell_summary if r["dataset"] == ds})
            for tbl, cid, sel in units:
                sm = next((ef for ef in EF_VALUES if cell_lookup.get((ds, tbl, cid, arm, ef), {}).get("passed")), None)
                smallest_ef_rows.append({
                    "dataset": ds,
                    "table": tbl,
                    "cell_id": cid,
                    "selectivity": sel,
                    "arm": arm,
                    "smallest_ef_passing": sm if sm is not None else "none",
                })
    _write_csv(out_dir / "smallest_ef_per_cell.csv", smallest_ef_rows)

    # 4. Operating-region subsets (selectivity >= primary T, plus H&M >= 0.1 sensitivity)
    op_specs = [
        ("hm", "primary_T_hm", t_hm),
        ("hm", "sensitivity_0_1", t_hm_sens),
        ("edgar_cal", "primary_T_edgar", t_edgar),
    ]
    op_rows: list[dict[str, Any]] = []
    for ds, label, thr in op_specs:
        for arm in ("always_exact", "default_hnsw", "always_iterative"):
            efs = [None] if arm == "always_exact" else list(EF_VALUES)
            for ef in efs:
                ef_key = "none" if ef is None else ef
                sub = [
                    r for r in cell_summary
                    if r["dataset"] == ds and r["arm"] == arm and r["ef_search"] == ef_key and r["selectivity"] >= thr
                ]
                valid_rec = [r["mean_recall"] for r in sub if r["mean_recall"] is not None]
                valid_lat = [r["median_latency_ms"] for r in sub if r["median_latency_ms"] is not None]
                op_rows.append({
                    "dataset": ds,
                    "subset": label,
                    "threshold_T": thr,
                    "arm": arm,
                    "ef_search": ef_key,
                    "n_cells": len(sub),
                    "n_pass": sum(1 for r in sub if r["passed"]),
                    "n_recall_only_pass": sum(1 for r in sub if r["recall_only_pass"]),
                    "n_latency_only_pass": sum(1 for r in sub if r["latency_only_pass"]),
                    "mean_of_cell_recalls": statistics.fmean(valid_rec) if valid_rec else None,
                    "median_of_cell_latencies_ms": statistics.median(valid_lat) if valid_lat else None,
                })
    _write_csv(out_dir / "operating_region.csv", op_rows)

    # 5. Cliff table s_pass(ef) per table for default_hnsw
    cliff_rows: list[dict[str, Any]] = []
    for ds, k_val in (("hm", 10), ("edgar_cal", 15)):
        tables = sorted({r["table"] for r in cell_summary if r["dataset"] == ds})
        for tbl in tables:
            for ef in EF_VALUES:
                sub = [
                    (r["selectivity"], r["recall_only_pass"])
                    for r in cell_summary
                    if r["dataset"] == ds and r["table"] == tbl and r["arm"] == "default_hnsw" and r["ef_search"] == ef
                ]
                sp = compute_s_pass(sub)
                k_over_ef = k_val / ef
                cliff_rows.append({
                    "dataset": ds,
                    "table": tbl,
                    "ef_search": ef,
                    "k": k_val,
                    "k_over_ef": k_over_ef,
                    "s_pass": sp,
                    "ratio_s_pass_to_k_over_ef": (sp / k_over_ef) if sp is not None else None,
                })
    _write_csv(out_dir / "cliff_table.csv", cliff_rows)

    # 6. Latency growth per ef step excluding early-stopped vectors
    vec_map: dict[tuple[str, str, str, str, str, int], dict[str, Any]] = {}
    for r in rows:
        if r["ef_search"] is not None:
            vec_map[(r["dataset"], r["table"], r["cell_id"], r["vector_key"], r["arm"], int(r["ef_search"]))] = r

    growth_rows: list[dict[str, Any]] = []
    steps = ((40, 100), (100, 200), (200, 400))
    for ds in ("hm", "edgar_cal", "edgar_eval"):
        for arm in ("default_hnsw", "always_iterative"):
            for ef_a, ef_b in steps:
                ratios: list[float] = []
                for key, ra in vec_map.items():
                    if key[0] != ds or key[4] != arm or key[5] != ef_a:
                        continue
                    rb = vec_map.get((ds, key[1], key[2], key[3], arm, ef_b))
                    if not rb or not ra.get("valid") or not rb.get("valid"):
                        continue
                    if ra.get("early_stopped") or rb.get("early_stopped"):
                        continue
                    la, lb = ra.get("median_latency_ms"), rb.get("median_latency_ms")
                    if la and lb and la > 0:
                        ratios.append(lb / la)
                growth_rows.append({
                    "dataset": ds,
                    "arm": arm,
                    "step": f"{ef_a}->{ef_b}",
                    "n_vectors_non_early": len(ratios),
                    "median_growth_factor": statistics.median(ratios) if ratios else None,
                })
    _write_csv(out_dir / "latency_growth.csv", growth_rows)

    # 7. Plan-node transitions from EXPLAIN pass
    explain_summary: list[dict[str, Any]] = []
    for e in explain_rows:
        explain_summary.append({
            "dataset": e["dataset"],
            "table": e["table"],
            "cell_id": e["cell_id"],
            "arm": e["arm"],
            "ef_search": e["ef_search"] if e["ef_search"] is not None else "none",
            "valid": e["valid"],
            "seq_scan_flagged": e.get("seq_scan_flagged", False),
            "plan_nodes": "/".join(e.get("plan_nodes") or []),
            "execution_time_ms": e.get("execution_time_ms"),
            "shared_hit_blocks": e.get("shared_hit_blocks"),
            "shared_read_blocks": e.get("shared_read_blocks"),
        })
    _write_csv(out_dir / "explain_transitions.csv", explain_summary)

    # 8. Secondary EDGAR 160-pair descriptive analysis (pair pass: recall@15 >= 14/15 and median <= 500 ms)
    eval_summary: list[dict[str, Any]] = []
    breadths = sorted({r.get("breadth") for r in eval_rows if r.get("breadth")})
    for br in [*breadths, "ALL"]:
        for arm in ("always_exact", "default_hnsw", "always_iterative"):
            efs = [None] if arm == "always_exact" else list(EF_VALUES)
            for ef in efs:
                sub = [
                    r for r in eval_rows
                    if (br == "ALL" or r.get("breadth") == br) and r["arm"] == arm and r["ef_search"] == ef
                ]
                n_pass = sum(
                    1 for r in sub
                    if r.get("valid") and (r.get("recall") or 0.0) >= (14.0 / 15.0) and (r.get("median_latency_ms") or 1e9) <= 500.0
                )
                recs = [r["recall"] for r in sub if r.get("valid") and r.get("recall") is not None]
                lats = [r["median_latency_ms"] for r in sub if r.get("valid") and r.get("median_latency_ms") is not None]
                eval_summary.append({
                    "breadth": br,
                    "arm": arm,
                    "ef_search": "none" if ef is None else ef,
                    "n_pairs": len(sub),
                    "n_pair_pass": n_pass,
                    "mean_recall15": statistics.fmean(recs) if recs else None,
                    "median_latency_ms": statistics.median(lats) if lats else None,
                })
    _write_csv(out_dir / "edgar_eval_secondary.csv", eval_summary)

    # 9. Markdown report
    is_smoke = "smoke" in results_path.as_posix().lower()
    lines = [
        "# Phase H, Amendment 13: `ef_search` Sweep Analysis Report",
        "",
        f"- **Input results:** `{results_path.as_posix()}` (`{len(rows)}` rows)",
        f"- **Input EXPLAIN:** `{explain_path.as_posix() if explain_path else 'none'}` (`{len(explain_rows)}` rows)",
        f"- **Primary thresholds:** `T_hm = {t_hm}` (sensitivity `0.1`), `T_edgar = {t_edgar}`",
    ]
    if is_smoke:
        lines.extend(["", "> **WARNING (SMOKE DRY RUN):** Input is a smoke subset (`n_vectors < 20` per cell); numbers below are for pipeline verification only and must NOT be interpreted."])

    lines.extend([
        "",
        "## 1. Confirmatory Hypotheses (Exact Two-Sided McNemar, Holm Step-Down α = 0.05)",
        "",
        "| Hypothesis | n_cells | pass@40 | pass@400 | n_01 (gain) | n_10 (loss) | p_value | Holm rank | Holm thr | Rejected |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for m in mcnemar_holm:
        lines.append(
            f"| {m['hypothesis']} | {m['n_cells']} | {m['pass_40']} | {m['pass_400']} | "
            f"{m['n_01_gain']} | {m['n_10_loss']} | {m['p_value']:.6f} | {m['holm_rank']} | "
            f"{m['holm_threshold']:.6f} | {m['rejected']} |"
        )

    lines.extend([
        "",
        "## 2. Pass-Rule Decomposition",
        "",
        "| Dataset | Arm | ef | n_cells | n_pass | recall_only_pass | latency_only_pass |",
        "|---|---|---|---:|---:|---:|---:|",
    ])
    for d in decomp_rows:
        lines.append(
            f"| {d['dataset']} | {d['arm']} | {d['ef_search']} | {d['n_cells']} | "
            f"{d['n_pass']} | {d['n_recall_only_pass']} | {d['n_latency_only_pass']} |"
        )

    lines.extend([
        "",
        "## 3. Operating-Region Subsets (`selectivity >= T`)",
        "",
        "| Dataset | Subset | T | Arm | ef | n_cells | n_pass | recall_only | latency_only |",
        "|---|---|---:|---|---|---:|---:|---:|---:|",
    ])
    for o in op_rows:
        lines.append(
            f"| {o['dataset']} | {o['subset']} | {o['threshold_T']:.6f} | {o['arm']} | {o['ef_search']} | "
            f"{o['n_cells']} | {o['n_pass']} | {o['n_recall_only_pass']} | {o['n_latency_only_pass']} |"
        )

    lines.extend([
        "",
        "## 4. `default_hnsw` Cliff Table (`s_pass(ef)` vs `k / ef`)",
        "",
        "*Caveat: Mandarapu & Kunkunuru (`arXiv:2606.16341v1`) assumes no attribute-vector correlation; the observed cliff may shift on the scrambled H&M tables and EDGAR.*",
        "",
        "| Dataset | Table | ef | k/ef | s_pass(ef) | s_pass / (k/ef) |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for c in cliff_rows:
        sp_s = f"{c['s_pass']:.6f}" if c["s_pass"] is not None else "None"
        rat_s = f"{c['ratio_s_pass_to_k_over_ef']:.3f}" if c["ratio_s_pass_to_k_over_ef"] is not None else "None"
        lines.append(f"| {c['dataset']} | {c['table']} | {c['ef_search']} | {c['k_over_ef']:.4f} | {sp_s} | {rat_s} |")

    lines.extend([
        "",
        "## 5. Plan Verification (`EXPLAIN (ANALYZE, BUFFERS)`)",
        f"- Total EXPLAIN rows: `{len(explain_summary)}`; `seq_scan_flagged`: `{sum(1 for e in explain_summary if e['seq_scan_flagged'])}`.",
        "",
    ])

    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return {"n_cells": len(cell_summary), "mcnemar": mcnemar_holm, "report_path": str(out_dir / "REPORT.md")}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Phase H Amendment 13 frozen analysis")
    p.add_argument("--results", required=True, help="Path to results.jsonl")
    p.add_argument("--explain", default=None, help="Optional path to explain_results.jsonl")
    p.add_argument("--out-dir", required=True, help="Output directory for CSVs and REPORT.md")
    p.add_argument("--main", action="store_true", help="Required flag to read main-run results")
    args = p.parse_args(argv)
    res = run_analysis(
        results_path=PROJECT_ROOT / args.results,
        out_dir=PROJECT_ROOT / args.out_dir,
        explain_path=(PROJECT_ROOT / args.explain) if args.explain else None,
        allow_main=args.main,
    )
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
