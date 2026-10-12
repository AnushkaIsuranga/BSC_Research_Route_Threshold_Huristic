# LEGACY — not used in final results. built finqa_evidence (Ollama nomic-embed-text, raw text, 768-d) on 30 Sept. The final runs use finqa_evidence_qwen3, built from finqa_evidence's rows by build_finqa_embedding_table.py.
import json
import hashlib
import time
import os
from pathlib import Path

import psycopg2
from pgvector.psycopg2 import register_vector
import numpy as np

from src import db_settings, PROJECT_ROOT
from src.utils.finqa_utils import get_embedding_client, extract_ticker_year
from src.phase_d_validation.ollama_client import OllamaClient

def get_content_hash(content: str) -> str:
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def setup_finqa_db():
    print("Setting up FinQA Vector Database...")
    
    # 1. Load FinQA Dataset
    finqa_path = PROJECT_ROOT / "data" / "raw" / "finqa_test.json"
    if not finqa_path.exists():
        raise FileNotFoundError(f"Cannot find {finqa_path}")
        
    with open(finqa_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    print(f"Loaded {len(dataset)} examples from FinQA test set.")

    # 2. Extract and prepare evidence chunks
    rows_to_insert = []
    embedding_cache = {}
    unique_texts_to_embed = {} # key: (content_hash, ticker, year), value: content
    
    for example in dataset:
        q_id = example.get("id", "")
        # Extract metadata properly via helper
        ticker, year = extract_ticker_year(q_id)
        
        metadata = {"ticker": ticker, "year": year}
        
        # Helper to process an evidence block
        def process_evidence(key, content):
            if not content: return
            content_str = str(content)
            c_hash = get_content_hash(content_str)
            cache_key = (c_hash, ticker, year)
            
            if cache_key not in unique_texts_to_embed:
                unique_texts_to_embed[cache_key] = content_str
                
            rows_to_insert.append({
                "query_id": q_id,
                "evidence_key": key,
                "content": content_str,
                "metadata": metadata,
                "cache_key": cache_key
            })

        # FinQA gold evidence uses one continuous text namespace (text_0,
        # text_1, ...), followed by table_i.  Do not expose the source-list
        # names here because the Phase-D coverage check uses gold_inds keys.
        for i, text in enumerate(example.get("pre_text", [])):
            process_evidence(f"text_{i}", text)
            
        # Process post_text
        text_offset = len(example.get("pre_text", []))
        for i, text in enumerate(example.get("post_text", [])):
            process_evidence(f"text_{text_offset + i}", text)
            
        # Process table
        table_rows = example.get("table", [])
        for i, row in enumerate(table_rows):
            process_evidence(f"table_{i}", " | ".join(map(str, row)))

    print(f"Total evidence rows to insert: {len(rows_to_insert)}")
    print(f"Unique distinct texts to embed (deduplicated by content+ticker+year): {len(unique_texts_to_embed)}")

    # 3. Embed Unique Texts
    embeddings_model = get_embedding_client()
    dim = 1536 # Default fallback
    
    if embeddings_model is None and os.getenv("EMBEDDING_BACKEND", "").lower() == "ollama":
        ollama_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "").strip()
        if not ollama_model:
            raise RuntimeError("EMBEDDING_BACKEND=ollama requires OLLAMA_EMBEDDING_MODEL")
        ollama = OllamaClient()
        print(f"Generating embeddings locally via Ollama model: {ollama_model}")
        cache_items = list(unique_texts_to_embed.items())
        batch_size = 64
        for start in range(0, len(cache_items), batch_size):
            batch = cache_items[start:start + batch_size]
            vectors = ollama.embed(ollama_model, [text for _, text in batch])
            for (cache_key, _), vector in zip(batch, vectors):
                embedding_cache[cache_key] = vector
            print(f"Embedded {min(start + batch_size, len(cache_items))}/{len(cache_items)} texts", flush=True)
        if embedding_cache:
            dim = len(next(iter(embedding_cache.values())))
    elif embeddings_model is None:
        raise RuntimeError(
            "No embedding backend configured. Set OPENROUTER_API_KEY or "
            "EMBEDDING_BACKEND=ollama and OLLAMA_EMBEDDING_MODEL. Random "
            "embeddings are intentionally disabled for research evaluation."
        )
    else:
        print(f"Generating embeddings via model: {os.getenv('EMBEDDING_MODEL', 'qwen/qwen3-embedding-8b')}")
        cache_keys_list = list(unique_texts_to_embed.keys())
        texts_list = list(unique_texts_to_embed.values())
        
        if texts_list:
            test_emb = embeddings_model.embed_query(texts_list[0])
            dim = len(test_emb)
            print(f"Detected vector dimensionality: {dim}")
        
        batch_size = 500
        for i in range(0, len(texts_list), batch_size):
            batch_texts = texts_list[i:i+batch_size]
            batch_keys = cache_keys_list[i:i+batch_size]
            
            print(f"Embedding batch {i//batch_size + 1}/{(len(texts_list)//batch_size)+1}...")
            batch_embeddings = embeddings_model.embed_documents(batch_texts)
            
            for key, emb in zip(batch_keys, batch_embeddings):
                embedding_cache[key] = emb
            time.sleep(1) 

    # 4. Insert into Postgres
    print("Connecting to Database...")
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    
    with conn.cursor() as cur:
        # Create Table
        print("Creating finqa_evidence table...")
        cur.execute("DROP TABLE IF EXISTS finqa_evidence;")
        cur.execute(f"""
            CREATE TABLE finqa_evidence (
                id SERIAL PRIMARY KEY,
                query_id TEXT,
                evidence_key TEXT,
                content TEXT,
                metadata JSONB,
                embedding vector({dim})
            );
        """)
        
        # Insert Rows
        print("Inserting rows...")
        insert_query = """
            INSERT INTO finqa_evidence (query_id, evidence_key, content, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s)
        """
        
        # Batch insert
        count = 0
        for row in rows_to_insert:
            emb = embedding_cache[row["cache_key"]]
            cur.execute(insert_query, (
                row["query_id"], 
                row["evidence_key"], 
                row["content"], 
                json.dumps(row["metadata"]), 
                emb
            ))
            count += 1
            if count % 5000 == 0:
                print(f"Inserted {count} rows...")
                
        # Create HNSW Index (to be used by post-filter route)
        print("Building HNSW index on embedding...")
        cur.execute("""
            CREATE INDEX ON finqa_evidence USING hnsw (embedding vector_l2_ops)
            WITH (m = 16, ef_construction = 64);
        """)

    conn.close()
    print("FinQA Vector Database setup complete!")

if __name__ == "__main__":
    setup_finqa_db()
