"""Unit tests for Phase H Amendment 13 (src/phase_h_efsweep)."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from src import PROJECT_ROOT
from src.phase_e_router import retriever as R
from src.phase_h_efsweep import EF_VALUES
from src.phase_h_efsweep.explain_pass import flag_seq_scan_on_base
from src.phase_h_efsweep.manifest import build_manifest, cell_rng
from src.phase_h_efsweep.runner import make_ef_config, should_early_stop, verify_env_snapshot


def test_manifest_counts_and_always_exact_once_per_unit():
    m = build_manifest(smoke=False)
    assert m["n_units"] == 65 + 13 + 160
    assert m["n_timed_rows"] == 15480
    assert m["n_explain_items"] == 2142

    by_ds = {"hm": 0, "edgar_cal": 0, "edgar_eval": 0}
    exact_per_uv: dict[tuple[str, str], int] = {}
    for r in m["timed_rows"]:
        by_ds[r["dataset"]] += 1
        if r["arm"] == "always_exact":
            assert r["ef_search"] is None
            k = (r["unit_id"], r["vector_key"])
            exact_per_uv[k] = exact_per_uv.get(k, 0) + 1
    assert by_ds == {"hm": 11700, "edgar_cal": 2340, "edgar_eval": 1440}
    assert len(exact_per_uv) == 1300 + 260 + 160
    assert all(v == 1 for v in exact_per_uv.values())


def test_manifest_reproducible_and_resume_order_identical():
    m1 = build_manifest(smoke=True)
    m2 = build_manifest(smoke=True)
    keys1 = [r["row_key"] for r in m1["timed_rows"]]
    keys2 = [r["row_key"] for r in m2["timed_rows"]]
    assert keys1 == keys2
    # Simulated resume after half the rows yields the exact remaining sequence
    half = len(keys1) // 2
    done = set(keys1[:half])
    resumed = [k for k in keys2 if k not in done]
    assert resumed == keys1[half:]


def test_per_cell_sub_rng_independent():
    r1 = cell_rng("hm|hm_clothes_0|lo3")
    r2 = cell_rng("hm|hm_clothes_0|lo3")
    seq1 = [r1.sample(EF_VALUES, len(EF_VALUES)) for _ in range(5)]
    # Advance another cell's RNG first; target cell's RNG must be unaffected
    _ = cell_rng("hm|hm_clothes_100|idx2").shuffle(list(EF_VALUES))
    seq2 = [r2.sample(EF_VALUES, len(EF_VALUES)) for _ in range(5)]
    assert seq1 == seq2


def test_early_stop_boundary_and_mocked_timings():
    assert should_early_stop([1500.0]) is False
    assert should_early_stop([1500.0, 1500.0]) is False  # exact 1500.0 does NOT stop
    assert should_early_stop([1400.0, 1600.0]) is False  # median == 1500.0
    assert should_early_stop([1500.0, 1500.2]) is True   # median == 1500.1 > 1500.0
    assert should_early_stop([1600.0, 1700.0]) is True


def test_route_settings_ef_override_and_iterative_budgets():
    base_hm = R.RouterConfig.load("config/router_hm.json")
    for ef in EF_VALUES:
        cfg_ef = make_ef_config(base_hm, ef)
        assert base_hm["ef_search"] == 40  # base untouched
        s_hnsw = R.route_settings(R.R_HNSW, cfg_ef)
        s_iter = R.route_settings(R.R_ITER, cfg_ef)
        assert s_hnsw["hnsw.ef_search"] == ef
        assert s_hnsw["hnsw.iterative_scan"] == "off"
        assert s_iter["hnsw.ef_search"] == ef
        assert s_iter["hnsw.iterative_scan"] == "relaxed_order"
        assert s_iter["hnsw.max_scan_tuples"] == 20000
        assert s_iter["hnsw.scan_mem_multiplier"] == 1


def test_explain_seq_scan_flagging():
    sort_only_plan = {"Node Type": "Sort", "Plans": [{"Node Type": "Index Scan", "Index Name": "edgar_chunks_embedding_idx"}]}
    seq_plan = {"Node Type": "Limit", "Plans": [{"Node Type": "Seq Scan", "Relation Name": "edgar_chunks"}]}
    assert flag_seq_scan_on_base("always_iterative", "edgar_chunks", sort_only_plan) is False
    assert flag_seq_scan_on_base("default_hnsw", "edgar_chunks", seq_plan) is True
    assert flag_seq_scan_on_base("always_iterative", "edgar_chunks", seq_plan) is True
    assert flag_seq_scan_on_base("always_exact", "edgar_chunks", seq_plan) is False


def test_no_network_or_api_client_imports():
    forbidden = {"google", "genai", "ollama", "openai", "anthropic", "httpx", "requests", "urllib", "aiohttp"}
    pkg_dir = PROJECT_ROOT / "src" / "phase_h_efsweep"
    for py in pkg_dir.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, f"Forbidden import {alias.name} in {py}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, f"Forbidden import {node.module} in {py}"


def test_tagged_paths_unmodified():
    for path in ("src/phase_e_router", "src/phase_f_edgar", "config", "docs/preregistration"):
        r = subprocess.run(["git", "diff", "--quiet", path], cwd=PROJECT_ROOT)
        assert r.returncode == 0, f"Tagged path modified: {path}"


def test_verify_env_snapshot_aborts_on_diff(tmp_path: Path):
    import json
    import pytest

    snap = {"postgresql_version": "PG 16.14", "extensions": {"vector": "0.8.3"}, "settings": {}, "tables": {}}
    sp = tmp_path / "snap.json"
    sp.write_text(json.dumps(snap), encoding="utf-8")

    class _FakeCur:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, sql, params=None): self._sql = sql
        def fetchone(self): return ("PG 16.99",)
        def fetchall(self): return [("vector", "0.8.3")]

    class _FakeConn:
        def cursor(self): return _FakeCur()
        def commit(self): pass

    with pytest.raises(RuntimeError, match="Stage 0c environment check failed"):
        verify_env_snapshot(_FakeConn(), snapshot_path=sp)
