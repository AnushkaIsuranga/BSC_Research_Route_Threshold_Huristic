"""Build an alternative FinQA evidence table from finqa_evidence (which is never modified) and audit it.

  python -m src.phase_d_validation.build_finqa_embedding_table --variant nomic_prefixed --out-dir outputs/embedding_build_<date>
  python -m src.phase_d_validation.build_finqa_embedding_table --variant qwen3 --out-dir outputs/embedding_build_<date>

Variants
  nomic_prefixed  nomic-embed-text (Ollama), documents "search_document: " + content, 768-d. Queries: "search_query: " + question.
  qwen3           qwen/qwen3-embedding-8b via OpenRouter, documents with NO prefix, `dimensions=1024` (the API parameter; checked in
                  api_calls.jsonl), queries "Instruct: <task>\\nQuery: <question>". Queries are embedded once and cached.
Same dedup as the 30 Sept build: one embedding per (md5(content), ticker, year). Rows keep the ids of finqa_evidence so
(distance, id) tie-breaking is comparable across tables. HNSW index m=16, ef_construction=64, vector_l2_ops.
Audit (as src/phase_d_validation/finqa_db_audit.py plus self-retrieval from retrieval_pilot.py): row count, unique count,
gold-pair resolution, zero vectors, dimension, self-retrieval 5/5, writes <out-dir>/audit_<table>.json.
The API key comes from the environment only and is never logged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import execute_values

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.embedding_tools import (NOMIC_DOC_PREFIX, NOMIC_QUERY_PREFIX, OpenRouterEmbedder, ollama_embed,
                                                    qwen3_query)
from src.phase_d_validation.finqa_db_audit import expected_counts
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset

SOURCE = "finqa_evidence"
VARIANTS = {
    "nomic_prefixed": {"table": "finqa_evidence_nomic_prefixed", "dim": 768, "model": "nomic-embed-text:latest"},
    "qwen3": {"table": "finqa_evidence_qwen3", "dim": 1024, "model": "qwen/qwen3-embedding-8b"},
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", required=True, choices=VARIANTS)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--cost-cap-usd", type=float, default=1.0)
    a = ap.parse_args()
    v = VARIANTS[a.variant]
    table, dim, model = v["table"], v["dim"], v["model"]
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    cur = conn.cursor()
    cur.execute("SELECT to_regclass(%s)", (table,))
    if cur.fetchone()[0] is not None:
        raise SystemExit(f"{table} already exists; not touching it")
    cur.execute(f"SELECT id, query_id, evidence_key, content, metadata FROM {SOURCE} ORDER BY id")
    rows = cur.fetchall()
    keys = [(hashlib.md5(r[3].encode()).hexdigest(), r[4]["ticker"], r[4]["year"]) for r in rows]
    unique: dict[tuple, str] = {}
    for k, r in zip(keys, rows):
        unique.setdefault(k, r[3])
    print(f"{len(rows)} rows, {len(unique)} unique (md5(content), ticker, year) texts", flush=True)

    # ---- embed documents
    uk, ut = list(unique), list(unique.values())
    client = None
    if a.variant == "nomic_prefixed":
        embed_docs = lambda texts: ollama_embed(model, [NOMIC_DOC_PREFIX + t for t in texts])
        batch = 64
    else:
        client = OpenRouterEmbedder(model, out / "api_calls.jsonl", a.cost_cap_usd, dimensions=dim)
        embed_docs = lambda texts: client.embed(texts, "documents (no prefix)")
        batch = 100
    cache: dict[tuple, np.ndarray] = {}
    t0 = time.time()
    for i in range(0, len(ut), batch):
        vecs = embed_docs(ut[i:i + batch])
        for k, vec in zip(uk[i:i + batch], vecs):
            if len(vec) != dim:
                raise RuntimeError(f"got dimension {len(vec)}, expected {dim}")
            cache[k] = np.asarray(vec, dtype=np.float32)
        if (i // batch) % 10 == 0:
            print(f"embedded {min(i + batch, len(ut))}/{len(ut)} ({time.time() - t0:.0f}s)", flush=True)

    # ---- create table, copy ids, index
    cur.execute(f"""CREATE TABLE {table} (id integer PRIMARY KEY, query_id text, evidence_key text, content text,
                    metadata jsonb, embedding vector({dim}))""")
    execute_values(cur, f"INSERT INTO {table} (id, query_id, evidence_key, content, metadata, embedding) VALUES %s",
                   [(r[0], r[1], r[2], r[3], json.dumps(r[4]), cache[k]) for r, k in zip(rows, keys)],
                   template="(%s,%s,%s,%s,%s::jsonb,%s)", page_size=1000)
    print("building HNSW index (m=16, ef_construction=64)...", flush=True)
    cur.execute(f"CREATE INDEX {table}_embedding_idx ON {table} USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64)")
    cur.execute(f"ANALYZE {table}")

    # ---- query embeddings (50 frozen questions), cached with hashes
    queries = load_finqa_subset(get_frozen_filepath())
    if a.variant == "nomic_prefixed":
        q_inputs = [NOMIC_QUERY_PREFIX + q["question"] for q in queries]
        q_vecs = ollama_embed(model, q_inputs)
    else:
        q_inputs = [qwen3_query(q["question"]) for q in queries]
        q_vecs = client.embed(q_inputs, "50 queries (instruct template), embedded once")
    (out / f"query_embeddings_{a.variant}.json").write_text(json.dumps({
        "model": model, "dimension": dim, "variant": a.variant,
        "queries": [{"query_id": q["id"], "input_text": t, "input_sha256": hashlib.sha256(t.encode()).hexdigest(), "vector": vec}
                    for q, t, vec in zip(queries, q_inputs, q_vecs)]}), encoding="utf-8")

    # ---- audit
    total_expected, unique_expected, gold = expected_counts(PROJECT_ROOT / "data/raw/finqa_test.json")
    cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT (md5(content), metadata->>'ticker', metadata->>'year')) FROM {table}")
    total_db, unique_db = cur.fetchone()
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE embedding::text ~ '^\\[0(,0)*\\]$'")
    zero_vectors = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE vector_dims(embedding) <> %s", (dim,))
    bad_dims = cur.fetchone()[0]
    unresolved = 0
    for qid, key in gold:
        cur.execute(f"SELECT 1 FROM {table} WHERE query_id=%s AND evidence_key=%s LIMIT 1", (qid, key))
        unresolved += int(cur.fetchone() is None)
    # self-retrieval: re-embed 5 evenly spaced documents with the document function; exact top-1 must have identical content
    pick = [rows[i] for i in np.linspace(0, len(rows) - 1, 5, dtype=int)]
    cur.execute("SET enable_indexscan = off")
    self_ok = 0
    detail = []
    for r in pick:
        qv = np.asarray(embed_docs([r[3]])[0], dtype=np.float32)
        cur.execute(f"SELECT id, content, embedding <-> %s::vector AS d FROM {table} ORDER BY d, id LIMIT 1", (qv,))
        top = cur.fetchone()
        ok = top[1] == r[3]
        self_ok += int(ok)
        detail.append({"row_id": r[0], "top1_id": top[0], "top1_same_content": ok, "distance": float(top[2])})
    cur.execute(f"SELECT COUNT(*) FROM {SOURCE}")
    src_rows = cur.fetchone()[0]
    audit = {"table": table, "model": model, "dimension": dim, "source_rows": src_rows, "expected_rows": total_expected,
             "db_rows": total_db, "expected_unique": unique_expected, "db_unique": unique_db, "zero_vectors": zero_vectors,
             "bad_dims": bad_dims, "unresolved_gold_pairs": unresolved, "self_retrieval": f"{self_ok}/5", "self_retrieval_detail": detail,
             "api_cost_usd": client.spent if client else 0.0, "api_prompt_tokens": client.tokens if client else 0}
    audit["passed"] = (total_db == total_expected == 35862 and unique_db == unique_expected and zero_vectors == 0 and bad_dims == 0
                       and unresolved == 0 and self_ok == 5)
    (out / f"audit_{table}.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
    if not audit["passed"]:
        raise SystemExit("AUDIT FAILED")


if __name__ == "__main__":
    main()
