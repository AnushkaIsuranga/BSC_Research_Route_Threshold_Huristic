"""Phase H (Amendment 13): Separate untimed EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) pass.

Run ONLY after all timed rows in results.jsonl are complete (never interleaved).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import PROJECT_ROOT
from src.phase_e_router import cells as C
from src.phase_e_router import retriever as R
from src.phase_h_efsweep.runner import ARM_TO_ROUTE, load_all_vectors, make_ef_config


def flag_seq_scan_on_base(arm: str, table: str, plan_root: dict[str, Any]) -> bool:
    """Flag ONLY a Seq Scan on the base table in default_hnsw and always_iterative (never Sort)."""
    if arm not in ("default_hnsw", "always_iterative"):
        return False
    for node in R.plan_nodes(plan_root):
        if node.get("Node Type") == "Seq Scan" and node.get("Relation Name") == table:
            return True
    return False


def _buffer_totals(plan_root: dict[str, Any]) -> dict[str, int]:
    return {
        "shared_hit_blocks": int(plan_root.get("Shared Hit Blocks", 0)),
        "shared_read_blocks": int(plan_root.get("Shared Read Blocks", 0)),
        "shared_dirtied_blocks": int(plan_root.get("Shared Dirtied Blocks", 0)),
        "shared_written_blocks": int(plan_root.get("Shared Written Blocks", 0)),
    }


def run_explain_pass(out_dir: Path) -> dict[str, Any]:
    """Execute one untimed EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) per (unit, arm, ef) on its first vector."""
    manifest_path = out_dir / "manifest.json"
    results_path = out_dir / "results.jsonl"
    if not manifest_path.exists() or not results_path.exists():
        raise RuntimeError(f"manifest.json and results.jsonl must exist in {out_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    done_timed = {json.loads(ln)["row_key"] for ln in results_path.read_text(encoding="utf-8").splitlines() if ln.strip()}
    expected_timed = {r["row_key"] for r in manifest["timed_rows"]}
    missing = expected_timed - done_timed
    if missing:
        raise RuntimeError(f"Refusing EXPLAIN pass before all timed rows complete: {len(missing)} missing")

    explain_path = out_dir / "explain_results.jsonl"
    done_explain: set[str] = set()
    if explain_path.exists():
        for ln in explain_path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                done_explain.add(json.loads(ln)["explain_key"])

    cfg_hm = R.RouterConfig.load("config/router_hm.json")
    cfg_ed = R.RouterConfig.load("config/router_edgar.json")
    hm_vecs, ed_vecs = load_all_vectors()

    conn = R.connect()
    n_written = 0
    try:
        R.configure_session(conn, cfg_hm)
        env = C.env_meta(conn)
        with explain_path.open("a", encoding="utf-8", newline="\n") as fh:
            for item in manifest["explain_items"]:
                ekey = item["explain_key"]
                if ekey in done_explain:
                    continue
                base_cfg = cfg_hm if item["dataset"] == "hm" else cfg_ed
                cfg_ef = make_ef_config(base_cfg, item["ef_search"])
                route = ARM_TO_ROUTE[item["arm"]]
                qv = R.vec_literal(hm_vecs[item["vector_key"]] if item["dataset"] == "hm" else ed_vecs[item["vector_key"]])

                rec: dict[str, Any] = {
                    "explain_key": ekey,
                    "unit_id": item["unit_id"],
                    "dataset": item["dataset"],
                    "table": item["table"],
                    "cell_id": item["cell_id"],
                    "vector_key": item["vector_key"],
                    "arm": item["arm"],
                    "ef_search": item["ef_search"],
                    "selectivity": item["selectivity"],
                    "git_commit": env["git_commit"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                try:
                    plan = R.explain_route(conn, route, item["table"], item["conditions"], int(item["k"]), qv, cfg_ef, analyze=True)
                    root = plan["Plan"]
                    nodes = R.plan_nodes(root)
                    rec.update({
                        "valid": True,
                        "error": None,
                        "plan_nodes": [n.get("Node Type") for n in nodes],
                        "seq_scan_flagged": flag_seq_scan_on_base(item["arm"], item["table"], root),
                        "execution_time_ms": plan.get("Execution Time"),
                        **_buffer_totals(root),
                    })
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    rec.update({"valid": False, "error": repr(e), "seq_scan_flagged": False})

                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
                done_explain.add(ekey)
                n_written += 1
    finally:
        conn.close()

    return {"n_written": n_written, "n_total_explain": len(done_explain)}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Phase H Amendment 13 untimed EXPLAIN pass")
    p.add_argument("--out-dir", required=True, help="Output directory relative to repo root")
    args = p.parse_args(argv)
    print(json.dumps(run_explain_pass(PROJECT_ROOT / args.out_dir), indent=1))


if __name__ == "__main__":
    main()
