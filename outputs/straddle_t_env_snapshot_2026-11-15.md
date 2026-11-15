# Straddle-T Pre-Run Environment Snapshot (2026-11-15)

- **Captured (UTC):** 2026-11-15T12:01:32.186833+00:00
- **Git HEAD:** 3a20691ced99129e74eca4cd7daa93f3bee5540b
- **PostgreSQL:** PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit
- **pgvector:** 0.8.3
- **Python:** 3.11.9 on Windows-10-10.0.26320-SP0 (12 logical cores, RAM=16366764032)

## Key GUCs
- shared_buffers: 128MB
- effective_cache_size: 4GB
- work_mem: 4MB
- maintenance_work_mem: 64MB
- max_parallel_workers_per_gather: 2
- jit: on
- random_page_cost: 4
- seq_page_cost: 1
- cpu_tuple_cost: 0.01
- default_statistics_target: 100
- hnsw.ef_search: None
- hnsw.iterative_scan: None
- hnsw.max_scan_tuples: None

## Tables
- edgar_chunks: 158308 rows (reltuples=158278.0, relpages=38436, 2482503680 B), pg_stats=['chunk_index', 'cik', 'company_name', 'embedding', 'fiscal_year', 'id', 'section', 'text', 'text_hash'], id_sha256=cb7214cbb830faa7...
- finqa_evidence: 35862 rows (reltuples=35862.0, relpages=1105, 218701824 B), pg_stats=['content', 'embedding', 'evidence_key', 'id', 'metadata', 'query_id'], id_sha256=6c5e7388b9d71c82...
- finqa_evidence_qwen3: 35862 rows (reltuples=35873.0, relpages=1105, 315236352 B), pg_stats=['content', 'embedding', 'evidence_key', 'id', 'metadata', 'query_id'], id_sha256=6c5e7388b9d71c82...
