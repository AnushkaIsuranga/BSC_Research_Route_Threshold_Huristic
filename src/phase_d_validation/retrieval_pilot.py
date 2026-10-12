# LEGACY — not used in final results. gate C of the 30 Sept FinQA build. NOTE: uses COSINE distance (<=>) on finqa_evidence, whereas all tables, indexes and runs use L2 (<->).
"""Gate C retrieval pilot, including self-retrieval consistency checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg2
from pgvector.psycopg2 import register_vector

from src import db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.ollama_client import OllamaClient
from src.utils.finqa_utils import extract_ticker_year


def self_retrieval(client: OllamaClient, model: str, sample_size: int) -> dict:
    conn = psycopg2.connect(**db_settings()); conn.autocommit = True; register_vector(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT id, content FROM finqa_evidence ORDER BY id LIMIT %s", (sample_size,))
        samples = cur.fetchall(); passed = 0; details = []
        for row_id, content in samples:
            vector = client.embed(model, content)
            cur.execute("SELECT id, content, embedding <=> %s::vector AS distance FROM finqa_evidence ORDER BY embedding <=> %s::vector LIMIT 1", (vector, vector))
            found_id, found_content, distance = cur.fetchone()
            ok = found_content == content
            passed += int(ok); details.append({"source_id": row_id, "found_id": found_id, "distance": distance, "passed": ok})
    conn.close(); return {"sample_size": len(samples), "passed": passed, "details": details}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--embedding-model", required=True); parser.add_argument("--sample-size", type=int, default=5); parser.add_argument("--subset", default=None); parser.add_argument("--k", type=int, default=6); args = parser.parse_args()
    client = OllamaClient(); print(json.dumps({"self_retrieval": self_retrieval(client, args.embedding_model, args.sample_size)}, indent=2))
    # The normal local runner supplies unit/full/any hit metrics for the 5-query pilot.
    print("Run local_ollama_runner --limit 5 and verify its unit_recall/full_hit/any_hit fields against PASS_CRITERIA.md.")


if __name__ == "__main__":
    main()
