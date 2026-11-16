"""Corrected exploratory post-hoc analyses v2 of the Phase G straddle-T results.

EXPLORATORY, post hoc; not part of the pre-registered confirmatory analysis.
Reads existing results and confirmatory tables without modifying them or querying the DB.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.phase_g_straddle import analyze_straddle as A

BANNER = "EXPLORATORY, post hoc; not part of the pre-registered confirmatory analysis"

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "outputs" / "straddle_t_results_2026-11-16"
SMOKE_RESULTS = REPO_ROOT / "outputs" / "straddle_t_smoke_2026-11-15" / "results.jsonl"
AMEND11_RESULTS = REPO_ROOT / "outputs" / "edgar_retrieval_comparison_2026-11-01" / "results.jsonl"
MANIFESTS_DIR = REPO_ROOT / "outputs" / "straddle_t_manifest_2026-11-15"
OUT_DIR = REPO_ROOT / "outputs" / "straddle_t_exploratory_v2_2026-11-16"


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


def _rankdata(x: np.ndarray) -> np.ndarray:
    """Average-tie rankdata (1-based) using numpy."""
    n = len(x)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(n, dtype=np.float64)
    sorted_x = x[order]
    i = 0
    while i < n:
        j = i + 1
        while j < n and sorted_x[j] == sorted_x[i]:
            j += 1
        avg_rank = 0.5 * (i + 1 + j)
        ranks[order[i:j]] = avg_rank
        i = j
    return ranks


def spearman_corr(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Return (rho, approx_two_sided_p) for Spearman rank correlation."""
    n = len(x)
    if n < 3:
        return (math.nan, math.nan)
    rx = _rankdata(x)
    ry = _rankdata(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = float(np.sqrt(np.sum(rx * rx) * np.sum(ry * ry)))
    if denom <= 0.0:
        return (math.nan, math.nan)
    rho = float(np.sum(rx * ry) / denom)
    rho_clamped = max(-0.999999999, min(0.999999999, rho))
    t_stat = rho_clamped * math.sqrt((n - 2.0) / (1.0 - rho_clamped * rho_clamped))
    # Normal approximation for large n (n=260, n=697)
    p_val = math.erfc(abs(t_stat) / math.sqrt(2.0))
    return (rho, p_val)


def run_x1b(
    manifest_records: dict[str, dict[str, list[dict[str, Any]]]],
    out_dir: Path,
) -> dict[str, Any]:
    """X1b: Counterfactual threshold per band and per group (below_T', above_T')."""
    specs = [
        ("edgar_pairs_primary_T_edgar.csv", [round(0.05 + 0.025 * i, 3) for i in range(37)]),
        ("finqa_pairs_primary_T_hm.csv", [round(0.02 + 0.02 * i, 2) for i in range(47)]),
    ]

    csv_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}

    for mname, grid in specs:
        recs_map = manifest_records[mname]
        exact_by_qp = {(r["qid"], r["pool_id"]): r for r in recs_map["always_exact"]}
        iter_by_qp = {(r["qid"], r["pool_id"]): r for r in recs_map["always_iterative"]}
        base_recs = recs_map["always_exact"]

        band_passing_ts: dict[str, list[float]] = {b: [] for b in A.BANDS_ORDER}
        edgar_all_except_far_above_ts: list[float] = []

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
                ("below_T_prime", [r for r in cf_recs if r["s"] < t_prime]),
                ("above_T_prime", [r for r in cf_recs if r["s"] >= t_prime]),
                *[(b, [r for r in cf_recs if r["band"] == b]) for b in A.BANDS_ORDER],
            ]

            band_pass_map: dict[str, bool] = {}
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

                if scope_name in A.BANDS_ORDER:
                    band_pass_map[scope_name] = passed
                    if passed:
                        band_passing_ts[scope_name].append(t_prime)

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

            if (
                mname == "edgar_pairs_primary_T_edgar.csv"
                and band_pass_map.get("far_below")
                and band_pass_map.get("near_below")
                and band_pass_map.get("near_above")
            ):
                edgar_all_except_far_above_ts.append(t_prime)

        no_pass_bands = [b for b, ts in band_passing_ts.items() if not ts]
        summary[mname] = {
            "band_passing_ts": band_passing_ts,
            "no_pass_bands": no_pass_bands,
            "edgar_all_except_far_above_ts": edgar_all_except_far_above_ts if "edgar" in mname else None,
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
    out_csv = out_dir / "x1b_counterfactual_threshold.csv"
    _write_csv(out_csv, cols, csv_rows)
    return {"csv": out_csv, "summary": summary}


def run_x2b(
    manifest_records: dict[str, dict[str, list[dict[str, Any]]]],
    out_dir: Path,
) -> dict[str, Any]:
    """X2b: Constrained oracle (recall@15 >= 14/15 AND median latency <= 500 ms)."""
    out_rows: list[dict[str, Any]] = []

    for mname in A.PRIMARY_SECONDARY_MANIFESTS:
        recs_map = manifest_records[mname]
        primary_router = "router" if mname == "edgar_pairs_primary_T_edgar.csv" else "router_hmT"
        arms = ["always_exact", "default_hnsw", "always_iterative", "vecadvisor", primary_router]
        by_arm_qp = {a: {(r["qid"], r["pool_id"]): r for r in recs_map[a]} for a in arms}
        base_recs = recs_map["always_exact"]

        for band in A.BANDS_ORDER:
            b_recs = [r for r in base_recs if r["band"] == band]
            n_p = len(b_recs)
            if n_p == 0:
                continue

            no_arm_both = 0
            only_exact_rec_gt500 = 0
            only_exact_both = 0
            any_both_count = 0
            winner_counts = {a: 0 for a in arms}
            tie_count = 0

            for base in b_recs:
                qp = (base["qid"], base["pool_id"])
                meets_recall: list[str] = []
                meets_both: list[tuple[float, str]] = []

                for a in arms:
                    r = by_arm_qp[a].get(qp)
                    if r is None or not r["valid"] or r["unavailable"]:
                        continue
                    rec = float(r["recall_at_15"])
                    lat = float(r["latency_median_ms"])
                    if rec >= A.PAIR_RECALL_THRESHOLD:
                        meets_recall.append(a)
                        if lat <= A.LATENCY_THRESHOLD_MS:
                            meets_both.append((lat, a))

                if meets_recall == ["always_exact"]:
                    ex_lat = float(by_arm_qp["always_exact"][qp]["latency_median_ms"])
                    if ex_lat > A.LATENCY_THRESHOLD_MS:
                        only_exact_rec_gt500 += 1

                if not meets_both:
                    no_arm_both += 1
                else:
                    any_both_count += 1
                    if [a for _, a in meets_both] == ["always_exact"]:
                        only_exact_both += 1
                    min_lat = min(lat for lat, _ in meets_both)
                    tied_arms = [a for lat, a in meets_both if lat <= min_lat + 1.0]
                    if len(tied_arms) > 1:
                        tie_count += 1
                    else:
                        winner_counts[tied_arms[0]] += 1

            denom = any_both_count if any_both_count > 0 else 1
            out_rows.append(
                {
                    "analysis_status": BANNER,
                    "manifest": mname,
                    "band": band,
                    "n_pairs": n_p,
                    "router_arm_name": primary_router,
                    "n_no_arm_meets_both": no_arm_both,
                    "share_no_arm_meets_both": no_arm_both / n_p,
                    "n_only_exact_recall_gt500ms": only_exact_rec_gt500,
                    "n_only_exact_meets_both": only_exact_both,
                    "n_at_least_one_meets_both": any_both_count,
                    "share_fastest_always_exact": winner_counts["always_exact"] / denom if any_both_count else math.nan,
                    "share_fastest_default_hnsw": winner_counts["default_hnsw"] / denom if any_both_count else math.nan,
                    "share_fastest_always_iterative": winner_counts["always_iterative"] / denom if any_both_count else math.nan,
                    "share_fastest_vecadvisor": winner_counts["vecadvisor"] / denom if any_both_count else math.nan,
                    "share_fastest_router": winner_counts[primary_router] / denom if any_both_count else math.nan,
                    "share_fastest_tie_within_1ms": tie_count / denom if any_both_count else math.nan,
                }
            )

    cols = [
        "analysis_status",
        "manifest",
        "band",
        "n_pairs",
        "router_arm_name",
        "n_no_arm_meets_both",
        "share_no_arm_meets_both",
        "n_only_exact_recall_gt500ms",
        "n_only_exact_meets_both",
        "n_at_least_one_meets_both",
        "share_fastest_always_exact",
        "share_fastest_default_hnsw",
        "share_fastest_always_iterative",
        "share_fastest_vecadvisor",
        "share_fastest_router",
        "share_fastest_tie_within_1ms",
    ]
    out_csv = out_dir / "x2b_oracle_constrained.csv"
    _write_csv(out_csv, cols, out_rows)
    return {"csv": out_csv, "rows": out_rows}


def _dispersion_rows_for_file(
    dataset_label: str,
    jsonl_path: Path,
    arm_key: str,
    band_key: str,
    runs_key: str,
    fresh_only: bool = False,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if fresh_only and r.get("reused_measurement"):
            continue
        if r.get("error") is not None or r.get("vecadvisor_unavailable"):
            continue
        if "valid" in r and not r["valid"]:
            continue
        runs = r.get(runs_key)
        if not runs or len(runs) < 2:
            continue
        med = statistics.median(runs)
        if med <= 0:
            continue
        max_med = max(runs) / med
        rng_med = (max(runs) - min(runs)) / med
        grouped[(str(r.get(arm_key, "NA")), str(r.get(band_key, "NA")))].append((max_med, rng_med))

    rows: list[dict[str, Any]] = []
    for (arm, band), vals in sorted(grouped.items()):
        mm = np.array([v[0] for v in vals], dtype=np.float64)
        rm = np.array([v[1] for v in vals], dtype=np.float64)
        q_mm = np.percentile(mm, [50, 90, 95, 99])
        q_rm = np.percentile(rm, [50, 90, 95, 99])
        rows.append(
            {
                "analysis_status": BANNER,
                "dataset": dataset_label,
                "arm_or_mode": arm,
                "band_or_breadth": band,
                "n_rows": len(vals),
                "max_over_med_p50": float(q_mm[0]),
                "max_over_med_p90": float(q_mm[1]),
                "max_over_med_p95": float(q_mm[2]),
                "max_over_med_p99": float(q_mm[3]),
                "range_over_med_p50": float(q_rm[0]),
                "range_over_med_p90": float(q_rm[1]),
                "range_over_med_p95": float(q_rm[2]),
                "range_over_med_p99": float(q_rm[3]),
            }
        )
    return rows


def run_x3b(
    index: dict[str, Any],
    manifest_rows_by_name: dict[str, list[dict[str, str]]],
    out_dir: Path,
) -> dict[str, Any]:
    """X3b: Latency dispersion, drift, and max/median > 1.5 latency-flag check."""
    # (a) Dispersion
    disp_rows: list[dict[str, Any]] = []
    disp_rows.extend(
        _dispersion_rows_for_file(
            "main_union_2026-11-16_fresh",
            RESULTS_DIR / "results.jsonl",
            "arm",
            "band",
            "latency_runs_ms",
            fresh_only=True,
        )
    )
    disp_rows.extend(
        _dispersion_rows_for_file(
            "smoke_2026-11-15",
            SMOKE_RESULTS,
            "arm",
            "band",
            "latency_runs_ms",
            fresh_only=False,
        )
    )
    if AMEND11_RESULTS.exists():
        disp_rows.extend(
            _dispersion_rows_for_file(
                "amendment11_edgar_2026-11-01",
                AMEND11_RESULTS,
                "mode",
                "breadth",
                "latency_raw_ms",
                fresh_only=False,
            )
        )
    disp_cols = [
        "analysis_status",
        "dataset",
        "arm_or_mode",
        "band_or_breadth",
        "n_rows",
        "max_over_med_p50",
        "max_over_med_p90",
        "max_over_med_p95",
        "max_over_med_p99",
        "range_over_med_p50",
        "range_over_med_p90",
        "range_over_med_p95",
        "range_over_med_p99",
    ]
    disp_csv = out_dir / "x3b_latency_dispersion.csv"
    _write_csv(disp_csv, disp_cols, disp_rows)

    # (b) Drift: always_exact fresh valid rows on edgar_chunks and finqa_evidence_qwen3
    drift_decile_rows: list[dict[str, Any]] = []
    drift_corr_rows: list[dict[str, Any]] = []

    all_rows = index["all_rows"]
    for tbl in ["edgar_chunks", "finqa_evidence_qwen3"]:
        exact_rows = [
            r
            for r in all_rows
            if r["arm"] == "always_exact"
            and r["table"] == tbl
            and r["valid"]
            and not r.get("reused_measurement")
        ]
        exact_rows.sort(key=lambda r: datetime.fromisoformat(r["timestamp"]).timestamp())
        x_rows = np.array([r["n_rows"] for r in exact_rows], dtype=np.float64)
        y_ms = np.array([r["latency_median_ms"] for r in exact_rows], dtype=np.float64)
        ts_sec = np.array(
            [datetime.fromisoformat(r["timestamp"]).timestamp() for r in exact_rows],
            dtype=np.float64,
        )
        slope_per_1000, intercept = A.compute_ols_slope_per_1000(x_rows, y_ms)
        pred = intercept + (slope_per_1000 / 1000.0) * x_rows
        resid = y_ms - pred

        rho, p_val = spearman_corr(ts_sec, resid)
        drift_corr_rows.append(
            {
                "analysis_status": BANNER,
                "table": tbl,
                "n_rows": len(exact_rows),
                "ols_slope_ms_per_1000": slope_per_1000,
                "ols_intercept_ms": intercept,
                "spearman_rho_resid_vs_ts": rho,
                "approx_p_two_sided": p_val,
            }
        )

        splits = np.array_split(np.arange(len(exact_rows)), 10)
        t0 = ts_sec[0]
        for d_idx, idxs in enumerate(splits, start=1):
            drift_decile_rows.append(
                {
                    "analysis_status": BANNER,
                    "table": tbl,
                    "decile": d_idx,
                    "n_rows": len(idxs),
                    "elapsed_min_start": (ts_sec[idxs[0]] - t0) / 60.0,
                    "elapsed_min_end": (ts_sec[idxs[-1]] - t0) / 60.0,
                    "mean_residual_ms": float(np.mean(resid[idxs])),
                    "median_residual_ms": float(np.median(resid[idxs])),
                }
            )

    _write_csv(
        out_dir / "x3b_drift_spearman.csv",
        [
            "analysis_status",
            "table",
            "n_rows",
            "ols_slope_ms_per_1000",
            "ols_intercept_ms",
            "spearman_rho_resid_vs_ts",
            "approx_p_two_sided",
        ],
        drift_corr_rows,
    )
    _write_csv(
        out_dir / "x3b_drift_deciles.csv",
        [
            "analysis_status",
            "table",
            "decile",
            "n_rows",
            "elapsed_min_start",
            "elapsed_min_end",
            "mean_residual_ms",
            "median_residual_ms",
        ],
        drift_decile_rows,
    )

    # (c) Rows with max/median > 1.5 and latency pass flags (<= 500 ms)
    valid_fresh = [
        r
        for r in all_rows
        if r["valid"] and not r.get("reused_measurement") and not r.get("vecadvisor_unavailable")
    ]
    spike_flags = [
        max(r["latency_runs_ms"]) / statistics.median(r["latency_runs_ms"]) > 1.5
        for r in valid_fresh
    ]
    n_valid_fresh = len(valid_fresh)
    n_spikes = sum(1 for f in spike_flags if f)
    spike_share = n_spikes / n_valid_fresh if n_valid_fresh else 0.0

    # Build filtered index excluding rows where max/median > 1.5
    kept_fixed = {}
    kept_router = {}
    kept_router_qp = {}
    for r in all_rows:
        if r["valid"] and not r.get("vecadvisor_unavailable"):
            runs = r.get("latency_runs_ms") or []
            if runs and (max(runs) / statistics.median(runs) > 1.5):
                continue
        qid = str(r["qid"])
        pool_id = str(r["pool_id"])
        arm = str(r["arm"])
        t_name = str(r.get("T_name", ""))
        if arm in A.FIXED_ARMS:
            kept_fixed[(qid, pool_id, arm)] = r
        else:
            kept_router[(qid, pool_id, t_name, arm)] = r
            kept_router_qp.setdefault((qid, pool_id, arm), []).append(r)

    kept_index = {
        "fixed": kept_fixed,
        "router": kept_router,
        "router_by_qp_arm": kept_router_qp,
        "all_rows": [],
    }

    flag_rows: list[dict[str, Any]] = []
    changed_flags: list[dict[str, Any]] = []

    for mname in A.PRIMARY_SECONDARY_MANIFESTS:
        mrows = manifest_rows_by_name[mname]
        full_map = A.build_manifest_records(mname, mrows, index)
        kept_map = A.build_manifest_records(mname, mrows, kept_index)

        for arm in full_map:
            # Bands
            for band in A.BANDS_ORDER:
                f_recs = [r for r in full_map[arm] if r["band"] == band and r["valid"]]
                k_recs = [r for r in kept_map[arm] if r["band"] == band and r["valid"]]
                if not f_recs:
                    continue
                f_med = float(np.median([r["latency_median_ms"] for r in f_recs]))
                k_med = float(np.median([r["latency_median_ms"] for r in k_recs])) if k_recs else math.nan
                f_pass = bool(f_med <= A.LATENCY_THRESHOLD_MS)
                k_pass = bool(k_med <= A.LATENCY_THRESHOLD_MS) if not math.isnan(k_med) else False
                changed = (f_pass != k_pass)
                row_d = {
                    "analysis_status": BANNER,
                    "manifest": mname,
                    "arm": arm,
                    "level": "band",
                    "band_or_group": band,
                    "n_valid_all": len(f_recs),
                    "n_valid_no_spike": len(k_recs),
                    "median_lat_all_ms": f_med,
                    "median_lat_no_spike_ms": k_med,
                    "lat_pass_all": f_pass,
                    "lat_pass_no_spike": k_pass,
                    "flag_changed": changed,
                }
                flag_rows.append(row_d)
                if changed:
                    changed_flags.append(row_d)

            # Groups on EDGAR
            if "edgar" in mname:
                for grp, comp in [("below_T", ["far_below", "near_below"]), ("above_T", ["near_above", "far_above"])]:
                    f_recs = [r for r in full_map[arm] if r["band"] in comp and r["valid"]]
                    k_recs = [r for r in kept_map[arm] if r["band"] in comp and r["valid"]]
                    if not f_recs:
                        continue
                    f_med = float(np.median([r["latency_median_ms"] for r in f_recs]))
                    k_med = float(np.median([r["latency_median_ms"] for r in k_recs])) if k_recs else math.nan
                    f_pass = bool(f_med <= A.LATENCY_THRESHOLD_MS)
                    k_pass = bool(k_med <= A.LATENCY_THRESHOLD_MS) if not math.isnan(k_med) else False
                    changed = (f_pass != k_pass)
                    row_d = {
                        "analysis_status": BANNER,
                        "manifest": mname,
                        "arm": arm,
                        "level": "group",
                        "band_or_group": grp,
                        "n_valid_all": len(f_recs),
                        "n_valid_no_spike": len(k_recs),
                        "median_lat_all_ms": f_med,
                        "median_lat_no_spike_ms": k_med,
                        "lat_pass_all": f_pass,
                        "lat_pass_no_spike": k_pass,
                        "flag_changed": changed,
                    }
                    flag_rows.append(row_d)
                    if changed:
                        changed_flags.append(row_d)

    _write_csv(
        out_dir / "x3b_latency_pass_flag_check.csv",
        [
            "analysis_status",
            "manifest",
            "arm",
            "level",
            "band_or_group",
            "n_valid_all",
            "n_valid_no_spike",
            "median_lat_all_ms",
            "median_lat_no_spike_ms",
            "lat_pass_all",
            "lat_pass_no_spike",
            "flag_changed",
        ],
        flag_rows,
    )

    return {
        "disp_csv": disp_csv,
        "disp_rows": disp_rows,
        "drift_corr_rows": drift_corr_rows,
        "drift_decile_rows": drift_decile_rows,
        "n_valid_fresh": n_valid_fresh,
        "n_spikes": n_spikes,
        "spike_share": spike_share,
        "changed_flags": changed_flags,
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

    x1b = run_x1b(manifest_records, OUT_DIR)
    x2b = run_x2b(manifest_records, OUT_DIR)
    x3b = run_x3b(index, manifest_rows_by_name, OUT_DIR)

    report = [
        f"# {BANNER}",
        "",
        "## X1b: Counterfactual Threshold Sweep (Per Band and Per Group)",
        "> **Note:** Descriptive counterfactual only over measured `always_exact` and `always_iterative` arms (overhead of estimate, count, and guard ignored); **not** a recommended threshold.",
        "",
    ]
    for mname, info in x1b["summary"].items():
        report.append(f"- **{mname}:**")
        for b, ts in info["band_passing_ts"].items():
            report.append(f"  - `{b}` passing `T'`: `{ts}`")
        report.append(f"  - Bands passing for no `T'`: `{info['no_pass_bands']}`")
        if info["edgar_all_except_far_above_ts"] is not None:
            report.append(
                f"  - `T'` where all bands except `far_above` pass: `{info['edgar_all_except_far_above_ts']}`"
            )
    report.extend(
        [
            "",
            "## X2b: Constrained Oracle (`recall@15 >= 14/15` AND `median_latency_ms <= 500`)",
            "- See `x2b_oracle_constrained.csv`.",
            "",
            "## X3b: Latency Dispersion, Drift, and Spike Check (`max/median > 1.5`)",
            f"- Fresh valid rows with `max/median > 1.5`: `{x3b['n_spikes']}` / `{x3b['n_valid_fresh']}` (`{x3b['spike_share']:.4%}`).",
            f"- Confirmatory latency pass flags changed when excluding `max/median > 1.5` rows: `{len(x3b['changed_flags'])}`.",
            "- See `x3b_latency_dispersion.csv`, `x3b_drift_spearman.csv`, `x3b_drift_deciles.csv`, `x3b_latency_pass_flag_check.csv`.",
            "",
        ]
    )
    (OUT_DIR / "EXPLORATORY_REPORT_V2.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Exploratory v2 outputs written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
