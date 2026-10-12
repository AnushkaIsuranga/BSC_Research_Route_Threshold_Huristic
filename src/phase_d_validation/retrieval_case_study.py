"""Show exact vs post-filter retrieval for one FinQA query: SQL, WHERE clause, plans, rows (id, ticker, year, distance).

  python -m src.phase_d_validation.retrieval_case_study "HIG/2004/page_140.pdf-1" [--embed-model nomic-embed-text:latest]
Read-only; query embedding from the local Ollama.
"""
import argparse

import psycopg2
import requests
from pgvector.psycopg2 import register_vector

from src import db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.utils.finqa_utils import extract_ticker_year

ap = argparse.ArgumentParser()
ap.add_argument("query_id")
ap.add_argument("--embed-model", default="nomic-embed-text:latest")
ap.add_argument("--table", default="finqa_evidence")
a = ap.parse_args()
q = next(r for r in load_finqa_subset(get_frozen_filepath()) if r["id"] == a.query_id)
t, y = extract_ticker_year(a.query_id)
print("question:", q["question"], "| gold:", q["answer"], "| gold keys:", q["gold_evidence_keys"], "| filter ticker/year:", t, y)
v = requests.post("http://127.0.0.1:11434/api/embed", json={"model": a.embed_model, "input": q["question"]}, timeout=120).json()["embeddings"][0]
c = psycopg2.connect(**db_settings()); c.autocommit = True; register_vector(c); cur = c.cursor()
cur.execute("SET hnsw.ef_search=40")
cur.execute(f"SELECT id, query_id, evidence_key, metadata->>'ticker', metadata->>'year' FROM {a.table} WHERE query_id=%s AND evidence_key = ANY(%s)", (a.query_id, q["gold_evidence_keys"].split("|")))
print("GOLD rows (id, query_id, key, ticker, year):", cur.fetchall())
W = f"metadata->>'ticker' = '{t}' AND metadata->>'year' = '{y}'"
S = f"SELECT id, query_id, evidence_key, metadata->>'ticker', metadata->>'year', embedding <-> %s::vector AS d FROM {a.table} WHERE {W} ORDER BY embedding <-> %s::vector LIMIT 12"
for label, sets in (("EXACT / pre-filter: SET enable_indexscan=off; SET enable_seqscan=on", "SET enable_indexscan=off; SET enable_seqscan=on; SET hnsw.iterative_scan=off"),
                    ("POST-FILTER: SET enable_indexscan=on; SET enable_seqscan=off; SET hnsw.iterative_scan=off", "SET enable_indexscan=on; SET enable_seqscan=off; SET hnsw.iterative_scan=off")):
    cur.execute(sets)
    print(f"\n== {label}\nSQL: {S.replace('%s::vector', ':query_vector')}")
    cur.execute("EXPLAIN " + S, (v, v)); print("plan:", " / ".join(r[0].strip()[:80] for r in cur.fetchall()[:3]))
    cur.execute(S, (v, v)); rows = cur.fetchall()
    print(f"rows returned: {len(rows)}")
    for r in rows: print("  id", r[0], r[1], r[2], r[3], r[4], f"{r[5]:.6f}")
cur.execute("SET enable_indexscan=on; SET enable_seqscan=off; SET hnsw.iterative_scan=off")
cur.execute(f"SELECT id, query_id, evidence_key, metadata->>'ticker', metadata->>'year', embedding <-> %s::vector FROM {a.table} ORDER BY embedding <-> %s::vector LIMIT 40", (v, v))
idx = [r for r in cur.fetchall() if r[3] == t and r[4] == y]
cur.execute("SET enable_indexscan=off; SET enable_seqscan=on")
cur.execute(f"SELECT id, query_id, evidence_key, metadata->>'ticker', metadata->>'year', embedding <-> %s::vector d FROM {a.table} ORDER BY d, id LIMIT 40", (v,))
ex = [r for r in cur.fetchall() if r[3] == t and r[4] == y]
print("\nUnfiltered top-40 via HNSW index, rows of this ticker/year:", [(r[2], r[1][-1:], round(r[5], 4)) for r in idx])
print("Unfiltered top-40 exact,        rows of this ticker/year:", [(r[2], r[1][-1:], round(r[5], 4)) for r in ex])
