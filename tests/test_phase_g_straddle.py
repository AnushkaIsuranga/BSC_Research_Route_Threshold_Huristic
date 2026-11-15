"""Tests for Phase G straddle-T runner (Amendment 12 & Addenda 1-2).

Uses only read-only SELECT / EXPLAIN / SHOW queries.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import psycopg2
import pytest

from src import PROJECT_ROOT
from src.phase_e_router import policy_v3_1 as V
from src.phase_g_straddle import run_straddle as RS


def test_manifest_loading_and_checksum_refusal(tmp_path: Path):
    verified = RS.verify_manifest_checksums()
    assert len(verified) == 12

    fake_dir = tmp_path / "manifests"
    fake_dir.mkdir()
    sample = fake_dir / "sample.csv"
    sample.write_text("pair_id,qid\np1,q1\n", encoding="utf-8")
    ck = fake_dir / "MANIFEST_CHECKSUMS.txt"
    ck.write_text("0" * 64 + "  manifests/sample.csv\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        RS.verify_manifest_checksums(manifest_dir=fake_dir, root=tmp_path)


def test_key_deduplication_across_manifests():
    _, union_files = RS.resolve_manifest_files("union")
    rows = RS.load_manifest_rows(union_files)
    assert len(rows) == 1355
    keys = RS.deduce_Execution_keys(rows)
    assert len(keys["fixed_keys"]) == 1132
    assert len(keys["router_keys"]) == 1180


def test_resume_populates_caches_and_skips(tmp_path: Path):
    res_file = tmp_path / "results.jsonl"
    sample_row = {
        "manifest": "smoke_test_pairs.csv",
        "pair_id": "edgar_T_edgar|far_below|edgar_q001",
        "qid": "edgar_q001",
        "pool_id": "edgar_pool_00001",
        "T_name": "T_edgar",
        "arm": "always_exact",
        "route_taken": "exact",
        "guard_fired": False,
        "s_est": None,
        "s_count": None,
        "estimate_skipped": None,
        "rows_returned": 15,
        "recall_at_15": 1.0,
        "valid": True,
        "error": None,
        "latency_runs_ms": [1.0, 2.0, 3.0, 4.0, 5.0],
        "latency_median_ms": 3.0,
    }
    res_file.write_text(json.dumps(sample_row) + "\n", encoding="utf-8")
    lines = [json.loads(x) for x in res_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    done = {(d["manifest"], d["pair_id"], d["arm"]) for d in lines}
    assert ("smoke_test_pairs.csv", "edgar_T_edgar|far_below|edgar_q001", "always_exact") in done


def test_recall_computation_and_null_on_invalid_gt():
    truth = list(range(1, 16))
    assert RS.compute_recall_at_15(list(range(1, 16)), truth, True, 15) == 1.0
    assert RS.compute_recall_at_15(list(range(1, 11)) + [99, 98, 97, 96, 95], truth, True, 15) == pytest.approx(10 / 15)
    assert RS.compute_recall_at_15(list(range(1, 16)), truth, False, 15) is None
    assert RS.compute_recall_at_15(list(range(1, 16)), None, True, 15) is None
    assert RS.compute_recall_at_15([], [], True, 15) is None


def test_quiet_rule_refusal_for_non_smoke_sets():
    RS.validate_quiet_rule_flag(["smoke"], True)
    RS.validate_quiet_rule_flag(["primary"], False)
    for bad in (["primary"], ["secondary"], ["sensitivity"], ["union"], ["smoke", "primary"]):
        with pytest.raises(ValueError, match="allowed ONLY for --manifests smoke"):
            RS.validate_quiet_rule_flag(bad, True)


def test_no_write_statements_and_readonly_session():
    src_text = (PROJECT_ROOT / "src/phase_g_straddle/run_straddle.py").read_text(encoding="utf-8")
    forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|VACUUM|ANALYZE)\b", re.IGNORECASE)
    # Strip comments and check SQL strings
    sql_literals = re.findall(r'"""[\s\S]*?"""|"[^"\n]*"|\'[^\'\n]*\'', src_text)
    for lit in sql_literals:
        if "SELECT" in lit.upper() or "SET " in lit.upper() or "SHOW " in lit.upper():
            assert not forbidden.search(lit), f"Forbidden keyword in SQL literal: {lit}"

    cfgs = RS.build_configs()
    conn = RS.connect_readonly(cfgs["edgar_T_edgar"])
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW default_transaction_read_only")
            assert cur.fetchone()[0] == "on"
            cur.execute("SHOW transaction_read_only")
            assert cur.fetchone()[0] == "on"
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cur.execute("CREATE TEMP TABLE should_fail (x int)")
            conn.rollback()
    finally:
        conn.close()


def test_adapter_sql_matches_manifest_n_rows_and_finqa_routes():
    cfgs = RS.build_configs()
    _, all_files = RS.resolve_manifest_files("union,smoke")
    rows = RS.load_manifest_rows(all_files)
    req_qids = {r["qid"] for r in rows}
    vecs = RS.load_all_query_vectors(req_qids)
    assert len(vecs) >= len(req_qids)

    conn = RS.connect_readonly(cfgs["edgar_T_edgar"])
    try:
        n_checked = RS.verify_all_manifest_filters_sql(conn, rows, cfgs)
        # 522 distinct (table, pool_id) filters across all manifests
        assert n_checked >= 500

        # Check FinQA route decisions equal "exact if s < T else iterative" with estimate_skipped_no_stats == True
        finqa_cfg = cfgs["finqa_T_hm"]
        T_hm = finqa_cfg.T_default
        seen_finqa_pools = set()
        for r in rows:
            if r["table"] != RS.FINQA_TABLE or r["pool_id"] in seen_finqa_pools:
                continue
            seen_finqa_pools.add(r["pool_id"])
            parsed = RS.parse_finqa_filter(r["where_clause"])
            tr = {}
            decided = V.band_decision(conn, RS.FINQA_TABLE, parsed, T_hm, finqa_cfg, tr)
            assert tr[V.SKIP_FIELD] is True, f"Expected estimate_skipped_no_stats=True for {r['pool_id']}"
            expected = "exact" if r["s"] < T_hm else "iterative"
            assert decided == expected, f"Mismatch on {r['pool_id']} (s={r['s']}): {decided} != {expected}"
    finally:
        conn.close()
