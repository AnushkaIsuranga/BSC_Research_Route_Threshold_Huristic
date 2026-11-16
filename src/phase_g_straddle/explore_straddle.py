"""Exploratory post-hoc analyses of the Phase G straddle-T main run results.

EXPLORATORY, post hoc; not part of the pre-registered confirmatory analysis.
Reads existing outputs/straddle_t_results_2026-11-16/ and
outputs/straddle_t_analysis_2026-11-16/ without modifying them or querying the DB.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.phase_g_straddle import analyze_straddle as A

BANNER = "EXPLORATORY, post hoc; not part of the pre-registered confirmatory analysis"

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "outputs" / "straddle_t_results_2026-11-16"
MANIFESTS_DIR = REPO_ROOT / "outputs" / "straddle_t_manifest_2026-11-15"
ANALYSIS_DIR = REPO_ROOT / "outputs" / "straddle_t_analysis_2026-11-16"
OUT_DIR = REPO_ROOT / "outputs" / "straddle_t_exploratory_2026-11-16"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            out = {}
            for k in fieldnames:
                v = r.get(k, "NA")
                if isinstance(v, bool):
                    out[k] = "True" if v else "False"
                elif isinstance(v, float):
                    out[k] = "NA" if math.isnan(v) else f"{v:.6f}"
                elif v is None:
                    out[k] = "NA"
                else:
                    out[k] = str(v)
            w.writerow(out)


def run_x1(
    manifest_records: dict[str, dict[str, list[dict[str, Any]]]],
    out_dir: Path,
) -> dict[str, Any]:
    """X1: Counterfactual threshold sweep using measured always_exact and always_iterative."""
    specs = [
        (
            "edgar_pairs_primary_T_edgar.csv",
            [round(0.05 + 0.025 * i, 3) for i in range(37)],
        ),
        (
            "finqa_pairs_primary_T_hm.csv",
            [round(0.02 + 0.02 * i, 2) for i in range(47)],  # 0.02..0.94
        ),
    ]

    csv_rows: list[dict[str, Any]] = []
    passing_summary: dict[str, dict[str, list[float]]] = {}

    for mname, grid in specs:
        recs_map = manifest_records[mname]
        exact_by_qp = {(r["qid"], r["pool_id"]): r for r in recs_map["always_exact"]}
        iter_by_qp = {(r["qid"], r["pool_id"]): r for r in recs_map["always_iterative"]}
        base_recs = recs_map["always_exact"]

        overall_pass_ts: list[float] = []
        all_bands_pass_ts: list[float] = []

        for t_prime in grid:
            cf_recs = []
            for base in base_recs:
                qp = (base["qid"], base["pool_id"])
                s_val = float(base["selectivity"])
                chosen = exact_by_qp[qp] if s_val < t_prime else iter_by_qp[qp]
                cf_recs.append(
                    {
                        "band": base["band"],
                        "s": s_val,
                        "valid": chosen["valid"],
                        "recall_at_15": chosen["recall_at_15"],
                        "latency_median_ms": chosen["latency_median_ms"],
                    }
                )

            scopes = [
                ("overall", cf_recs),
                ("below_T_prime", [r for r in cf_recs if r["s"] < t_prime]),
                ("above_T_prime", [r for r in cf_recs if r["s"] >= t_prime]),
                *[(b, [r for r in cf_recs if r["band"] == b]) for b in A.BANDS_ORDER],
            ]

            band_passes = []
            for scope_name, s_recs in scopes:
                valid_s = [r for r in s_recs if r["valid"]]
                n_p = len(s_recs)
                n_v = len(valid_s)
                if n_v > 0:
                    m_rec = float(np.mean([r["recall_at_15"] for r in valid_s]))
                    m_lat = float(np.median([r["latency_median_ms"] for r in valid_s]))
                    passed = bool(
                        n_v == n_p
                        and m_rec >= A.RECALL_THRESHOLD
                        and m_lat <= A.LATENCY_THRESHOLD_MS
                    )
                else:
                    m_rec = math.nan
                    m_lat = math.nan
                    passed = False

                if scope_name == "overall" and passed:
                    overall_pass_ts.append(t_prime)
                if scope_name in A.BANDS_ORDER:
                    band_passes.append(passed)

                csv_rows.append(
                    {
                        "analysis_status": BANNER,
                        "manifest": mname,
                        "T_prime": t_prime,
                        "scope": scope_name,
                        "n_pairs": n_p,
                        "n_valid": n_v,
                        "mean_recall": m_rec,
                        "median_latency_ms": m_lat,
                        "pass": passed,
                    }
                )
            if all(band_passes) and len(band_passes) == 4:
                all_bands_pass_ts.append(t_prime)

        passing_summary[mname] = {
            "overall_pass": overall_pass_ts,
            "all_4_bands_pass": all_bands_pass_ts,
        }

    cols = [
        "analysis_status",
        "manifest",
        "T_prime",
        "scope",
        "n_pairs",
        "n_valid",
        "mean_recall",
        "median_latency_ms",
        "pass",
    ]
    out_csv = out_dir / "x1_counterfactual_threshold.csv"
    _write_csv(out_csv, cols, csv_rows)
    return {"csv": out_csv, "passing_summary": passing_summary}


def run_x2(
    manifest_records: dict[str, dict[str, list[dict[str, Any]]]],
    out_dir: Path,
) -> dict[str, Any]:
    """X2: Per-pair oracle summary across all 4 main/secondary manifests and bands."""
    oracle_rows: list[dict[str, Any]] = []
    no_qual_rows: list[dict[str, Any]] = []

    for mname in A.PRIMARY_SECONDARY_MANIFESTS:
        recs_map = manifest_records[mname]
        primary_router = "router" if mname == "edgar_pairs_primary_T_edgar.csv" else "router_hmT"
        candidate_arms = [
            "always_exact",
            "default_hnsw",
            "always_iterative",
            "vecadvisor",
            primary_router,
        ]
        by_arm_qp = {
            a: {(r["qid"], r["pool_id"]): r for r in recs_map[a]}
            for a in candidate_arms
        }
        base_recs = recs_map["always_exact"]

        for band in A.BANDS_ORDER:
            b_recs = [r for r in base_recs if r["band"] == band]
            n_p = len(b_recs)
            win_counts = {a: 0 for a in candidate_arms}
            no_qual_count = 0

            for base in b_recs:
                qp = (base["qid"], base["pool_id"])
                qualifying: list[tuple[float, str]] = []
                for a in candidate_arms:
                    r = by_arm_qp[a].get(qp)
                    if (
                        r is not None
                        and r["valid"]
                        and not r["unavailable"]
                        and r["recall_at_15"] >= A.PAIR_RECALL_THRESHOLD
                    ):
                        qualifying.append((float(r["latency_median_ms"]), a))
                if qualifying:
                    qualifying.sort(key=lambda x: x[0])
                    win_counts[qualifying[0][1]] += 1
                else:
                    no_qual_count += 1
                    no_qual_rows.append(
                        {
                            "analysis_status": BANNER,
                            "manifest": mname,
                            "band": band,
                            "pair_id": base["pair_id"],
                            "qid": base["qid"],
                            "pool_id": base["pool_id"],
                            "s": base["selectivity"],
                            "n_rows": base["n_rows"],
                        }
                    )

            row_out: dict[str, Any] = {
                "analysis_status": BANNER,
                "manifest": mname,
                "band": band,
                "n_pairs": n_p,
                "router_arm_name": primary_router,
            }
            for a in ["always_exact", "default_hnsw", "always_iterative", "vecadvisor"]:
                row_out[f"share_{a}"] = win_counts[a] / n_p if n_p else math.nan
            row_out["share_router"] = win_counts[primary_router] / n_p if n_p else math.nan
            row_out["share_no_arm_qualifies"] = no_qual_count / n_p if n_p else math.nan
            row_out["count_no_arm_qualifies"] = no_qual_count
            oracle_rows.append(row_out)

    oracle_cols = [
        "analysis_status",
        "manifest",
        "band",
        "n_pairs",
        "router_arm_name",
        "share_always_exact",
        "share_default_hnsw",
        "share_always_iterative",
        "share_vecadvisor",
        "share_router",
        "share_no_arm_qualifies",
        "count_no_arm_qualifies",
    ]
    no_qual_cols = [
        "analysis_status",
        "manifest",
        "band",
        "pair_id",
        "qid",
        "pool_id",
        "s",
        "n_rows",
    ]
    out_oracle = out_dir / "x2_oracle_summary.csv"
    out_no_qual = out_dir / "x2_no_qualifying_pairs.csv"
    _write_csv(out_oracle, oracle_cols, oracle_rows)
    _write_csv(out_no_qual, no_qual_cols, no_qual_rows)
    return {
        "oracle_csv": out_oracle,
        "no_qual_csv": out_no_qual,
        "oracle_rows": oracle_rows,
        "no_qual_rows": no_qual_rows,
    }


def run_x3(
    index: dict[str, Any],
    manifest_rows_by_name: dict[str, list[dict[str, str]]],
    out_dir: Path,
) -> dict[str, Any]:
    """X3: Host-load sensitivity (exclude rows within 150s of cpu_total_pct > 25)."""
    host_samples = json.loads((RESULTS_DIR / "host_load.json").read_text(encoding="utf-8"))
    high_cpu_ts = [
        datetime.fromisoformat(s["utc"])
        for s in host_samples
        if float(s["cpu_total_pct"]) > 25.0
    ]

    def is_high_cpu_row(row: dict[str, Any]) -> bool:
        ts_str = row.get("timestamp")
        if not ts_str:
            return False
        rts = datetime.fromisoformat(ts_str)
        return any(abs((rts - hts).total_seconds()) <= 150.0 for hts in high_cpu_ts)

    # Filter results index to exclude rows within 150s of cpu_total_pct > 25
    all_rows = index["all_rows"]
    affected_flags = [is_high_cpu_row(r) for r in all_rows]
    n_total_rows = len(all_rows)
    n_affected_rows = sum(1 for x in affected_flags if x)

    filtered_rows = [r for r, flag in zip(all_rows, affected_flags) if not flag]
    filtered_fixed = {}
    filtered_router = {}
    filtered_router_qp = {}
    for r in filtered_rows:
        qid = str(r["qid"])
        pool_id = str(r["pool_id"])
        arm = str(r["arm"])
        t_name = str(r.get("T_name", ""))
        if arm in A.FIXED_ARMS:
            filtered_fixed[(qid, pool_id, arm)] = r
        else:
            filtered_router[(qid, pool_id, t_name, arm)] = r
            filtered_router_qp.setdefault((qid, pool_id, arm), []).append(r)

    filtered_index = {
        "fixed": filtered_fixed,
        "router": filtered_router,
        "router_by_qp_arm": filtered_router_qp,
        "all_rows": filtered_rows,
    }

    # Key hypothesis cells
    cells = [
        ("H1a", "edgar_pairs_primary_T_edgar.csv", "router", ["far_below", "near_below"]),
        ("H1b", "edgar_pairs_primary_T_edgar.csv", "router", ["above_T"]),
        ("H3", "edgar_pairs_primary_T_edgar.csv", "default_hnsw", ["far_below", "near_below"]),
        ("H5a", "finqa_pairs_primary_T_hm.csv", "router_hmT", ["far_below", "near_below", "near_above", "far_above"]),
        ("H5b", "edgar_pairs_secondary_T_hm.csv", "router_hmT", ["far_below", "near_above", "far_above"]),
    ]

    seed_seq = np.random.SeedSequence(A.BOOTSTRAP_SEED)
    out_rows: list[dict[str, Any]] = []

    for hyp, mname, arm, scopes in cells:
        mrows = manifest_rows_by_name[mname]
        recs_full = A.build_manifest_records(mname, mrows, index)[arm]
        recs_filt = A.build_manifest_records(mname, mrows, filtered_index)[arm]

        for scope in scopes:
            if scope == "above_T":
                sub_full = [r for r in recs_full if r["band"] in ("near_above", "far_above")]
                sub_filt = [r for r in recs_filt if r["band"] in ("near_above", "far_above")]
                # Only keep pairs whose arm row (and exact row) were not excluded
                sub_filt_kept = [r for r in sub_filt if r["valid"]]
            else:
                sub_full = [r for r in recs_full if r["band"] == scope]
                sub_filt = [r for r in recs_filt if r["band"] == scope]
                sub_filt_kept = [r for r in sub_filt if r["valid"]]

            for subset_label, sub_recs in [("all_rows", sub_full), ("low_cpu_only", sub_filt_kept)]:
                children = seed_seq.spawn(2)
                st = A.summarize_records(
                    sub_recs,
                    np.random.default_rng(children[0]),
                    np.random.default_rng(children[1]),
                    b_resamples=A.BOOTSTRAP_B,
                )
                out_rows.append(
                    {
                        "analysis_status": BANNER,
                        "hypothesis": hyp,
                        "manifest": mname,
                        "arm": arm,
                        "band_or_group": scope,
                        "subset": subset_label,
                        "n_pairs": st["n_pairs"],
                        "n_valid": st["n_valid"],
                        "mean_recall": st["mean_recall"],
                        "q_ci_recall_lo": st["q_ci_recall_lo"],
                        "q_ci_recall_hi": st["q_ci_recall_hi"],
                        "median_latency_ms": st["median_latency_ms"],
                        "q_ci_lat_lo": st["q_ci_lat_lo"],
                        "q_ci_lat_hi": st["q_ci_lat_hi"],
                        "pass": st["pass"],
                    }
                )

    cols = [
        "analysis_status",
        "hypothesis",
        "manifest",
        "arm",
        "band_or_group",
        "subset",
        "n_pairs",
        "n_valid",
        "mean_recall",
        "q_ci_recall_lo",
        "q_ci_recall_hi",
        "median_latency_ms",
        "q_ci_lat_lo",
        "q_ci_lat_hi",
        "pass",
    ]
    out_csv = out_dir / "x3_host_load_sensitivity.csv"
    _write_csv(out_csv, cols, out_rows)
    return {
        "csv": out_csv,
        "n_total_rows": n_total_rows,
        "n_affected_rows": n_affected_rows,
        "share_affected": n_affected_rows / n_total_rows if n_total_rows else 0.0,
        "rows": out_rows,
    }


def run_x4(
    manifest_records: dict[str, dict[str, list[dict[str, Any]]]],
    out_dir: Path,
) -> dict[str, Any]:
    """X4: Tier split (natural vs plausible_constructed) for the 5 hypotheses' key cells."""
    cells = [
        ("H1a", "edgar_pairs_primary_T_edgar.csv", "router", ["far_below", "near_below"]),
        ("H1b", "edgar_pairs_primary_T_edgar.csv", "router", ["above_T"]),
        ("H3", "edgar_pairs_primary_T_edgar.csv", "default_hnsw", ["far_below", "near_below"]),
        ("H5a", "finqa_pairs_primary_T_hm.csv", "router_hmT", ["far_below", "near_below", "near_above", "far_above"]),
        ("H5b", "edgar_pairs_secondary_T_hm.csv", "router_hmT", ["far_below", "near_above", "far_above"]),
    ]

    seed_seq = np.random.SeedSequence(A.BOOTSTRAP_SEED)
    out_rows: list[dict[str, Any]] = []

    for hyp, mname, arm, scopes in cells:
        recs = manifest_records[mname][arm]
        for scope in scopes:
            for tier in ["natural", "plausible_constructed"]:
                if scope == "above_T":
                    sub = [
                        r
                        for r in recs
                        if r["band"] in ("near_above", "far_above") and r["question_tier"] == tier
                    ]
                else:
                    sub = [r for r in recs if r["band"] == scope and r["question_tier"] == tier]

                if not sub:
                    out_rows.append(
                        {
                            "analysis_status": BANNER,
                            "hypothesis": hyp,
                            "manifest": mname,
                            "arm": arm,
                            "band_or_group": scope,
                            "tier": tier,
                            "n_pairs": 0,
                            "n_valid": 0,
                            "mean_recall": math.nan,
                            "median_latency_ms": math.nan,
                            "pass": False,
                            "note": "too_few_pairs(0)",
                        }
                    )
                    continue

                children = seed_seq.spawn(2)
                st = A.summarize_records(
                    sub,
                    np.random.default_rng(children[0]),
                    np.random.default_rng(children[1]),
                    b_resamples=A.BOOTSTRAP_B,
                )
                note = f"too_few_pairs({st['n_pairs']})" if st["n_pairs"] < 10 else "ok"
                out_rows.append(
                    {
                        "analysis_status": BANNER,
                        "hypothesis": hyp,
                        "manifest": mname,
                        "arm": arm,
                        "band_or_group": scope,
                        "tier": tier,
                        "n_pairs": st["n_pairs"],
                        "n_valid": st["n_valid"],
                        "mean_recall": st["mean_recall"],
                        "median_latency_ms": st["median_latency_ms"],
                        "pass": st["pass"],
                        "note": note,
                    }
                )

    cols = [
        "analysis_status",
        "hypothesis",
        "manifest",
        "arm",
        "band_or_group",
        "tier",
        "n_pairs",
        "n_valid",
        "mean_recall",
        "median_latency_ms",
        "pass",
        "note",
    ]
    out_csv = out_dir / "x4_tier_split.csv"
    _write_csv(out_csv, cols, out_rows)
    return {"csv": out_csv, "rows": out_rows}


def run_x5(
    index: dict[str, Any],
    manifest_rows_by_name: dict[str, list[dict[str, str]]],
    out_dir: Path,
) -> dict[str, Any]:
    """X5: Estimate vs count (misrouting rate relative to exact if s < T else iterative_default)."""
    targets = [
        ("edgar_pairs_primary_T_edgar.csv", "router", "T_edgar"),
        ("edgar_pairs_secondary_T_hm.csv", "router_hmT", "T_hm"),
        ("finqa_pairs_primary_T_hm.csv", "router_hmT", "T_hm"),
        ("finqa_pairs_secondary_random.csv", "router_hmT", "T_hm"),
    ]

    summary_rows: list[dict[str, Any]] = []
    misrouted_rows: list[dict[str, Any]] = []

    for mname, arm, t_name in targets:
        mrows = manifest_rows_by_name[mname]
        for band in A.BANDS_ORDER:
            b_mrows = [mr for mr in mrows if mr["band"] == band]
            if not b_mrows:
                continue
            n_p = len(b_mrows)
            n_mis = 0
            mis_s_vals: list[str] = []

            for mr in b_mrows:
                qid = mr["qid"]
                pid = mr["pool_id"]
                s_val = float(mr["s"])
                t_val = float(mr["T_value"])
                expected_route = "exact" if s_val < t_val else "iterative_default"
                rrow = A.resolve_arm_row(index, qid, pid, t_name, arm)
                actual_route = str(rrow.get("route_taken")) if rrow else "missing"
                if actual_route != expected_route:
                    n_mis += 1
                    mis_s_vals.append(f"{s_val:.6f}")
                    misrouted_rows.append(
                        {
                            "analysis_status": BANNER,
                            "manifest": mname,
                            "arm": arm,
                            "band": band,
                            "pair_id": mr["pair_id"],
                            "qid": qid,
                            "pool_id": pid,
                            "s": s_val,
                            "T_value": t_val,
                            "expected_route": expected_route,
                            "actual_route": actual_route,
                            "s_est": rrow.get("s_est") if rrow else None,
                            "s_count": rrow.get("s_count") if rrow else None,
                            "guard_fired": rrow.get("guard_fired") if rrow else None,
                            "estimate_skipped": rrow.get("estimate_skipped") if rrow else None,
                        }
                    )

            summary_rows.append(
                {
                    "analysis_status": BANNER,
                    "manifest": mname,
                    "arm": arm,
                    "band": band,
                    "n_pairs": n_p,
                    "n_misrouted": n_mis,
                    "misrouting_rate": n_mis / n_p if n_p else math.nan,
                    "misrouted_s_values": ";".join(mis_s_vals) if mis_s_vals else "none",
                }
            )

    sum_cols = [
        "analysis_status",
        "manifest",
        "arm",
        "band",
        "n_pairs",
        "n_misrouted",
        "misrouting_rate",
        "misrouted_s_values",
    ]
    mis_cols = [
        "analysis_status",
        "manifest",
        "arm",
        "band",
        "pair_id",
        "qid",
        "pool_id",
        "s",
        "T_value",
        "expected_route",
        "actual_route",
        "s_est",
        "s_count",
        "guard_fired",
        "estimate_skipped",
    ]
    out_sum = out_dir / "x5_estimate_vs_count.csv"
    out_mis = out_dir / "x5_misrouted_pairs.csv"
    _write_csv(out_sum, sum_cols, summary_rows)
    _write_csv(out_mis, mis_cols, misrouted_rows)
    return {
        "summary_csv": out_sum,
        "misrouted_csv": out_mis,
        "summary_rows": summary_rows,
        "misrouted_rows": misrouted_rows,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    A.verify_manifest_checksums(MANIFESTS_DIR)
    index = A.load_results_index(RESULTS_DIR / "results.jsonl")

    manifest_rows_by_name = {
        mname: A.load_manifest_rows(MANIFESTS_DIR / mname)
        for mname in A.PRIMARY_SECONDARY_MANIFESTS
    }
    manifest_records = {
        mname: A.build_manifest_records(mname, mrows, index)
        for mname, mrows in manifest_rows_by_name.items()
    }

    x1 = run_x1(manifest_records, OUT_DIR)
    x2 = run_x2(manifest_records, OUT_DIR)
    x3 = run_x3(index, manifest_rows_by_name, OUT_DIR)
    x4 = run_x4(manifest_records, OUT_DIR)
    x5 = run_x5(index, manifest_rows_by_name, OUT_DIR)

    lines = [
        f"# {BANNER}",
        "",
        "## X1: Counterfactual Threshold Sweep (Descriptive Only)",
        "> **Note:** This is a descriptive counterfactual over measured `always_exact` and `always_iterative` arms (ignoring estimate, count, and guard overhead), **not** a recommended threshold.",
        "",
    ]
    for mname, info in x1["passing_summary"].items():
        lines.append(f"- **{mname}:**")
        lines.append(f"  - `T'` passing overall (`mean_recall >= 0.90` & `median_latency_ms <= 500`): `{info['overall_pass']}`")
        lines.append(f"  - `T'` passing all 4 bands simultaneously: `{info['all_4_bands_pass']}`")

    lines.extend(
        [
            "",
            "## X2: Per-Pair Oracle Summary",
            f"- See `x2_oracle_summary.csv` and `x2_no_qualifying_pairs.csv` (`{len(x2['no_qual_rows'])}` pairs where no arm qualifies).",
            "",
            "## X3: Host-Load Sensitivity (`cpu_total_pct > 25` within 150s)",
            f"- Rows affected: `{x3['n_affected_rows']}` / `{x3['n_total_rows']}` (`{x3['share_affected']:.4%}`).",
            "- See `x3_host_load_sensitivity.csv`.",
            "",
            "## X4: Tier Split (`natural` vs `plausible_constructed`)",
            "- See `x4_tier_split.csv`.",
            "",
            "## X5: Estimate vs Count (Misrouting Rate)",
            f"- Total misrouted pairs across target manifests: `{len(x5['misrouted_rows'])}`.",
            "- See `x5_estimate_vs_count.csv` and `x5_misrouted_pairs.csv`.",
            "",
        ]
    )
    (OUT_DIR / "EXPLORATORY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Exploratory outputs written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
