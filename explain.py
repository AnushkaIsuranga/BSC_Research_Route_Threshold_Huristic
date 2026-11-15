import psycopg2
from src import db_settings
from src.phase_d_validation.ollama_client import OllamaClient
client = OllamaClient()
vector = client.embed('nomic-embed-text:latest', 'Test')
conn = psycopg2.connect(**db_settings())
cur = conn.cursor()
cur.execute('SET hnsw.ef_search = 40')
cur.execute('SET enable_indexscan = on')
cur.execute('SET enable_seqscan = off')
cur.execute('SET hnsw.iterative_scan = off')
cur.execute("EXPLAIN SELECT query_id FROM finqa_evidence WHERE metadata->>'ticker'='ECL' AND metadata->>'year'='2016' ORDER BY embedding <-> %s::vector LIMIT 6", (vector,))
print('\n'.join(r[0] for r in cur.fetchall()))
