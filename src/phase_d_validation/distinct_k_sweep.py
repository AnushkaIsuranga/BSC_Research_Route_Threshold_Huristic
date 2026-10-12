"""Retrieval-only sweep of k DISTINCT passages on finqa_evidence_qwen3 (no LLM, no API call; cached query embeddings).

  python -m src.phase_d_validation.distinct_k_sweep --out-dir outputs/phase_d_k_sweep_distinct_<date>

Routes exact and post-filter, k in 6, 10, 15, 20 distinct passages (router.retrieve(distinct=True): repeats dropped by
md5(content), over-fetch as needed). Because a retained copy of a passage may carry another page's id, a gold hit is
defined on the passage text: a gold evidence row counts as retrieved if its text is among the retrieved texts.
  all_gold_hit  every gold row's text retrieved;  any_gold_hit  at least one.
Prompt tokens are estimated with the cl100k -> qwen2.5 linear fit of outputs/phase_d_k_sweep_2026-10-12/token_calibration.json.
Pre-stated rule (reported, not applied by this script to anything else): chosen k = the smallest k whose exact-route
all-gold hit is within 2 queries of the k = 20 value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

from src import db_settings
from src.phase_b_router.router import retrieve
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.k_sweep import ntok
from src.utils.finqa_utils import extract_ticker_year

TABLE = "finqa_evidence_qwen3"
ROUTES = ["exact", "post-filter"]
KS = [6, 10, 15, 20]
RULE_TOLERANCE = 2


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--query-cache", default="outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json")
    ap.add_argument("--calibration", default="outputs/phase_d_k_sweep_2026-10-12/token_calibration.json")
    a = ap.parse_args()
    out = Path(a.out_dir)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    queries = load_finqa_subset(get_frozen_filepath())
    cache_bytes = Path(a.query_cache).read_bytes()
    cache = json.loads(cache_bytes)
    assert [x["query_id"] for x in cache["queries"]] == [q["id"] for q in queries]
    for x in cache["queries"]:
        assert hashlib.sha256(x["input_text"].encode()).hexdigest() == x["input_sha256"]
    cal = json.loads(Path(a.calibration).read_text(encoding="utf-8"))
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute("SET hnsw.ef_search = 40")
    gold = {}
    with conn.cursor() as cur:
        for q in queries:
            keys = [k.strip() for k in q["gold_evidence_keys"].split("|") if k.strip()]
            cur.execute(f"SELECT content FROM {TABLE} WHERE query_id = %s AND evidence_key = ANY(%s)", (q["id"], keys))
            texts = {r[0] for r in cur.fetchall()}
            if not texts:
                raise RuntimeError(f"no gold rows for {q['id']}")
            gold[q["id"]] = texts
    summary, per_query = [], []
    for route in ROUTES:
        for k in KS:
            ha = hy = 0
            rows_ret, toks, dropped = [], [], []
            for q, x in zip(queries, cache["queries"]):
                t, y = extract_ticker_year(q["id"])
                res = retrieve(conn, route, t, y, x["vector"], k, TABLE, distinct=True)
                rows = res["rows"]
                texts = {r[3] for r in rows}
                all_hit, any_hit = int(gold[q["id"]] <= texts), int(bool(gold[q["id"]] & texts))
                nt = ntok(rows, q["question"])
                ha += all_hit; hy += any_hit
                rows_ret.append(len(rows)); toks.append(nt); dropped.append(res["distinct_dropped"])
                per_query.append({"route": route, "k": k, "query_id": q["id"], "all_gold_hit": all_hit, "any_gold_hit": any_hit,
                                  "distinct_rows_returned": len(rows), "rows_fetched": res["rows_fetched"],
                                  "duplicates_dropped": res["distinct_dropped"], "tie_truncated": res["tie_truncated"],
                                  "prompt_tokens_cl100k": nt, "retrieved_ids": [r[0] for r in rows]})
            n = len(queries)
            mt = float(np.mean(toks))
            summary.append({"route": route, "k": k, "all_gold_hits": ha, "any_gold_hits": hy, "n_queries": n,
                            "mean_distinct_rows_returned": float(np.mean(rows_ret)), "queries_underfilled": int(sum(r < k for r in rows_ret)),
                            "mean_duplicates_dropped": float(np.mean(dropped)),
                            "mean_prompt_tokens_cl100k": mt, "mean_prompt_tokens_qwen_est": cal["slope"] * mt + cal["intercept"]})
            print(f"{route:11s} k={k:2d} all {ha:2d}/50 any {hy:2d}/50 rows {np.mean(rows_ret):.1f} underfilled {summary[-1]['queries_underfilled']} tokens~{summary[-1]['mean_prompt_tokens_qwen_est']:.0f}", flush=True)
    ex = {s["k"]: s["all_gold_hits"] for s in summary if s["route"] == "exact"}
    chosen = min(k for k in KS if ex[20] - ex[k] <= RULE_TOLERANCE)
    rule = {"rule": f"chosen k = smallest k whose exact-route all-gold hit is within {RULE_TOLERANCE} queries of the k=20 value",
            "exact_all_gold_hits_by_k": ex, "k20_value": ex[20], "chosen_k": chosen,
            "query_cache": a.query_cache, "query_cache_sha256": hashlib.sha256(cache_bytes).hexdigest(),
            "hit_definition": "gold row text among retrieved distinct passage texts"}
    (out / "chosen_k_rule.json").write_text(json.dumps(rule, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / "per_query.jsonl").open("w", encoding="utf-8") as f:
        for r in per_query:
            f.write(json.dumps(r) + "\n")
    print(json.dumps(rule, indent=2))


if __name__ == "__main__":
    main()
