"""Unit tests for Phase H Amendment 13 analysis (src/phase_h_efsweep/analysis.py)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from scipy.stats import binomtest

from src import PROJECT_ROOT
from src.phase_e_router.policy_v3 import cell_passes
from src.phase_h_efsweep import EF_VALUES
from src.phase_h_efsweep.analysis import compute_s_pass, exact_mcnemar_two_sided, guard_main_path, holm_step_down, run_analysis


def test_exact_mcnemar_matches_scipy_binomtest():
    assert exact_mcnemar_two_sided(0, 0) == 1.0
    for n in range(1, 14):
        assert exact_mcnemar_two_sided(n, 0) == pytest.approx(binomtest(0, n, 0.5, alternative="two-sided").pvalue)
        assert exact_mcnemar_two_sided(0, n) == pytest.approx(binomtest(0, n, 0.5, alternative="two-sided").pvalue)
    # Split cases
    for n_01, n_10 in ((2, 3), (4, 4), (1, 7), (5, 8)):
        exp = binomtest(min(n_01, n_10), n_01 + n_10, 0.5, alternative="two-sided").pvalue
        assert exact_mcnemar_two_sided(n_01, n_10) == pytest.approx(exp)


def test_holm_step_down_blocking_behavior():
    # Rank 1 (0.010 <= 0.0125) passes; Rank 2 (0.020 > 0.01667) fails and MUST block Rank 3 & 4
    # even though Rank 3 (0.021 <= 0.025) and Rank 4 (0.030 <= 0.05) are below their individual thresholds!
    tests = [
        {"name": "t1", "p_value": 0.010},
        {"name": "t2", "p_value": 0.020},
        {"name": "t3", "p_value": 0.021},
        {"name": "t4", "p_value": 0.030},
    ]
    res = holm_step_down(tests, alpha=0.05)
    by_name = {r["name"]: r for r in res}
    assert by_name["t1"]["rejected"] is True
    assert by_name["t2"]["rejected"] is False
    assert by_name["t3"]["rejected"] is False
    assert by_name["t4"]["rejected"] is False


def test_s_pass_monotone_and_non_monotone():
    assert compute_s_pass([(0.01, False), (0.05, False), (0.10, True), (0.20, True)]) == 0.10
    # Non-monotone: 0.05 passes, 0.10 fails, 0.20 & 0.30 pass -> s_pass must be 0.20
    assert compute_s_pass([(0.05, True), (0.10, False), (0.20, True), (0.30, True)]) == 0.20
    # Highest fails -> None
    assert compute_s_pass([(0.05, True), (0.30, False)]) is None


def test_cell_passes_with_invalid_vector():
    recalls = [1.0] * 19 + [None]
    lats = [10.0] * 19 + [None]
    res = cell_passes(recalls, lats, n_expected=20, recall_target=0.90, latency_limit_ms=500.0)
    assert res["valid"] is False
    assert res["passed"] is False


def test_main_path_guard():
    with pytest.raises(RuntimeError, match="--main"):
        guard_main_path(Path("outputs/ef_sweep_main_2026-11-17/results.jsonl"), allow_main=False)
    guard_main_path(Path("outputs/ef_sweep_main_2026-11-17/results.jsonl"), allow_main=True)


def test_early_stop_latency_handling_and_smoke_dry_run(tmp_path: Path):
    smoke_res = PROJECT_ROOT / "outputs" / "ef_sweep_smoke_2026-11-17" / "results.jsonl"
    out = tmp_path / "smoke_analysis"
    res = run_analysis(smoke_res, out_dir=out, allow_main=False)
    report = (out / "REPORT.md").read_text(encoding="utf-8")
    assert "SMOKE DRY RUN" in report
    assert (out / "analysis_inputs.json").exists()
    assert (out / "confirmatory_mcnemar.csv").exists()
    assert (out / "cliff_table.csv").exists()
    assert res["n_cells"] > 0


def test_end_to_end_synthetic_pipeline(tmp_path: Path):
    """End-to-end synthetic test with hand-computed expectations (uses real config/grid files for metadata)."""
    res_path = tmp_path / "results.jsonl"
    exp_path = tmp_path / "explain_results.jsonl"
    out_dir = tmp_path / "analysis_out"

    hm_cells = [("c1", 0.05), ("c2", 0.15), ("c3", 0.30)]
    ed_cells = [("g01", 0.10), ("g11", 0.40)]

    rows = []
    for ds, tbl, cells, k_val in (("hm", "hm_clothes_0", hm_cells, 10), ("edgar_cal", "edgar_chunks", ed_cells, 15)):
        for cid, sel in cells:
            for v in range(20):
                for arm in ("always_exact", "default_hnsw", "always_iterative"):
                    efs = [None] if arm == "always_exact" else list(EF_VALUES)
                    for ef in efs:
                        valid = True
                        early = False
                        rec = 0.95
                        lat = 10.0

                        if ds == "hm" and arm == "default_hnsw":
                            lat = {40: 10.0, 100: 20.0, 200: 40.0, 400: 80.0}[ef]
                            if cid == "c1":
                                rec = {40: 0.50, 100: 0.60, 200: 0.70, 400: 0.95}[ef]
                            elif cid == "c2":
                                rec = 0.80 if ef == 40 else 0.95
                            elif cid == "c3" and ef == 400:
                                lat = 600.0  # loss at ef=400 on latency
                        elif ds == "hm" and arm == "always_iterative":
                            lat = {40: 50.0, 100: 100.0, 200: 200.0, 400: 400.0}[ef]
                            if cid == "c3" and ef == 40 and v == 19:
                                valid = False  # 1 invalid vector -> cell fails at ef=40
                            if cid == "c1" and ef == 200 and v == 0:
                                early = True
                                lat = 1650.0
                        elif ds == "edgar_cal" and arm == "default_hnsw":
                            lat = {40: 15.0, 100: 30.0, 200: 60.0, 400: 120.0}[ef]
                            if cid == "g01" and ef == 40:
                                rec = 0.60

                        reps = [lat, lat] if early else [lat] * 5
                        rows.append({
                            "row_key": f"{ds}|{tbl}|{cid}|{v}|{arm}|{ef}",
                            "unit_id": f"{ds}|{tbl}|{cid}",
                            "dataset": ds,
                            "role": "primary",
                            "table": tbl,
                            "cell_id": cid,
                            "vector_key": str(v),
                            "k": k_val,
                            "ef_search": ef,
                            "arm": arm,
                            "selectivity": sel,
                            "rows_returned": k_val if valid else None,
                            "recall": rec if valid else None,
                            "rep_latencies_ms": reps if valid else [],
                            "median_latency_ms": lat if valid else None,
                            "early_stopped": early,
                            "valid": valid,
                            "error": None if valid else "SimulatedError",
                        })

    res_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    exp_rows = [
        {"dataset": "edgar_cal", "table": "edgar_chunks", "cell_id": "g01", "arm": "default_hnsw", "ef_search": 40,
         "valid": True, "seq_scan_flagged": True, "plan_nodes": ["Limit", "Seq Scan"], "execution_time_ms": 12.0,
         "shared_hit_blocks": 10, "shared_read_blocks": 0},
        {"dataset": "hm", "table": "hm_clothes_0", "cell_id": "c1", "arm": "always_iterative", "ef_search": 40,
         "valid": True, "seq_scan_flagged": False, "plan_nodes": ["Sort", "CTE Scan", "Index Scan"], "execution_time_ms": 5.0,
         "shared_hit_blocks": 8, "shared_read_blocks": 0},
    ]
    exp_path.write_text("\n".join(json.dumps(e) for e in exp_rows) + "\n", encoding="utf-8")

    run_analysis(res_path, out_dir=out_dir, explain_path=exp_path, allow_main=False)

    mc = {r["hypothesis"]: r for r in csv.DictReader((out_dir / "confirmatory_mcnemar.csv").open())}
    decomp = {(r["dataset"], r["arm"], r["ef_search"]): r for r in csv.DictReader((out_dir / "pass_decomposition.csv").open())}
    cliff = {(r["dataset"], int(r["ef_search"])): r for r in csv.DictReader((out_dir / "cliff_table.csv").open())}
    growth = {(r["dataset"], r["arm"], r["step"]): r for r in csv.DictReader((out_dir / "latency_growth.csv").open())}
    ex_out = list(csv.DictReader((out_dir / "explain_transitions.csv").open()))

    checks = [
        ("hm_default_hnsw n_01/n_10", (2, 1), (int(mc["hm_default_hnsw"]["n_01_gain"]), int(mc["hm_default_hnsw"]["n_10_loss"]))),
        ("hm_always_iterative n_01/n_10", (1, 0), (int(mc["hm_always_iterative"]["n_01_gain"]), int(mc["hm_always_iterative"]["n_10_loss"]))),
        ("edgar_cal_default_hnsw n_01/n_10", (1, 0), (int(mc["edgar_cal_default_hnsw"]["n_01_gain"]), int(mc["edgar_cal_default_hnsw"]["n_10_loss"]))),
        ("edgar_cal_always_iterative n_01/n_10", (0, 0), (int(mc["edgar_cal_always_iterative"]["n_01_gain"]), int(mc["edgar_cal_always_iterative"]["n_10_loss"]))),
        ("hm_default_hnsw p_value", 1.0, float(mc["hm_default_hnsw"]["p_value"])),
        ("hm_default_hnsw ef=400 recall_only/lat_only", (3, 2), (int(decomp[("hm", "default_hnsw", "400")]["n_recall_only_pass"]), int(decomp[("hm", "default_hnsw", "400")]["n_latency_only_pass"]))),
        ("hm_always_iterative ef=40 n_pass", 2, int(decomp[("hm", "always_iterative", "40")]["n_pass"])),
        ("hm s_pass(40,100,200,400)", [0.30, 0.15, 0.15, 0.05], [float(cliff[("hm", ef)]["s_pass"]) for ef in EF_VALUES]),
        ("edgar s_pass(40,400)", [0.40, 0.10], [float(cliff[("edgar_cal", 40)]["s_pass"]), float(cliff[("edgar_cal", 400)]["s_pass"])]),
        ("hm always_iter 100->200 non_early_n", 59, int(growth[("hm", "always_iterative", "100->200")]["n_vectors_non_early"])),
        ("explain seq_scan_flagged count", 1, sum(1 for e in ex_out if e["seq_scan_flagged"] == "True")),
    ]
    print("\n=== Synthetic End-to-End Expected vs Actual ===")
    for name, exp, act in checks:
        print(f"  {name:42s} | expected={exp} | actual={act}")
        assert act == exp, f"Mismatch on {name}: expected {exp}, got {act}"
