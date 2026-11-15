import json, psycopg2
from pathlib import Path
from src import db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.ollama_client import OllamaClient
from src.utils.finqa_utils import extract_ticker_year

def main():
    RESULTS = Path("outputs/phase_d_results_ollama_corrected.jsonl")
    queries = load_finqa_subset(get_frozen_filepath())
    client = OllamaClient()
    by_id = {}
    with RESULTS.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                by_id[r["id"]] = r

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    
    with conn.cursor() as cur:
        try:
            cur.execute("SET hnsw.iterative_scan = off")
            has_iterative = True
        except psycopg2.errors.UndefinedObject:
            has_iterative = False
    
    print(f"Has hnsw.iterative_scan parameter: {has_iterative}")

    match_a = match_b = match_c = total = 0

    for q in queries:
        qid = q["id"]
        if qid not in by_id: continue
        res = by_id[qid]
        if res.get("naive_route") != "post-filter": continue
        
        ticker, year = extract_ticker_year(qid)
        vector = client.embed("nomic-embed-text:latest", q["question"])
        
        with conn.cursor() as cur:
            cur.execute("SET hnsw.ef_search = 40")
            cur.execute("SET enable_indexscan = on")
            cur.execute("SET enable_seqscan = off")
            if has_iterative: cur.execute("SET hnsw.iterative_scan = off")
            cur.execute("SELECT metadata->>'ticker', metadata->>'year' FROM finqa_evidence ORDER BY embedding <-> %s::vector LIMIT 40", (vector,))
            top = cur.fetchall()
            passed = sum(1 for t, y in top if t == ticker and y == year)
            pred_a = min(passed, 6)
            
            if has_iterative: cur.execute("SET hnsw.iterative_scan = off")
            cur.execute("SELECT query_id FROM finqa_evidence WHERE metadata->>'ticker'=%s AND metadata->>'year'=%s ORDER BY embedding <-> %s::vector LIMIT 6", (ticker, year, vector))
            pred_b = len(cur.fetchall())
            
            if has_iterative:
                cur.execute("SET hnsw.iterative_scan = 'relaxed_order'")
                cur.execute("SELECT query_id FROM finqa_evidence WHERE metadata->>'ticker'=%s AND metadata->>'year'=%s ORDER BY embedding <-> %s::vector LIMIT 6", (ticker, year, vector))
                pred_c = len(cur.fetchall())
            else:
                pred_c = pred_b
                
        obs = int(res["naive_retrieved"])
        
        if pred_a != obs or pred_b != obs or pred_c != obs:
            print(f"[{qid}] Obs: {obs} | (a) Uncond Top40: {pred_a} | (b) Filtered (default/off): {pred_b} | (c) Filtered (iter ON): {pred_c}")
            
        if pred_a == obs: match_a += 1
        if pred_b == obs: match_b += 1
        if pred_c == obs: match_c += 1
        total += 1

    print(f"\nTotal post-filter queries: {total}")
    print(f"Matches for (a) Uncond Top40: {match_a}")
    print(f"Matches for (b) Filtered (default/off): {match_b}")
    print(f"Matches for (c) Filtered (iter ON): {match_c}")

main()
