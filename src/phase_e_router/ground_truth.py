"""Amendment 9 D3: exact top-10 ids for every (table, filter, vector) of the in-sample, held-out 1 and held-out 2 sets.

enable_indexscan = off, ORDER BY distance, id (deterministic tie-break); the 11th row is fetched only to flag a distance
tie at rank 10/11. Writes outputs/ground_truth_hm/ground_truth.jsonl and meta.json (refuses to overwrite).

  python -m src.phase_e_router.ground_truth            # build
  python -m src.phase_e_router.ground_truth --repro    # D3 reproducibility check (forced-hnsw on 3 in-sample cells)
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict

from src import PROJECT_ROOT
from src.phase_e_router import retriever as R
from src.phase_e_router.cells import GT_DIR, SETS, env_meta, load_filters, load_ground_truth, load_vectors, recall, vector_indices

K = 10


def build():
    out_path, meta_path = GT_DIR / "ground_truth.jsonl", GT_DIR / "meta.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists; ground truth is computed once")
    GT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = R.RouterConfig.load()
    conn = R.connect()
    R.configure_session(conn, cfg)
    vectors, vsha = load_vectors(60)
    meta = {**env_meta(conn), "rule": "enable_indexscan = off, hnsw.iterative_scan = off, ORDER BY distance, id LIMIT 11 (11th row only for the tie flag)",
            "k": K, "vectors_sha256_lines_0_59": vsha, "sets": SETS}
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for set_name in SETS:
            for flt in load_filters(set_name):
                for table in cfg["tables"]:
                    for vi in vector_indices(set_name):
                        rows, ms = R.run_route(conn, R.R_EXACT, table, flt["conditions"], K + 1, R.vec_literal(vectors[vi]), cfg)
                        top, d = rows[:K], [r[1] for r in rows]
                        f.write(json.dumps({"set": set_name, "table": table, "filter_id": flt["filter_id"], "vector_idx": vi,
                                            "ids": [r[0] for r in top], "distances": [r[1] for r in top],
                                            "tie_at_rank_10_11": len(d) > K and d[K - 1] == d[K], "n_rows": len(top),
                                            "query_ms": round(ms, 3)}) + "\n")
                        n += 1
                print(f"{set_name} {flt['filter_id']} done ({n})", flush=True)
    meta["n_rows"] = n
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {n} rows")


def repro():
    """Re-run forced-hnsw (Amendment 2 settings, iterative off) on the 3 in-sample cells with the lowest stored forced-hnsw
    mean recall; recall against the new ground truth vs the stored per-vector recall."""
    out_path = GT_DIR / "repro_check.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists")
    stored = defaultdict(dict)
    with open(PROJECT_ROOT / "outputs/phase_a_arms/results.jsonl", encoding="utf-8") as f:
        for ln in f:
            d = json.loads(ln)
            if d["arm"] == "forced-hnsw":
                stored[(d["table"], d["filter_id"])][d["vector_idx"]] = d["recall"]
    cells = sorted(stored, key=lambda c: (statistics.fmean(stored[c].values()), c))[:3]
    gt = load_ground_truth()
    cfg = R.RouterConfig.load()
    conn = R.connect()
    R.configure_session(conn, cfg)
    vectors, _ = load_vectors(20)
    filters = {f["filter_id"]: f for f in load_filters("in_sample")}
    res = []
    for table, fid in cells:
        per = []
        for vi in range(20):
            rows, _ = R.run_route(conn, R.R_HNSW, table, filters[fid]["conditions"], K, R.vec_literal(vectors[vi]), cfg)
            new = recall([r[0] for r in rows], gt[(table, fid, vi)])
            per.append({"vector_idx": vi, "stored_recall": stored[(table, fid)][vi], "new_recall": new, "rows": len(rows)})
        same = sum(1 for p in per if abs(p["stored_recall"] - p["new_recall"]) < 1e-9)
        res.append({"table": table, "filter_id": fid, "stored_mean": statistics.fmean(p["stored_recall"] for p in per),
                    "new_mean": statistics.fmean(p["new_recall"] for p in per), "vectors_identical": same, "per_vector": per})
        print(f"{table} {fid}: stored {res[-1]['stored_mean']:.3f} new {res[-1]['new_mean']:.3f} identical {same}/20")
    out_path.write_text(json.dumps({"selection": "3 in-sample cells with lowest stored forced-hnsw mean recall",
                                    "git_commit": env_meta(conn)["git_commit"], "cells": res}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repro", action="store_true")
    a = ap.parse_args()
    repro() if a.repro else build()
