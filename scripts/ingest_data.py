import psycopg2
import numpy as np
import json
import pandas as pd
from pgvector.psycopg2 import register_vector
import os

# 1. Connect to PostgreSQL
conn = psycopg2.connect(
    dbname="vector_db",
    user="postgres",
    password="mysecretpassword",
    host="127.0.0.1",
    port="5433"
)
register_vector(conn)
cur = conn.cursor()

def create_deranged_dataset(original_categories, correlation_percent, all_unique_categories):
    """
    Guarantees exactly X% correlation by explicitly forcing a derangement (no accidental matches)
    on the randomized portion of the dataset.
    """
    df = pd.DataFrame({'original_category': original_categories})
    n_total = len(df)
    n_scramble = int(n_total * (1 - (correlation_percent / 100.0)))
    
    # 1. Randomly select the indices to scramble
    # We use numpy's random.choice without replacement
    scramble_indices = np.random.choice(df.index, size=n_scramble, replace=False)
    
    # 2. For each row we are scrambling, explicitly pick from ALL categories EXCEPT the original one
    scrambled_categories = []
    # Pre-compute to speed up
    unique_cats = set(all_unique_categories)
    for idx in scramble_indices:
        orig = df.loc[idx, 'original_category']
        # Remove the original category from the valid choices
        valid_choices = list(unique_cats - {orig})
        # Pick a random one from the valid choices
        new_cat = np.random.choice(valid_choices)
        scrambled_categories.append(new_cat)
        
    # 3. Create the final category list
    final_categories = df['original_category'].copy()
    final_categories.loc[scramble_indices] = scrambled_categories
    
    return final_categories.tolist()

# 2. Load the Qdrant H&M Dataset
print("Loading dataset...")
data_dir = os.path.join("ann-filtering-benchmark-datasets", "data")
vectors_path = os.path.join(data_dir, 'vectors.npy')
payloads_path = os.path.join(data_dir, 'payloads.jsonl')

if not os.path.exists(vectors_path):
    print(f"Error: {vectors_path} not found.")
    exit(1)

vectors = np.load(vectors_path) 

with open(payloads_path, 'r') as f:
    payloads = [json.loads(line) for line in f]

# Extract base categories
original_categories = [p.get('department_name', 'Unknown') for p in payloads]
all_unique_categories = list(set(original_categories))
print(f"Loaded {len(vectors)} vectors and payloads.")
print(f"Found {len(all_unique_categories)} unique categories.")

# Generate the scrambled datasets
print("Generating scrambled datasets (derangement logic)...")
categories_100 = create_deranged_dataset(original_categories, 100, all_unique_categories)
categories_75 = create_deranged_dataset(original_categories, 75, all_unique_categories)
categories_50 = create_deranged_dataset(original_categories, 50, all_unique_categories)
categories_25 = create_deranged_dataset(original_categories, 25, all_unique_categories)
categories_0 = create_deranged_dataset(original_categories, 0, all_unique_categories)

tables_and_categories = {
    "hm_clothes_100": categories_100,
    "hm_clothes_75": categories_75,
    "hm_clothes_50": categories_50,
    "hm_clothes_25": categories_25,
    "hm_clothes_0": categories_0
}

# 3. Batch Insert into PostgreSQL
batch_size = 1000

for table_name, categories in tables_and_categories.items():
    print(f"Starting ingestion for {table_name}...")
    data_batch = []
    
    for i in range(len(vectors)):
        vec = vectors[i].tolist()
        category = categories[i]
        
        data_batch.append((i, category, vec))
        
        if len(data_batch) >= batch_size:
            # We use string formatting for table name, which is safe here as it's hardcoded
            cur.executemany(
                f"INSERT INTO {table_name} (vector_id, category, embedding) VALUES (%s, %s, %s)", 
                data_batch
            )
            conn.commit()
            data_batch = []
            
    # Insert remaining
    if data_batch:
        cur.executemany(
            f"INSERT INTO {table_name} (vector_id, category, embedding) VALUES (%s, %s, %s)", 
            data_batch
        )
        conn.commit()
        
    print(f"Ingestion for {table_name} complete.")

print("All Data Ingested Successfully.")
cur.close()
conn.close()
