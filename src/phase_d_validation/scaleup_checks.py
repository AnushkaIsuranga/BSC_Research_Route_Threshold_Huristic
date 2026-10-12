"""Read-only checks for the Amendment 4 scale-up and creation of the confirmation-set subset file.

  python -m src.phase_d_validation.scaleup_checks --out-dir outputs/scaleup_checks_<date>

(a) frozen 50 within the 1,147-question pool; confirmation set = pool minus the 50
(b) where any confirmation-set query id appears in outputs/ (answer-level exposure check)
(c) evidence-breadth strata (single / dual / multi gold evidence) for the 50 and for the confirmation set
(d) exact selectivity (DB count) and policy_v2 route for every confirmation question; gold answers parseable; gold keys in DB
(e) Gemini full-run wall clock and call rate; time and cost estimate for the scale-up
Writes <out-dir>/confirmation_subset.csv (same columns the runner reads: id, question, answer, gold_evidence_keys, breadth)
and <out-dir>/checks.json. Reads only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import psycopg2

from src import db_settings
from src.phase_b_router.policy_v2 import get_routing_decision_v2
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.scoring import UnparseableNumber, parse_financial_number, _bool_word
from src.utils.finqa_utils import exact_selectivity, extract_ticker_year

GEMINI_FULL = Path("outputs/phase_d_gemini_full_2026-10-12")


def breadth(n: int) -> str:
    return "single" if n == 1 else "dual" if n == 2 else "multi"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = Path(a.out_dir)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty")
    out.mkdir(parents=True)
    pool = json.loads(Path("data/raw/finqa_test.json").read_text(encoding="utf-8"))
    pool_ids = [e["id"] for e in pool]
    frozen = load_finqa_subset(get_frozen_filepath())
    fids = {q["id"] for q in frozen}
    res = {"pool_size": len(pool), "pool_unique_ids": len(set(pool_ids)), "frozen_50_in_pool": len(fids & set(pool_ids)),
           "frozen_size": len(fids)}
    conf = [e for e in pool if e["id"] not in fids]
    res["confirmation_size"] = len(conf)

    # (b) exposure: every file under outputs/ that mentions a confirmation id
    cids = {e["id"] for e in conf}
    hits = {}
    for p in sorted(Path("outputs").rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".jsonl", ".json", ".csv", ".md", ".txt") or p.stat().st_size > 50_000_000:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        n = sum(1 for c in cids if c in text)
        if n:
            hits[p.as_posix()] = n
    res["files_mentioning_confirmation_ids"] = hits

    # (c) strata
    def strata(examples):
        return dict(Counter(breadth(len(e["qa"]["gold_inds"])) for e in examples))
    res["strata_frozen_50"] = strata([e for e in pool if e["id"] in fids])
    res["strata_confirmation"] = strata(conf)

    # (d) selectivity, routes, gold answers, gold keys
    conn = psycopg2.connect(**db_settings())
    sels, routes, unparseable, missing_keys = [], Counter(), [], []
    rows = []
    with conn.cursor() as cur:
        for e in conf:
            t, y = extract_ticker_year(e["id"])
            s, _, _ = exact_selectivity(conn, t, y)
            sels.append(s)
            routes[get_routing_decision_v2(s)] += 1
            g = str(e["qa"]["answer"])
            if _bool_word(g) is None:
                try:
                    parse_financial_number(g, strip_scale=True)
                except UnparseableNumber:
                    unparseable.append((e["id"], g))
            keys = list(e["qa"]["gold_inds"])
            for k in keys:
                cur.execute("SELECT 1 FROM finqa_evidence_qwen3 WHERE query_id = %s AND evidence_key = %s", (e["id"], k))
                if cur.fetchone() is None:
                    missing_keys.append((e["id"], k))
            rows.append({"id": e["id"], "question": e["qa"]["question"], "answer": g, "gold_evidence_keys": "|".join(keys),
                         "breadth": breadth(len(keys)), "selectivity": s})
    res.update({"confirmation_selectivity_min": min(sels), "confirmation_selectivity_max": max(sels),
                "max_le_0_0297": max(sels) <= 0.0297, "policy_v2_routes": dict(routes),
                "unparseable_gold_answers": unparseable, "gold_keys_missing_in_db": missing_keys,
                "duplicate_question_texts": sum(c - 1 for c in Counter(r["question"] for r in rows).values() if c > 1),
                "empty_questions": sum(1 for r in rows if not r["question"].strip())})
    with (out / "confirmation_subset.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "question", "answer", "gold_evidence_keys", "breadth", "selectivity"])
        w.writeheader()
        w.writerows(rows)
    res["confirmation_subset_sha256"] = hashlib.sha256((out / "confirmation_subset.csv").read_bytes()).hexdigest()

    # (e) Gemini full-run rate and estimate
    meta = json.loads((GEMINI_FULL / "run_meta.json").read_text(encoding="utf-8"))
    g_rows = [json.loads(l) for l in (GEMINI_FULL / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    t0, t1 = datetime.fromisoformat(meta["start_utc"]), datetime.fromisoformat(meta["end_utc"])
    minutes = (t1 - t0).total_seconds() / 60
    calls = sum(1 for r in g_rows) + sum(1 for r in g_rows if r["router_raw"] is not None)
    cost = sum(r["cost_usd"] for r in g_rows)
    n = len(conf)
    arm_runs = n * 4
    new_calls = arm_runs + 2 * n            # 4 answer calls + 2 router calls per question
    res["gemini_full_run"] = {"wall_clock_minutes": minutes, "arm_runs": len(g_rows), "calls": calls,
                              "calls_per_minute": calls / minutes, "arm_runs_per_minute": len(g_rows) / minutes,
                              "cost_usd": cost, "cost_per_arm_run": cost / len(g_rows)}
    res["scaleup_estimate"] = {"questions": n, "arm_runs": arm_runs, "calls": new_calls,
                               "minutes_at_same_call_rate": new_calls / (calls / minutes),
                               "cost_usd_at_same_cost_per_arm_run": arm_runs * cost / len(g_rows)}
    (out / "checks.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "files_mentioning_confirmation_ids"}, indent=2))
    print("files mentioning confirmation ids:")
    for k, v in hits.items():
        print(f"  {v:5d}  {k}")


if __name__ == "__main__":
    main()
