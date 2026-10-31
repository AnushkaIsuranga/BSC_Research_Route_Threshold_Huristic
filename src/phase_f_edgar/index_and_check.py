"""Task 3 (Phase F): normalisation check, indexes, ANALYZE, extended statistics and table checks for edgar_chunks.

  python -m src.phase_f_edgar.index_and_check --chunks outputs/edgar_chunks_2026-10-31/chunks.jsonl \
      --out-dir outputs/edgar_index_2026-10-31 --allow-paid --budget-usd 0.01

1. Stops if any row has no embedding, or if any embedding's L2 norm differs from 1 by more than 1e-3 (before indexing).
2. embedding SET NOT NULL; HNSW (embedding vector_l2_ops) m = 16, ef_construction = 64 (as finqa_evidence_qwen3);
   B-tree on cik, fiscal_year, section; CREATE STATISTICS (dependencies, mcv) on (fiscal_year, section) and (cik, fiscal_year);
   ANALYZE; pg_stats must have rows for cik, fiscal_year and section.
3. Checks: row count vs chunks.jsonl, zero vectors, dimension mismatches, 5 self-retrieval checks (re-embed 5 seeded chunks
   with the same settings -> exact top-1 must have the same text_hash; paid, needs --allow-paid), 10 seeded chunks printed.
Writes checks.json and spot_check_chunks.md. Touches no other table.
"""

from __future__ import annotations

import argparse
import json
import random
import time

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.embedding_tools import OpenRouterEmbedder
from src.phase_f_edgar import common as C

T = C.TABLE
NORM_TOL = 1e-3
MAINTENANCE_WORK_MEM = "512MB"


def q(cur, sql, args=None):
    cur.execute(sql, args)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--budget-usd", type=float, default=0.01)
    a = ap.parse_args()
    if not a.allow_paid:
        raise SystemExit("the self-retrieval check re-embeds 5 chunks (paid): needs --allow-paid")
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    n_expected = sum(1 for _ in open(PROJECT_ROOT / a.chunks, encoding="utf-8"))
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    cur = conn.cursor()
    res = {"table": T}

    # ---- 1. completeness and normalisation (before any index)
    (n_rows, n_null, nmin, nmax, n_off), = q(cur, f"""SELECT count(*), count(*) FILTER (WHERE embedding IS NULL),
        min(vector_norm(embedding)), max(vector_norm(embedding)),
        count(*) FILTER (WHERE abs(vector_norm(embedding) - 1) > {NORM_TOL}) FROM {T}""")
    res["normalisation"] = {"rows": n_rows, "rows_without_embedding": n_null, "norm_min": nmin, "norm_max": nmax,
                            f"rows_with_abs_norm_minus_1_gt_{NORM_TOL}": n_off, "unit_normalised": n_null == 0 and n_off == 0}
    if n_null or n_off:
        (out / "checks.json").write_text(json.dumps(res, indent=1), encoding="utf-8", newline="\n")
        raise SystemExit(f"stopping before indexing: {n_null} rows without embedding, {n_off} rows not unit-normalised")

    # ---- 2. indexes and statistics
    timings = {}
    cur.execute(f"ALTER TABLE {T} ALTER COLUMN embedding SET NOT NULL")
    cur.execute(f"SET maintenance_work_mem = '{MAINTENANCE_WORK_MEM}'")
    for name, sql in [
        ("hnsw", f"CREATE INDEX {T}_embedding_idx ON {T} USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64)"),
        ("btree_cik", f"CREATE INDEX {T}_cik_idx ON {T} (cik)"),
        ("btree_fiscal_year", f"CREATE INDEX {T}_fiscal_year_idx ON {T} (fiscal_year)"),
        ("btree_section", f"CREATE INDEX {T}_section_idx ON {T} (section)"),
        ("stats_year_section", f"CREATE STATISTICS {T}_year_section_stats (dependencies, mcv) ON fiscal_year, section FROM {T}"),
        ("stats_cik_year", f"CREATE STATISTICS {T}_cik_year_stats (dependencies, mcv) ON cik, fiscal_year FROM {T}"),
        ("analyze", f"ANALYZE {T}"),
    ]:
        t0 = time.perf_counter()
        cur.execute(sql)
        timings[name] = round(time.perf_counter() - t0, 1)
        print(f"{name}: {timings[name]} s", flush=True)
    res["build"] = {"maintenance_work_mem": MAINTENANCE_WORK_MEM, "seconds": timings,
                    "indexes": [r[0] for r in q(cur, "SELECT indexdef FROM pg_indexes WHERE tablename = %s ORDER BY indexname", (T,))]}
    stats = q(cur, """SELECT attname, null_frac, n_distinct, coalesce(array_length(most_common_vals::text::text[], 1), 0)
                      FROM pg_stats WHERE tablename = %s AND attname IN ('cik', 'fiscal_year', 'section') ORDER BY attname""", (T,))
    res["pg_stats"] = [{"attname": s[0], "null_frac": s[1], "n_distinct": s[2], "n_most_common_vals": s[3]} for s in stats]
    res["pg_stats_ok"] = {s[0] for s in stats} == {"cik", "fiscal_year", "section"}
    res["extended_statistics"] = [{"name": r[0], "kinds": r[1], "has_dependencies": r[2], "has_mcv": r[3]} for r in q(cur, """
        SELECT s.stxname, s.stxkind::text, d.stxddependencies IS NOT NULL, d.stxdmcv IS NOT NULL
        FROM pg_statistic_ext s JOIN pg_statistic_ext_data d ON d.stxoid = s.oid
        WHERE s.stxrelid = %s::regclass ORDER BY s.stxname""", (T,))]
    res["reltuples"] = q(cur, "SELECT reltuples FROM pg_class WHERE oid = %s::regclass", (T,))[0][0]

    # ---- 3. checks
    (zero,), = q(cur, f"SELECT count(*) FROM {T} WHERE vector_norm(embedding) = 0")
    (bad_dim,), = q(cur, f"SELECT count(*) FROM {T} WHERE vector_dims(embedding) <> {C.EMBED_DIM}")
    (dup_rows,), = q(cur, f"SELECT count(*) - count(DISTINCT (cik, fiscal_year, section, chunk_index)) FROM {T}")
    (hash_mismatch,), = q(cur, f"SELECT count(*) FROM {T} WHERE encode(sha256(convert_to(text, 'UTF8')), 'hex') <> text_hash")
    res["checks"] = {"rows": n_rows, "rows_expected_from_chunks_jsonl": n_expected, "zero_vectors": zero, "dimension_mismatches": bad_dim,
                     "duplicate_keys": dup_rows, "text_hash_mismatches": hash_mismatch}

    ids = sorted(random.Random(C.SEED).sample(range(1, n_rows + 1), 5))
    client = OpenRouterEmbedder(C.EMBED_MODEL, out / "api_calls_self_retrieval.jsonl", a.budget_usd, dimensions=C.EMBED_DIM)
    detail = []
    for i in ids:
        (txt, h), = q(cur, f"SELECT text, text_hash FROM {T} WHERE id = %s", (i,))
        qv = np.asarray(client.embed([txt], "self-retrieval check (document, no prefix)")[0], dtype=np.float32)
        cur.execute("BEGIN")
        cur.execute("SET LOCAL enable_indexscan = off")
        (tid, th, d), = q(cur, f"SELECT id, text_hash, embedding <-> %s AS d FROM {T} ORDER BY d, id LIMIT 1", (qv,))
        cur.execute("COMMIT")
        detail.append({"row_id": i, "top1_id": tid, "top1_same_text_hash": th == h, "distance": float(d)})
    res["self_retrieval"] = {"passed": sum(x["top1_same_text_hash"] for x in detail), "of": 5, "detail": detail,
                             "cost_usd": client.spent, "tokens": client.tokens}

    spot = sorted(random.Random(f"{C.SEED}-spot").sample(range(1, n_rows + 1), 10))
    lines = ["# edgar_chunks: 10 seeded chunks for spot-checking", "", f"Seed \"{C.SEED}-spot\"; ids {spot}.", ""]
    res["spot_check_ids"] = spot
    for i in spot:
        (cik, name, fy, sec, ci, txt, h), = q(cur, f"SELECT cik, company_name, fiscal_year, section, chunk_index, text, text_hash FROM {T} WHERE id = %s", (i,))
        lines += [f"## id {i}: cik {cik}, company_name {name!r}, fiscal_year {fy}, section {sec}, chunk_index {ci}",
                  f"text_hash `{h[:16]}...`, {len(txt)} characters", "", "```text", txt, "```", ""]
    (out / "spot_check_chunks.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    ok = (res["pg_stats_ok"] and n_rows == n_expected and zero == 0 and bad_dim == 0 and dup_rows == 0 and hash_mismatch == 0
          and res["self_retrieval"]["passed"] == 5)
    res["passed"] = ok
    (out / "checks.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in res.items() if k != "spot_check_ids"}, indent=1, default=str))
    if not ok:
        raise SystemExit("CHECKS FAILED")


if __name__ == "__main__":
    main()
