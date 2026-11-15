import os
import json
import time
import psycopg2
import sys

from src.database.connection import connect_pgvector
from src.phase_a_sweep.logger import SweepLogger
from src.phase_a_sweep.explain_analyze_wrapper import run_sweep_point, measure_graph_baseline, conditions_to_where
from src.phase_a_sweep.recall_calculator import calculate_recall

def load_query_vectors(file_path, limit=5):
    vectors = []
    with open(file_path, 'r') as f:
        for i in range(limit):
            line = f.readline()
            if not line: break
            vectors.append(json.loads(line)["query"])
    return vectors

def run_targeted_sweep(sweep_name, results_file, filters_to_test, ef_values, k_values, memcap_flag, tables_to_test=None):
    print(f"--- Starting {sweep_name} ---")
    logger = SweepLogger(output_dir="outputs", results_file=results_file)
    
    with open(os.path.join("outputs", "filters_reference.json"), "r") as f:
        frozen_filters = json.load(f)
        
    target_filters = [f for f in frozen_filters if any(c[1] in filters_to_test for c in f["conditions"])]
    print(f"Loaded {len(target_filters)} target filters.")

    tests_file = os.path.join("ann-filtering-benchmark-datasets", "data", "tests.jsonl")
    query_vectors = load_query_vectors(tests_file, limit=5)

    if tables_to_test is None:
        tables = ["hm_clothes_100", "hm_clothes_75", "hm_clothes_50", "hm_clothes_25", "hm_clothes_0"]
    else:
        tables = tables_to_test
    
    completed = logger.get_completed_combinations()
    
    baselines = {}
    if os.path.exists(logger.baselines_file):
        with open(logger.baselines_file, "r") as f:
            baselines = json.load(f)

    sweep_conn = connect_pgvector()
    sweep_conn.commit()
    sweep_conn.autocommit = True
    
    truth_conn = connect_pgvector()
    truth_conn.commit()
    truth_conn.autocommit = True
    with truth_conn.cursor() as cur:
        cur.execute("SET enable_indexscan = off;")
        
    try:
        for table in tables:
            for v_idx, qv in enumerate(query_vectors):
                for k_val in k_values:
                    for ef_val in ef_values:
                        
                        # Generate baseline key
                        baseline_key = f"{table}_v{v_idx}"
                        if ef_val != 40:
                            baseline_key += f"_ef{ef_val}"
                        if k_val != 10:
                            baseline_key += f"_k{k_val}"
                        if memcap_flag:
                            baseline_key += "_memcap"
                            
                        if baseline_key in baselines:
                            baseline_ms = baselines[baseline_key]["baseline_ms"]
                        else:
                            print(f"Measuring baseline for {baseline_key}...")
                            with sweep_conn.cursor() as cur:
                                cur.execute(f"SET hnsw.ef_search = {ef_val};")
                            baseline_ms = measure_graph_baseline(sweep_conn, table, "embedding", qv, k=k_val, repeats=10)
                            logger.log_baseline(table, v_idx, ef_val, k_val, memcap_flag, baseline_ms)
                            baselines[baseline_key] = {"baseline_ms": baseline_ms}

                        for filt in target_filters:
                            filter_id = filt["filter_id"]
                            
                            if (filter_id, table, v_idx, ef_val, k_val) in completed:
                                continue
                            
                            where_clause, filter_params = conditions_to_where(filt["conditions"])
                            
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
                                with sweep_conn.cursor() as cur:
                                    cur.execute(f"SET hnsw.ef_search = {ef_val};")
                                    
                                result = run_sweep_point(
                                    conn=sweep_conn,
                                    table=table,
                                    vector_col="embedding",
                                    where_clause=where_clause,
                                    filter_params=filter_params,
                                    query_vector=qv,
                                    k=k_val,
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
                                
                                if scan_strategy == "Index Scan":
                                    try:
                                        recall = calculate_recall(
                                            truth_conn=truth_conn,
                                            sweep_conn=sweep_conn,
                                            table=table,
                                            vector_col="embedding",
                                            where_clause=where_clause,
                                            filter_params=filter_params,
                                            query_vector=qv,
                                            k=k_val,
                                            timeout_ms=30000
                                        )
                                    except Exception as re:
                                        recall_error = str(re)
                                else:
                                    filter_time_ms = None
                                    if scan_strategy in ("Bitmap Heap Scan", "Seq Scan"):
                                        recall = 1.0
                                    else:
                                        recall = None
                                        recall_error = f"Unrecognized scan strategy: {scan_strategy}"
                                    
                            except Exception as e:
                                success = False
                                error_msg = str(e)
                                
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
                                k=k_val,
                                hnsw_ef_search=ef_val,
                                planning_time_ms=planning_time_ms,
                                recall_error=recall_error
                            )
                            print(f"Logged {sweep_name} | {table} | v{v_idx} | filter:{filt['conditions'][0][1]} | ef:{ef_val} | k:{k_val} | Strategy: {scan_strategy}")
    finally:
        sweep_conn.close()
        truth_conn.close()
        print(f"--- Completed {sweep_name} ---")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python targeted_sweeps.py [item11|item12|item10]")
        sys.exit(1)
        
    mode = sys.argv[1]
    filters = ["Baby/Children", "Ladieswear", "Solid"]
    
    if mode == "item11":
        # ef_search mitigation sweep
        run_targeted_sweep(
            sweep_name="Item 11 (ef_search)", 
            results_file="mitigation_sweep_results.jsonl",
            filters_to_test=filters,
            ef_values=[40, 100, 200, 400],
            k_values=[10],
            memcap_flag=False
        )
    elif mode == "item12":
        # alternate K value check
        run_targeted_sweep(
            sweep_name="Item 12 (k=50)", 
            results_file="k_sweep_results.jsonl",
            filters_to_test=filters,
            ef_values=[40, 100, 200, 400],
            k_values=[50],
            memcap_flag=False
        )
    elif mode == "item10":
        # memory constraint spot check
        run_targeted_sweep(
            sweep_name="Item 10 (memory spot-check)", 
            results_file="memory_spot_check.jsonl",
            filters_to_test=filters,
            ef_values=[40],
            k_values=[10],
            memcap_flag=True
        )
    elif mode == "item12_ef800":
        # extreme ef_search to test fragmentation resistance
        run_targeted_sweep(
            sweep_name="Item 12b (k=50, ef=800)", 
            results_file="k_sweep_results.jsonl",
            filters_to_test=filters,
            ef_values=[800],
            k_values=[50],
            memcap_flag=False,
            tables_to_test=["hm_clothes_100"]
        )
