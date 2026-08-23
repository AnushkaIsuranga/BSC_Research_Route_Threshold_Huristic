import contextlib

def fetch_top_k_ids(conn, table, vector_col, where_clause, filter_params, query_vector, k, timeout_ms=30000):
    """
    Executes the query and returns a set of the top-K returned row IDs.
    Does NOT use EXPLAIN, so we actually get the result payload.
    """
    if isinstance(query_vector, list):
        vector_str = f"[{','.join(map(str, query_vector))}]"
    else:
        vector_str = query_vector
        
    sql = f"SELECT id FROM {table} WHERE {where_clause} ORDER BY {vector_col}::halfvec(2048) <=> %s::halfvec(2048) LIMIT %s"
    full_params = tuple(filter_params) + (vector_str, k)
    
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = {timeout_ms};")
        cur.execute(sql, full_params)
        return {row[0] for row in cur.fetchall()}

def calculate_recall(truth_conn, sweep_conn, table, vector_col, where_clause, filter_params, query_vector, k=10, timeout_ms=30000):
    """
    Calculates Recall@k.
    truth_conn: Dedicated connection where enable_indexscan = off
    sweep_conn: Normal sweep connection
    """
    # 1. Fetch approximate IDs using standard connection
    try:
        approx_ids = fetch_top_k_ids(sweep_conn, table, vector_col, where_clause, filter_params, query_vector, k, timeout_ms)
    except Exception as e:
        sweep_conn.rollback()
        raise e
        
    # 2. Fetch ground truth IDs using dedicated connection
    try:
        truth_ids = fetch_top_k_ids(truth_conn, table, vector_col, where_clause, filter_params, query_vector, k, timeout_ms)
    except Exception as e:
        truth_conn.rollback()
        raise e
        
    # 3. Calculate Recall
    k_actual = len(truth_ids)
    if k_actual == 0:
        return 1.0  # Both empty -> perfect recall
        
    intersection = approx_ids & truth_ids
    return len(intersection) / k_actual

@contextlib.contextmanager
def get_truth_connection():
    """
    Helper to yield a dedicated connection for ground truth generation, ensuring
    it doesn't pollute the latency-measuring connection pool.
    """
    from src.database.connection import connect_pgvector
    conn = connect_pgvector()
    try:
        yield conn
    finally:
        conn.close()
