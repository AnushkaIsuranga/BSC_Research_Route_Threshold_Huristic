"""Load H&M vector data into controlled correlation-tier pgvector tables."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src import BENCHMARK_DATA_DIR, CORRELATION_TIERS
from src.database.connection import connect_pgvector


def create_deranged_dataset(
    original_categories: list[str],
    correlation_percent: int,
    all_unique_categories: list[str],
) -> list[str]:
    """Return categories with exactly the requested percentage unchanged."""
    df = pd.DataFrame({"original_category": original_categories})
    n_total = len(df)
    n_scramble = int(n_total * (1 - (correlation_percent / 100.0)))
    scramble_indices = np.random.choice(df.index, size=n_scramble, replace=False)

    unique_cats = set(all_unique_categories)
    scrambled_categories = []
    for idx in scramble_indices:
        original = df.loc[idx, "original_category"]
        valid_choices = list(unique_cats - {original})
        scrambled_categories.append(np.random.choice(valid_choices))

    final_categories = df["original_category"].copy()
    final_categories.loc[scramble_indices] = scrambled_categories
    return final_categories.tolist()


def load_hm_dataset(data_dir=BENCHMARK_DATA_DIR):
    vectors_path = data_dir / "vectors.npy"
    payloads_path = data_dir / "payloads.jsonl"

    if not vectors_path.exists():
        raise FileNotFoundError(f"{vectors_path} not found. Run the dataset download step first.")

    vectors = np.load(vectors_path)
    with payloads_path.open(encoding="utf-8") as source:
        payloads = [json.loads(line) for line in source]

    original_categories = [payload.get("department_name", "Unknown") for payload in payloads]
    return vectors, original_categories, sorted(set(original_categories))


def ingest_hm_correlation_tables(batch_size: int = 1000) -> None:
    vectors, original_categories, unique_categories = load_hm_dataset()
    tables_and_categories = {
        f"hm_clothes_{tier}": create_deranged_dataset(
            original_categories,
            tier,
            unique_categories,
        )
        for tier in CORRELATION_TIERS
    }

    conn = connect_pgvector()
    cur = conn.cursor()
    try:
        for table_name, categories in tables_and_categories.items():
            print(f"Starting ingestion for {table_name}...")
            data_batch = []

            for vector_id, vector in enumerate(vectors):
                data_batch.append((vector_id, categories[vector_id], vector.tolist()))

                if len(data_batch) >= batch_size:
                    cur.executemany(
                        f"INSERT INTO {table_name} (vector_id, category, embedding) VALUES (%s, %s, %s)",
                        data_batch,
                    )
                    conn.commit()
                    data_batch = []

            if data_batch:
                cur.executemany(
                    f"INSERT INTO {table_name} (vector_id, category, embedding) VALUES (%s, %s, %s)",
                    data_batch,
                )
                conn.commit()

            print(f"Ingestion for {table_name} complete.")
    finally:
        cur.close()
        conn.close()

    print("All data ingested successfully.")


def main() -> None:
    ingest_hm_correlation_tables()

if __name__ == "__main__":
    main()
