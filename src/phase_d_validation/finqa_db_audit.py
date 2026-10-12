"""Gate B: independently audit the rebuilt FinQA evidence database."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.utils.finqa_utils import extract_ticker_year


def expected_counts(path: Path) -> tuple[int, int, set[tuple[str, str]]]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    total = 0; unique: set[tuple[str, str, str]] = set(); gold: set[tuple[str, str]] = set()
    for example in dataset:
        qid = example["id"]; ticker, year = extract_ticker_year(qid)
        for i, content in enumerate(example.get("pre_text", [])):
            if content: total += 1; unique.add((hashlib.md5(str(content).encode()).hexdigest(), ticker, year))
        offset = len(example.get("pre_text", []))
        for i, content in enumerate(example.get("post_text", [])):
            if content: total += 1; unique.add((hashlib.md5(str(content).encode()).hexdigest(), ticker, year))
        for i, table_row in enumerate(example.get("table", [])):
            content = " | ".join(map(str, table_row)); total += 1; unique.add((hashlib.md5(content.encode()).hexdigest(), ticker, year))
        gold.update((qid, key) for key in example.get("qa", {}).get("gold_inds", {}))
    return total, len(unique), gold


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--expected-dim", type=int, required=True); args = parser.parse_args()
    total_expected, unique_expected, gold = expected_counts(PROJECT_ROOT / "data/raw/finqa_test.json")
    conn = psycopg2.connect(**db_settings())
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT (md5(content), metadata->>'ticker', metadata->>'year')) FROM finqa_evidence")
        total_db, unique_db = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM finqa_evidence WHERE evidence_key LIKE 'pre_text_%' OR evidence_key LIKE 'post_text_%'")
        legacy_keys = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM finqa_evidence WHERE embedding::text ~ '^\\[0(,0)*\\]$'")
        zero_vectors = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM finqa_evidence WHERE vector_dims(embedding) <> %s", (args.expected_dim,))
        bad_dims = cur.fetchone()[0]
        unresolved = 0
        for qid, key in gold:
            cur.execute("SELECT 1 FROM finqa_evidence WHERE query_id=%s AND evidence_key=%s LIMIT 1", (qid, key))
            unresolved += int(cur.fetchone() is None)
    conn.close()
    checks = {"expected_rows": total_expected, "db_rows": total_db, "expected_unique": unique_expected, "db_unique": unique_db, "legacy_keys": legacy_keys, "zero_vectors": zero_vectors, "bad_dims": bad_dims, "unresolved_gold_pairs": unresolved}
    print(json.dumps(checks, indent=2))
    if total_expected != total_db or unique_expected != unique_db or legacy_keys or zero_vectors or bad_dims or unresolved:
        raise SystemExit("FinQA DB audit failed")


if __name__ == "__main__":
    main()
