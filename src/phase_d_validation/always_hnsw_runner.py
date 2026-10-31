"""Phase D Amendment 10: always_hnsw answer arm (+ 1-pass policy_v2 drift reference) on the frozen 50 FinQA questions.

Settings as the frozen Gemini run (outputs/phase_d_gemini_full_2026-10-12): table finqa_evidence_qwen3, cached Qwen3 query
embeddings, hnsw.ef_search 40, k = 15 distinct, Gemini 3.8 Flash per config/generation.json. always_hnsw = router.retrieve
route "post-filter" for every question (no guard, no fallback). The 300 items are shuffled together with
random.Random(20261031). Record building and scoring reuse comparison_runner.build_record. Any error stops the run
(errors.jsonl); --resume continues it with unchanged settings.

  python -m src.phase_d_validation.always_hnsw_runner --pilot --allow-paid --budget-usd 0.10 --output-dir <dir>
  python -m src.phase_d_validation.always_hnsw_runner --allow-paid --budget-usd 1.40 --output-dir <dir> [--resume]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from pgvector.psycopg2 import register_vector

from src import db_settings
from src.phase_b_router.router import ANSWER_SYSTEM, Deps, _deterministic_graph, build_policy_v2_graph
from src.phase_d_validation import comparison_runner as CR
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.llm_client import load_generation_config, make_client
from src.phase_e_router.cells import host_load
from src.utils.finqa_utils import exact_selectivity, extract_ticker_year

MODEL = "gemini-3.8-flash"
TABLE = "finqa_evidence_qwen3"
QUERY_CACHE = "outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json"
EXPECT_ROWS = 35862
K, DISTINCT = 15, True
SEED = 20261031
PILOT_SEED = "20261031-pilot"
PILOT_N = 5
HNSW_PASSES = 5
ARM_HNSW, ARM_V2 = "always_hnsw", "policy_v2"


def schedule(query_ids, pilot=False):
    """[(pass, query_id, arm)]: pilot = always_hnsw pass 1 on 5 drawn questions; full = always_hnsw x 5 passes +
    policy_v2 x 1 pass, all 300 items shuffled together."""
    ids = sorted(query_ids)
    if pilot:
        return [(1, q, ARM_HNSW) for q in random.Random(PILOT_SEED).sample(ids, PILOT_N)]
    items = [(p, q, ARM_HNSW) for p in range(1, HNSW_PASSES + 1) for q in ids] + [(1, q, ARM_V2) for q in ids]
    random.Random(SEED).shuffle(items)
    return items


def build_always_hnsw_graph(deps):
    return _deterministic_graph(deps, lambda s: "post-filter", {"post-filter": "post-filter"})


def run(args):
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()) and not args.resume:
        raise SystemExit(f"{out} exists and is not empty (use --resume)")
    if args.resume and not (out / "run_meta.json").exists():
        raise SystemExit("--resume: run_meta.json not found")
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_generation_config()
    client = make_client(MODEL, allow_paid=args.allow_paid, budget_usd=args.budget_usd, config=cfg)
    subset = get_frozen_filepath()
    queries = {q["id"]: q for q in load_finqa_subset(subset)}
    items = schedule(queries, pilot=args.pilot)

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute(f"SET hnsw.ef_search = {int(cfg['retrieval']['ef_search'])}")
        cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
        if cur.fetchone()[0] != EXPECT_ROWS:
            raise SystemExit(f"{TABLE} row count differs from {EXPECT_ROWS}")
    qlist = list(queries.values())
    CR.coverage_check(conn, qlist, TABLE)
    embed_fn, cache = CR.make_cached_embedder(QUERY_CACHE, qlist)
    gold_md5 = {}
    with conn.cursor() as cur:
        for q in qlist:
            gk = [x.strip() for x in q["gold_evidence_keys"].split("|") if x.strip()]
            cur.execute(f"SELECT md5(content) FROM {TABLE} WHERE query_id = %s AND evidence_key = ANY(%s)", (q["id"], gk))
            gold_md5[q["id"]] = [r[0] for r in cur.fetchall()]
    deps = Deps(conn, embed_fn, client, client, K, cfg["roles"]["router_max_output_tokens"],
                cfg["roles"]["answer_max_output_tokens"], TABLE, DISTINCT)
    graphs = {ARM_HNSW: build_always_hnsw_graph(deps), ARM_V2: build_policy_v2_graph(deps)}

    used = ["src/phase_b_router/router.py", "src/phase_b_router/policy_v2.py", "src/phase_d_validation/comparison_runner.py",
            "src/phase_d_validation/always_hnsw_runner.py", "src/phase_d_validation/llm_client.py",
            "src/phase_d_validation/scoring.py", "config/generation.json", "config/policy_v2.json", "config/prices.json",
            QUERY_CACHE, str(subset)]
    meta = {"run_id": out.name, "amendment": "PHASE_D_AMENDMENT_10.md (tag phase-d-amendment-10-2026-10-31)",
            "argv": sys.argv, "commit": CR.git("rev-parse", "HEAD"),
            "uncommitted_used_files": CR.git("status", "--porcelain", "--", *[u for u in used if not u.startswith("outputs")]) or None,
            "start_utc": datetime.now(timezone.utc).isoformat(), "end_utc": None, "pilot": args.pilot,
            "answer_model": MODEL, "evidence_table": TABLE, "k": K, "distinct": DISTINCT, "ef_search": cfg["retrieval"]["ef_search"],
            "seed": PILOT_SEED if args.pilot else SEED, "n_items": len(items), "schedule": [list(x) for x in items],
            "answer_system_prompt": ANSWER_SYSTEM, "generation_config": cfg,
            "query_embedding_cache": {"path": QUERY_CACHE, "sha256": CR.sha256_file(QUERY_CACHE), "model": cache.get("model")},
            "file_sha256": {u: CR.sha256_file(u) for u in used},
            "machine_note": "no quiet rule (Amendment 10); the author was using the machine; latency descriptive only",
            "cpu_start": host_load(), "cpu_end": None}
    done, prior = set(), 0.0
    if args.resume:
        orig = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
        changed = [k for k in ("schedule", "file_sha256", "generation_config", "k", "distinct") if orig.get(k) != meta.get(k)]
        if changed:
            raise SystemExit(f"--resume refused: changed {changed}")
        st = CR.load_resume_state(out)
        done = {(p, q, a) for p, q, a in st["done"]}
        prior = st["prior_spent"]
        if client.guard is not None:
            client.guard.spent = prior
        with (out / "resumes.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"resumed_utc": meta["start_utc"], "commit": meta["commit"], "rows_present": len(done),
                                "prior_spent_usd": prior, "cpu": meta["cpu_start"]}) + "\n")
        meta = orig
    else:
        (out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    jsonl = out / "results.jsonl"
    try:
        with jsonl.open("a", encoding="utf-8") as fh:
            for i, (pass_no, qid, arm) in enumerate(items, 1):
                if (pass_no, qid, arm) in done:
                    continue
                row = queries[qid]
                gold_keys = {k.strip() for k in row["gold_evidence_keys"].split("|") if k.strip()}
                ticker, year = extract_ticker_year(qid)
                sel, _, _ = exact_selectivity(conn, ticker, year)
                state = {"query_id": qid, "ticker": ticker, "year": year, "question": row["question"],
                         "gold_evidence_keys": sorted(gold_keys), "estimated_selectivity": sel, "correlation_level": ""}
                err, tb, final = None, None, dict(state)
                t0 = time.perf_counter()
                try:
                    final.update(graphs[arm].invoke(dict(state)))
                except Exception as exc:
                    err, tb = f"{type(exc).__name__}: {exc}", traceback.format_exc()
                total_ms = (time.perf_counter() - t0) * 1000
                # build_record knows the frozen arm keys only; "v2" gives the policy_v2 record layout, arm name set below
                rec = CR.build_record(out.name, pass_no, "v2", row, gold_keys, sel, final, total_ms, MODEL, None, err,
                                      None, gold_md5[qid])
                rec["arm"] = arm
                rec["schedule_position"] = i
                rec["cumulative_cost_usd"] = client.spent_usd
                if err:
                    rec["error_kind"], rec["error_traceback"] = CR.error_kind(err), tb
                    with (out / "errors.jsonl").open("a", encoding="utf-8") as ef:
                        ef.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    raise RuntimeError(f"stopped at item {i} ({arm} pass {pass_no} {qid}); resume with --resume: {err}")
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                print(f"[{i}/{len(items)}] {arm:11s} p{pass_no} {qid} rows={rec['rows_returned']} correct={rec['correct']} "
                      f"cost={client.spent_usd:.4f}", flush=True)
    finally:
        cpu_end = host_load()
        if args.resume:
            with (out / "resumes.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"segment_end_utc": datetime.now(timezone.utc).isoformat(), "cpu": cpu_end}) + "\n")
        else:
            meta["end_utc"], meta["cpu_end"] = datetime.now(timezone.utc).isoformat(), cpu_end
            (out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        if jsonl.exists():
            CR.write_csv(jsonl, out / "results.csv")
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--budget-usd", type=float, required=True)
    p.add_argument("--resume", action="store_true")
    run(p.parse_args())


if __name__ == "__main__":
    main()
