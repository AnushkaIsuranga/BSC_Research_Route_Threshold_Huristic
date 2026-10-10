import json
import csv
import time
import os
from pathlib import Path
from typing import Dict, Any

try:
    from langchain_community.callbacks import get_openai_callback
except ImportError:
    get_openai_callback = None

from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_b_router.router import (
    build_decision_matrix_graph,
    build_naive_graph,
    MockChatModel
)

import re
import math
import psycopg2
from src import db_settings

def parse_financial_number(s: str) -> float:
    s = s.replace(",", "").replace("$", "").strip()
    if not s:
        return float('nan')
        
    # Handle accounting negatives (5.2) -> -5.2
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1].strip()
        
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except:
            return float('nan')
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 2:
            try:
                return float(parts[0]) / float(parts[1])
            except:
                return float('nan')
    try:
        return float(s)
    except:
        return float('nan')

def is_match(pred: str, gold: str, rel_tol: float = 0.01) -> bool:
    p_val = parse_financial_number(pred)
    g_val = parse_financial_number(gold)
    
    if math.isnan(p_val) or math.isnan(g_val):
        # Boolean fallback
        p_clean = pred.lower().strip()
        g_clean = gold.lower().strip()
        if g_clean in ("yes", "no", "true", "false"):
            return p_clean == g_clean
        return False
        
    return math.isclose(p_val, g_val, rel_tol=rel_tol)

def get_corpus_size(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM finqa_evidence;")
        return cur.fetchone()[0]

def get_matching_rows(conn, ticker: str, year: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM finqa_evidence WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s;", (ticker, year))
        return cur.fetchone()[0]

from src.utils.finqa_utils import extract_ticker_year

def run_comparison(target_models: list = None, correlation_level: str | None = None):
    # Default models for multi-model answer generation testing
    if not target_models:
        target_models = [
            "openai/gpt-5.6-sol",
            "meta-llama/llama-3.1-8b-instruct",
            "google/gemini-3-flash"
        ]
        
    # 1. Load Data
    fp = get_frozen_filepath()
    queries = load_finqa_subset(fp)
    
    # 2. Load Thresholds
    thresholds_path = Path("outputs/thresholds.json")
    if not thresholds_path.exists():
        raise FileNotFoundError("thresholds.json not found. Run threshold_detector.py first.")
    with open(thresholds_path) as f:
        thresholds_dict = json.load(f)

    # 3. Setup LLM for Naive Router (ROUTING fixed to one model)
    ai_api_key = os.getenv("AI_API_KEY")
    ai_api_base = os.getenv("AI_API_BASE")
    if not ai_api_key:
        raise RuntimeError("AI_API_KEY is required for the API comparison runner; mock answers are disabled.")
    if not correlation_level:
        correlation_level = os.getenv("CORRELATION_LEVEL", "").strip()
    if not correlation_level:
        raise RuntimeError("correlation_level must be provided explicitly; refusing to default silently.")
    if ai_api_key:
        from langchain_openai import ChatOpenAI
        routing_llm = ChatOpenAI(
            model="openai/gpt-5.6-sol", 
            api_key=ai_api_key, 
            base_url=ai_api_base if ai_api_base else None,
            temperature=0
        )

    # 4. Build Graphs
    naive_graph = build_naive_graph(routing_llm)
    dm_graph = build_decision_matrix_graph(thresholds_dict)

    # DB Connection for Selectivity
    conn = psycopg2.connect(**db_settings())
    total_corpus_rows = get_corpus_size(conn)
    if total_corpus_rows == 0:
        raise RuntimeError("finqa_evidence table is empty. Please run finqa_db_setup.py first.")

    # 4.5 Coverage Check
    print("Running pre-flight Coverage Check...")
    with conn.cursor() as cur:
        for row in queries:
            q_id = row['id']
            keys = [k.strip() for k in row['gold_evidence_keys'].split("|") if k.strip()]
            for k in keys:
                cur.execute("SELECT 1 FROM finqa_evidence WHERE query_id = %s AND evidence_key = %s;", (q_id, k))
                if not cur.fetchone():
                    raise RuntimeError(f"Coverage Check Failed: evidence_key '{k}' for query_id '{q_id}' not found in DB!")
    print("Coverage Check passed! All gold evidence is present.")

    # 5. Execute & Compare over models
    for model_name in target_models:
        print(f"\n==========================================")
        print(f"Running validation pass with Answer Model: {model_name}")
        print(f"==========================================")
        
        # Override the AI_MODEL so router.py picks it up for the generation step
        os.environ["AI_MODEL"] = model_name
        
        results = []
        
        for row in queries:
            q_id = row['id']
            question = row['question']
            gold_answer = row['answer']
            
            ticker, year = extract_ticker_year(q_id)
            
            matching_rows = get_matching_rows(conn, ticker, year)
            estimated_sel = matching_rows / total_corpus_rows if total_corpus_rows > 0 else 0.0
            corr_level = correlation_level
            
            state_input = {
                "query_id": q_id,
                "ticker": ticker,
                "year": year,
                "gold_evidence_keys": [k.strip() for k in row['gold_evidence_keys'].split("|") if k.strip()],
                "question": question,
                "estimated_selectivity": estimated_sel,
                "correlation_level": corr_level,
                "sub_queries": []
            }

            def run_graph(graph_obj, state):
                latency = 0
                cost = 0
                route = ""
                is_correct = 0
                try:
                    start = time.time()
                    if ai_api_key and get_openai_callback:
                        with get_openai_callback() as cb:
                            res = graph_obj.invoke(dict(state)) # Defensive copy
                            if cb.total_tokens > 0 and cb.total_cost == 0.0:
                                cost = (cb.prompt_tokens / 1e6 * 0.15) + (cb.completion_tokens / 1e6 * 0.60)
                            else:
                                cost = cb.total_cost
                    else:
                        res = graph_obj.invoke(dict(state)) # Defensive copy
                        
                    latency = (time.time() - start) * 1000
                    route = res.get("chosen_route", "error")
                    final_answer = res.get("final_answer", "")
                    is_correct = 1 if is_match(final_answer, gold_answer, 0.01) else 0
                except Exception as e:
                    print(f"Error for query {q_id}: {e}")
                    route = "error"
                return route, latency, cost, is_correct

            # --- Run Naive ---
            naive_route, naive_latency, naive_cost, naive_correct = run_graph(naive_graph, state_input)

            # --- Run Decision Matrix ---
            dm_route, dm_latency, dm_cost, dm_correct = run_graph(dm_graph, state_input)

            results.append({
                "id": q_id,
                "naive_route": naive_route,
                "naive_latency_ms": naive_latency,
                "naive_cost_usd": naive_cost,
                "naive_error": 1 - naive_correct,
                "dm_route": dm_route,
                "dm_latency_ms": dm_latency,
                "dm_cost_usd": dm_cost,
                "dm_error": 1 - dm_correct
            })

        # Save Results per model
        model_safe_name = model_name.replace("/", "_")
        out_file = Path(f"outputs/phase_d_results_{model_safe_name}.csv")
        with out_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
            
        # Update manifest
        manifest_path = Path("outputs/phase_d_manifest.json")
        manifest_data = {}
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)
        manifest_data[model_safe_name] = model_name
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest_data, mf, indent=2)
        
        print(f"Executed 50 queries for {model_name}. Results saved to {out_file}.")

    conn.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", help="List of model names to test")
    parser.add_argument("--correlation-level", required=False, help="Explicit threshold-table correlation tier")
    args = parser.parse_args()
    run_comparison(target_models=args.models, correlation_level=args.correlation_level)
