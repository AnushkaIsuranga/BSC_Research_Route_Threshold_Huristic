"""Task 2 (Phase F): create table edgar_chunks and load the chunks (embedding NULL until Task 3). Touches no other table.

  python -m src.phase_f_edgar.load_table --chunks outputs/edgar_chunks_2026-10-31/chunks.jsonl

Refuses to run if edgar_chunks exists (reset: see docs/RUNBOOK_EDGAR.md). ids are 1..N in chunks.jsonl order.
"""

from __future__ import annotations

import argparse
import json

import psycopg2
from psycopg2.extras import execute_values

from src import PROJECT_ROOT, db_settings
from src.phase_f_edgar import common as C

DDL = f"""CREATE TABLE {C.TABLE} (
    id bigint PRIMARY KEY,
    cik text NOT NULL,
    company_name text,
    fiscal_year integer NOT NULL,
    section text NOT NULL,
    chunk_index integer NOT NULL,
    text text NOT NULL,
    text_hash text NOT NULL,
    embedding vector({C.EMBED_DIM}),
    UNIQUE (cik, fiscal_year, section, chunk_index)
)"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks", required=True)
    a = ap.parse_args()
    rows = []
    with open(PROJECT_ROOT / a.chunks, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            r = json.loads(line)
            if C.text_hash(r["text"]) != r["text_hash"]:
                raise SystemExit(f"line {i}: text_hash does not match text")
            rows.append((i, r["cik"], r["company_name"], int(r["fiscal_year"]), r["section"], int(r["chunk_index"]), r["text"], r["text_hash"]))
    conn = psycopg2.connect(**db_settings())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (C.TABLE,))
            if cur.fetchone()[0] is not None:
                raise SystemExit(f"{C.TABLE} already exists; not touching it")
            cur.execute(DDL)
            execute_values(cur, f"INSERT INTO {C.TABLE} (id, cik, company_name, fiscal_year, section, chunk_index, text, text_hash) VALUES %s",
                           rows, page_size=2000)
            cur.execute(f"SELECT count(*), count(DISTINCT text_hash) FROM {C.TABLE}")
            n, nu = cur.fetchone()
        if n != len(rows):
            raise SystemExit(f"inserted {n} rows, expected {len(rows)}")
        conn.commit()
    finally:
        conn.close()
    print(json.dumps({"table": C.TABLE, "rows": n, "distinct_text_hash": nu}))


if __name__ == "__main__":
    main()
