import os
import json
import time
import psycopg2

from src.database.connection import connect_pgvector
from src.phase_a_sweep.logger import SweepLogger
from src.phase_a_sweep.explain_analyze_wrapper import run_sweep_point, measure_graph_baseline, conditions_to_where
from src.phase_a_sweep.recall_calculator import calculate_recall, get_truth_connection

def load_query_vectors(file_path, limit=5):
    vectors = []
    with open(file_path, 'r') as f:
        for i in range(limit):
            line = f.readline()
            if not line: break
            vectors.append(json.loads(line)["query"])
    return vectors

HNSW_EF_SEARCH = 40
K_NEIGHBORS = 10

def main(output_dir="outputs", limit_tables=None, limit_vectors=5, limit_filters=None):
    print("Initializing Selectivity Sweep Loop Orchestrator...")
    logger = SweepLogger(output_dir=output_dir)
    
    # 1. Load and Freeze Filters
    with open(os.path.join(output_dir, "filters.json"), "r") as f:
        raw_filters = json.load(f)
    if limit_filters:
        raw_filters = raw_filters[:limit_filters]
    frozen_filters = logger.freeze_filters(raw_filters)
    print(f"Loaded and frozen {len(frozen_filters)} filters.")
    
    # 2. Load Query Vectors
    tests_file = os.path.join("ann-filtering-benchmark-datasets", "data", "tests.jsonl")
    query_vectors = load_query_vectors(tests_file, limit=limit_vectors)
    print(f"Loaded {len(query_vectors)} query vectors.")
    
    # 3. Tables to test
    tables = limit_tables or [
        "hm_clothes_100",
        "hm_clothes_75",
        "hm_clothes_50",
        "hm_clothes_25",
        "hm_clothes_0"
    ]
    
    # 4. Get completed points for resumption
    completed = logger.get_completed_combinations()
    print(f"Found {len(completed)} already completed combinations.")
    
    # Pre-load baselines to avoid recomputing if we resume
    baselines = {}
    if os.path.exists(logger.baselines_file):
        with open(logger.baselines_file, "r") as f:
            baselines = json.load(f)
            
    total_combinations = len(tables) * len(query_vectors) * len(frozen_filters)
    points_completed_this_run = 0
    total_completed_overall = len(completed)
    
    start_time = time.time()
    
    # Connections setup with explicit try/finally
    sweep_conn = connect_pgvector()
    sweep_conn.commit()
    sweep_conn.autocommit = True
    
    truth_conn = connect_pgvector()
    truth_conn.commit()
    truth_conn.autocommit = True
    with truth_conn.cursor() as cur:
        cur.execute("SET enable_indexscan = off;")
    
    try:
        # Enforce ef_search at session level
        with sweep_conn.cursor() as cur:
            cur.execute(f"SET hnsw.ef_search = {HNSW_EF_SEARCH};")
            cur.execute("SET hnsw.iterative_scan = off;")
            
        for table in tables:
            for v_idx, qv in enumerate(query_vectors):
                # Check baseline cache first to prevent resume-drift
                baseline_key = f"{table}_v{v_idx}"
                if baseline_key in baselines:
                    baseline_ms = baselines[baseline_key]["baseline_ms"]
                else:
                    # Measure and log baseline
                    print(f"Measuring baseline for {table} / vector {v_idx}...")
                    baseline_ms = measure_graph_baseline(sweep_conn, table, "embedding", qv, k=K_NEIGHBORS, repeats=10)
                    logger.log_baseline(table, v_idx, HNSW_EF_SEARCH, K_NEIGHBORS, False, baseline_ms)
                    baselines[baseline_key] = {"baseline_ms": baseline_ms}
                    
                for filt in frozen_filters:
                    filter_id = filt["filter_id"]
                    
                    # Skip if already tested
                    if (filter_id, table, v_idx, HNSW_EF_SEARCH, K_NEIGHBORS) in completed:
                        continue
                        
                    where_clause, filter_params = conditions_to_where(filt["conditions"])
                    
                    # Measurement variables
                    success = False
                    error_msg = None
                    recall_error = None
                    scan_strategy = None
                    latency_ms = None
                    filter_time_ms = None
                    rows_removed = None
                    recall = None
                    index_used = None
                    planning_time_ms = None
                    
                    try:
                        # 1. Run Latency Point
                        result = run_sweep_point(
                            conn=sweep_conn,
                            table=table,
                            vector_col="embedding",
                            where_clause=where_clause,
                            filter_params=filter_params,
                            query_vector=qv,
                            k=K_NEIGHBORS,
                            graph_baseline_ms=baseline_ms,
                            repeats=5
                        )
                        
                        success = True
                        scan_strategy = result["scan_strategy"]
                        latency_ms = result["execution_time_ms"]
                        rows_removed = result["rows_removed_by_filter"]
                        index_used = result["index_used"]
                        planning_time_ms = result["planning_time_ms"]
                        filter_time_ms = result["filter_execution_time_ms"]
                        
                        # 2. Handle Recall based on strategy
                        if scan_strategy == "Index Scan":
                            # Fetch recall via exact truth connection
                            try:
                                recall = calculate_recall(
                                    truth_conn=truth_conn,
                                    sweep_conn=sweep_conn,
                                    table=table,
                                    vector_col="embedding",
                                    where_clause=where_clause,
                                    filter_params=filter_params,
                                    query_vector=qv,
                                    k=K_NEIGHBORS,
                                    timeout_ms=30000
                                )
                            except Exception as re:
                                recall_error = str(re)
                        else:
                            filter_time_ms = None
                            if scan_strategy in ("Bitmap Heap Scan", "Seq Scan"):
                                # Planner natively fell back to exact B-Tree filtering -> Recall is 1.0
                                recall = 1.0
                            else:
                                recall = None
                                recall_error = f"Unrecognized scan strategy: {scan_strategy}"
                            
                    except Exception as e:
                        success = False
                        error_msg = str(e)
                        
                    # 3. Log Result
                    logger.log_result(
                        filter_id=filter_id,
                        table=table,
                        query_vector_idx=v_idx,
                        success=success,
                        scan_strategy=scan_strategy,
                        latency_ms=latency_ms,
                        filter_time_ms=filter_time_ms,
                        rows_removed=rows_removed,
                        recall=recall,
                        error_msg=error_msg,
                        index_used=index_used,
                        k=K_NEIGHBORS,
                        hnsw_ef_search=HNSW_EF_SEARCH,
                        planning_time_ms=planning_time_ms,
                        recall_error=recall_error
                    )
                    
                    completed.add((filter_id, table, v_idx, HNSW_EF_SEARCH, K_NEIGHBORS))
                    points_completed_this_run += 1
                    total_completed_overall += 1
                    
                    # Progress Printer
                    if points_completed_this_run % 25 == 0:
                        elapsed_min = (time.time() - start_time) / 60
                        print(f"[{total_completed_overall}/{total_combinations} done] | ~{elapsed_min:.1f} min elapsed this run")
                        
    finally:
        sweep_conn.close()
        truth_conn.close()
        print(f"Sweep Orchestrator stopped. Total points logged overall: {total_completed_overall}/{total_combinations}")

if __name__ == "__main__":
    main()
