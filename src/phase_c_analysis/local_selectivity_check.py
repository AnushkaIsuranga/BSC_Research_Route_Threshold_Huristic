# LEGACY — not used in final results. 30 Sept diagnostic of post-filter under-fill (no id tie-break).
import csv
import psycopg2
from pathlib import Path
from src import db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.utils.finqa_utils import extract_ticker_year
from src.phase_d_validation.ollama_client import OllamaClient

def main():
    fp = get_frozen_filepath()
    queries = load_finqa_subset(fp)
    
    # We will read naive_retrieved from the CSV to verify the pattern
    csv_path = Path("outputs/phase_d_results_ollama.csv")
    results_by_id = {}
    if csv_path.exists():
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Naive router might have chosen pre-filter or post-filter.
                # If post-filter, the retrieved count might have been affected by ef_search.
                if row["naive_route"] == "post-filter":
                    results_by_id[row["id"]] = int(row["naive_retrieved"])
    
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    
    client = OllamaClient()
    
    matches = 0
    total = 0
    
    for row in queries:
        qid = row["id"]
        ticker, year = extract_ticker_year(qid)
        question = row["question"]
        
        vector = client.embed("nomic-embed-text:latest", question)
        
        with conn.cursor() as cur:
            # Unfiltered top-40 neighbors (approximate nearest neighbors without metadata filter)
            cur.execute("SET enable_indexscan = on; SET enable_seqscan = off; SET hnsw.ef_search = 40;")
            cur.execute("""
                SELECT query_id, metadata->>'ticker', metadata->>'year'
                FROM finqa_evidence
                ORDER BY embedding <-> %s::vector
                LIMIT 40
            """, (vector,))
            
            top_40 = cur.fetchall()
            
            # Count how many of these 40 pass the application-level filter
            passed_filter = sum(1 for r in top_40 if r[1] == ticker and r[2] == year)
            
            naive_retrieved = results_by_id.get(qid)
            
            if naive_retrieved is not None:
                total += 1
                if passed_filter == naive_retrieved:
                    matches += 1
                print(f"Query {qid}: Unfiltered passed = {passed_filter}, Naive retrieved = {naive_retrieved}")
            
    print(f"\nPattern Check: {matches} out of {total} queries matched the expected naive_retrieved count.")
    
    conn.close()

if __name__ == "__main__":
    main()
