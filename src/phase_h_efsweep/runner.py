"""Phase H (Amendment 13): Timed retrieval runner for the ef_search sweep."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import PROJECT_ROOT
from src.phase_e_router import cells as C
from src.phase_e_router import retriever as R
from src.phase_f_edgar import session_tools as S
from src.phase_h_efsweep import AMENDMENT_TAG, EARLY_STOP_MS, SEED, TIMED_REPS
from src.phase_h_efsweep.manifest import write_manifest

HM_GT_PATH = "outputs/ground_truth_hm/ground_truth.jsonl"
EDGAR_CAL_GT_PATH = "outputs/edgar_calibration_2026-11-01/ground_truth.json"
EDGAR_EVAL_GT_PATH = "outputs/edgar_retrieval_comparison_2026-11-01/ground_truth.json"
ENV_SNAPSHOT_PATH = "outputs/straddle_t_env_snapshot_2026-11-15.json"

ARM_TO_ROUTE = {
    "always_exact": R.R_EXACT,
    "default_hnsw": R.R_HNSW,
    "always_iterative": R.R_ITER,
}


def make_ef_config(base_cfg: R.RouterConfig, ef: int | None) -> R.RouterConfig:
    """Return a RouterConfig copy with ef_search overridden (no mutation of base_cfg)."""
    if ef is None:
        return R.RouterConfig(raw=dict(base_cfg.raw), T_default=base_cfg.T_default, T_tuned=base_cfg.T_tuned)
    return R.RouterConfig(raw={**base_cfg.raw, "ef_search": int(ef)}, T_default=base_cfg.T_default, T_tuned=base_cfg.T_tuned)


def should_early_stop(rep_latencies_ms: list[float], threshold_ms: float = EARLY_STOP_MS) -> bool:
    """Addendum 1 early-stop: strictly > 1500.0 ms on median of first 2 timed reps."""
    if len(rep_latencies_ms) != 2:
        return False
    return statistics.median(rep_latencies_ms) > threshold_ms


def load_all_ground_truth(root: Path = PROJECT_ROOT) -> dict[tuple[str, str, str, str], list[int]]:
    """Load frozen ground truth keyed by (dataset, table, cell_id, vector_key)."""
    gt: dict[tuple[str, str, str, str], list[int]] = {}

    with (root / HM_GT_PATH).open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            gt[("hm", d["table"], d["filter_id"], str(d["vector_idx"]))] = d["ids"]

    ed_cal = json.loads((root / EDGAR_CAL_GT_PATH).read_text(encoding="utf-8"))
    for key, ids in ed_cal.items():
        fid, qid = key.split("|", 1)
        gt[("edgar_cal", "edgar_chunks", fid, qid)] = ids

    ed_eval = json.loads((root / EDGAR_EVAL_GT_PATH).read_text(encoding="utf-8"))
    for pair_id, ids in ed_eval.items():
        qid = pair_id.split("|", 1)[0]
        gt[("edgar_eval", "edgar_chunks", pair_id, qid)] = ids

    return gt


def load_all_vectors(root: Path = PROJECT_ROOT) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Return (hm_vectors {str(idx): vec}, edgar_vectors {qid: vec})."""
    hm_raw, _ = C.load_vectors(20)
    hm_vecs = {str(k): v for k, v in hm_raw.items()}
    ed_vecs = S.load_question_vectors()
    return hm_vecs, ed_vecs


def check_main_preconditions(tag: str = AMENDMENT_TAG, root: Path = PROJECT_ROOT) -> None:
    """Refuse MAIN run unless working tree is clean and at/descended from amendment tag."""
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=root).stdout.strip()
    if dirty:
        raise RuntimeError(f"MAIN run refused: working tree is dirty:\n{dirty}")
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", tag, "HEAD"], capture_output=True, text=True, cwd=root)
    if anc.returncode != 0:
        raise RuntimeError(f"MAIN run refused: HEAD is not a descendant of tag {tag!r}")


def verify_env_snapshot(conn, snapshot_path: Path = PROJECT_ROOT / ENV_SNAPSHOT_PATH) -> dict[str, Any]:
    """Re-run Stage 0c environment fingerprint check against straddle_t_env_snapshot_2026-11-15.json; abort on diff."""
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    diffs: list[str] = []
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        pg_ver = cur.fetchone()[0]
        if pg_ver != snap["postgresql_version"]:
            diffs.append(f"postgresql_version: {pg_ver!r} != {snap['postgresql_version']!r}")

        cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname IN ('plpgsql', 'vector') ORDER BY extname")
        exts = dict(cur.fetchall())
        if exts != snap["extensions"]:
            diffs.append(f"extensions: {exts!r} != {snap['extensions']!r}")

        for guc, exp in snap["settings"].items():
            if exp is None:
                continue  # hnsw.* are None in snapshot before vector library is loaded
            cur.execute("SELECT current_setting(%s)", (guc,))
            got = cur.fetchone()[0]
            if got != exp:
                diffs.append(f"setting {guc}: {got!r} != {exp!r}")

        for tbl, info in snap["tables"].items():
            cur.execute(f"SELECT count(*) FROM {tbl}")
            rc = cur.fetchone()[0]
            if rc != info["row_count"]:
                diffs.append(f"{tbl}.row_count: {rc} != {info['row_count']}")
            cur.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = %s ORDER BY indexname",
                (tbl,),
            )
            idxs = [{"name": r[0], "indexdef": r[1]} for r in cur.fetchall()]
            if idxs != info["indexes"]:
                diffs.append(f"{tbl}.indexes mismatch")
            cur.execute(f"SELECT id FROM {tbl} ORDER BY id")
            h_id = hashlib.sha256(",".join(str(r[0]) for r in cur.fetchall()).encode("utf-8")).hexdigest()
            exp_hash = info["fingerprints"]["sorted_id_sha256"]
            if h_id != exp_hash:
                diffs.append(f"{tbl}.sorted_id_sha256: {h_id} != {exp_hash}")
    conn.commit()
    if diffs:
        raise RuntimeError("Stage 0c environment check failed:\n  " + "\n  ".join(diffs))
    return {"snapshot": str(snapshot_path), "verified": True}


def measure_row(
    conn,
    row: dict[str, Any],
    qv: list[float],
    truth: list[int],
    base_cfg: R.RouterConfig,
    env: dict[str, Any],
    git_dirty: bool,
) -> dict[str, Any]:
    """Execute 1 warm-up + up to 5 timed reps of R.retrieve() with Addendum 1 early stop."""
    arm = row["arm"]
    ef = row["ef_search"]
    cfg_ef = make_ef_config(base_cfg, ef)
    route = ARM_TO_ROUTE[arm]
    r_settings = R.route_settings(route, cfg_ef)
    k = int(row["k"])

    rep_latencies_ms: list[float] = []
    early_stopped = False
    rows_returned: int | None = None
    recall: float | None = None
    valid = True
    error: str | None = None

    try:
        # 1 untimed warm-up (also captures returned ids & recall)
        res_rows, _ = R.retrieve(qv, row["conditions"], k, arm, cfg_ef, conn=conn, table=row["table"])
        returned_ids = [r[0] for r in res_rows]
        rows_returned = len(returned_ids)
        recall = S.recall_at(returned_ids, truth, k)

        for rep_idx in range(TIMED_REPS):
            _, trace = R.retrieve(qv, row["conditions"], k, arm, cfg_ef, conn=conn, table=row["table"])
            rep_latencies_ms.append(float(trace["total_ms"]))
            if rep_idx == 1 and should_early_stop(rep_latencies_ms):
                early_stopped = True
                break
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        valid = False
        error = repr(e)

    median_ms = statistics.median(rep_latencies_ms) if (valid and rep_latencies_ms) else None

    return {
        "row_key": row["row_key"],
        "unit_id": row["unit_id"],
        "dataset": row["dataset"],
        "role": row["role"],
        "table": row["table"],
        "cell_id": row["cell_id"],
        "vector_key": row["vector_key"],
        "k": k,
        "ef_search": ef,
        "arm": arm,
        "selectivity": row["selectivity"],
        "breadth": row.get("breadth"),
        "rows_returned": rows_returned,
        "recall": recall,
        "rep_latencies_ms": rep_latencies_ms,
        "median_latency_ms": median_ms,
        "early_stopped": early_stopped,
        "valid": valid,
        "error": error,
        "route_settings": r_settings,
        "host_info": {"python": platform.python_version(), "platform": platform.platform()},
        "git_commit": env["git_commit"],
        "git_dirty": git_dirty,
        "pg_version": env["pg_version"],
        "pgvector_version": env["pgvector_version"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_session(out_dir: Path, smoke: bool = False, seed: int = SEED) -> dict[str, Any]:
    """Run timed ef_search sweep (resume-safe, append-only results.jsonl)."""
    if not smoke:
        check_main_preconditions()

    out_dir.mkdir(parents=True, exist_ok=True)
    mpath, manifest_sha = write_manifest(out_dir, smoke=smoke, seed=seed)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    timed_rows = manifest["timed_rows"]

    cfg_hm = R.RouterConfig.load("config/router_hm.json")
    cfg_ed = R.RouterConfig.load("config/router_edgar.json")
    gt_map = load_all_ground_truth()
    hm_vecs, ed_vecs = load_all_vectors()

    conn = R.connect()
    loads: S.LoadLogger | None = None
    try:
        if not smoke:
            verify_env_snapshot(conn)
        R.configure_session(conn, cfg_hm)
        env = C.env_meta(conn)
        git_dirty = bool(C.git("status", "--porcelain"))

        if smoke:
            q_info = C.quiet_check()
            S.write_json(out_dir / "quiet_check_smoke.json", q_info)
        else:
            q_info = S.quiet_start(out_dir)

        results_path = out_dir / "results.jsonl"
        done_keys: set[str] = set()
        if results_path.exists():
            for ln in results_path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    done_keys.add(json.loads(ln)["row_key"])

        S.write_json(out_dir / "run_meta.json", {
            "smoke": smoke,
            "seed": seed,
            "manifest_sha256": manifest_sha,
            "n_timed_rows": len(timed_rows),
            "n_already_done": len(done_keys),
            "quiet_check": q_info,
            "git_commit": env["git_commit"],
            "git_dirty": git_dirty,
            "pg_version": env["pg_version"],
            "pgvector_version": env["pgvector_version"],
            "started_utc": datetime.now(timezone.utc).isoformat(),
        })

        loads = S.LoadLogger(out_dir / "host_load.json", every_s=300)
        loads.sample("start")
        loads.start()

        n_written = 0
        t0 = time.perf_counter()
        with results_path.open("a", encoding="utf-8", newline="\n") as fh:
            for row in timed_rows:
                if row["row_key"] in done_keys:
                    continue
                base_cfg = cfg_hm if row["dataset"] == "hm" else cfg_ed
                qv = hm_vecs[row["vector_key"]] if row["dataset"] == "hm" else ed_vecs[row["vector_key"]]
                truth = gt_map[(row["dataset"], row["table"], row["cell_id"], row["vector_key"])]
                rec = measure_row(conn, row, qv, truth, base_cfg, env, git_dirty)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
                done_keys.add(row["row_key"])
                n_written += 1
        elapsed_s = time.perf_counter() - t0
    finally:
        if loads is not None:
            loads.stop_evt.set()
            loads.sample("end")
        conn.close()

    return {"n_written": n_written, "n_total_done": len(done_keys), "elapsed_s": elapsed_s, "quiet": q_info}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Phase H Amendment 13 ef_search sweep runner")
    p.add_argument("--out-dir", required=True, help="Output directory relative to repo root")
    p.add_argument("--smoke", action="store_true", help="Run deterministic smoke subset")
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args(argv)
    summary = run_session(PROJECT_ROOT / args.out_dir, smoke=args.smoke, seed=args.seed)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
