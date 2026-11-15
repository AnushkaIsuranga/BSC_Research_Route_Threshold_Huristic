"""Straddle-T analysis script per Amendment 12 Addendum 3.

Reads results.jsonl from run_straddle.py, joins to the manifest CSV files,
and computes the exact confirmatory, secondary, and descriptive statistics
defined in docs/preregistration/PHASE_G_AMENDMENT_12_ADDENDUM_3.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFESTS_DIR = REPO_ROOT / "outputs" / "straddle_t_manifest_2026-11-15"
VALIDATION_OUT_DIR = REPO_ROOT / "outputs" / "straddle_t_analysis_validation"

BOOTSTRAP_SEED = 20261115
BOOTSTRAP_B = 10_000
RECALL_THRESHOLD = 0.90
LATENCY_THRESHOLD_MS = 500.0
PAIR_RECALL_THRESHOLD = 14.0 / 15.0 - 1e-12
HOLM_ALPHA = 0.05

BANDS_ORDER = ["far_below", "near_below", "near_above", "far_above"]
FIXED_ARMS = ["always_exact", "default_hnsw", "always_iterative", "vecadvisor"]
ROUTER_ARMS = ["router", "router_hmT"]
ALL_ARMS = ["router", "router_hmT", "always_exact", "default_hnsw", "always_iterative", "vecadvisor"]

PRIMARY_SECONDARY_MANIFESTS = [
    "edgar_pairs_primary_T_edgar.csv",
    "edgar_pairs_secondary_T_hm.csv",
    "finqa_pairs_primary_T_hm.csv",
    "finqa_pairs_secondary_random.csv",
]
SENSITIVITY_MANIFESTS = [
    "natural_only_edgar_T_edgar.csv",
    "natural_only_edgar_T_hm.csv",
    "natural_only_finqa_T_hm.csv",
    "natural_only_finqa_random.csv",
]

BAND_TABLE_COLUMNS = [
    "arm",
    "manifest",
    "band",
    "tier_set",
    "n_pairs",
    "n_valid",
    "n_invalid",
    "n_unavailable",
    "mean_recall",
    "median_latency_ms",
    "pass",
    "q_ci_recall_lo",
    "q_ci_recall_hi",
    "q_ci_lat_lo",
    "q_ci_lat_hi",
    "f_ci_recall_lo",
    "f_ci_recall_hi",
    "f_ci_lat_lo",
    "f_ci_lat_hi",
    "q_recall_crosses",
    "f_recall_crosses",
    "q_lat_crosses",
    "f_lat_crosses",
    "recall_inconclusive",
    "lat_inconclusive",
    "overall_inconclusive",
]

GROUP_TABLE_COLUMNS = [
    "arm",
    "manifest",
    "group",
    "component_bands",
    "tier_set",
    "n_pairs",
    "n_valid",
    "n_invalid",
    "n_unavailable",
    "mean_recall",
    "median_latency_ms",
    "pass",
    "q_ci_recall_lo",
    "q_ci_recall_hi",
    "q_ci_lat_lo",
    "q_ci_lat_hi",
    "f_ci_recall_lo",
    "f_ci_recall_hi",
    "f_ci_lat_lo",
    "f_ci_lat_hi",
    "q_recall_crosses",
    "f_recall_crosses",
    "q_lat_crosses",
    "f_lat_crosses",
    "recall_inconclusive",
    "lat_inconclusive",
    "overall_inconclusive",
]

HYPOTHESES_COLUMNS = [
    "hypothesis",
    "group",
    "manifest",
    "arm",
    "component_bands",
    "direction",
    "point_estimate_satisfied",
    "raw_p_question_clustered",
    "raw_p_filter_clustered",
    "holm_adjusted_p",
    "decision",
]

SECONDARY_TABLES_COLUMNS = [
    "subtable",
    "manifest",
    "arm",
    "stratum",
    "band",
    "n_pairs",
    "n_valid",
    "n_invalid",
    "n_unavailable",
    "mean_recall",
    "median_latency_ms",
    "band_pass",
    "pair_pass_count",
    "pair_pass_rate",
    "q_ci_pair_pass_lo",
    "q_ci_pair_pass_hi",
    "q_ci_recall_lo",
    "q_ci_recall_hi",
    "q_ci_lat_lo",
    "q_ci_lat_hi",
]

DESCRIPTIVE_TABLES_COLUMNS = [
    "analysis_type",
    "table_or_manifest",
    "band_or_scope",
    "arm_or_route",
    "n_pairs",
    "n_valid",
    "n_unavailable",
    "metric_name",
    "estimate",
    "ci_lo",
    "ci_hi",
    "notes",
]


def check_smoke_guard(
    results_path: Path,
    manifests_dir: Path,
    out_dir: Path,
    validation: bool,
) -> Path:
    """Enforce Addendum 3 Step 3 smoke guard.

    Refuses to read any --results or --manifests-dir path containing 'smoke'
    unless --validation is given, in which case it writes only to
    outputs/straddle_t_analysis_validation/ and prints a banner.
    """
    has_smoke = (
        "smoke" in str(results_path).lower()
        or "smoke" in str(manifests_dir).lower()
    )
    if has_smoke and not validation:
        raise ValueError(
            "Refusing to analyze path containing 'smoke' without --validation flag. "
            "Pass --validation to run format validation into outputs/straddle_t_analysis_validation/."
        )
    if validation:
        print("=" * 78)
        print("VALIDATION MODE ONLY (NOT REPORTABLE): Output forced to outputs/straddle_t_analysis_validation/")
        print("=" * 78)
        return VALIDATION_OUT_DIR
    return out_dir


def verify_manifest_checksums(manifests_dir: Path) -> None:
    """Verify MANIFEST_CHECKSUMS.txt in manifests_dir before reading manifests."""
    checksum_file = manifests_dir / "MANIFEST_CHECKSUMS.txt"
    if not checksum_file.exists():
        raise FileNotFoundError(f"Missing {checksum_file}")
    with open(checksum_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"Invalid checksum line in {checksum_file}: {line!r}")
            expected_sha, fname = parts
            fpath = manifests_dir / Path(fname).name
            if not fpath.exists():
                fpath = REPO_ROOT / fname
            if not fpath.exists():
                raise FileNotFoundError(f"Manifest file missing: {fpath}")
            actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
            if actual_sha.lower() != expected_sha.lower():
                raise ValueError(
                    f"Checksum mismatch for {fname}: expected {expected_sha}, got {actual_sha}"
                )


def load_results_index(results_path: Path) -> dict[str, Any]:
    """Load results.jsonl and index fixed arms by (qid, pool_id, arm) and router arms by (qid, pool_id, T_name, arm)."""
    fixed_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    router_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    router_by_qp_arm: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    all_rows: list[dict[str, Any]] = []

    with open(results_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            all_rows.append(row)
            qid = str(row["qid"])
            pool_id = str(row["pool_id"])
            arm = str(row["arm"])
            t_name = str(row.get("T_name", ""))
            if arm in FIXED_ARMS:
                fixed_by_key[(qid, pool_id, arm)] = row
            else:
                router_by_key[(qid, pool_id, t_name, arm)] = row
                router_by_qp_arm.setdefault((qid, pool_id, arm), []).append(row)

    return {
        "fixed": fixed_by_key,
        "router": router_by_key,
        "router_by_qp_arm": router_by_qp_arm,
        "all_rows": all_rows,
    }


def load_manifest_rows(manifest_path: Path) -> list[dict[str, str]]:
    with open(manifest_path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def infer_corpus(mrow: dict[str, str]) -> str:
    """Infer corpus ('edgar' or 'finqa') from manifest row."""
    if "corpus" in mrow and mrow["corpus"]:
        return mrow["corpus"].strip().lower()
    pid = str(mrow.get("pair_id", "")).lower()
    pool_id = str(mrow.get("pool_id", "")).lower()
    if pid.startswith("edgar") or pool_id.startswith("edgar"):
        return "edgar"
    return "finqa"


def get_arms_for_manifest_row(mrow: dict[str, str]) -> list[str]:
    """Return applicable arms for a manifest row."""
    corpus = infer_corpus(mrow)
    if corpus == "edgar":
        return ["router", "router_hmT", "always_exact", "default_hnsw", "always_iterative", "vecadvisor"]
    return ["router_hmT", "always_exact", "default_hnsw", "always_iterative", "vecadvisor"]


def resolve_arm_row(
    index: dict[str, Any],
    qid: str,
    pool_id: str,
    t_name: str,
    arm: str,
) -> dict[str, Any] | None:
    """Resolve the logged result row for a manifest pair and arm."""
    if arm in FIXED_ARMS:
        return index["fixed"].get((qid, pool_id, arm))
    row = index["router"].get((qid, pool_id, t_name, arm))
    if row is not None:
        return row
    # Fallback for router_hmT if shared across T_name on same (qid, pool_id)
    candidates = index["router_by_qp_arm"].get((qid, pool_id, arm), [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def evaluate_pair_validity(
    arm_row: dict[str, Any] | None,
    exact_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate validity and metrics of a single pair for an arm per Addendum 3 Sec 1."""
    if arm_row is None:
        return {
            "status": "invalid",
            "valid": False,
            "unavailable": False,
            "recall_at_15": None,
            "latency_median_ms": None,
            "route_taken": None,
            "unavailable_reason": None,
        }

    if bool(arm_row.get("vecadvisor_unavailable", False)):
        reason = arm_row.get("vecadvisor_unavailable_reason") or arm_row.get("unavailable_reason") or arm_row.get("error")
        return {
            "status": "unavailable",
            "valid": False,
            "unavailable": True,
            "recall_at_15": None,
            "latency_median_ms": None,
            "route_taken": arm_row.get("route_taken"),
            "unavailable_reason": reason,
        }

    exact_ok = (
        exact_row is not None
        and bool(exact_row.get("valid", False))
        and exact_row.get("recall_at_15") is not None
    )
    arm_ok = (
        bool(arm_row.get("valid", False))
        and arm_row.get("recall_at_15") is not None
        and arm_row.get("latency_median_ms") is not None
    )

    if exact_ok and arm_ok:
        return {
            "status": "valid",
            "valid": True,
            "unavailable": False,
            "recall_at_15": float(arm_row["recall_at_15"]),
            "latency_median_ms": float(arm_row["latency_median_ms"]),
            "route_taken": arm_row.get("route_taken"),
            "unavailable_reason": None,
        }

    return {
        "status": "invalid",
        "valid": False,
        "unavailable": False,
        "recall_at_15": None,
        "latency_median_ms": None,
        "route_taken": arm_row.get("route_taken"),
        "unavailable_reason": arm_row.get("error"),
    }


def compute_band_pass(
    n_pairs: int,
    n_valid: int,
    n_invalid: int,
    n_unavailable: int,
    mean_recall: float,
    median_latency_ms: float,
) -> bool:
    """Addendum 3 Section 2 band pass rule.

    A band passes iff all pairs in the band are valid (no invalid and no unavailable pairs),
    mean(recall_at_15) >= 0.90, and median(latency_median_ms) <= 500 ms.
    """
    if n_pairs <= 0 or n_valid != n_pairs or n_invalid > 0 or n_unavailable > 0:
        return False
    if math.isnan(mean_recall) or math.isnan(median_latency_ms):
        return False
    return bool(mean_recall >= RECALL_THRESHOLD and median_latency_ms <= LATENCY_THRESHOLD_MS)


def cluster_bootstrap_stats(
    records: list[dict[str, Any]],
    cluster_key: str,
    rng: np.random.Generator,
    b_resamples: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Perform nonparametric cluster bootstrap over valid records.

    Resamples distinct cluster_key values with replacement and keeps all their pairs
    in the band or group. Computes mean(recall_at_15), median(latency_median_ms),
    and mean(pair_pass) for each of B resamples.
    """
    valid_recs = [r for r in records if r["valid"]]
    if not valid_recs:
        empty = np.full(b_resamples, np.nan)
        return {
            "boot_mean_recall": empty,
            "boot_median_lat": empty,
            "boot_pair_pass_rate": empty,
            "ci_recall": (math.nan, math.nan),
            "ci_lat": (math.nan, math.nan),
            "ci_pair_pass": (math.nan, math.nan),
        }

    # Group valid records by cluster_key in deterministic order of first appearance
    clusters: list[str] = []
    cluster_map: dict[str, list[int]] = {}
    for idx, rec in enumerate(valid_recs):
        ck = str(rec[cluster_key])
        if ck not in cluster_map:
            clusters.append(ck)
            cluster_map[ck] = []
        cluster_map[ck].append(idx)

    k_clusters = len(clusters)
    recalls = np.array([r["recall_at_15"] for r in valid_recs], dtype=np.float64)
    lats = np.array([r["latency_median_ms"] for r in valid_recs], dtype=np.float64)
    pair_passes = np.array(
        [
            1.0
            if (r["recall_at_15"] >= PAIR_RECALL_THRESHOLD and r["latency_median_ms"] <= LATENCY_THRESHOLD_MS)
            else 0.0
            for r in valid_recs
        ],
        dtype=np.float64,
    )

    # Check if every cluster has size 1 (fast path)
    all_singleton = all(len(cluster_map[ck]) == 1 for ck in clusters)
    draws = rng.integers(0, k_clusters, size=(b_resamples, k_clusters))

    if all_singleton:
        # Order arrays by cluster order
        order_idx = np.array([cluster_map[ck][0] for ck in clusters], dtype=np.int64)
        r_ordered = recalls[order_idx]
        l_ordered = lats[order_idx]
        p_ordered = pair_passes[order_idx]

        boot_recalls = r_ordered[draws].mean(axis=1)
        boot_lats = np.median(l_ordered[draws], axis=1)
        boot_passes = p_ordered[draws].mean(axis=1)
    else:
        # General path for variable-size clusters
        cluster_r_sums = np.array([recalls[cluster_map[ck]].sum() for ck in clusters], dtype=np.float64)
        cluster_p_sums = np.array([pair_passes[cluster_map[ck]].sum() for ck in clusters], dtype=np.float64)
        cluster_counts = np.array([len(cluster_map[ck]) for ck in clusters], dtype=np.float64)
        cluster_lat_arrays = [lats[cluster_map[ck]] for ck in clusters]

        total_counts = cluster_counts[draws].sum(axis=1)
        boot_recalls = cluster_r_sums[draws].sum(axis=1) / total_counts
        boot_passes = cluster_p_sums[draws].sum(axis=1) / total_counts

        boot_lats = np.empty(b_resamples, dtype=np.float64)
        for b_idx in range(b_resamples):
            sampled_lats = np.concatenate([cluster_lat_arrays[c_i] for c_i in draws[b_idx]])
            boot_lats[b_idx] = np.median(sampled_lats)

    ci_recall = (float(np.percentile(boot_recalls, 2.5)), float(np.percentile(boot_recalls, 97.5)))
    ci_lat = (float(np.percentile(boot_lats, 2.5)), float(np.percentile(boot_lats, 97.5)))
    ci_pair_pass = (float(np.percentile(boot_passes, 2.5)), float(np.percentile(boot_passes, 97.5)))

    return {
        "boot_mean_recall": boot_recalls,
        "boot_median_lat": boot_lats,
        "boot_pair_pass_rate": boot_passes,
        "ci_recall": ci_recall,
        "ci_lat": ci_lat,
        "ci_pair_pass": ci_pair_pass,
    }


def crosses_threshold(ci_lo: float, ci_hi: float, threshold: float) -> bool:
    """True when the 95% CI includes/straddles the threshold."""
    if math.isnan(ci_lo) or math.isnan(ci_hi):
        return False
    return bool(ci_lo <= threshold <= ci_hi)


def compute_one_sided_pvalue_meets_rule(
    boot_mean_recall: np.ndarray,
    boot_median_lat: np.ndarray,
    n_invalid: int = 0,
    n_unavailable: int = 0,
) -> float:
    """Addendum 3 Sec 4 one-sided bootstrap p-value for 'meets the rule' in a band or group.

    p = max((#{boot mean recall < 0.90} + 1)/(B + 1), (#{boot median latency > 500} + 1)/(B + 1))
    """
    if n_invalid > 0 or n_unavailable > 0 or len(boot_mean_recall) == 0 or np.isnan(boot_mean_recall).any():
        return 1.0
    b = len(boot_mean_recall)
    count_rec_fail = int(np.sum(boot_mean_recall < RECALL_THRESHOLD))
    count_lat_fail = int(np.sum(boot_median_lat > LATENCY_THRESHOLD_MS))
    p_rec = (count_rec_fail + 1.0) / (b + 1.0)
    p_lat = (count_lat_fail + 1.0) / (b + 1.0)
    return float(max(p_rec, p_lat))


def compute_one_sided_pvalue_fails_recall(
    boot_mean_recall: np.ndarray,
    n_invalid: int = 0,
    n_unavailable: int = 0,
) -> float:
    """Addendum 3 Sec 4 one-sided bootstrap p-value for 'fails the recall criterion' in a band.

    p = (#{boot mean recall >= 0.90} + 1)/(B + 1)
    """
    if n_invalid > 0 or n_unavailable > 0 or len(boot_mean_recall) == 0 or np.isnan(boot_mean_recall).any():
        return 1.0
    b = len(boot_mean_recall)
    count_rec_pass = int(np.sum(boot_mean_recall >= RECALL_THRESHOLD))
    return float((count_rec_pass + 1.0) / (b + 1.0))


def holm_adjust(p_values: list[float]) -> list[float]:
    """Step-down Holm-Bonferroni adjustment across m hypotheses."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, (orig_idx, p_val) in enumerate(indexed):
        mult = m - rank
        adj = min(1.0, mult * float(p_val))
        running_max = max(running_max, adj)
        adjusted[orig_idx] = running_max
    return adjusted


def fmt_float(val: float | None) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "NA"
    return f"{val:.6f}"


def summarize_records(
    records: list[dict[str, Any]],
    q_rng: np.random.Generator,
    f_rng: np.random.Generator,
    b_resamples: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Compute band/group summary statistics and question/filter clustered bootstrap CIs."""
    n_pairs = len(records)
    valid_recs = [r for r in records if r["valid"]]
    n_valid = len(valid_recs)
    n_unavailable = sum(1 for r in records if r["unavailable"])
    n_invalid = n_pairs - n_valid - n_unavailable

    if n_valid > 0:
        mean_recall = float(np.mean([r["recall_at_15"] for r in valid_recs]))
        median_latency_ms = float(np.median([r["latency_median_ms"] for r in valid_recs]))
        pair_pass_count = sum(
            1
            for r in valid_recs
            if r["recall_at_15"] >= PAIR_RECALL_THRESHOLD and r["latency_median_ms"] <= LATENCY_THRESHOLD_MS
        )
        pair_pass_rate = float(pair_pass_count / n_valid) if n_invalid == 0 else float(pair_pass_count / n_pairs)
    else:
        mean_recall = math.nan
        median_latency_ms = math.nan
        pair_pass_count = 0
        pair_pass_rate = math.nan

    passed = compute_band_pass(
        n_pairs=n_pairs,
        n_valid=n_valid,
        n_invalid=n_invalid,
        n_unavailable=n_unavailable,
        mean_recall=mean_recall,
        median_latency_ms=median_latency_ms,
    )

    q_boot = cluster_bootstrap_stats(records, "qid", q_rng, b_resamples=b_resamples)
    f_boot = cluster_bootstrap_stats(records, "pool_id", f_rng, b_resamples=b_resamples)

    q_rec_lo, q_rec_hi = q_boot["ci_recall"]
    q_lat_lo, q_lat_hi = q_boot["ci_lat"]
    f_rec_lo, f_rec_hi = f_boot["ci_recall"]
    f_lat_lo, f_lat_hi = f_boot["ci_lat"]

    q_rec_cross = crosses_threshold(q_rec_lo, q_rec_hi, RECALL_THRESHOLD)
    f_rec_cross = crosses_threshold(f_rec_lo, f_rec_hi, RECALL_THRESHOLD)
    q_lat_cross = crosses_threshold(q_lat_lo, q_lat_hi, LATENCY_THRESHOLD_MS)
    f_lat_cross = crosses_threshold(f_lat_lo, f_lat_hi, LATENCY_THRESHOLD_MS)

    rec_inconc = bool(q_rec_cross != f_rec_cross)
    lat_inconc = bool(q_lat_cross != f_lat_cross)
    overall_inconc = bool(rec_inconc or lat_inconc)

    p_meets_q = compute_one_sided_pvalue_meets_rule(
        q_boot["boot_mean_recall"], q_boot["boot_median_lat"], n_invalid, n_unavailable
    )
    p_meets_f = compute_one_sided_pvalue_meets_rule(
        f_boot["boot_mean_recall"], f_boot["boot_median_lat"], n_invalid, n_unavailable
    )
    p_fails_rec_q = compute_one_sided_pvalue_fails_recall(
        q_boot["boot_mean_recall"], n_invalid, n_unavailable
    )
    p_fails_rec_f = compute_one_sided_pvalue_fails_recall(
        f_boot["boot_mean_recall"], n_invalid, n_unavailable
    )

    return {
        "n_pairs": n_pairs,
        "n_valid": n_valid,
        "n_invalid": n_invalid,
        "n_unavailable": n_unavailable,
        "mean_recall": mean_recall,
        "median_latency_ms": median_latency_ms,
        "pass": passed,
        "pair_pass_count": pair_pass_count,
        "pair_pass_rate": pair_pass_rate,
        "q_ci_pair_pass_lo": q_boot["ci_pair_pass"][0],
        "q_ci_pair_pass_hi": q_boot["ci_pair_pass"][1],
        "q_ci_recall_lo": q_rec_lo,
        "q_ci_recall_hi": q_rec_hi,
        "q_ci_lat_lo": q_lat_lo,
        "q_ci_lat_hi": q_lat_hi,
        "f_ci_recall_lo": f_rec_lo,
        "f_ci_recall_hi": f_rec_hi,
        "f_ci_lat_lo": f_lat_lo,
        "f_ci_lat_hi": f_lat_hi,
        "q_recall_crosses": q_rec_cross,
        "f_recall_crosses": f_rec_cross,
        "q_lat_crosses": q_lat_cross,
        "f_lat_crosses": f_lat_cross,
        "recall_inconclusive": rec_inconc,
        "lat_inconclusive": lat_inconc,
        "overall_inconclusive": overall_inconc,
        "p_meets_q": p_meets_q,
        "p_meets_f": p_meets_f,
        "p_fails_rec_q": p_fails_rec_q,
        "p_fails_rec_f": p_fails_rec_f,
    }


def build_manifest_records(
    manifest_name: str,
    mrows: list[dict[str, str]],
    index: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Join manifest rows with results.jsonl rows for each applicable arm."""
    if not mrows:
        return {}
    # Determine the union of arms present in this manifest (smoke_test_pairs.csv has both edgar and finqa rows)
    arms_seen: list[str] = []
    for mrow in mrows:
        for a in get_arms_for_manifest_row(mrow):
            if a not in arms_seen:
                arms_seen.append(a)
    records_by_arm: dict[str, list[dict[str, Any]]] = {arm: [] for arm in arms_seen}

    for mrow in mrows:
        qid = str(mrow["qid"])
        pool_id = str(mrow["pool_id"])
        t_name = str(mrow["T_name"])
        band = str(mrow["band"])
        tier = str(mrow.get("tier") or mrow.get("question_tier", ""))
        boundary_flag = str(mrow.get("boundary_flag", "False")).lower() == "true"
        n_rows = int(mrow["n_rows"])
        selectivity = float(mrow.get("s") if "s" in mrow and mrow["s"] != "" else mrow["selectivity"])
        corpus = infer_corpus(mrow)
        row_arms = get_arms_for_manifest_row(mrow)

        exact_row = resolve_arm_row(index, qid, pool_id, t_name, "always_exact")
        for arm in row_arms:
            arm_row = resolve_arm_row(index, qid, pool_id, t_name, arm)
            ev = evaluate_pair_validity(arm_row, exact_row)
            records_by_arm[arm].append(
                {
                    "manifest": manifest_name,
                    "pair_id": mrow["pair_id"],
                    "corpus": corpus,
                    "qid": qid,
                    "pool_id": pool_id,
                    "T_name": t_name,
                    "band": band,
                    "question_tier": tier,
                    "boundary_flag": boundary_flag,
                    "n_rows": n_rows,
                    "selectivity": selectivity,
                    "arm": arm,
                    **ev,
                }
            )
    return records_by_arm


def compute_ols_slope_per_1000(
    x_rows: np.ndarray,
    y_ms: np.ndarray,
) -> tuple[float, float]:
    """Return (slope_ms_per_1000_rows, intercept_ms) via ordinary least squares."""
    if len(x_rows) < 2:
        return (math.nan, math.nan)
    x_mean = float(np.mean(x_rows))
    y_mean = float(np.mean(y_ms))
    dx = x_rows - x_mean
    var_x = float(np.sum(dx * dx))
    if var_x <= 0.0:
        return (math.nan, y_mean)
    cov_xy = float(np.sum(dx * (y_ms - y_mean)))
    slope_per_row = cov_xy / var_x
    intercept = y_mean - slope_per_row * x_mean
    return (float(1000.0 * slope_per_row), float(intercept))


def bootstrap_ols_slope(
    records: list[dict[str, Any]],
    rng: np.random.Generator,
    b_resamples: int = BOOTSTRAP_B,
) -> dict[str, float]:
    """Question-clustered 95% CI for E1 OLS slope (ms per 1,000 matched rows) and intercept."""
    valid_recs = [r for r in records if r["valid"]]
    if len(valid_recs) < 2:
        return {
            "slope": math.nan,
            "slope_ci_lo": math.nan,
            "slope_ci_hi": math.nan,
            "intercept": math.nan,
            "intercept_ci_lo": math.nan,
            "intercept_ci_hi": math.nan,
        }
    x_all = np.array([r["n_rows"] for r in valid_recs], dtype=np.float64)
    y_all = np.array([r["latency_median_ms"] for r in valid_recs], dtype=np.float64)
    slope, intercept = compute_ols_slope_per_1000(x_all, y_all)

    clusters: list[str] = []
    cluster_map: dict[str, list[int]] = {}
    for idx, rec in enumerate(valid_recs):
        ck = str(rec["qid"])
        if ck not in cluster_map:
            clusters.append(ck)
            cluster_map[ck] = []
        cluster_map[ck].append(idx)

    k_clusters = len(clusters)
    draws = rng.integers(0, k_clusters, size=(b_resamples, k_clusters))
    cluster_x = [x_all[cluster_map[ck]] for ck in clusters]
    cluster_y = [y_all[cluster_map[ck]] for ck in clusters]

    boot_slopes = np.empty(b_resamples, dtype=np.float64)
    boot_intercepts = np.empty(b_resamples, dtype=np.float64)
    for b_idx in range(b_resamples):
        bx = np.concatenate([cluster_x[c_i] for c_i in draws[b_idx]])
        by = np.concatenate([cluster_y[c_i] for c_i in draws[b_idx]])
        s_b, i_b = compute_ols_slope_per_1000(bx, by)
        boot_slopes[b_idx] = s_b
        boot_intercepts[b_idx] = i_b

    valid_s = boot_slopes[~np.isnan(boot_slopes)]
    valid_i = boot_intercepts[~np.isnan(boot_intercepts)]
    return {
        "slope": slope,
        "slope_ci_lo": float(np.percentile(valid_s, 2.5)) if len(valid_s) else math.nan,
        "slope_ci_hi": float(np.percentile(valid_s, 97.5)) if len(valid_s) else math.nan,
        "intercept": intercept,
        "intercept_ci_lo": float(np.percentile(valid_i, 2.5)) if len(valid_i) else math.nan,
        "intercept_ci_hi": float(np.percentile(valid_i, 97.5)) if len(valid_i) else math.nan,
    }


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            out_row = {}
            for col in columns:
                val = r.get(col, "NA")
                if isinstance(val, bool):
                    out_row[col] = "True" if val else "False"
                elif isinstance(val, float):
                    out_row[col] = fmt_float(val)
                elif val is None:
                    out_row[col] = "NA"
                else:
                    out_row[col] = str(val)
            writer.writerow(out_row)


def run_analysis(
    results_path: Path,
    manifests_dir: Path,
    out_dir: Path,
    validation: bool = False,
    b_resamples: int = BOOTSTRAP_B,
) -> dict[str, Path]:
    """Run the full Addendum 3 analysis and write all 6 required files."""
    actual_out_dir = check_smoke_guard(results_path, manifests_dir, out_dir, validation)
    verify_manifest_checksums(manifests_dir)
    index = load_results_index(results_path)

    if validation and "smoke" in str(results_path).lower():
        manifest_names_main = ["smoke_test_pairs.csv"]
        manifest_names_sens: list[str] = []
    else:
        manifest_names_main = list(PRIMARY_SECONDARY_MANIFESTS)
        manifest_names_sens = list(SENSITIVITY_MANIFESTS)

    seed_seq = np.random.SeedSequence(BOOTSTRAP_SEED)

    def next_rng_pair() -> tuple[np.random.Generator, np.random.Generator]:
        children = seed_seq.spawn(2)
        return np.random.default_rng(children[0]), np.random.default_rng(children[1])

    band_table_rows: list[dict[str, Any]] = []
    group_table_rows: list[dict[str, Any]] = []
    secondary_rows: list[dict[str, Any]] = []
    descriptive_rows: list[dict[str, Any]] = []

    # Store computed stats keyed by (manifest, arm, band_or_group) for hypotheses
    stats_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    all_manifest_records: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for mname in manifest_names_main + manifest_names_sens:
        mpath = manifests_dir / mname
        if not mpath.exists():
            continue
        mrows = load_manifest_rows(mpath)
        records_by_arm = build_manifest_records(mname, mrows, index)
        all_manifest_records[mname] = records_by_arm

        is_main = mname in manifest_names_main
        tier_set = "natural_only" if mname.startswith("natural_only") else "all_tiers"

        for arm, recs in records_by_arm.items():
            # Per band
            for band in BANDS_ORDER:
                band_recs = [r for r in recs if r["band"] == band]
                if not band_recs and not is_main:
                    continue
                q_rng, f_rng = next_rng_pair()
                st = summarize_records(band_recs, q_rng, f_rng, b_resamples=b_resamples)
                stats_lookup[(mname, arm, band)] = st

                if is_main:
                    band_table_rows.append(
                        {
                            "arm": arm,
                            "manifest": mname,
                            "band": band,
                            "tier_set": tier_set,
                            **st,
                        }
                    )
                    # Also record per-pair pass rate in secondary_tables.csv
                    secondary_rows.append(
                        {
                            "subtable": "pair_pass_rate_by_band",
                            "manifest": mname,
                            "arm": arm,
                            "stratum": "all_tiers",
                            "band": band,
                            "n_pairs": st["n_pairs"],
                            "n_valid": st["n_valid"],
                            "n_invalid": st["n_invalid"],
                            "n_unavailable": st["n_unavailable"],
                            "mean_recall": st["mean_recall"],
                            "median_latency_ms": st["median_latency_ms"],
                            "band_pass": st["pass"],
                            "pair_pass_count": st["pair_pass_count"],
                            "pair_pass_rate": st["pair_pass_rate"],
                            "q_ci_pair_pass_lo": st["q_ci_pair_pass_lo"],
                            "q_ci_pair_pass_hi": st["q_ci_pair_pass_hi"],
                            "q_ci_recall_lo": st["q_ci_recall_lo"],
                            "q_ci_recall_hi": st["q_ci_recall_hi"],
                            "q_ci_lat_lo": st["q_ci_lat_lo"],
                            "q_ci_lat_hi": st["q_ci_lat_hi"],
                        }
                    )
                else:
                    # Sensitivity manifest rows go to secondary_tables.csv
                    secondary_rows.append(
                        {
                            "subtable": "sensitivity_manifest",
                            "manifest": mname,
                            "arm": arm,
                            "stratum": "natural_only",
                            "band": band,
                            "n_pairs": st["n_pairs"],
                            "n_valid": st["n_valid"],
                            "n_invalid": st["n_invalid"],
                            "n_unavailable": st["n_unavailable"],
                            "mean_recall": st["mean_recall"],
                            "median_latency_ms": st["median_latency_ms"],
                            "band_pass": st["pass"],
                            "pair_pass_count": st["pair_pass_count"],
                            "pair_pass_rate": st["pair_pass_rate"],
                            "q_ci_pair_pass_lo": st["q_ci_pair_pass_lo"],
                            "q_ci_pair_pass_hi": st["q_ci_pair_pass_hi"],
                            "q_ci_recall_lo": st["q_ci_recall_lo"],
                            "q_ci_recall_hi": st["q_ci_recall_hi"],
                            "q_ci_lat_lo": st["q_ci_lat_lo"],
                            "q_ci_lat_hi": st["q_ci_lat_hi"],
                        }
                    )

            # Pooled groups below_T and above_T on EDGAR (or smoke validation)
            has_edgar = any(r["corpus"] == "edgar" for r in recs)
            if is_main and has_edgar:
                for grp_name, comp_bands in [
                    ("below_T", ["far_below", "near_below"]),
                    ("above_T", ["near_above", "far_above"]),
                ]:
                    grp_recs = [r for r in recs if r["band"] in comp_bands and r["corpus"] == "edgar"]
                    q_rng, f_rng = next_rng_pair()
                    st_grp = summarize_records(grp_recs, q_rng, f_rng, b_resamples=b_resamples)
                    stats_lookup[(mname, arm, grp_name)] = st_grp
                    group_table_rows.append(
                        {
                            "arm": arm,
                            "manifest": mname,
                            "group": grp_name,
                            "component_bands": "+".join(comp_bands),
                            "tier_set": tier_set,
                            **st_grp,
                        }
                    )

            # Secondary analyses on main manifests: tier split and boundary stratum
            if is_main:
                for tier_val in ["natural", "plausible_constructed"]:
                    for band in BANDS_ORDER:
                        t_recs = [r for r in recs if r["question_tier"] == tier_val and r["band"] == band]
                        if not t_recs:
                            continue
                        q_rng, f_rng = next_rng_pair()
                        st_t = summarize_records(t_recs, q_rng, f_rng, b_resamples=b_resamples)
                        secondary_rows.append(
                            {
                                "subtable": "tier_split",
                                "manifest": mname,
                                "arm": arm,
                                "stratum": tier_val,
                                "band": band,
                                "n_pairs": st_t["n_pairs"],
                                "n_valid": st_t["n_valid"],
                                "n_invalid": st_t["n_invalid"],
                                "n_unavailable": st_t["n_unavailable"],
                                "mean_recall": st_t["mean_recall"],
                                "median_latency_ms": st_t["median_latency_ms"],
                                "band_pass": st_t["pass"],
                                "pair_pass_count": st_t["pair_pass_count"],
                                "pair_pass_rate": st_t["pair_pass_rate"],
                                "q_ci_pair_pass_lo": st_t["q_ci_pair_pass_lo"],
                                "q_ci_pair_pass_hi": st_t["q_ci_pair_pass_hi"],
                                "q_ci_recall_lo": st_t["q_ci_recall_lo"],
                                "q_ci_recall_hi": st_t["q_ci_recall_hi"],
                                "q_ci_lat_lo": st_t["q_ci_lat_lo"],
                                "q_ci_lat_hi": st_t["q_ci_lat_hi"],
                            }
                        )

                # Boundary stratum |s - T| / T <= 0.25 (pooled across boundary pairs and per band)
                b_all_recs = [r for r in recs if r["boundary_flag"]]
                if b_all_recs:
                    q_rng, f_rng = next_rng_pair()
                    st_b = summarize_records(b_all_recs, q_rng, f_rng, b_resamples=b_resamples)
                    secondary_rows.append(
                        {
                            "subtable": "boundary_stratum",
                            "manifest": mname,
                            "arm": arm,
                            "stratum": "boundary_le_0.25",
                            "band": "all_boundary",
                            "n_pairs": st_b["n_pairs"],
                            "n_valid": st_b["n_valid"],
                            "n_invalid": st_b["n_invalid"],
                            "n_unavailable": st_b["n_unavailable"],
                            "mean_recall": st_b["mean_recall"],
                            "median_latency_ms": st_b["median_latency_ms"],
                            "band_pass": st_b["pass"],
                            "pair_pass_count": st_b["pair_pass_count"],
                            "pair_pass_rate": st_b["pair_pass_rate"],
                            "q_ci_pair_pass_lo": st_b["q_ci_pair_pass_lo"],
                            "q_ci_pair_pass_hi": st_b["q_ci_pair_pass_hi"],
                            "q_ci_recall_lo": st_b["q_ci_recall_lo"],
                            "q_ci_recall_hi": st_b["q_ci_recall_hi"],
                            "q_ci_lat_lo": st_b["q_ci_lat_lo"],
                            "q_ci_lat_hi": st_b["q_ci_lat_hi"],
                        }
                    )

    # 3. Hypotheses table (Addendum 3 Section 4)
    edgar_pri = "smoke_test_pairs.csv" if (validation and "smoke_test_pairs.csv" in all_manifest_records) else "edgar_pairs_primary_T_edgar.csv"
    edgar_sec = "smoke_test_pairs.csv" if (validation and "smoke_test_pairs.csv" in all_manifest_records) else "edgar_pairs_secondary_T_hm.csv"
    finqa_pri = "smoke_test_pairs.csv" if (validation and "smoke_test_pairs.csv" in all_manifest_records) else "finqa_pairs_primary_T_hm.csv"

    def get_st(m: str, a: str, b: str) -> dict[str, Any]:
        return stats_lookup.get(
            (m, a, b),
            {
                "pass": False,
                "mean_recall": math.nan,
                "n_invalid": 1,
                "n_unavailable": 0,
                "p_meets_q": 1.0,
                "p_meets_f": 1.0,
                "p_fails_rec_q": 1.0,
                "p_fails_rec_f": 1.0,
            },
        )

    # H1a: router on EDGAR (T_edgar) meets rule in far_below and near_below separately; p = max(p_fb, p_nb)
    h1a_fb = get_st(edgar_pri, "router", "far_below")
    h1a_nb = get_st(edgar_pri, "router", "near_below")
    h1a_pt = bool(h1a_fb["pass"] and h1a_nb["pass"])
    h1a_pq = float(max(h1a_fb["p_meets_q"], h1a_nb["p_meets_q"]))
    h1a_pf = float(max(h1a_fb["p_meets_f"], h1a_nb["p_meets_f"]))

    # H1b: router on EDGAR (T_edgar) meets rule in above_T (near_above + far_above pooled)
    h1b_ab = get_st(edgar_pri, "router", "above_T")
    h1b_pt = bool(h1b_ab["pass"])
    h1b_pq = float(h1b_ab["p_meets_q"])
    h1b_pf = float(h1b_ab["p_meets_f"])

    # H3: default_hnsw on EDGAR (T_edgar) fails recall (< 0.90) in far_below and near_below; p = max(p_fb, p_nb)
    h3_fb = get_st(edgar_pri, "default_hnsw", "far_below")
    h3_nb = get_st(edgar_pri, "default_hnsw", "near_below")
    h3_pt = bool(
        h3_fb["n_invalid"] == 0
        and h3_nb["n_invalid"] == 0
        and not math.isnan(h3_fb["mean_recall"])
        and not math.isnan(h3_nb["mean_recall"])
        and h3_fb["mean_recall"] < RECALL_THRESHOLD
        and h3_nb["mean_recall"] < RECALL_THRESHOLD
    )
    h3_pq = float(max(h3_fb["p_fails_rec_q"], h3_nb["p_fails_rec_q"]))
    h3_pf = float(max(h3_fb["p_fails_rec_f"], h3_nb["p_fails_rec_f"]))

    # H5a: router_hmT on FinQA (T_hm) meets rule in all four bands; p = max(p_fb, p_nb, p_na, p_fa)
    h5a_bands = [get_st(finqa_pri, "router_hmT", b) for b in BANDS_ORDER]
    h5a_pt = bool(all(st["pass"] for st in h5a_bands))
    h5a_pq = float(max(st["p_meets_q"] for st in h5a_bands))
    h5a_pf = float(max(st["p_meets_f"] for st in h5a_bands))

    # H5b: router_hmT on EDGAR (T_hm) fails recall in at least one of far_below, near_above, far_above; p = min(1, 3 * min(p_fb, p_na, p_fa))
    h5b_target_bands = ["far_below", "near_above", "far_above"]
    h5b_sts = [get_st(edgar_sec, "router_hmT", b) for b in h5b_target_bands]
    h5b_pt = bool(
        any(
            st["n_invalid"] == 0
            and not math.isnan(st["mean_recall"])
            and st["mean_recall"] < RECALL_THRESHOLD
            for st in h5b_sts
        )
    )
    h5b_pq = float(min(1.0, 3.0 * min(st["p_fails_rec_q"] for st in h5b_sts)))
    h5b_pf = float(min(1.0, 3.0 * min(st["p_fails_rec_f"] for st in h5b_sts)))

    raw_hyp_rows = [
        {
            "hypothesis": "H1a",
            "group": "R",
            "manifest": edgar_pri,
            "arm": "router",
            "component_bands": "far_below,near_below",
            "direction": "meets_rule_each_band",
            "point_estimate_satisfied": h1a_pt,
            "raw_p_question_clustered": h1a_pq,
            "raw_p_filter_clustered": h1a_pf,
        },
        {
            "hypothesis": "H1b",
            "group": "N",
            "manifest": edgar_pri,
            "arm": "router",
            "component_bands": "above_T(near_above+far_above)",
            "direction": "meets_rule_pooled_group",
            "point_estimate_satisfied": h1b_pt,
            "raw_p_question_clustered": h1b_pq,
            "raw_p_filter_clustered": h1b_pf,
        },
        {
            "hypothesis": "H3",
            "group": "R",
            "manifest": edgar_pri,
            "arm": "default_hnsw",
            "component_bands": "far_below,near_below",
            "direction": "fails_recall_each_band",
            "point_estimate_satisfied": h3_pt,
            "raw_p_question_clustered": h3_pq,
            "raw_p_filter_clustered": h3_pf,
        },
        {
            "hypothesis": "H5a",
            "group": "N",
            "manifest": finqa_pri,
            "arm": "router_hmT",
            "component_bands": "far_below,near_below,near_above,far_above",
            "direction": "meets_rule_all_4_bands",
            "point_estimate_satisfied": h5a_pt,
            "raw_p_question_clustered": h5a_pq,
            "raw_p_filter_clustered": h5a_pf,
        },
        {
            "hypothesis": "H5b",
            "group": "R",
            "manifest": edgar_sec,
            "arm": "router_hmT",
            "component_bands": "far_below,near_above,far_above",
            "direction": "fails_recall_at_least_one_band",
            "point_estimate_satisfied": h5b_pt,
            "raw_p_question_clustered": h5b_pq,
            "raw_p_filter_clustered": h5b_pf,
        },
    ]

    holm_ps = holm_adjust([r["raw_p_question_clustered"] for r in raw_hyp_rows])
    hypotheses_rows: list[dict[str, Any]] = []
    for r, hp in zip(raw_hyp_rows, holm_ps):
        supported = bool(r["point_estimate_satisfied"] and hp < HOLM_ALPHA)
        hypotheses_rows.append(
            {
                **r,
                "holm_adjusted_p": hp,
                "decision": "supported" if supported else "not_supported",
            }
        )

    # 5. Descriptive analyses (Addendum 3 Section 5)
    # 5a. E1: always_exact latency vs matched rows per table with OLS slope (ms per 1,000 rows) and question-clustered 95% CI
    for corpus_name, table_name in [("edgar", "edgar_chunks"), ("finqa", "finqa_evidence_qwen3")]:
        # Deduplicate distinct (qid, pool_id) pairs across main manifests for this corpus
        seen_qp: set[tuple[str, str]] = set()
        e1_recs: list[dict[str, Any]] = []
        for mname in manifest_names_main:
            for r in all_manifest_records.get(mname, {}).get("always_exact", []):
                if r["corpus"] == corpus_name and (r["qid"], r["pool_id"]) not in seen_qp:
                    seen_qp.add((r["qid"], r["pool_id"]))
                    e1_recs.append(r)
        if e1_recs:
            q_rng, _ = next_rng_pair()
            ols_res = bootstrap_ols_slope(e1_recs, q_rng, b_resamples=b_resamples)
            descriptive_rows.append(
                {
                    "analysis_type": "E1_exact_latency_vs_rows",
                    "table_or_manifest": table_name,
                    "band_or_scope": "all_distinct_pairs",
                    "arm_or_route": "always_exact",
                    "n_pairs": len(e1_recs),
                    "n_valid": sum(1 for r in e1_recs if r["valid"]),
                    "n_unavailable": 0,
                    "metric_name": "ols_slope_ms_per_1000_rows",
                    "estimate": ols_res["slope"],
                    "ci_lo": ols_res["slope_ci_lo"],
                    "ci_hi": ols_res["slope_ci_hi"],
                    "notes": f"intercept_ms={fmt_float(ols_res['intercept'])}",
                }
            )

    # 5b. Router overhead by band (router median latency minus median latency of the always_* arm matching route_taken)
    for mname in manifest_names_main:
        recs_map = all_manifest_records.get(mname, {})
        exact_by_qp = {(r["qid"], r["pool_id"]): r for r in recs_map.get("always_exact", [])}
        iter_by_qp = {(r["qid"], r["pool_id"]): r for r in recs_map.get("always_iterative", [])}
        for r_arm in ["router", "router_hmT"]:
            if r_arm not in recs_map:
                continue
            for band in BANDS_ORDER:
                b_recs = [r for r in recs_map[r_arm] if r["band"] == band and r["valid"]]
                if not b_recs:
                    continue
                router_lats: list[float] = []
                matched_lats: list[float] = []
                routes_seen: set[str] = set()
                for r in b_recs:
                    qp = (r["qid"], r["pool_id"])
                    rt = str(r.get("route_taken", ""))
                    routes_seen.add(rt)
                    m_rec = exact_by_qp.get(qp) if rt == "exact" else iter_by_qp.get(qp)
                    if m_rec is not None and m_rec["valid"]:
                        router_lats.append(float(r["latency_median_ms"]))
                        matched_lats.append(float(m_rec["latency_median_ms"]))
                if router_lats and matched_lats:
                    r_med = float(np.median(router_lats))
                    m_med = float(np.median(matched_lats))
                    overhead_ms = r_med - m_med
                    pair_diff_med = float(np.median(np.array(router_lats) - np.array(matched_lats)))
                    descriptive_rows.append(
                        {
                            "analysis_type": "router_overhead_by_band",
                            "table_or_manifest": mname,
                            "band_or_scope": band,
                            "arm_or_route": f"{r_arm}_vs_{'+'.join(sorted(routes_seen))}",
                            "n_pairs": len(b_recs),
                            "n_valid": len(router_lats),
                            "n_unavailable": 0,
                            "metric_name": "router_median_minus_matched_always_median_ms",
                            "estimate": overhead_ms,
                            "ci_lo": math.nan,
                            "ci_hi": math.nan,
                            "notes": f"router_med={fmt_float(r_med)};matched_med={fmt_float(m_med)};median_pair_diff={fmt_float(pair_diff_med)}",
                        }
                    )

    # 5c. VecAdvisor availability and results where it ran
    for mname in manifest_names_main:
        va_recs = all_manifest_records.get(mname, {}).get("vecadvisor", [])
        for band in BANDS_ORDER:
            b_recs = [r for r in va_recs if r["band"] == band]
            if not b_recs:
                continue
            n_p = len(b_recs)
            n_v = sum(1 for r in b_recs if r["valid"])
            n_u = sum(1 for r in b_recs if r["unavailable"])
            reasons = sorted({str(r["unavailable_reason"]) for r in b_recs if r["unavailable_reason"]})
            mean_rec = float(np.mean([r["recall_at_15"] for r in b_recs if r["valid"]])) if n_v > 0 else math.nan
            med_lat = float(np.median([r["latency_median_ms"] for r in b_recs if r["valid"]])) if n_v > 0 else math.nan
            descriptive_rows.append(
                {
                    "analysis_type": "vecadvisor_availability",
                    "table_or_manifest": mname,
                    "band_or_scope": band,
                    "arm_or_route": "vecadvisor",
                    "n_pairs": n_p,
                    "n_valid": n_v,
                    "n_unavailable": n_u,
                    "metric_name": "median_latency_ms_where_available",
                    "estimate": med_lat,
                    "ci_lo": math.nan,
                    "ci_hi": math.nan,
                    "notes": f"mean_recall={fmt_float(mean_rec)};reasons={'|'.join(reasons) if reasons else 'none'}",
                }
            )

    # 5d. Offline oracle per pair: fastest valid arm among always_exact, default_hnsw, always_iterative, vecadvisor (where available), and router that meets recall@15 >= 14/15
    for mname in manifest_names_main:
        recs_map = all_manifest_records.get(mname, {})
        if not recs_map:
            continue
        primary_router_arm = "router" if mname == "edgar_pairs_primary_T_edgar.csv" else "router_hmT"
        candidate_arms = [
            a
            for a in ["always_exact", "default_hnsw", "always_iterative", "vecadvisor", primary_router_arm]
            if a in recs_map
        ]
        # Index by (qid, pool_id)
        by_arm_qp: dict[str, dict[tuple[str, str], dict[str, Any]]] = {
            a: {(r["qid"], r["pool_id"]): r for r in recs_map[a]} for a in candidate_arms
        }
        base_arm = candidate_arms[0]
        for band in BANDS_ORDER:
            b_qps = [
                (r["qid"], r["pool_id"])
                for r in recs_map[base_arm]
                if r["band"] == band
            ]
            if not b_qps:
                continue
            oracle_lats: list[float] = []
            oracle_winners: dict[str, int] = {}
            for qp in b_qps:
                qualifying: list[tuple[float, str]] = []
                for a in candidate_arms:
                    r = by_arm_qp[a].get(qp)
                    if (
                        r is not None
                        and r["valid"]
                        and not r["unavailable"]
                        and r["recall_at_15"] >= PAIR_RECALL_THRESHOLD
                    ):
                        qualifying.append((float(r["latency_median_ms"]), a))
                if qualifying:
                    qualifying.sort(key=lambda x: x[0])
                    best_lat, best_arm = qualifying[0]
                    oracle_lats.append(best_lat)
                    oracle_winners[best_arm] = oracle_winners.get(best_arm, 0) + 1
            winner_summary = ",".join(f"{k}:{v}" for k, v in sorted(oracle_winners.items()))
            descriptive_rows.append(
                {
                    "analysis_type": "offline_oracle",
                    "table_or_manifest": mname,
                    "band_or_scope": band,
                    "arm_or_route": f"oracle(router={primary_router_arm})",
                    "n_pairs": len(b_qps),
                    "n_valid": len(oracle_lats),
                    "n_unavailable": 0,
                    "metric_name": "oracle_median_latency_ms",
                    "estimate": float(np.median(oracle_lats)) if oracle_lats else math.nan,
                    "ci_lo": math.nan,
                    "ci_hi": math.nan,
                    "notes": f"winners={winner_summary if winner_summary else 'none'}",
                }
            )

    # Write all output files
    band_csv = actual_out_dir / "band_table.csv"
    group_csv = actual_out_dir / "group_table.csv"
    hyp_csv = actual_out_dir / "hypotheses.csv"
    sec_csv = actual_out_dir / "secondary_tables.csv"
    desc_csv = actual_out_dir / "descriptive_tables.csv"
    report_md = actual_out_dir / "REPORT.md"

    write_csv(band_csv, BAND_TABLE_COLUMNS, band_table_rows)
    write_csv(group_csv, GROUP_TABLE_COLUMNS, group_table_rows)
    write_csv(hyp_csv, HYPOTHESES_COLUMNS, hypotheses_rows)
    write_csv(sec_csv, SECONDARY_TABLES_COLUMNS, secondary_rows)
    write_csv(desc_csv, DESCRIPTIVE_TABLES_COLUMNS, descriptive_rows)

    # Generate REPORT.md
    report_lines = [
        "# Phase G Amendment 12 — Straddle-T Analysis Report",
        "",
    ]
    if validation:
        report_lines.extend(
            [
                "> **WARNING — VALIDATION MODE ONLY (NOT REPORTABLE)**",
                "> This file was generated with `--validation` for schema and pipeline verification only.",
                "",
            ]
        )
    report_lines.extend(
        [
            "## 1. Parameters",
            f"- Bootstrap seed: `{BOOTSTRAP_SEED}`",
            f"- Bootstrap resamples (`B`): `{b_resamples}`",
            f"- Band pass rule: `n_invalid == 0`, `mean(recall_at_15) >= {RECALL_THRESHOLD:.2f}`, `median(latency_median_ms) <= {LATENCY_THRESHOLD_MS:.1f} ms`",
            f"- Family-wise error rate control: Holm step-down across 5 hypotheses (`alpha = {HOLM_ALPHA}`)",
            "",
            "## 2. Confirmatory Hypotheses (`hypotheses.csv`)",
            "",
            "| Hypothesis | Group | Manifest | Arm | Component Bands | Point Est. | Raw p (Q-Cluster) | Raw p (F-Cluster) | Holm Adj. p | Decision |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for hr in hypotheses_rows:
        report_lines.append(
            f"| {hr['hypothesis']} | {hr['group']} | {hr['manifest']} | {hr['arm']} | {hr['component_bands']} "
            f"| {hr['point_estimate_satisfied']} | {fmt_float(hr['raw_p_question_clustered'])} "
            f"| {fmt_float(hr['raw_p_filter_clustered'])} | {fmt_float(hr['holm_adjusted_p'])} | **{hr['decision']}** |"
        )
    report_lines.extend(
        [
            "",
            "## 3. Generated Output Files",
            "- `band_table.csv`",
            "- `group_table.csv`",
            "- `hypotheses.csv`",
            "- `secondary_tables.csv`",
            "- `descriptive_tables.csv`",
            "- `REPORT.md`",
            "",
        ]
    )
    report_md.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "band_table": band_csv,
        "group_table": group_csv,
        "hypotheses": hyp_csv,
        "secondary_tables": sec_csv,
        "descriptive_tables": desc_csv,
        "report": report_md,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze Phase G straddle-T results per Amendment 12 Addendum 3."
    )
    parser.add_argument(
        "--results",
        type=Path,
        required=True,
        help="Path to results.jsonl from run_straddle.py",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=DEFAULT_MANIFESTS_DIR,
        help="Directory containing straddle-T manifest CSVs and MANIFEST_CHECKSUMS.txt",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Output directory for analysis CSVs and REPORT.md",
    )
    parser.add_argument(
        "--validation",
        action="store_true",
        help="Allow reading smoke paths and force output to outputs/straddle_t_analysis_validation/",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_analysis(
        results_path=args.results,
        manifests_dir=args.manifests_dir,
        out_dir=args.out_dir,
        validation=args.validation,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
