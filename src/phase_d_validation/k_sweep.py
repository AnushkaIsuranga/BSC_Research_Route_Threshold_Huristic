"""Retrieval-only k sweep over embeddings x routes (no chat/answer LLM, no paid call).

  python -m src.phase_d_validation.k_sweep --out-dir outputs/phase_d_k_sweep_<date> --embedding-cache-dir outputs/embedding_build_<date>

Embeddings: nomic_asis (table finqa_evidence, raw question, as the 12 Oct run), nomic_prefixed ("search_query: " question,
table finqa_evidence_nomic_prefixed), qwen3 (instruct-template question from the cache, table finqa_evidence_qwen3).
Routes: exact (pre-filter) and post-filter, via src.phase_b_router.router.retrieve (deterministic (distance, id) order).
k in 6, 10, 15, 20. Per (embedding, route, k), over the 50 frozen queries:
  all_gold_hit   all gold evidence keys of the query retrieved as (query_id, key) pairs  (the runner's definition)
  any_gold_hit   at least one gold pair retrieved
  content_all_gold_hit (extra diagnostic) every gold row's text appears among the retrieved texts (each passage exists as
                 several identical copies under different page ids; the model sees the same text from any copy)
  mean prompt tokens: tiktoken cl100k_base count of the exact answer prompt (system + evidence + question), then mapped to
                 qwen2.5 tokens with a linear fit calibrated on the 12 Oct run (input_tokens of 50 DM pass-1 rows, k=6).
The selection of k and embedding is not made here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import psycopg2
import tiktoken
from pgvector.psycopg2 import register_vector

from src import db_settings
from src.phase_b_router.router import ANSWER_SYSTEM, retrieve
from src.phase_d_validation.embedding_tools import ollama_embed
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.utils.finqa_utils import extract_ticker_year

EMBEDDINGS = {"nomic_asis": "finqa_evidence", "nomic_prefixed": "finqa_evidence_nomic_prefixed", "qwen3": "finqa_evidence_qwen3"}
ROUTES = ["exact", "post-filter"]
KS = [6, 10, 15, 20]
ENC = tiktoken.get_encoding("cl100k_base")


def prompt_text(rows, question):
    context = "\n".join(f"[{q}::{key}] {content}" for _, q, key, content, _ in rows)
    return f"Evidence:\n{context}\n\nQuestion: {question}"


def ntok(rows, question):
    return len(ENC.encode(ANSWER_SYSTEM)) + len(ENC.encode(prompt_text(rows, question)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--embedding-cache-dir", required=True)
    ap.add_argument("--calibration-run", default="outputs/phase_d_local_2026-10-12/results.jsonl")
    a = ap.parse_args()
    out = Path(a.out_dir)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    queries = load_finqa_subset(get_frozen_filepath())
    cache = Path(a.embedding_cache_dir)

    qvecs = {}
    asis_in = [q["question"] for q in queries]
    asis = ollama_embed("nomic-embed-text:latest", asis_in)
    (out / "query_embeddings_nomic_asis.json").write_text(json.dumps({"model": "nomic-embed-text:latest", "queries": [
        {"query_id": q["id"], "input_text": t, "input_sha256": hashlib.sha256(t.encode()).hexdigest(), "vector": v}
        for q, t, v in zip(queries, asis_in, asis)]}), encoding="utf-8")
    qvecs["nomic_asis"] = asis
    for name in ("nomic_prefixed", "qwen3"):
        d = json.loads((cache / f"query_embeddings_{name}.json").read_text(encoding="utf-8"))
        assert [x["query_id"] for x in d["queries"]] == [q["id"] for q in queries]
        for x in d["queries"]:
            assert hashlib.sha256(x["input_text"].encode()).hexdigest() == x["input_sha256"]
        qvecs[name] = [x["vector"] for x in d["queries"]]

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute("SET hnsw.ef_search = 40")

    # gold rows (text) per query, per table
    def gold_info(table):
        info = {}
        with conn.cursor() as cur:
            for q in queries:
                keys = [k.strip() for k in q["gold_evidence_keys"].split("|") if k.strip()]
                cur.execute(f"SELECT evidence_key, content FROM {table} WHERE query_id = %s AND evidence_key = ANY(%s)", (q["id"], keys))
                got = cur.fetchall()
                if len(got) != len(keys):
                    raise RuntimeError(f"{table}: gold rows for {q['id']} not all found")
                info[q["id"]] = {"pairs": {(q["id"], k) for k, _ in got}, "texts": {c for _, c in got}}
        return info

    per_query, summary, raw_for_cal = [], [], []
    for emb, table in EMBEDDINGS.items():
        gold = gold_info(table)
        for route in ROUTES:
            for k in KS:
                hit_all = hit_any = hit_txt = 0
                rows_ret, toks = [], []
                for q, vec in zip(queries, qvecs[emb]):
                    t, y = extract_ticker_year(q["id"])
                    res = retrieve(conn, route, t, y, vec, k, table)
                    rows = res["rows"]
                    got = {(r[1], r[2]) for r in rows}
                    texts = {r[3] for r in rows}
                    g = gold[q["id"]]
                    all_hit, any_hit = int(g["pairs"] <= got), int(bool(g["pairs"] & got))
                    txt_hit = int(g["texts"] <= texts)
                    nt = ntok(rows, q["question"])
                    hit_all += all_hit; hit_any += any_hit; hit_txt += txt_hit
                    rows_ret.append(len(rows)); toks.append(nt)
                    per_query.append({"embedding": emb, "route": route, "k": k, "query_id": q["id"], "all_gold_hit": all_hit,
                                      "any_gold_hit": any_hit, "content_all_gold_hit": txt_hit, "rows_returned": len(rows),
                                      "rows_fetched": res["rows_fetched"], "tie_truncated": res["tie_truncated"], "prompt_tokens_cl100k": nt,
                                      "retrieved_ids": [r[0] for r in rows]})
                    if emb == "nomic_asis" and route == "exact" and k == 6:
                        raw_for_cal.append((q["id"], nt))
                n = len(queries)
                summary.append({"embedding": emb, "route": route, "k": k, "n_queries": n, "all_gold_hit_rate": hit_all / n,
                                "all_gold_hits": hit_all, "any_gold_hit_rate": hit_any / n, "any_gold_hits": hit_any,
                                "content_all_gold_hit_rate": hit_txt / n, "mean_rows_returned": float(np.mean(rows_ret)),
                                "mean_prompt_tokens_cl100k": float(np.mean(toks))})
                print(f"{emb:15s} {route:11s} k={k:2d} all {hit_all:2d}/50 any {hit_any:2d}/50 content-all {hit_txt:2d}/50 rows {np.mean(rows_ret):.1f} tok(cl100k) {np.mean(toks):.0f}", flush=True)

    # calibration: qwen2.5 input_tokens (12 Oct run, DM arm pass 1, exact route, k=6, same evidence set) vs cl100k count
    actual = {}
    for l in open(a.calibration_run, encoding="utf-8"):
        r = json.loads(l)
        if r["pass"] == 1 and r["arm"] == "decision_matrix":
            actual[r["query_id"]] = r["input_tokens"]
    x = np.array([nt for qid, nt in raw_for_cal], float)
    yv = np.array([actual[qid] for qid, _ in raw_for_cal], float)
    slope, icpt = np.polyfit(x, yv, 1)
    r2 = float(np.corrcoef(x, yv)[0, 1] ** 2)
    resid = float(np.abs(yv - (slope * x + icpt)).mean())
    for s in summary:
        s["mean_prompt_tokens_qwen2.5_est"] = slope * s["mean_prompt_tokens_cl100k"] + icpt
    (out / "token_calibration.json").write_text(json.dumps({"fit": "qwen_input_tokens = slope * cl100k_tokens + intercept",
        "n": len(x), "slope": slope, "intercept": icpt, "r2": r2, "mean_abs_residual_tokens": resid,
        "calibration_source": a.calibration_run + " (arm decision_matrix, pass 1, input_tokens)",
        "note": "The 12 Oct evidence sets are identical to the sets retrieved here for nomic_asis/exact/k=6 only up to tie order; token counts do not depend on order."}, indent=2), encoding="utf-8")
    with (out / "per_query.jsonl").open("w", encoding="utf-8") as f:
        for r in per_query:
            f.write(json.dumps(r) + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
    print(f"calibration: qwen_tokens = {slope:.3f} * cl100k + {icpt:.1f}  (R^2 {r2:.4f}, mean abs residual {resid:.1f} tokens)")


if __name__ == "__main__":
    main()
