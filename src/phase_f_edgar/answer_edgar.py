"""Phase F Task 5 (Amendment 11 section 5): answer runs with Gemini 3.8 Flash on the passages of every comparison mode. Paid.

  python -m src.phase_f_edgar.answer_edgar plan  --out-dir outputs/edgar_answers_2026-11-01
  python -m src.phase_f_edgar.answer_edgar pilot --allow-paid --out-dir outputs/edgar_answers_2026-11-01
  python -m src.phase_f_edgar.answer_edgar main  --allow-paid --out-dir outputs/edgar_answers_2026-11-01

plan: from the comparison's normal executions, the prompt per (pair, mode): rows in returned order, duplicate texts dropped (no
over-fetch); identical ordered passage lists of one pair share one answer per pass (reuse map). pilot: 5 unique prompts drawn with
random.Random("20261101-pilot"), 1 call each, excluded from analysis; writes the projection. main: the pass count decided from
the pilot (largest of 5 / 3 / 1 whose projection <= USD 4.50 and keeps the session under USD 6.00; written to the run log before
any main call); items shuffled with random.Random(20261105); single attempt per call, a failed call = abstained (listed).
Resumable: (pass, prompt_id) already answered are skipped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timezone

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_f_edgar import session_tools as S

COMPARISON = "outputs/edgar_retrieval_comparison_2026-11-01"
EVAL = "outputs/edgar_eval_set_2026-11-01"
MODEL = "gemini-3.8-flash"
ANSWER_CAP_USD = 4.50
PASS_OPTIONS = (5, 3, 1)
SEED = 20261105
PILOT_N = 5


def passage_line(meta: dict, text: str) -> str:
    who = meta["company_name"] or f"CIK {meta['cik']}"
    return f"[{who} | FY {meta['fiscal_year']} | Item {meta['section']}] {text}"


def build_prompts(results: list[dict], chunk_meta: dict, questions: dict) -> tuple[list[dict], dict]:
    """(unique prompts, reuse map (pair_id, mode) -> prompt_id). Duplicate texts within a list are dropped (first kept)."""
    prompts, reuse = {}, {}
    for r in sorted(results, key=lambda x: (x["pair_id"], x["mode"])):
        seen, kept = set(), []
        for i in r["ids"]:
            h = chunk_meta[i]["text_hash"]
            if h not in seen:
                seen.add(h)
                kept.append(i)
        key = hashlib.sha256(json.dumps([r["pair_id"], kept]).encode()).hexdigest()[:16]
        pid = f"{r['pair_id']}#{key}"
        if pid not in prompts:
            ev = "\n".join(passage_line(chunk_meta[i], chunk_meta[i]["text"]) for i in kept)
            prompts[pid] = {"prompt_id": pid, "pair_id": r["pair_id"], "qid": r["qid"], "breadth": r["breadth"], "passage_ids": kept,
                            "n_rows": len(r["ids"]), "n_distinct": len(kept), "user": f"Evidence:\n{ev}\n\nQuestion: {questions[r['qid']]}",
                            "modes": []}
        prompts[pid]["modes"].append(r["mode"])
        reuse[(r["pair_id"], r["mode"])] = pid
    return list(prompts.values()), reuse


def plan(a):
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    rows = [json.loads(ln) for ln in (PROJECT_ROOT / COMPARISON / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    questions = {r["qid"]: r["question"] for r in csv.DictReader(open(PROJECT_ROOT / EVAL / "selected.csv", encoding="utf-8", newline=""))}
    ids = sorted({i for r in rows for i in r["ids"]})
    conn = psycopg2.connect(**db_settings())
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SELECT id, cik, company_name, fiscal_year, section, text, text_hash FROM edgar_chunks WHERE id = ANY(%s)", (ids,))
        meta = {r[0]: {"cik": r[1], "company_name": r[2], "fiscal_year": r[3], "section": r[4], "text": r[5], "text_hash": r[6]}
                for r in cur.fetchall()}
    prompts, reuse = build_prompts(rows, meta, questions)
    with open(out / "prompts.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for p in prompts:
            fh.write(json.dumps(p) + "\n")
    S.write_json(out / "reuse_map.json", {f"{k[0]}|{k[1]}": v for k, v in sorted(reuse.items())})
    by_pair = defaultdict(int)
    for p in prompts:
        by_pair[p["pair_id"]] += 1
    S.write_json(out / "plan.json", {"n_mode_pairs": len(reuse), "n_unique_prompts": len(prompts),
                                     "unique_prompts_per_pair": {"min": min(by_pair.values()), "max": max(by_pair.values()),
                                                                 "mean": sum(by_pair.values()) / len(by_pair)},
                                     "n_rows_with_duplicates_dropped": sum(1 for p in prompts if p["n_distinct"] < p["n_rows"]),
                                     "created_utc": datetime.now(timezone.utc).isoformat()})
    print(f"{len(reuse)} (pair, mode) -> {len(prompts)} unique prompts")


def _client(budget):
    from src.phase_d_validation.llm_client import load_generation_config, make_client
    gcfg = load_generation_config()
    return make_client(MODEL, allow_paid=True, budget_usd=budget, config=gcfg), gcfg


def _call(client, gcfg, prompt, step, pass_no, fh):
    from src.phase_b_router.router import ANSWER_SYSTEM
    rec = {"prompt_id": prompt["prompt_id"], "pair_id": prompt["pair_id"], "pass": pass_no, "utc": datetime.now(timezone.utc).isoformat()}
    try:
        resp = client.generate(ANSWER_SYSTEM, prompt["user"], max_output_tokens=gcfg["roles"]["answer_max_output_tokens"])
        rec.update({"raw": resp.text, "finish_reason": resp.finish_reason, "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens, "thinking_tokens": resp.thinking_tokens, "cached_tokens": resp.cached_tokens,
                    "traffic_type": resp.traffic_type, "latency_ms": resp.latency_ms, "cost_usd": resp.cost_usd, "call_error": None})
    except Exception as e:                                   # single attempt (Amendment 4 Addendum 1): abstained, listed
        rec.update({"raw": None, "call_error": f"{type(e).__name__}: {e}"[:800], "cost_usd": 0.0})
    S.cost_add(step, rec["cost_usd"], {"prompt_id": prompt["prompt_id"], "pass": pass_no})
    fh.write(json.dumps(rec) + "\n")
    fh.flush()
    return rec


def pilot(a):
    if not a.allow_paid:
        raise SystemExit("paid: needs --allow-paid")
    out = PROJECT_ROOT / a.out_dir
    if (out / "pilot.jsonl").exists():
        raise SystemExit("pilot already run")
    prompts = [json.loads(ln) for ln in (out / "prompts.jsonl").read_text(encoding="utf-8").splitlines()]
    picks = random.Random("20261101-pilot").sample(sorted(prompts, key=lambda p: p["prompt_id"]), PILOT_N)
    client, gcfg = _client(S.SESSION_CAP_USD - S.cost_spent())
    with open(out / "pilot.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        recs = [_call(client, gcfg, p, "answer pilot (excluded)", 0, fh) for p in picks]
    ok = [r for r in recs if not r["call_error"]]
    if not ok:
        raise SystemExit("all pilot calls failed")
    per_call = sum(r["cost_usd"] for r in ok) / len(ok)
    spent = S.cost_spent()
    proj = {n: per_call * len(prompts) * n for n in PASS_OPTIONS}
    allowed = [n for n in PASS_OPTIONS if proj[n] <= ANSWER_CAP_USD and spent + proj[n] <= S.SESSION_CAP_USD]
    decision = {"pilot_calls": len(recs), "pilot_errors": len(recs) - len(ok), "mean_cost_per_call_usd": per_call,
                "unique_prompts_per_pass": len(prompts), "projection_usd": proj, "session_spent_before_main_usd": spent,
                "answer_cap_usd": ANSWER_CAP_USD, "session_cap_usd": S.SESSION_CAP_USD, "passes": max(allowed) if allowed else None,
                "decided_utc": datetime.now(timezone.utc).isoformat(),
                "rule": "largest of 5, 3, 1 passes whose projection <= USD 4.50 and keeps the session under USD 6.00"}
    S.write_json(out / "pass_decision.json", decision)
    with open(out / "run_log.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"event": "pass_decision", **decision}) + "\n")
    print(json.dumps(decision, indent=1))
    if decision["passes"] is None:
        raise SystemExit("STOP: the projection exceeds the cap even at 1 pass")


def main_run(a):
    if not a.allow_paid:
        raise SystemExit("paid: needs --allow-paid")
    out = PROJECT_ROOT / a.out_dir
    decision = json.loads((out / "pass_decision.json").read_text(encoding="utf-8"))
    n_pass = decision["passes"]
    if not n_pass:
        raise SystemExit("no pass count decided")
    prompts = {json.loads(ln)["prompt_id"]: json.loads(ln) for ln in (out / "prompts.jsonl").read_text(encoding="utf-8").splitlines()}
    items = [(ps, pid) for ps in range(1, n_pass + 1) for pid in sorted(prompts)]
    random.Random(SEED).shuffle(items)
    path = out / "responses.jsonl"
    done = set()
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            d = json.loads(ln)
            done.add((d["pass"], d["prompt_id"]))
    client, gcfg = _client(S.SESSION_CAP_USD - S.cost_spent())
    with open(out / "run_log.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"event": "main_start", "utc": datetime.now(timezone.utc).isoformat(), "passes": n_pass, "items": len(items),
                             "already_done": len(done), "session_spent_usd": S.cost_spent()}) + "\n")
    n = 0
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        for ps, pid in items:
            if (ps, pid) in done:
                continue
            rec = _call(client, gcfg, prompts[pid], f"answer main pass {ps}", ps, fh)
            n += 1
            if n % 100 == 0:
                print(f"{n} calls, session total USD {S.cost_spent():.4f}", flush=True)
    with open(out / "run_log.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"event": "main_end", "utc": datetime.now(timezone.utc).isoformat(), "new_calls": n,
                             "session_spent_usd": S.cost_spent()}) + "\n")
    print(f"done: {n} calls; session total USD {S.cost_spent():.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "pilot", "main"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--allow-paid", action="store_true")
    a = ap.parse_args()
    {"plan": plan, "pilot": pilot, "main": main_run}[a.cmd](a)
