"""Load H&M vector data into controlled correlation-tier pgvector tables."""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
from psycopg2.extras import execute_values

from src import BENCHMARK_DATA_DIR, CORRELATION_TIERS
from src.database.connection import connect_pgvector

def create_deranged_dataset(
    original_metadata: list[dict],
    correlation_percent: int,
) -> list[dict]:
    df = pd.DataFrame(original_metadata)
    n_total = len(df)
    n_scramble = int(n_total * (1 - (correlation_percent / 100.0)))
    
    if n_scramble > 0:
        scramble_indices = np.random.choice(df.index, size=n_scramble, replace=False)
        permuted_indices = np.random.permutation(scramble_indices)
        while np.any(permuted_indices == scramble_indices) and len(scramble_indices) > 1:
            permuted_indices = np.random.permutation(scramble_indices)
        df.loc[scramble_indices] = df.loc[permuted_indices].values

    return df.to_dict('records')


def load_hm_dataset(data_dir=BENCHMARK_DATA_DIR):
    vectors_path = data_dir / "vectors.npy"
    payloads_path = data_dir / "payloads.jsonl"

    if not vectors_path.exists():
        raise FileNotFoundError(f"{vectors_path} not found. Run the dataset download step first.")

    vectors = np.load(vectors_path)
    
    target_columns = [
        "index_group_name",
        "product_type_name",
        "garment_group_name",
        "perceived_colour_master_name",
        "graphical_appearance_name"
    ]
    
    original_metadata = []
    with payloads_path.open(encoding="utf-8") as source:
        for line in source:
            payload = json.loads(line)
            metadata_bundle = {col: payload.get(col, "Unknown") for col in target_columns}
            original_metadata.append(metadata_bundle)

    return vectors, original_metadata


def ingest_hm_correlation_tables(batch_size: int = 5000) -> None:
    vectors, original_metadata = load_hm_dataset()
    tables_and_metadata = {
        f"hm_clothes_{tier}": create_deranged_dataset(
            original_metadata,
            tier,
        )
        for tier in CORRELATION_TIERS
    }

    conn = connect_pgvector()
    cur = conn.cursor()
    try:
        for table_name, metadata_list in tables_and_metadata.items():
            print(f"Starting ingestion for {table_name}...")
            # Truncate table first to be safe
            cur.execute(f"TRUNCATE TABLE {table_name};")
            
            data_batch = []
            
            # execute_values is much faster than executemany
            insert_query = f"INSERT INTO {table_name} (vector_id, index_group_name, product_type_name, garment_group_name, perceived_colour_master_name, graphical_appearance_name, embedding) VALUES %s"

            for vector_id, vector in enumerate(vectors):
                meta = metadata_list[vector_id]
                data_batch.append((
                    vector_id, 
                    meta["index_group_name"],
                    meta["product_type_name"],
                    meta["garment_group_name"],
                    meta["perceived_colour_master_name"],
                    meta["graphical_appearance_name"],
                    vector.tolist()
                ))

                if len(data_batch) >= batch_size:
                    execute_values(cur, insert_query, data_batch)
                    conn.commit()
                    data_batch = []

            if data_batch:
                execute_values(cur, insert_query, data_batch)
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
