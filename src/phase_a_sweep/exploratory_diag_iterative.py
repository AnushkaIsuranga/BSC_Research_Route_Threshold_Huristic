"""EXPLORATORY diagnostic (not part of the pre-registered run).

Question: on hm_clothes_100 at lo3 and lo4, iterative-relaxed / iterative-strict return 10 rows
with low recall (0.82 / 0.42). Is that explained by hnsw.ef_search, by the hnsw.max_scan_tuples
cap, or by neither? Recall only, one untimed execution per point, 20 vectors.

Configs (ef_search, max_scan_tuples, scan_mem_multiplier):
  base 40/20000/1 ; ef100 100/20000/1 ; ef200 200/20000/1 ; cap100000 40/100000/1   (requested)
  mem4 40/20000/4 ; cap+mem 40/100000/4 ; all-raised 200/100000/4                    (extra: pgvector also
  limits iterative scans by memory, work_mem x hnsw.scan_mem_multiplier; not in the request)

Also recomputes the exact top-10 with a forced Seq Scan and compares it with the exact reference
used by the run (enable_indexscan=off), and checks for a distance tie at rank 10/11.

Writes outputs/phase_a_arms/exploratory_diag.jsonl (never touches results.jsonl).
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from src.phase_a_sweep.arm_comparison import (K, OUT_DIR, STATEMENT_TIMEOUT_MS, apply_arm, connect, find_scan_node, git,
                                              load_vectors)
from src.phase_a_sweep.recall_calculator import fetch_top_k_ids

TABLE = "hm_clothes_100"
FILTERS = ["lo3", "lo4"]
ARMS = ["iterative-relaxed", "iterative-strict"]
CONFIGS = [("base", 40, 20000, 1), ("ef100", 100, 20000, 1), ("ef200", 200, 20000, 1), ("cap100000", 40, 100000, 1),
           ("mem4 (extra)", 40, 20000, 4), ("cap+mem (extra)", 40, 100000, 4), ("all-raised (extra)", 200, 100000, 4)]


def main():
    filters = {f["filter_id"]: f for f in json.loads((OUT_DIR / "filters.json").read_text(encoding="utf-8"))}
    vectors, _ = load_vectors()
    commit = git("rev-parse", "HEAD")
    recorded = {}
    for ln in (OUT_DIR / "results.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(ln)
        if d["table"] == TABLE and d["filter_id"] in FILTERS and d["arm"] in ARMS:
            recorded[(d["filter_id"], d["arm"], d["vector_idx"])] = d["recall"]

    sweep, truth_a, truth_b = connect(), connect(), connect()
    with truth_a.cursor() as c:                      # the run's reference: enable_indexscan = off
        c.execute("SET enable_indexscan = off")
        c.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
    with truth_b.cursor() as c:                      # forced Seq Scan
        c.execute("SET enable_indexscan = off")
        c.execute("SET enable_bitmapscan = off")
        c.execute("SET enable_seqscan = on")
        c.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
    cur = sweep.cursor()
    out = open(OUT_DIR / "exploratory_diag.jsonl", "w", encoding="utf-8")

    def write(d):
        d.update({"exploratory": True, "git_commit": commit, "timestamp": datetime.now(timezone.utc).isoformat()})
        out.write(json.dumps(d) + "\n")
        out.flush()

    truth = {}
    for fid in FILTERS:
        f = filters[fid]
        for v, qv in enumerate(vectors):
            ids_a = fetch_top_k_ids(truth_a, TABLE, "embedding", f["where"], f["params"], qv, K, STATEMENT_TIMEOUT_MS)
            tc = truth_b.cursor()
            # parameter order: select-list vector, WHERE params, ORDER BY vector
            q = (f"SELECT id, (embedding::halfvec(2048)) <=> %s::halfvec(2048) AS d FROM {TABLE} WHERE {f['where']} "
                 f"ORDER BY (embedding::halfvec(2048)) <=> %s::halfvec(2048), id LIMIT 12")
            args = (qv,) + tuple(f["params"]) + (qv,)
            tc.execute("EXPLAIN (FORMAT JSON) " + q, args)
            node = find_scan_node(tc.fetchone()[0][0]["Plan"]).get("Node Type")
            tc.execute(q, args)
            rows = tc.fetchall()
            ids_b = {r[0] for r in rows[:K]}
            d10, d11 = rows[K - 1][1], rows[K][1] if len(rows) > K else None
            truth[(fid, v)] = ids_b
            write({"type": "truth", "table": TABLE, "filter_id": fid, "vector_idx": v, "seqscan_node": node,
                   "truth_original_method_matches_seqscan": ids_a == ids_b, "tie_at_rank_10_11": d11 is not None and d10 == d11,
                   "distance_rank10": d10, "distance_rank11": d11})

    for name, ef, cap, mem in CONFIGS:
        for fid in FILTERS:
            f = filters[fid]
            for arm in ARMS:
                eff = apply_arm(cur, arm)
                cur.execute(f"SET hnsw.ef_search = {ef}")
                cur.execute(f"SET hnsw.max_scan_tuples = {cap}")
                cur.execute(f"SET hnsw.scan_mem_multiplier = {mem}")
                cur.execute("SELECT current_setting('hnsw.ef_search'), current_setting('hnsw.max_scan_tuples'), "
                            "current_setting('hnsw.scan_mem_multiplier'), current_setting('hnsw.iterative_scan'), current_setting('work_mem')")
                got = cur.fetchone()
                for v, qv in enumerate(vectors):
                    ids = fetch_top_k_ids(sweep, TABLE, "embedding", f["where"], f["params"], qv, K, STATEMENT_TIMEOUT_MS)
                    t = truth[(fid, v)]
                    write({"type": "run", "table": TABLE, "filter_id": fid, "arm": arm, "config": name, "ef_search": got[0],
                           "max_scan_tuples": got[1], "scan_mem_multiplier": got[2], "iterative_scan": got[3], "work_mem": got[4],
                           "vector_idx": v, "recall": len(ids & t) / len(t), "rows_returned": len(ids),
                           "recorded_recall_in_results_jsonl": recorded.get((fid, arm, v)) if name == "base" else None})
    out.close()

    rows = [json.loads(ln) for ln in (OUT_DIR / "exploratory_diag.jsonl").read_text(encoding="utf-8").splitlines()]
    tr = [r for r in rows if r["type"] == "truth"]
    print(f"truth rows {len(tr)}: seq-scan node set {sorted({r['seqscan_node'] for r in tr})}; "
          f"original-method == seq-scan top-10 in {sum(r['truth_original_method_matches_seqscan'] for r in tr)}/{len(tr)}; "
          f"ties at rank 10/11: {sum(r['tie_at_rank_10_11'] for r in tr)}")
    base = [r for r in rows if r["type"] == "run" and r["config"] == "base"]
    print(f"base config recall equals recorded run recall in {sum(abs(r['recall'] - r['recorded_recall_in_results_jsonl']) < 1e-9 for r in base)}/{len(base)}")
    print(f"{'config':20s} {'filter':5s} {'arm':18s} mean_recall  min_recall  median_rows  min_rows  n<10rows")
    for name, *_ in CONFIGS:
        for fid in FILTERS:
            for arm in ARMS:
                x = [r for r in rows if r["type"] == "run" and r["config"] == name and r["filter_id"] == fid and r["arm"] == arm]
                print(f"{name:20s} {fid:5s} {arm:18s} {statistics.mean(r['recall'] for r in x):9.3f} {min(r['recall'] for r in x):10.2f} "
                      f"{statistics.median(r['rows_returned'] for r in x):11.0f} {min(r['rows_returned'] for r in x):9d} {sum(r['rows_returned'] < 10 for r in x):9d}")

    # markdown summary (EXPLORATORY) for the report
    L = ["| config (ef_search / max_scan_tuples / scan_mem_multiplier) | filter | arm | mean recall | min recall (any vector) | median rows | min rows | vectors with <10 rows |", "|---|---|---|---|---|---|---|---|"]
    for name, ef, cap, mem in CONFIGS:
        for fid in FILTERS:
            for arm in ARMS:
                x = [r for r in rows if r["type"] == "run" and r["config"] == name and r["filter_id"] == fid and r["arm"] == arm]
                L.append(f"| {name} ({ef} / {cap} / {mem}) | {fid} | {arm} | {statistics.mean(r['recall'] for r in x):.3f} | {min(r['recall'] for r in x):.2f} | "
                         f"{statistics.median(r['rows_returned'] for r in x):.0f} | {min(r['rows_returned'] for r in x)} | {sum(r['rows_returned'] < 10 for r in x)}/20 |")
    (OUT_DIR / "exploratory_diag_summary.md").write_text(chr(10).join(L) + chr(10), encoding="utf-8")


if __name__ == "__main__":
    main()
