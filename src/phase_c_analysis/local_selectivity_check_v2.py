# LEGACY — not used in final results. 30 Sept diagnostic of post-filter under-fill (no id tie-break).
"""Read-only check: does an unfiltered top-40 probe reproduce the post-filter counts?

It mirrors the post-filter branch of local_ollama_runner._retrieve:
  unfiltered ORDER BY embedding <-> query LIMIT 40, filter in Python, keep first k.
It reads the corrected JSONL (authoritative) and writes a CSV for the record.
It only runs SELECT and EXPLAIN statements.
"""
import csv
import json
from pathlib import Path

import psycopg2
from pgvector.psycopg2 import register_vector

from src import db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.ollama_client import OllamaClient
from src.utils.finqa_utils import extract_ticker_year

RESULTS = Path("outputs/phase_d_results_ollama_corrected.jsonl")
OUT = Path("outputs/local_selectivity_check.csv")
EMBED_MODEL = "nomic-embed-text:latest"
POOL, K, EF_SEARCH = 40, 6, 40
EXPECTED_CORPUS = 35862

PROBE_SQL = """
    SELECT metadata->>'ticker', metadata->>'year'
    FROM finqa_evidence
    ORDER BY embedding <-> %s::vector
    LIMIT %s
"""


def load_results():
    by_id = {}
    with RESULTS.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                by_id[r["id"]] = r
    return by_id


def main():
    results = load_results()
    queries = load_finqa_subset(get_frozen_filepath())
    client = OllamaClient()

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM finqa_evidence")
        corpus = cur.fetchone()[0]
        if corpus != EXPECTED_CORPUS:
            raise RuntimeError(f"Corpus is {corpus} rows, expected {EXPECTED_CORPUS}. The DB changed since the run.")
        cur.execute(f"SET hnsw.ef_search = {EF_SEARCH}")
        cur.execute("SET enable_indexscan = on")
        cur.execute("SET enable_seqscan = off")

    rows_out = []
    explained = False
    for q in queries:
        qid = q["id"]
        if qid not in results:
            continue
        res = results[qid]
        ticker, year = extract_ticker_year(qid)
        vector = client.embed(EMBED_MODEL, q["question"])
        with conn.cursor() as cur:
            if not explained:
                cur.execute("EXPLAIN " + PROBE_SQL, (vector, POOL))
                print("Probe plan:", [r[0] for r in cur.fetchall()][:3])
                explained = True
            cur.execute(PROBE_SQL, (vector, POOL))
            top = cur.fetchall()
        passed = sum(1 for t, y in top if t == ticker and y == year)
        global_sel = float(res["selectivity"])
        local_sel = passed / POOL
        predicted = min(passed, K)  # the runner truncates to k
        is_post = res.get("naive_route") == "post-filter"
        observed = int(res["naive_retrieved"]) if is_post else None
        rows_out.append({
            "id": qid,
            "global_selectivity": global_sel,
            "probe_passed_of_40": passed,
            "local_selectivity": local_sel,
            "local_over_global": local_sel / global_sel if global_sel else None,
            "predicted_post_filter_rows": predicted,
            "naive_route": res.get("naive_route"),
            "observed_naive_retrieved": observed,
            "match": (predicted == observed) if observed is not None else None,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)

    post = [r for r in rows_out if r["match"] is not None]
    mism = [r for r in post if not r["match"]]
    print(f"Post-filter queries compared: {len(post)}; matched: {len(post) - len(mism)}; mismatched: {len(mism)}")
    for r in mism:
        print("  mismatch:", r["id"], "predicted", r["predicted_post_filter_rows"], "observed", r["observed_naive_retrieved"])
    print(f"Wrote {OUT}")
    conn.close()


if __name__ == "__main__":
    main()
