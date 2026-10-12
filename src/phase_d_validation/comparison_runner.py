"""Phase D FinQA comparison runner: Decision Matrix vs policy_v2 vs naive LLM router.

No mock or fallback behaviour; the only randomness is the seeded, recorded arm-order shuffle. Any failure is logged to the row and then raised (the run
stops); a failure is never replaced by a default answer, route or cost. The only recorded
non-exception outcome is a naive-router output that fails its JSON schema (route_parse_failure,
counted; that query/arm gets no retrieval and is scored wrong).

Example (local):
  python -m src.phase_d_validation.comparison_runner --model qwen2.5:7b \
      --correlation-level hm_clothes_0 --thresholds outputs/thresholds.json \
      --output-dir outputs/phase_d_local_2026-10-12 --passes 2

Paid backends additionally need --allow-paid, --budget-usd and a verified config/prices.json entry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import requests
from pgvector.psycopg2 import register_vector

from src import db_settings
from src.phase_b_router.router import (ANSWER_SYSTEM, NAIVE_ROUTER_SYSTEM, Deps, build_decision_matrix_graph,
                                       build_naive_graph, build_policy_v2_graph)
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.llm_client import BudgetExceeded, load_generation_config, make_client
from src.phase_d_validation.scoring import score_answer
from src.utils.finqa_utils import exact_selectivity, extract_ticker_year

ARM_ORDER_SEED = 20261015
ARMS = ("dm", "v2", "naive")
ARM_NAMES = {"dm": "decision_matrix", "v2": "policy_v2", "naive": "naive_llm"}
CSV_FIELDS = ["run_id", "pass", "arm", "query_id", "ticker", "year", "selectivity", "route", "router_model", "answer_model",
              "arm_order", "arm_position", "retrieved_evidence_keys", "retrieved_ids", "retrieved_distances", "rows_returned", "rows_fetched",
              "tie_truncated", "distinct_dropped", "gold_evidence_keys", "retrieval_hit", "retrieval_hit_passage", "raw_output", "parsed_answer", "gold_answer",
              "correct", "parse_failure", "route_parse_failure", "router_raw", "router_reason", "input_tokens",
              "output_tokens", "thinking_tokens", "router_input_tokens", "router_output_tokens", "cost_usd", "embed_ms",
              "db_ms", "router_ms", "generation_ms", "total_ms", "error"]


def git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout.strip()


def sha256_file(p: str | Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ollama_digest(model: str, base: str = "http://127.0.0.1:11434") -> dict:
    tags = requests.get(f"{base}/api/tags", timeout=10)
    tags.raise_for_status()
    for m in tags.json()["models"]:
        if m["name"] == model:
            ver = requests.get(f"{base}/api/version", timeout=10).json().get("version")
            return {"name": m["name"], "digest": m["digest"], "ollama_version": ver, "details": m.get("details")}
    raise RuntimeError(f"model {model!r} not installed in Ollama")


def make_embedder(model: str, base: str = "http://127.0.0.1:11434"):
    def embed(text: str) -> list:
        r = requests.post(f"{base}/api/embed", json={"model": model, "input": text}, timeout=120)
        r.raise_for_status()
        return r.json()["embeddings"][0]
    return embed


def make_cached_embedder(cache_path: str, queries: list):
    """Question -> vector from a cached query-embedding file (no API/model call; unknown question raises).
    The cache is keyed by query_id in the frozen subset order; sha256 of every input text is verified."""
    d = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    if [x["query_id"] for x in d["queries"]] != [q["id"] for q in queries]:
        raise RuntimeError("query-embedding cache does not match the query subset/order")
    table = {}
    for q, x in zip(queries, d["queries"]):
        if hashlib.sha256(x["input_text"].encode()).hexdigest() != x["input_sha256"]:
            raise RuntimeError(f"cache hash mismatch for {q['id']}")
        table[q["question"]] = x["vector"]

    def embed(text: str) -> list:
        if text not in table:
            raise KeyError("question not in the cached query embeddings; refusing to embed it on the fly")
        return table[text]
    return embed, d


def coverage_check(conn, queries, table: str = "finqa_evidence") -> None:
    with conn.cursor() as cur:
        for row in queries:
            for k in (x.strip() for x in row["gold_evidence_keys"].split("|") if x.strip()):
                cur.execute(f"SELECT 1 FROM {table} WHERE query_id = %s AND evidence_key = %s", (row["id"], k))
                if not cur.fetchone():
                    raise RuntimeError(f"coverage check failed: gold key {k!r} of {row['id']!r} not in DB")


def build_record(run_id, pass_no, arm, row, gold_keys, sel, state, total_ms, answer_model, router_model, error, arm_order=None, gold_md5=None):
    score = None
    parsed = None
    gold = row["answer"]
    route_fail = bool(state.get("route_parse_failure"))
    raw = state.get("raw_output")
    if error is None and not route_fail:
        score = score_answer(raw, gold)
        parsed = score.parsed
    retrieved = state.get("retrieved_evidence_keys")
    hit = None
    hit_passage = None
    if gold_md5 is not None and state.get("retrieved_content_md5") is not None:
        hit_passage = int(set(gold_md5) <= set(state["retrieved_content_md5"]))
    if retrieved is not None:
        hit = int(all(f"{row['id']}::{k}" in retrieved for k in gold_keys))
    rec = {
        "run_id": run_id, "pass": pass_no, "arm": ARM_NAMES[arm], "query_id": row["id"],
        "ticker": state["ticker"], "year": state["year"], "selectivity": sel, "route": state.get("chosen_route") or None,
        "router_model": router_model if arm == "naive" else None, "answer_model": answer_model,
        "arm_order": [ARM_NAMES[a] for a in arm_order] if arm_order else None,
        "arm_position": (arm_order.index(arm) + 1) if arm_order else None,
        "retrieved_evidence_keys": retrieved, "retrieved_ids": state.get("retrieved_ids"),
        "retrieved_distances": state.get("retrieved_distances"), "rows_returned": state.get("rows_returned"),
        "rows_fetched": state.get("rows_fetched"), "tie_truncated": state.get("tie_truncated"), "distinct_dropped": state.get("distinct_dropped"),
        "gold_evidence_keys": sorted(gold_keys), "retrieval_hit": hit, "retrieval_hit_passage": hit_passage,
        "raw_output": raw, "parsed_answer": parsed, "gold_answer": gold,
        # a naive-router schema failure yields no answer: scored wrong, flagged as route_parse_failure
        "correct": None if error else int(bool(score and score.correct)),
        "parse_failure": int(bool(score and score.parse_failure)), "route_parse_failure": int(route_fail),
        "router_raw": state.get("router_raw"), "router_reason": state.get("router_reason"),
        "input_tokens": state.get("gen_input_tokens"), "output_tokens": state.get("gen_output_tokens"),
        "thinking_tokens": state.get("gen_thinking_tokens"), "router_input_tokens": state.get("router_input_tokens"),
        "router_output_tokens": state.get("router_output_tokens"), "cost_usd": state.get("cost_usd"),
        "embed_ms": state.get("embed_ms"), "db_ms": state.get("db_ms"), "router_ms": state.get("router_ms"),
        "generation_ms": state.get("generation_ms"), "total_ms": total_ms, "error": error,
        "settings_used": state.get("settings_used"),
    }
    return rec


def write_csv(jsonl: Path, csv_path: Path) -> None:
    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def run(args: argparse.Namespace) -> Path:
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty; every run writes to a new folder")
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_generation_config()
    router_model = args.router_model or args.model
    arms = [a for a in args.arms.split(",")]
    if any(a not in ARMS for a in arms):
        raise SystemExit(f"--arms must be a subset of {ARMS}")

    answer_client = make_client(args.model, allow_paid=args.allow_paid, budget_usd=args.budget_usd, config=cfg)
    router_client = answer_client if router_model == args.model else make_client(
        router_model, allow_paid=args.allow_paid, budget_usd=args.budget_usd, config=cfg)

    subset = Path(args.subset) if args.subset else get_frozen_filepath()
    queries = load_finqa_subset(subset)
    if args.query_ids:
        wanted = args.query_ids.split(",")
        queries = [q for q in queries if q["id"] in wanted]
        if len(queries) != len(wanted):
            raise SystemExit("some --query-ids not in the frozen subset")
    elif args.limit:
        queries = queries[: args.limit]
    thresholds = json.loads(Path(args.thresholds).read_text(encoding="utf-8")) if "dm" in arms else None

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute(f"SET hnsw.ef_search = {int(cfg['retrieval']['ef_search'])}")
        cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT (metadata->>'ticker')||'/'||(metadata->>'year')) FROM {args.table}")
        rows_total, groups = cur.fetchone()
    if args.expect_rows is not None and rows_total != args.expect_rows:
        raise SystemExit(f"{args.table} has {rows_total} rows, expected {args.expect_rows}")
    coverage_check(conn, queries, args.table)

    embed_cfg = cfg["embedding"]
    cache_meta = None
    if args.query_embeddings:
        embed_fn, cache_meta = make_cached_embedder(args.query_embeddings, queries)
        cache_meta = {"path": args.query_embeddings, "sha256": sha256_file(args.query_embeddings), "model": cache_meta.get("model"),
                      "dimension": cache_meta.get("dimension")}
    else:
        embed_fn = make_embedder(embed_cfg["model"])
    k = args.k or cfg["retrieval"]["k"]
    gold_md5_by_q = {}
    with conn.cursor() as cur:
        for qrow in queries:
            gk = [x.strip() for x in qrow["gold_evidence_keys"].split("|") if x.strip()]
            cur.execute(f"SELECT md5(content) FROM {args.table} WHERE query_id = %s AND evidence_key = ANY(%s)", (qrow["id"], gk))
            gold_md5_by_q[qrow["id"]] = [r[0] for r in cur.fetchall()]
    deps = Deps(conn, embed_fn, router_client, answer_client, k,
                cfg["roles"]["router_max_output_tokens"], cfg["roles"]["answer_max_output_tokens"], args.table, args.distinct)
    graphs = {}
    if "dm" in arms:
        graphs["dm"] = build_decision_matrix_graph(thresholds, deps)
    if "v2" in arms:
        graphs["v2"] = build_policy_v2_graph(deps)
    if "naive" in arms:
        graphs["naive"] = build_naive_graph(deps)

    # Untimed warm-up (loads the local model / embedder into memory) so the first logged row is not a cold start.
    # Not written to results.jsonl; recorded in run_meta.json. Skipped for paid backends (no cold-load effect worth paying for).
    warmup = None
    if answer_client.backend == "ollama":
        w0 = time.perf_counter()
        if not args.query_embeddings:
            deps.embed("warm-up")
        answer_client.generate("Reply with the single word OK.", "warm-up", max_output_tokens=8)
        if router_client is not answer_client:
            router_client.generate("Reply with the single word OK.", "warm-up", max_output_tokens=8)
        warmup = {"seconds": time.perf_counter() - w0}

    run_id = out.name
    used = ["src/phase_b_router/policy.py", "src/phase_b_router/policy_v2.py", "src/phase_b_router/router.py",
            "src/phase_d_validation/comparison_runner.py", "src/phase_d_validation/llm_client.py",
            "src/phase_d_validation/scoring.py", "config/generation.json", "config/policy_v2.json", str(subset)]
    if thresholds is not None:
        used.append(args.thresholds)
    dirty = git("status", "--porcelain", "--", *[u for u in used if not u.startswith("outputs")])
    meta = {
        "run_id": run_id, "argv": sys.argv, "commit": git("rev-parse", "HEAD"), "uncommitted_used_files": dirty or None,
        "start_utc": datetime.now(timezone.utc).isoformat(), "end_utc": None, "host": platform.platform(),
        "python": sys.version, "answer_model": args.model, "router_model": router_model, "arms": arms, "passes": args.passes,
        "backend": answer_client.backend, "ollama": ollama_digest(args.model) if answer_client.backend == "ollama" else None,
        "embedding_model": None if args.query_embeddings else ollama_digest(embed_cfg["model"]),
        "evidence_table": args.table, "k": k, "distinct": args.distinct, "query_embedding_cache": cache_meta, "generation_config": cfg,
        "answer_system_prompt": ANSWER_SYSTEM, "naive_router_system_prompt": NAIVE_ROUTER_SYSTEM,
        "finqa_rows": rows_total, "finqa_ticker_year_groups": groups, "n_queries": len(queries),
        "correlation_level": args.correlation_level, "warmup": warmup,
        "arm_order": f"per (pass, query): arms shuffled with random.Random('{ARM_ORDER_SEED}|pass|query_id'); order recorded in every row",
        "file_sha256": {u: sha256_file(u) for u in used},
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    jsonl = out / "results.jsonl"
    try:
        with jsonl.open("w", encoding="utf-8") as fh:
            for pass_no in range(1, args.passes + 1):
                for qi, row in enumerate(queries, 1):
                    qid = row["id"]
                    gold_keys = {k.strip() for k in row["gold_evidence_keys"].split("|") if k.strip()}
                    ticker, year = extract_ticker_year(qid)
                    sel, _, _ = exact_selectivity(conn, ticker, year)
                    order = arms[:]
                    random.Random(f"{ARM_ORDER_SEED}|{pass_no}|{qid}").shuffle(order)  # seeded, deterministic, recorded per row
                    for arm in order:
                        state = {"query_id": qid, "ticker": ticker, "year": year, "question": row["question"],
                                 "gold_evidence_keys": sorted(gold_keys), "estimated_selectivity": sel,
                                 "correlation_level": args.correlation_level or ""}
                        err, final = None, dict(state)
                        t0 = time.perf_counter()
                        try:
                            final.update(graphs[arm].invoke(dict(state)))
                        except Exception as exc:  # logged to the row, then re-raised below: no default substitution
                            err = f"{type(exc).__name__}: {exc}"
                        total_ms = (time.perf_counter() - t0) * 1000
                        rec = build_record(run_id, pass_no, arm, row, gold_keys, sel, final, total_ms, args.model,
                                           router_model, err, order, gold_md5_by_q[qid])
                        rec["cumulative_cost_usd"] = answer_client.spent_usd + (
                            router_client.spent_usd if router_client is not answer_client else 0.0)
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        fh.flush()
                        if err:
                            (out / "error.log").write_text(err + "\n" + traceback.format_exc(), encoding="utf-8")
                            raise RuntimeError(f"stopped: pass {pass_no} {qid} arm {arm}: {err}")
                        print(f"[pass {pass_no} {qi}/{len(queries)}] {arm:5s} {qid} route={rec['route']} correct={rec['correct']}")
    finally:
        meta["end_utc"] = datetime.now(timezone.utc).isoformat()
        (out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        if jsonl.exists():
            write_csv(jsonl, out / "results.csv")
        conn.close()
    return jsonl


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True, help="answer model (a key of config/generation.json)")
    p.add_argument("--router-model", default=None, help="naive-router model; default = --model")
    p.add_argument("--arms", default="dm,v2,naive")
    p.add_argument("--correlation-level", default=None, help="threshold-table tier for the Decision Matrix arm (required with dm)")
    p.add_argument("--thresholds", default="outputs/thresholds.json")
    p.add_argument("--subset", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--query-ids", default=None, help="comma-separated ids (smoke tests)")
    p.add_argument("--passes", type=int, default=1)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--expect-rows", type=int, default=None)
    p.add_argument("--table", default="finqa_evidence", help="evidence table (Amendment 1: finqa_evidence_qwen3)")
    p.add_argument("--query-embeddings", default=None, help="cached query-embedding JSON; if given, no embedding model is called")
    p.add_argument("--distinct", action="store_true", help="retrieve k distinct passages (dedupe by md5(content))")
    p.add_argument("--k", type=int, default=None, help="override config retrieval.k")
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--budget-usd", type=float, default=None)
    args = p.parse_args()
    if "dm" in args.arms.split(",") and not args.correlation_level:
        p.error("--correlation-level is required when the dm arm is run (no silent default)")
    try:
        print(f"Saved results to {run(args)}")
    except BudgetExceeded as exc:
        raise SystemExit(f"ABORTED (budget): {exc}")


if __name__ == "__main__":
    main()
