"""Hypothesis-composition and edge-case tests for analyze_straddle.py (Stage A3)."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.phase_g_straddle.analyze_straddle import (
    BAND_TABLE_COLUMNS,
    GROUP_TABLE_COLUMNS,
    HYPOTHESES_COLUMNS,
    REPO_ROOT,
    run_analysis,
)


MANIFEST_FIELDS = [
    "pair_id",
    "qid",
    "band",
    "T_name",
    "T_value",
    "analysis_group",
    "pool_id",
    "where_clause",
    "n_rows",
    "s",
    "tier",
    "boundary_flag",
    "natural_available",
    "gold_in_filter",
]


def _write_manifest(manifests_dir: Path, filename: str, rows: list[dict[str, str]]) -> str:
    path = manifests_dir / filename
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_manifest_row(
    prefix: str,
    t_name: str,
    t_val: float,
    band: str,
    qid: str,
    pool_id: str,
    n_rows: int = 100,
    s: float = 0.05,
    tier: str = "natural",
) -> dict[str, str]:
    ana_grp = "below_T" if band in ("far_below", "near_below") else "above_T"
    return {
        "pair_id": f"{prefix}_{t_name}|{band}|{qid}",
        "qid": qid,
        "band": band,
        "T_name": t_name,
        "T_value": str(t_val),
        "analysis_group": ana_grp,
        "pool_id": pool_id,
        "where_clause": "fiscal_year = 2020",
        "n_rows": str(n_rows),
        "s": str(s),
        "tier": tier,
        "boundary_flag": "False",
        "natural_available": "True",
        "gold_in_filter": "True",
    }


def _make_result_row(
    qid: str,
    pool_id: str,
    t_name: str,
    arm: str,
    recall: float | None,
    latency_ms: float | None,
    valid: bool = True,
    route_taken: str = "exact",
) -> dict[str, object]:
    return {
        "qid": qid,
        "pool_id": pool_id,
        "T_name": t_name,
        "arm": arm,
        "valid": valid,
        "vecadvisor_unavailable": False,
        "vecadvisor_unavailable_reason": None,
        "recall_at_15": recall,
        "latency_median_ms": latency_ms,
        "route_taken": route_taken,
    }


def _setup_synthetic_suite(
    tmp_path: Path,
    *,
    edgar_pri_router_above_rec: float = 0.80,
    default_hnsw_nb_rec: float = 0.50,
    edgar_sec_hm_recalls: dict[str, float] | None = None,
    finqa_hm_recalls: dict[str, float] | None = None,
    finqa_invalid_band: str | None = None,
) -> tuple[Path, Path]:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    edgar_sec_hm_recalls = edgar_sec_hm_recalls or {
        "far_below": 1.0,
        "near_above": 0.80,
        "far_above": 1.0,
    }
    finqa_hm_recalls = finqa_hm_recalls or {
        "far_below": 0.95,
        "near_below": 0.95,
        "near_above": 0.95,
        "far_above": 0.95,
    }

    edgar_pri_rows: list[dict[str, str]] = []
    edgar_sec_rows: list[dict[str, str]] = []
    finqa_pri_rows: list[dict[str, str]] = []
    results: list[dict[str, object]] = []

    n_per_band = 12
    for b_idx, band in enumerate(["far_below", "near_below", "near_above", "far_above"]):
        for i in range(n_per_band):
            qid_e = f"eq_{band}_{i}"
            pid_e = f"edgar_pool_{band}_{i}"
            edgar_pri_rows.append(
                _make_manifest_row("edgar", "T_edgar", 0.378692, band, qid_e, pid_e, n_rows=100 * (b_idx + 1))
            )

            # Fixed arms for EDGAR primary
            results.append(_make_result_row(qid_e, pid_e, "T_edgar", "always_exact", 1.0, 20.0))
            results.append(_make_result_row(qid_e, pid_e, "T_edgar", "always_iterative", 1.0, 25.0, route_taken="iterative_default"))
            hnsw_rec = 0.50
            if band == "near_below":
                hnsw_rec = default_hnsw_nb_rec
            elif band in ("near_above", "far_above"):
                hnsw_rec = 0.95
            results.append(_make_result_row(qid_e, pid_e, "T_edgar", "default_hnsw", hnsw_rec, 10.0, route_taken="hnsw"))

            # Router arm on EDGAR primary
            if band in ("far_below", "near_below"):
                r_rec, r_lat = 1.0, 20.0
            else:
                r_rec, r_lat = edgar_pri_router_above_rec, 30.0
            results.append(_make_result_row(qid_e, pid_e, "T_edgar", "router", r_rec, r_lat))

            # EDGAR secondary T_hm (far_below, near_above, far_above)
            if band != "near_below":
                qid_es = f"eqs_{band}_{i}"
                pid_es = f"edgar_pool_sec_{band}_{i}"
                edgar_sec_rows.append(
                    _make_manifest_row("edgar", "T_hm", 0.071192, band, qid_es, pid_es, n_rows=100 * (b_idx + 1))
                )
                results.append(_make_result_row(qid_es, pid_es, "T_hm", "always_exact", 1.0, 20.0))
                results.append(_make_result_row(qid_es, pid_es, "T_hm", "always_iterative", 1.0, 25.0, route_taken="iterative_default"))
                results.append(_make_result_row(qid_es, pid_es, "T_hm", "default_hnsw", 0.90, 10.0, route_taken="hnsw"))
                results.append(
                    _make_result_row(
                        qid_es, pid_es, "T_hm", "router_hmT", edgar_sec_hm_recalls[band], 30.0
                    )
                )

            # FinQA primary T_hm
            qid_f = f"fq_{band}_{i}"
            pid_f = f"finqa_pool_{band}_{i}"
            finqa_pri_rows.append(
                _make_manifest_row("finqa", "T_hm", 0.071192, band, qid_f, pid_f, n_rows=50 * (b_idx + 1))
            )
            results.append(_make_result_row(qid_f, pid_f, "T_hm", "always_exact", 1.0, 40.0))
            results.append(_make_result_row(qid_f, pid_f, "T_hm", "always_iterative", 1.0, 40.0, route_taken="iterative_default"))
            results.append(_make_result_row(qid_f, pid_f, "T_hm", "default_hnsw", 0.95, 10.0, route_taken="hnsw"))
            is_valid = not (finqa_invalid_band == band and i == 0)
            results.append(
                _make_result_row(
                    qid_f,
                    pid_f,
                    "T_hm",
                    "router_hmT",
                    finqa_hm_recalls[band] if is_valid else None,
                    40.0 if is_valid else None,
                    valid=is_valid,
                )
            )

    checksums = []
    for fname, rows in [
        ("edgar_pairs_primary_T_edgar.csv", edgar_pri_rows),
        ("edgar_pairs_secondary_T_hm.csv", edgar_sec_rows),
        ("finqa_pairs_primary_T_hm.csv", finqa_pri_rows),
    ]:
        sha = _write_manifest(manifests_dir, fname, rows)
        checksums.append(f"{sha}  {fname}")
    (manifests_dir / "MANIFEST_CHECKSUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    results_path = tmp_path / "results.jsonl"
    results_path.write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")
    return results_path, manifests_dir


def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_a_b_c_d_hypothesis_compositions(tmp_path: Path):
    # Case (a)-(d) baseline: H1a supported, H1b not supported, H3 supported, H5a supported, H5b supported
    res1, man1 = _setup_synthetic_suite(tmp_path / "case1")
    out1 = tmp_path / "out1"
    files1 = run_analysis(res1, man1, out1, b_resamples=400)
    hyps1 = {r["hypothesis"]: r for r in _read_csv_dicts(files1["hypotheses"])}

    assert hyps1["H1a"]["decision"] == "supported"
    assert hyps1["H1b"]["decision"] == "not_supported"
    assert hyps1["H3"]["decision"] == "supported"
    assert hyps1["H5a"]["decision"] == "supported"
    assert hyps1["H5b"]["decision"] == "supported"

    # Variant (b): default_hnsw recall 0.95 in near_below only -> H3 not supported
    res2, man2 = _setup_synthetic_suite(tmp_path / "case2", default_hnsw_nb_rec=0.95)
    files2 = run_analysis(res2, man2, tmp_path / "out2", b_resamples=400)
    hyps2 = {r["hypothesis"]: r for r in _read_csv_dicts(files2["hypotheses"])}
    assert hyps2["H3"]["decision"] == "not_supported"

    # Variant (c1): EDGAR secondary router_hmT every band 0.95 -> H5b not supported
    res3, man3 = _setup_synthetic_suite(
        tmp_path / "case3",
        edgar_sec_hm_recalls={"far_below": 0.95, "near_above": 0.95, "far_above": 0.95},
    )
    files3 = run_analysis(res3, man3, tmp_path / "out3", b_resamples=400)
    hyps3 = {r["hypothesis"]: r for r in _read_csv_dicts(files3["hypotheses"])}
    assert hyps3["H5b"]["decision"] == "not_supported"
    # Verify 3 * min(p) is capped at 1.0 when every band has p_fails_rec near 1.0
    assert float(hyps3["H5b"]["raw_p_question_clustered"]) == pytest.approx(1.0)

    # Variant (d1): FinQA router_hmT one band at 0.80 -> H5a not supported
    res4, man4 = _setup_synthetic_suite(
        tmp_path / "case4",
        finqa_hm_recalls={"far_below": 0.95, "near_below": 0.80, "near_above": 0.95, "far_above": 0.95},
    )
    files4 = run_analysis(res4, man4, tmp_path / "out4", b_resamples=400)
    hyps4 = {r["hypothesis"]: r for r in _read_csv_dicts(files4["hypotheses"])}
    assert hyps4["H5a"]["decision"] == "not_supported"

    # Variant (d2): FinQA router_hmT one invalid pair in one band -> that band does not pass, H5a not supported
    res5, man5 = _setup_synthetic_suite(tmp_path / "case5", finqa_invalid_band="far_above")
    files5 = run_analysis(res5, man5, tmp_path / "out5", b_resamples=400)
    hyps5 = {r["hypothesis"]: r for r in _read_csv_dicts(files5["hypotheses"])}
    bands5 = {
        (r["manifest"], r["arm"], r["band"]): r for r in _read_csv_dicts(files5["band_table"])
    }
    assert bands5[("finqa_pairs_primary_T_hm.csv", "router_hmT", "far_above")]["pass"] == "False"
    assert hyps5["H5a"]["decision"] == "not_supported"


def test_e_pooled_group_mean_over_pairs_not_mean_of_band_means(tmp_path: Path):
    """(e) above_T group mean recall is the mean over pairs of both bands, not mean of band means."""
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    mrows: list[dict[str, str]] = []
    results: list[dict[str, object]] = []

    # near_above: 2 pairs with recall 1.0
    # far_above: 6 pairs with recall 0.6
    # Mean of band means = (1.0 + 0.6) / 2 = 0.80
    # Pooled mean over all 8 pairs = (2*1.0 + 6*0.6) / 8 = 5.6 / 8 = 0.70
    for i in range(2):
        qid, pid = f"q_na_{i}", f"edgar_pool_na_{i}"
        mrows.append(_make_manifest_row("edgar", "T_edgar", 0.378, "near_above", qid, pid))
        results.append(_make_result_row(qid, pid, "T_edgar", "always_exact", 1.0, 20.0))
        results.append(_make_result_row(qid, pid, "T_edgar", "router", 1.0, 20.0))
    for i in range(6):
        qid, pid = f"q_fa_{i}", f"edgar_pool_fa_{i}"
        mrows.append(_make_manifest_row("edgar", "T_edgar", 0.378, "far_above", qid, pid))
        results.append(_make_result_row(qid, pid, "T_edgar", "always_exact", 1.0, 20.0))
        results.append(_make_result_row(qid, pid, "T_edgar", "router", 0.6, 20.0))

    sha = _write_manifest(manifests_dir, "edgar_pairs_primary_T_edgar.csv", mrows)
    (manifests_dir / "MANIFEST_CHECKSUMS.txt").write_text(
        f"{sha}  edgar_pairs_primary_T_edgar.csv\n", encoding="utf-8"
    )
    res_path = tmp_path / "results.jsonl"
    res_path.write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")

    files = run_analysis(res_path, manifests_dir, tmp_path / "out", b_resamples=100)
    grp_rows = {
        (r["arm"], r["group"]): r for r in _read_csv_dicts(files["group_table"])
    }
    assert float(grp_rows[("router", "above_T")]["mean_recall"]) == pytest.approx(0.70)


def test_f_inconclusive_rule_question_vs_filter_disagreement(tmp_path: Path):
    """(f) Inconclusive when question-clustered CI crosses 0.90 and filter-clustered does not, vs both agree."""
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    mrows: list[dict[str, str]] = []
    results: list[dict[str, object]] = []

    # Band far_below (disagree -> overall_inconclusive True):
    # 10 pairs: 5 distinct questions, 2 distinct filters? Wait:
    # Make 4 questions (q0..q3) where q0 has 4 pairs with recall=0.70, q1..q3 have 4 pairs each with recall=1.0.
    # Total 16 pairs, mean recall = (4*0.7 + 12*1.0)/16 = 0.925.
    # If all pairs in q0..q3 are evenly spread across 4 pool_ids (each pool_id has 1 pair at 0.70 and 3 pairs at 1.0 -> every pool_id has mean 0.925):
    # Filter-clustered resamples always have mean recall == 0.925 (CI [0.925, 0.925], does NOT cross 0.90).
    # Question-clustered resamples can draw q0 multiple times -> CI straddles 0.90!
    for q_idx in range(4):
        for p_idx in range(4):
            qid = f"q_fb_{q_idx}"
            pid = f"edgar_pool_fb_{p_idx}"
            rec = 0.70 if q_idx == 0 else 1.0
            mrows.append(_make_manifest_row("edgar", "T_edgar", 0.378, "far_below", qid, pid))
            results.append(_make_result_row(qid, pid, "T_edgar", "always_exact", 1.0, 20.0))
            results.append(_make_result_row(qid, pid, "T_edgar", "router", rec, 20.0))

    # Band near_below (both agree -> overall_inconclusive False):
    # All pairs have recall=1.0, latency=20.0 -> neither CI crosses 0.90 or 500.0
    for idx in range(4):
        qid = f"q_nb_{idx}"
        pid = f"edgar_pool_nb_{idx}"
        mrows.append(_make_manifest_row("edgar", "T_edgar", 0.378, "near_below", qid, pid))
        results.append(_make_result_row(qid, pid, "T_edgar", "always_exact", 1.0, 20.0))
        results.append(_make_result_row(qid, pid, "T_edgar", "router", 1.0, 20.0))

    sha = _write_manifest(manifests_dir, "edgar_pairs_primary_T_edgar.csv", mrows)
    (manifests_dir / "MANIFEST_CHECKSUMS.txt").write_text(
        f"{sha}  edgar_pairs_primary_T_edgar.csv\n", encoding="utf-8"
    )
    res_path = tmp_path / "results.jsonl"
    res_path.write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")

    files = run_analysis(res_path, manifests_dir, tmp_path / "out", b_resamples=1000)
    bands = {(r["arm"], r["band"]): r for r in _read_csv_dicts(files["band_table"])}

    fb = bands[("router", "far_below")]
    assert fb["q_recall_crosses"] == "True"
    assert fb["f_recall_crosses"] == "False"
    assert fb["recall_inconclusive"] == "True"
    assert fb["overall_inconclusive"] == "True"

    nb = bands[("router", "near_below")]
    assert nb["q_recall_crosses"] == "False"
    assert nb["f_recall_crosses"] == "False"
    assert nb["overall_inconclusive"] == "False"


def test_g_holm_and_group_labels(tmp_path: Path):
    """(g) Holm over all five hypotheses and R/N group labels."""
    res, man = _setup_synthetic_suite(tmp_path / "case_g")
    files = run_analysis(res, man, tmp_path / "out", b_resamples=200)
    hyps = {r["hypothesis"]: r for r in _read_csv_dicts(files["hypotheses"])}

    assert hyps["H1a"]["group"] == "R"
    assert hyps["H3"]["group"] == "R"
    assert hyps["H5b"]["group"] == "R"
    assert hyps["H1b"]["group"] == "N"
    assert hyps["H5a"]["group"] == "N"

    # Verify Holm adjustment matches step-down across all 5 raw_p_question_clustered values
    raw_ps = [float(hyps[h]["raw_p_question_clustered"]) for h in ["H1a", "H1b", "H3", "H5a", "H5b"]]
    adj_ps = [float(hyps[h]["holm_adjusted_p"]) for h in ["H1a", "H1b", "H3", "H5a", "H5b"]]
    indexed = sorted(enumerate(raw_ps), key=lambda x: x[1])
    expected_adj = [0.0] * 5
    running_max = 0.0
    for rank, (idx, p) in enumerate(indexed):
        running_max = max(running_max, min(1.0, (5 - rank) * p))
        expected_adj[idx] = running_max
    assert adj_ps == pytest.approx(expected_adj, abs=1e-6)


def test_h_cli_determinism_sha256(tmp_path: Path):
    """(h) Two CLI runs on the same synthetic files produce identical SHA-256 for every output file."""
    res, man = _setup_synthetic_suite(tmp_path / "det")
    out1 = tmp_path / "cli_out1"
    out2 = tmp_path / "cli_out2"

    for out_dir in (out1, out2):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.phase_g_straddle.analyze_straddle",
                "--results",
                str(res),
                "--manifests-dir",
                str(man),
                "--out-dir",
                str(out_dir),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        assert proc.returncode == 0

    files1 = sorted(p.name for p in out1.iterdir())
    files2 = sorted(p.name for p in out2.iterdir())
    assert files1 == files2
    for fname in files1:
        h1 = hashlib.sha256((out1 / fname).read_bytes()).hexdigest()
        h2 = hashlib.sha256((out2 / fname).read_bytes()).hexdigest()
        assert h1 == h2, f"Mismatch for {fname}"


def test_i_cli_refuses_smoke_path_without_validation(tmp_path: Path):
    """(i) A path containing 'smoke' is refused without --validation."""
    smoke_res = tmp_path / "smoke_results.jsonl"
    smoke_res.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.phase_g_straddle.analyze_straddle",
            "--results",
            str(smoke_res),
            "--manifests-dir",
            str(tmp_path),
            "--out-dir",
            str(tmp_path / "out"),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "smoke" in (proc.stderr + proc.stdout).lower()
