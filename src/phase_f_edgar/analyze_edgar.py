"""Phase F Task 6 (Amendment 11 section 6): scoring, hallucination classes, P1-P5, tables by mode and breadth, label sheet.

  python -m src.phase_f_edgar.analyze_edgar --out-dir outputs/edgar_analysis_2026-11-01

Primary score: scoring.score_answer(rule="primary") on verify_questions.first_number(answer).span vs gold_number.
Classes: correct; abstained ("not answerable", no number, failed call); wrong_in_context (answer number, rule A of
verify_questions.number_in_text, appears in a passage of the prompt); wrong_not_in_context.
Uncertainty: cluster bootstrap over the 40 questions (all four pairs of a question move together), 10,000 resamples,
numpy default_rng(20261104), percentile 95 % intervals.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
from collections import defaultdict

import numpy as np
import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.paired_stats import mcnemar_exact
from src.phase_d_validation.scoring import score_answer
from src.phase_f_edgar import session_tools as S
from src.phase_f_edgar.compare_edgar import BREADTHS, MODES
from src.phase_f_edgar.verify_questions import first_number, number_in_text

COMPARISON = "outputs/edgar_retrieval_comparison_2026-11-01"
ANSWERS = "outputs/edgar_answers_2026-11-01"
EVAL = "outputs/edgar_eval_set_2026-11-01"
CLASSES = ("correct", "abstained", "wrong_in_context", "wrong_not_in_context")
BOOT_N, BOOT_SEED, LABEL_SEED, LABEL_N = 10_000, 20261104, 20261103, 40
MARGIN = 0.10


def classify(raw: str | None, gold_number: str, passages: list[str]) -> tuple[str, str]:
    """(class, parsed number span)."""
    if raw is None or re.search(r"not answerable", raw, re.IGNORECASE):
        return "abstained", ""
    n = first_number(raw)
    if n is None:
        return "abstained", ""
    if score_answer(n.span, gold_number, rule="primary").correct:
        return "correct", n.span
    return ("wrong_in_context" if any(number_in_text(n, t) for t in passages) else "wrong_not_in_context"), n.span


def cluster_boot(per_q: dict, stat, n=BOOT_N, seed=BOOT_SEED):
    """per_q: {qid: data}; stat(list of data) -> float. Percentile 95 % CI over resampled questions."""
    qids = sorted(per_q)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(qids), len(qids))
        vals.append(stat([per_q[qids[i]] for i in idx]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    comp = [json.loads(ln) for ln in (PROJECT_ROOT / COMPARISON / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    cby = {(r["pair_id"], r["mode"]): r for r in comp}
    sel = {r["qid"]: r for r in csv.DictReader(open(PROJECT_ROOT / EVAL / "selected.csv", encoding="utf-8", newline=""))}
    prompts = {json.loads(ln)["prompt_id"]: json.loads(ln) for ln in (PROJECT_ROOT / ANSWERS / "prompts.jsonl").read_text(encoding="utf-8").splitlines()}
    reuse = json.loads((PROJECT_ROOT / ANSWERS / "reuse_map.json").read_text(encoding="utf-8"))
    n_pass = json.loads((PROJECT_ROOT / ANSWERS / "pass_decision.json").read_text(encoding="utf-8"))["passes"]
    resp = {}
    for ln in (PROJECT_ROOT / ANSWERS / "responses.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(ln)
        resp[(d["pass"], d["prompt_id"])] = d
    if len(resp) != n_pass * len(prompts):
        raise SystemExit(f"incomplete answer run: {len(resp)} of {n_pass * len(prompts)} responses")
    ids = sorted({i for p in prompts.values() for i in p["passage_ids"]})
    conn = psycopg2.connect(**db_settings())
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SELECT id, text FROM edgar_chunks WHERE id = ANY(%s)", (ids,))
        text = dict(cur.fetchall())

    rows = []
    for (pair_id, mode), r in sorted(cby.items()):
        pid = reuse[f"{pair_id}|{mode}"]
        p = prompts[pid]
        gold = sel[r["qid"]]["gold_number"]
        for ps in range(1, n_pass + 1):
            d = resp[(ps, pid)]
            cls, span = classify(d.get("raw"), gold, [text[i] for i in p["passage_ids"]])
            rows.append({"pair_id": pair_id, "qid": r["qid"], "breadth": r["breadth"], "mode": mode, "pass": ps, "prompt_id": pid,
                         "class": cls, "correct": int(cls == "correct"), "answer_span": span, "gold_number": gold,
                         "raw": d.get("raw"), "call_error": d.get("call_error"), "gold_hit": r["gold_hit"], "recall15": r["recall15"],
                         "rows_returned": r["rows_returned"], "n_passages": p["n_distinct"], "latency_ms": r["latency_ms"],
                         "finish_reason": d.get("finish_reason")})
    with open(out / "answers_scored.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    # ---- per-pair mean correctness / class rates over passes
    pp = defaultdict(lambda: defaultdict(list))         # (mode) -> pair_id -> [rows]
    for r in rows:
        pp[r["mode"]][r["pair_id"]].append(r)
    qof = {r["pair_id"]: r["qid"] for r in rows}
    bof = {r["pair_id"]: r["breadth"] for r in rows}

    def per_question(mode, metric, breadth="all"):
        acc = defaultdict(list)
        for pair_id, rs in pp[mode].items():
            if breadth != "all" and bof[pair_id] != breadth:
                continue
            acc[qof[pair_id]].append(statistics.fmean(metric(x) for x in rs))
        return acc

    mean_of = lambda groups: statistics.fmean(v for g in groups for v in g)
    table = []
    for mode in MODES:
        for b in ("all",) + BREADTHS:
            rec = {"mode": mode, "breadth": b}
            for cls in CLASSES:
                pq = per_question(mode, lambda x, c=cls: x["class"] == c, b)
                est = mean_of(pq.values())
                lo, hi = cluster_boot(pq, mean_of, n=2000) if cls != "correct" else cluster_boot(pq, mean_of)
                rec.update({f"{cls}": round(est, 4), f"{cls}_ci": f"[{lo:.3f}, {hi:.3f}]"})
            comp_rows = [cby[(p, mode)] for p in pp[mode] if b == "all" or bof[p] == b]
            lat = [c["latency_ms"] for c in comp_rows if c["latency_ms"] is not None]
            rec.update({"n_pairs": len(comp_rows), "gold_hit_rate": round(sum(c["gold_hit"] for c in comp_rows) / len(comp_rows), 4),
                        "median_latency_ms": round(statistics.median(lat), 2) if lat else None})
            table.append(rec)
    with open(out / "answers_by_mode_breadth.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(table)

    # ---- predictions
    pred = {}
    router_rows = [c for c in comp if c["mode"] == "router"]
    share = sum(1 for c in router_rows if (c["recall15"] or 0) >= 0.9) / len(router_rows)
    pred["P1"] = {"router_pairs_recall15_ge_0.90": sum(1 for c in router_rows if (c["recall15"] or 0) >= 0.9), "n": len(router_rows),
                  "share": share, "held": share >= 0.95,
                  "by_breadth": {b: sum(1 for c in router_rows if c["breadth"] == b and (c["recall15"] or 0) >= 0.9) for b in BREADTHS}}

    def diff_stat(m1, m2, metric, breadth="all"):
        a1, a2 = per_question(m1, metric, breadth), per_question(m2, metric, breadth)
        both = {q: (a1[q], a2[q]) for q in a1}
        est = mean_of([v[0] for v in both.values()]) - mean_of([v[1] for v in both.values()])
        lo, hi = cluster_boot(both, lambda gs: mean_of([g[0] for g in gs]) - mean_of([g[1] for g in gs]))
        return est, lo, hi

    corr = lambda x: x["correct"]
    est, lo, hi = diff_stat("router", "always_exact", corr)
    pred["P2"] = {"router_minus_always_exact": est, "ci95": [lo, hi], "margin": -MARGIN, "held": lo > -MARGIN,
                  "by_breadth": {b: dict(zip(("est", "lo", "hi"), diff_stat("router", "always_exact", corr, b))) for b in BREADTHS}}
    p1 = {(r["pair_id"], r["mode"]): r["correct"] for r in rows if r["pass"] == 1}
    pairs = sorted({r["pair_id"] for r in rows})
    b_ = sum(1 for p in pairs if p1[(p, "router")] and not p1[(p, "default_hnsw")])
    c_ = sum(1 for p in pairs if not p1[(p, "router")] and p1[(p, "default_hnsw")])
    pv = mcnemar_exact(b_, c_)
    pred["P3"] = {"b_router_only": b_, "c_default_hnsw_only": c_, "p_exact_mcnemar": pv, "held": pv < 0.05 and b_ > c_,
                  "router_correct_pass1": sum(p1[(p, "router")] for p in pairs), "default_hnsw_correct_pass1": sum(p1[(p, "default_hnsw")] for p in pairs)}
    wnic = lambda x: x["class"] == "wrong_not_in_context"
    est, lo, hi = diff_stat("router", "default_hnsw", wnic)
    pred["P4"] = {"router_minus_default_hnsw_wrong_not_in_context": est, "ci95": [lo, hi], "held": est < 0,
                  "router_rate": mean_of(per_question("router", wnic).values()), "default_hnsw_rate": mean_of(per_question("default_hnsw", wnic).values()),
                  "note": "descriptive; held = point estimate lower"}
    p5 = {}
    for b in ("year+section", "section"):
        med = {m: statistics.median(c["latency_ms"] for c in comp if c["mode"] == m and c["breadth"] == b and c["latency_ms"] is not None)
               for m in ("router", "always_exact")}
        p5[b] = {**med, "router_lower": med["router"] < med["always_exact"]}
    pred["P5"] = {**p5, "held": all(v["router_lower"] for v in p5.values())}
    S.write_json(out / "predictions.json", pred)

    # ---- transfer: router vs router_hmT
    tr = {"answer_diff_router_minus_router_hmT": dict(zip(("est", "lo", "hi"), diff_stat("router", "router_hmT", corr))),
          "same_route_pairs": sum(1 for p in pairs if cby[(p, "router")]["trace"].get("decided") == cby[(p, "router_hmT")]["trace"].get("decided")),
          "n_pairs": len(pairs)}
    S.write_json(out / "transfer.json", tr)

    # ---- validation sample (pass 1 wrong answers), drafted labels added by hand afterwards
    wrong = [r for r in rows if r["pass"] == 1 and r["class"] in ("wrong_in_context", "wrong_not_in_context")]
    rng = random.Random(LABEL_SEED)
    pick = {}
    for m in ("router", "default_hnsw"):
        pool = sorted((r for r in wrong if r["mode"] == m), key=lambda r: r["pair_id"])
        pick[m] = rng.sample(pool, min(LABEL_N // 2, len(pool)))
    for m, other in (("router", "default_hnsw"), ("default_hnsw", "router")):
        short = LABEL_N // 2 - len(pick[m])
        if short > 0:
            pool = sorted((r for r in wrong if r["mode"] == other and r not in pick[other]), key=lambda r: r["pair_id"])
            pick[other] += rng.sample(pool, min(short, len(pool)))
    sample = pick["router"] + pick["default_hnsw"]
    rng.shuffle(sample)
    key, sheet = [], []
    for i, r in enumerate(sample, 1):
        sid = f"L{i:02d}"
        p = prompts[r["prompt_id"]]
        key.append({"sample_id": sid, "pair_id": r["pair_id"], "mode": r["mode"], "pass": 1, "proxy_class": r["class"]})
        sheet.append({"sample_id": sid, "question": sel[r["qid"]]["question"], "gold_answer": sel[r["qid"]]["answer"],
                      "model_answer": r["raw"], "answer_number": r["answer_span"],
                      "passages": "\n\n".join(f"[{j + 1}] {text[i_]}" for j, i_ in enumerate(p["passage_ids"])),
                      "drafted_label": "", "drafted_reason": "", "author_label": "", "author_note": ""})
    for name, data in (("label_sheet.csv", sheet), ("label_key.csv", key)):
        if data:
            with open(out / name, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(data[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(data)
    print(json.dumps(pred, indent=1, default=str))
    print(json.dumps(tr, indent=1))
    print(f"label sample: {len(sample)} rows ({len(pick['router'])} router, {len(pick['default_hnsw'])} default_hnsw)")


if __name__ == "__main__":
    main()
