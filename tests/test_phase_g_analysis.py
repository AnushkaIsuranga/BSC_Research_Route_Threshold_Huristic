"""Unit tests for Phase G Amendment 12 Addendum 3 analysis script (analyze_straddle.py)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.phase_g_straddle.analyze_straddle import (
    BAND_TABLE_COLUMNS,
    BOOTSTRAP_SEED,
    DESCRIPTIVE_TABLES_COLUMNS,
    GROUP_TABLE_COLUMNS,
    HYPOTHESES_COLUMNS,
    SECONDARY_TABLES_COLUMNS,
    VALIDATION_OUT_DIR,
    check_smoke_guard,
    cluster_bootstrap_stats,
    compute_band_pass,
    compute_one_sided_pvalue_fails_recall,
    compute_one_sided_pvalue_meets_rule,
    evaluate_pair_validity,
    holm_adjust,
    run_analysis,
)


def test_band_pass_rule_with_invalid_and_unavailable_pairs():
    """Verify Addendum 3 Sec 2 band pass rule with valid, invalid, and unavailable pairs."""
    # All valid, meets recall >= 0.90 and median latency <= 500 ms -> True
    assert compute_band_pass(
        n_pairs=20,
        n_valid=20,
        n_invalid=0,
        n_unavailable=0,
        mean_recall=0.92,
        median_latency_ms=120.0,
    ) is True

    # Boundary values: exact 0.90 and 500.0 -> True
    assert compute_band_pass(
        n_pairs=20,
        n_valid=20,
        n_invalid=0,
        n_unavailable=0,
        mean_recall=0.90,
        median_latency_ms=500.0,
    ) is True

    # Any invalid pair causes band to fail even if valid subset has recall=1.0 and lat=10ms
    assert compute_band_pass(
        n_pairs=20,
        n_valid=19,
        n_invalid=1,
        n_unavailable=0,
        mean_recall=1.0,
        median_latency_ms=10.0,
    ) is False

    # Any unavailable pair (e.g., vecadvisor unavailable) causes band pass to be False
    assert compute_band_pass(
        n_pairs=20,
        n_valid=0,
        n_invalid=0,
        n_unavailable=20,
        mean_recall=float("nan"),
        median_latency_ms=float("nan"),
    ) is False

    # Fails recall (< 0.90) -> False
    assert compute_band_pass(
        n_pairs=20,
        n_valid=20,
        n_invalid=0,
        n_unavailable=0,
        mean_recall=0.899,
        median_latency_ms=50.0,
    ) is False

    # Fails latency (> 500.0) -> False
    assert compute_band_pass(
        n_pairs=20,
        n_valid=20,
        n_invalid=0,
        n_unavailable=0,
        mean_recall=0.95,
        median_latency_ms=500.1,
    ) is False


def test_vecadvisor_unavailable_excluded_from_invalid_count():
    """Verify vecadvisor_unavailable rows are marked unavailable, not invalid executions."""
    exact_row = {"valid": True, "recall_at_15": 1.0, "latency_median_ms": 50.0}
    va_row = {
        "valid": False,
        "vecadvisor_unavailable": True,
        "unavailable_reason": "no_history_column_on_edgar_chunks",
        "recall_at_15": None,
        "latency_median_ms": None,
    }
    ev = evaluate_pair_validity(va_row, exact_row)
    assert ev["status"] == "unavailable"
    assert ev["valid"] is False
    assert ev["unavailable"] is True
    assert ev["unavailable_reason"] == "no_history_column_on_edgar_chunks"

    # Contrast with a true execution error on a regular arm
    err_row = {
        "valid": False,
        "vecadvisor_unavailable": False,
        "error": "statement timeout",
        "recall_at_15": None,
        "latency_median_ms": None,
    }
    ev_err = evaluate_pair_validity(err_row, exact_row)
    assert ev_err["status"] == "invalid"
    assert ev_err["valid"] is False
    assert ev_err["unavailable"] is False


def test_cluster_bootstrap_on_synthetic_dataset_known_answer():
    """Verify cluster bootstrap on a synthetic dataset with known cluster structure."""
    # 1. Constant values across clusters -> zero variance, exact known CI
    records_const = [
        {"qid": "q1", "pool_id": "p1", "valid": True, "recall_at_15": 0.95, "latency_median_ms": 100.0},
        {"qid": "q1", "pool_id": "p2", "valid": True, "recall_at_15": 0.95, "latency_median_ms": 100.0},
        {"qid": "q2", "pool_id": "p3", "valid": True, "recall_at_15": 0.95, "latency_median_ms": 100.0},
    ]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    res_const = cluster_bootstrap_stats(records_const, "qid", rng, b_resamples=1000)
    assert res_const["ci_recall"] == pytest.approx((0.95, 0.95))
    assert res_const["ci_lat"] == pytest.approx((100.0, 100.0))

    # 2. Two question clusters of unequal size:
    # q1 has 2 pairs with recall=1.0, lat=100; q2 has 1 pair with recall=0.4, lat=400.
    # Possible 2-cluster resamples with replacement from {q1, q2}:
    # - (q1, q1): 4 pairs of 1.0 -> mean_recall = 1.0, median_lat = 100.0 (prob 0.25)
    # - (q1, q2) or (q2, q1): 2 pairs of 1.0 + 1 pair of 0.4 -> mean_recall = 2.4/3 = 0.8, median_lat = 100.0 (prob 0.50)
    # - (q2, q2): 2 pairs of 0.4 -> mean_recall = 0.4, median_lat = 400.0 (prob 0.25)
    records_two = [
        {"qid": "q1", "pool_id": "p1", "valid": True, "recall_at_15": 1.0, "latency_median_ms": 100.0},
        {"qid": "q1", "pool_id": "p2", "valid": True, "recall_at_15": 1.0, "latency_median_ms": 100.0},
        {"qid": "q2", "pool_id": "p3", "valid": True, "recall_at_15": 0.4, "latency_median_ms": 400.0},
    ]
    rng2 = np.random.default_rng(BOOTSTRAP_SEED)
    res_two = cluster_bootstrap_stats(records_two, "qid", rng2, b_resamples=5000)
    unique_means = np.unique(np.round(res_two["boot_mean_recall"], 6))
    assert set(unique_means) == {0.4, 0.8, 1.0}
    assert res_two["ci_recall"] == pytest.approx((0.4, 1.0))
    assert res_two["ci_lat"] == pytest.approx((100.0, 400.0))


def test_one_sided_pvalue_formula_count_plus_1_over_b_plus_1():
    """Verify exact (count + 1) / (B + 1) formula for 'meets the rule' and 'fails recall'."""
    b = 100
    # Suppose 4 resamples out of 100 have recall < 0.90, and 9 resamples have latency > 500
    boot_rec = np.array([0.85] * 4 + [0.95] * 96, dtype=np.float64)
    boot_lat = np.array([600.0] * 9 + [120.0] * 91, dtype=np.float64)

    p_meets = compute_one_sided_pvalue_meets_rule(boot_rec, boot_lat, n_invalid=0, n_unavailable=0)
    # max((4 + 1)/101, (9 + 1)/101) = 10 / 101
    assert p_meets == pytest.approx(10.0 / 101.0)

    # Zero violations -> (0 + 1) / (B + 1)
    boot_rec_all_pass = np.full(b, 0.98, dtype=np.float64)
    boot_lat_all_pass = np.full(b, 50.0, dtype=np.float64)
    assert compute_one_sided_pvalue_meets_rule(boot_rec_all_pass, boot_lat_all_pass) == pytest.approx(1.0 / 101.0)

    # Fails recall formula: (#{boot mean recall >= 0.90} + 1) / (B + 1)
    # In boot_rec above, 96 resamples have >= 0.90 -> (96 + 1) / 101
    p_fails = compute_one_sided_pvalue_fails_recall(boot_rec, n_invalid=0, n_unavailable=0)
    assert p_fails == pytest.approx(97.0 / 101.0)


def test_holm_adjustment_on_known_pvalues():
    """Verify step-down Holm adjustment on 5 known p-values."""
    raw_p = [0.005, 0.040, 0.011, 0.020, 0.250]
    # Sorted order of (index, p):
    # rank 0 (mult 5): idx 0, p=0.005 -> 5 * 0.005 = 0.025
    # rank 1 (mult 4): idx 2, p=0.011 -> max(0.025, 4 * 0.011) = 0.044
    # rank 2 (mult 3): idx 3, p=0.020 -> max(0.044, 3 * 0.020) = 0.060
    # rank 3 (mult 2): idx 1, p=0.040 -> max(0.060, 2 * 0.040) = 0.080
    # rank 4 (mult 1): idx 4, p=0.250 -> max(0.080, 1 * 0.250) = 0.250
    adj = holm_adjust(raw_p)
    assert adj == pytest.approx([0.025, 0.080, 0.044, 0.060, 0.250])


def test_refusal_of_smoke_path_without_validation():
    """Verify check_smoke_guard refuses smoke paths unless --validation is passed."""
    smoke_res = Path("outputs/straddle_t_smoke_2026-11-15/results.jsonl")
    normal_man = Path("outputs/straddle_t_manifest_2026-11-15")
    out_dir = Path("outputs/some_custom_out")

    with pytest.raises(ValueError, match="Refusing to analyze path containing 'smoke'"):
        check_smoke_guard(smoke_res, normal_man, out_dir, validation=False)

    # With validation=True, it succeeds and forces output to VALIDATION_OUT_DIR
    forced_dir = check_smoke_guard(smoke_res, normal_man, out_dir, validation=True)
    assert forced_dir == VALIDATION_OUT_DIR


def test_deterministic_outputs_for_fixed_seed(tmp_path: Path):
    """Verify two runs of run_analysis produce byte-for-byte identical outputs for seed 20261115."""
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    mname = "edgar_pairs_primary_T_edgar.csv"
    mpath = manifests_dir / mname
    fieldnames = [
        "pair_id",
        "manifest_name",
        "corpus",
        "table_name",
        "qid",
        "question_tier",
        "pool_id",
        "band",
        "T_name",
        "T_value",
        "n_rows",
        "N_total",
        "selectivity",
        "boundary_distance",
        "boundary_flag",
        "filter_sql",
    ]
    mrows = []
    results_rows = []
    for b_idx, band in enumerate(["far_below", "near_below", "near_above", "far_above"]):
        for i in range(4):
            qid = f"Q_{band}_{i}"
            pid = f"P_{band}_{i}"
            pair_id = f"PAIR_{band}_{i}"
            mrows.append(
                {
                    "pair_id": pair_id,
                    "manifest_name": "edgar_pairs_primary_T_edgar",
                    "corpus": "edgar",
                    "table_name": "edgar_chunks",
                    "qid": qid,
                    "question_tier": "natural" if i % 2 == 0 else "plausible_constructed",
                    "pool_id": pid,
                    "band": band,
                    "T_name": "T_edgar",
                    "T_value": "0.3786921696945195",
                    "n_rows": str(100 * (b_idx + 1) + 10 * i),
                    "N_total": "245218",
                    "selectivity": str(0.05 * (b_idx + 1)),
                    "boundary_distance": "0.10",
                    "boundary_flag": "True" if i == 0 else "False",
                    "filter_sql": "form = '10-K'",
                }
            )
            for arm in ["always_exact", "default_hnsw", "always_iterative", "router", "router_hmT", "vecadvisor"]:
                if arm == "vecadvisor":
                    results_rows.append(
                        {
                            "pair_id": pair_id,
                            "qid": qid,
                            "pool_id": pid,
                            "arm": arm,
                            "T_name": "T_edgar",
                            "valid": False,
                            "vecadvisor_unavailable": True,
                            "unavailable_reason": "no_history_column_on_edgar_chunks",
                            "recall_at_15": None,
                            "latency_median_ms": None,
                            "route_taken": "unavailable",
                        }
                    )
                else:
                    results_rows.append(
                        {
                            "pair_id": pair_id,
                            "qid": qid,
                            "pool_id": pid,
                            "arm": arm,
                            "T_name": "T_edgar",
                            "valid": True,
                            "vecadvisor_unavailable": False,
                            "unavailable_reason": None,
                            "recall_at_15": 1.0 if arm != "default_hnsw" else (0.5 + 0.1 * i),
                            "latency_median_ms": 25.0 + 3.0 * i + b_idx,
                            "route_taken": "exact" if b_idx < 2 else "iterative_default",
                        }
                    )

    with open(mpath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(mrows)

    sha = hashlib.sha256(mpath.read_bytes()).hexdigest()
    (manifests_dir / "MANIFEST_CHECKSUMS.txt").write_text(f"{sha}  {mname}\n", encoding="utf-8")

    results_path = tmp_path / "results.jsonl"
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results_rows:
            f.write(json.dumps(r) + "\n")

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    files1 = run_analysis(results_path, manifests_dir, out1, validation=False, b_resamples=200)
    files2 = run_analysis(results_path, manifests_dir, out2, validation=False, b_resamples=200)

    for key in files1:
        assert files1[key].read_bytes() == files2[key].read_bytes()

    # Also verify exact headers match schema constants
    with open(files1["band_table"], "r", encoding="utf-8") as f:
        assert next(csv.reader(f)) == BAND_TABLE_COLUMNS
    with open(files1["group_table"], "r", encoding="utf-8") as f:
        assert next(csv.reader(f)) == GROUP_TABLE_COLUMNS
    with open(files1["hypotheses"], "r", encoding="utf-8") as f:
        assert next(csv.reader(f)) == HYPOTHESES_COLUMNS
    with open(files1["secondary_tables"], "r", encoding="utf-8") as f:
        assert next(csv.reader(f)) == SECONDARY_TABLES_COLUMNS
    with open(files1["descriptive_tables"], "r", encoding="utf-8") as f:
        assert next(csv.reader(f)) == DESCRIPTIVE_TABLES_COLUMNS
