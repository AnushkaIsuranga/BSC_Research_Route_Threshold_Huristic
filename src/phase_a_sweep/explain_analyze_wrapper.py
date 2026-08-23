import json
import statistics

SCAN_NODE_TYPES = {"Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Bitmap Index Scan"}

def run_explain_analyze(conn, query_sql, params=None, timeout_ms=30000):
    """Runs EXPLAIN (ANALYZE, FORMAT JSON, BUFFERS) and returns the parsed plan dict."""
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = {timeout_ms};")  # guard against pathological seq scans
        cur.execute("SET jit = off;")  # JIT compilation adds timing noise on ad-hoc queries
        explain_sql = f"EXPLAIN (ANALYZE, FORMAT JSON, BUFFERS, TIMING) {query_sql}"
        cur.execute(explain_sql, params)
        result = cur.fetchone()[0]  # returns a list containing one dict
    return result[0]  # {"Plan": {...}, "Planning Time": ..., "Execution Time": ...}

def find_scan_node(plan_node):
    """DFS through the plan tree for the first scan-type node."""
    if plan_node.get("Node Type") in SCAN_NODE_TYPES:
        node = plan_node
        # Bitmap Heap Scan doesn't carry its own Index Name — that lives on
        # its Bitmap Index Scan child. Pull it up so index_used isn't always null.
        if node["Node Type"] == "Bitmap Heap Scan":
            for child in node.get("Plans", []):
                if child.get("Node Type") == "Bitmap Index Scan":
                    node = dict(node)  # don't mutate the original plan dict
                    node["Index Name"] = child.get("Index Name")
                    break
        return node
    for child in plan_node.get("Plans", []):
        found = find_scan_node(child)
        if found:
            return found
    return None

def parse_query_metrics(explain_output, graph_baseline_ms=None):
    top_plan = explain_output["Plan"]
    execution_time_ms = explain_output["Execution Time"]
    planning_time_ms = explain_output.get("Planning Time", 0)

    scan_node = find_scan_node(top_plan)
    scan_strategy = scan_node.get("Node Type") if scan_node else "Unknown"
    index_used = scan_node.get("Index Name") if scan_node else None
    rows_removed = scan_node.get("Rows Removed by Filter", 0) if scan_node else 0

    filter_time_ms = None
    if graph_baseline_ms is not None and scan_strategy == "Index Scan":
        filter_time_ms = max(0, execution_time_ms - graph_baseline_ms)

    return {
        "execution_time_ms": execution_time_ms,
        "planning_time_ms": planning_time_ms,
        "graph_traversal_time_ms": graph_baseline_ms,
        "filter_execution_time_ms": filter_time_ms,
        "scan_strategy": scan_strategy,
        "index_used": index_used,
        "rows_removed_by_filter": rows_removed,
    }

def measure_graph_baseline(conn, table, vector_col, query_vector, k=10, repeats=5):
    """Unfiltered ANN search timing. Doesn't depend on the filter, so measure
    once per table (with a few repeats for noise), not once per filter."""
    sql = f"SELECT id FROM {table} ORDER BY ({vector_col}::halfvec(2048)) <=> %s::halfvec(2048) LIMIT %s"
    times = []
    
    # format query_vector if it's a list
    if isinstance(query_vector, list):
        vector_str = f"[{','.join(map(str, query_vector))}]"
    else:
        vector_str = query_vector

    # warmup
    try:
        run_explain_analyze(conn, sql, (vector_str, k))
    except Exception as e:
        print(f"Warmup baseline failed: {e}")
        conn.rollback()

    for _ in range(repeats):
        try:
            result = run_explain_analyze(conn, sql, (vector_str, k))
            times.append(result["Execution Time"])
        except Exception as e:
            print(f"Repeat baseline failed: {e}")
            conn.rollback()
            
    if not times:
        raise RuntimeError(f"All {repeats} baseline measurement attempts failed for table {table}")
    return statistics.median(times)

def run_sweep_point(conn, table, vector_col, where_clause, filter_params,
                     query_vector, k, graph_baseline_ms, repeats=5):
    sql = f"SELECT id FROM {table} WHERE {where_clause} ORDER BY ({vector_col}::halfvec(2048)) <=> %s::halfvec(2048) LIMIT %s"
    
    if isinstance(query_vector, list):
        vector_str = f"[{','.join(map(str, query_vector))}]"
    else:
        vector_str = query_vector

    full_params = tuple(filter_params) + (vector_str, k)

    try:
        run_explain_analyze(conn, sql, full_params)  # warmup
    except Exception as e:
        conn.rollback()

    runs = []
    errors = []
    for i in range(repeats):
        try:
            explain_out = run_explain_analyze(conn, sql, full_params)
            runs.append(parse_query_metrics(explain_out, graph_baseline_ms))
        except Exception as e:
            errors.append(str(e))
            conn.rollback()
            continue

    if not runs:
        return {"error": "; ".join(errors), "execution_time_ms": None, "failed_repeats": repeats}

    # Take the FULL RECORD from the median-latency run
    runs_sorted = sorted(runs, key=lambda r: r["execution_time_ms"])
    result = runs_sorted[len(runs_sorted) // 2]
    result["failed_repeats"] = len(errors)
    return result

def conditions_to_where(conditions):
    where_clause = " AND ".join(f"{col} = %s" for col, _ in conditions)
    params = [val for _, val in conditions]
    return where_clause, params

def load_query_vectors(file_path, limit=None):
    vectors = []
    with open(file_path, 'r') as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            data = json.loads(line)
            vectors.append(data['query'])
    return vectors
