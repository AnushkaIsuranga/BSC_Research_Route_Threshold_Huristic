# LEGACY — not used in final results. gate A of the 30 Sept FinQA build (checks the nomic table only); not run for the final runs.
"""Gate A: verify PostgreSQL/pgvector and Ollama before running Phase D."""

from __future__ import annotations

import argparse
import os

import psycopg2

from src import db_settings
from src.phase_d_validation.ollama_client import OllamaClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-model", required=True)
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--expected-dim", type=int, required=True)
    args = parser.parse_args()

    conn = psycopg2.connect(**db_settings())
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        extension = cur.fetchone()
        if not extension:
            raise RuntimeError("pgvector extension is not installed")
    conn.close()

    client = OllamaClient()
    models = client.tags()
    required = {args.chat_model, args.embedding_model}
    missing = required - set(models)
    if missing:
        raise RuntimeError(f"Missing Ollama models: {', '.join(sorted(missing))}")
    vector = client.embed(args.embedding_model, "Phase D embedding preflight")
    if len(vector) != args.expected_dim:
        raise RuntimeError(f"Embedding dimension {len(vector)} != expected {args.expected_dim}")
    print({"postgres": "ok", "pgvector": extension[0], "ollama_version": client.version(), "embedding_dim": len(vector), "models": sorted(required)})


if __name__ == "__main__":
    main()
