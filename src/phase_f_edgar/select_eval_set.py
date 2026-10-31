"""Phase F evaluation, Task 1: apply the author review and the selection rule of docs/EDGAR_QUESTION_METHOD.md section 4
(no paid calls).

  python -m src.phase_f_edgar.select_eval_set --out-dir outputs/edgar_eval_set_2026-11-01

- eligible = status auto_pass (checks.csv), or author decision keep / fix (review_sheet_author.csv); a fix uses
  corrected_answer / corrected_type. A drop removes the question even if it was auto_pass.
- every eligible calculation question is kept; lookups are drawn with random.Random(20261101).sample(sorted ids, 40 - n_calc).
  If fewer than 40 qualify, all are used and the shortfall is recorded.
- gold_number = verify_questions.first_number(answer).span (the function check B used).
- pairs: each selected question x the four breadths of its gold chunk; exact selectivity = count / count(*), gold ids =
  rows with the gold chunk's text_hash that pass the filter; query vectors reused from question_embeddings.json after
  checking its sha256 against outputs/data_checksums.json.
- calibration_queries.csv: the candidates not selected (disjoint from the evaluation set).
Writes selected.csv, pairs.csv, calibration_queries.csv, selection_log.json (UTF-8, LF); refuses to overwrite.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_f_edgar import common as C
from src.phase_f_edgar.verify_questions import BREADTHS, build_filter, first_number

SEED = 20261101
N_TARGET = 40
VERIFY = "outputs/edgar_questions_verify_2026-11-01"
REVIEW = "outputs/edgar_questions_review_2026-11-01/review_sheet_author.csv"
CANDIDATES = "outputs/edgar_questions_draft_2026-10-31/candidates.csv"
QUALIFIERS = re.compile(r"\b(approximately|approx|about|around|nearly|almost|over|under|more than|less than|up to|at least|"
                        r"at most|roughly|estimated)\b", re.IGNORECASE)


def select(checks: dict, review: dict, cands: dict, seed: int = SEED, n_target: int = N_TARGET) -> dict:
    """checks/review/cands: qid -> row. Returns the selection with reasons; pure (no I/O)."""
    eligible = {}
    for qid, c in cands.items():
        rv = review.get(qid)
        dec = (rv or {}).get("decision", "").strip().lower()
        if rv is not None and dec not in ("keep", "fix", "drop"):
            raise ValueError(f"{qid}: decision {dec!r} is not keep / fix / drop")
        if dec == "drop":
            continue
        if checks[qid]["status"] == "auto_pass" or dec in ("keep", "fix"):
            answer, qtype = c["drafted_answer"], c["type"]
            if dec == "fix":
                answer = rv["corrected_answer"].strip() or answer
                qtype = rv["corrected_type"].strip() or qtype
            if qtype not in ("lookup", "calculation"):
                raise ValueError(f"{qid}: type {qtype!r}")
            eligible[qid] = {"answer": answer, "type": qtype, "basis": checks[qid]["status"] if not dec else f"author_{dec}"}
    calcs = sorted(q for q, e in eligible.items() if e["type"] == "calculation")
    lookups = sorted(q for q, e in eligible.items() if e["type"] == "lookup")
    need = max(0, n_target - len(calcs))
    drawn = sorted(random.Random(seed).sample(lookups, min(need, len(lookups))))
    selected = sorted(calcs + drawn)
    return {"eligible": eligible, "calculations": calcs, "lookups_eligible": lookups, "lookups_drawn": drawn,
            "selected": selected, "shortfall": max(0, n_target - len(selected))}


def residual_flag(answer: str, span_text: str) -> str:
    """Why cutting removed more than unit words ('' if only units): a qualifier, another number, or a sign/scale change."""
    reasons = []
    if QUALIFIERS.search(answer):
        reasons.append("qualifier")
    if len(re.findall(r"\d[\d,]*(?:\.\d+)?", answer)) > 1:
        reasons.append("more than one number")
    return "; ".join(reasons)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    rd = lambda p: {r["qid"]: r for r in csv.DictReader(open(PROJECT_ROOT / p, encoding="utf-8", newline=""))}
    checks, review, cands = rd(f"{VERIFY}/checks.csv"), rd(REVIEW), rd(CANDIDATES)
    if len(review) != 40 or any(not r["decision"].strip() for r in review.values()) or not set(review) <= set(cands):
        raise SystemExit("review file: expected 40 rows with a decision, all candidate qids")
    sel = select(checks, review, cands)

    sums = json.loads((PROJECT_ROOT / "outputs/data_checksums.json").read_text(encoding="utf-8"))["files"]
    emb_path = f"{VERIFY}/question_embeddings.json"
    emb_sha = C.sha256_file(PROJECT_ROOT / emb_path)
    if sums[emb_path]["sha256"] != emb_sha:
        raise SystemExit(f"{emb_path}: sha256 {emb_sha} differs from data_checksums.json")
    emb = json.loads((PROJECT_ROOT / emb_path).read_text(encoding="utf-8"))
    vec_ok = {}
    for q in emb["queries"]:
        if hashlib.sha256(q["input_text"].encode()).hexdigest() != q["input_sha256"]:
            raise SystemExit(f"{q['query_id']}: input hash mismatch")
        vec_ok[q["query_id"]] = q["input_text"]

    conn = psycopg2.connect(**db_settings())
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {C.TABLE}")
    (n_total,) = cur.fetchone()

    sel_rows, pair_rows, cut_rows = [], [], []
    for qid in sel["selected"]:
        c, e = cands[qid], sel["eligible"][qid]
        if not vec_ok[qid].endswith("\nQuery: " + c["question"]):
            raise SystemExit(f"{qid}: cached embedding input does not end with the question text")
        gold_ids = json.loads(c["gold_chunk_ids"])
        cur.execute(f"SELECT cik, fiscal_year, section, text_hash, text FROM {C.TABLE} WHERE id = %s", (gold_ids[0],))
        cik, fy, sec, h, text = cur.fetchone()
        if text != c["gold_chunk_text"]:
            raise SystemExit(f"{qid}: gold chunk text changed")
        span = first_number(e["answer"]).span
        flag = residual_flag(e["answer"], span)
        if flag:
            cut_rows.append({"qid": qid, "answer": e["answer"], "gold_number": span, "why": flag})
        sel_rows.append({"qid": qid, "question": c["question"], "type": e["type"], "answer": e["answer"], "gold_number": span,
                         "selection_basis": e["basis"], "drafted_breadth": c["filter_breadth"], "company_name": c["company_name"],
                         "cik": cik, "fiscal_year": fy, "section": sec, "gold_text_hash": h, "gold_chunk_text": text})
        meta = {"cik": cik, "fiscal_year": fy, "section": sec}
        for b in BREADTHS:
            f = build_filter(meta, b)
            where = " AND ".join(f"{col} = %s" for col, _ in f)
            params = [v[0] for _, v in f]
            cur.execute(f"SELECT count(*) FROM {C.TABLE} WHERE {where}", params)
            (n,) = cur.fetchone()
            cur.execute(f"SELECT id FROM {C.TABLE} WHERE {where} AND text_hash = %s ORDER BY id", [*params, h])
            g = [x[0] for x in cur.fetchall()]
            if not g:
                raise SystemExit(f"{qid} {b}: no gold row under the filter")
            pair_rows.append({"pair_id": f"{qid}|{b}", "qid": qid, "breadth": b, "filter": json.dumps(f), "n_match": n,
                              "selectivity": n / n_total, "gold_ids": json.dumps(g), "drafted_breadth": c["filter_breadth"],
                              "type": e["type"]})

    def write(name, rows, fields):
        with open(out / name, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    write("selected.csv", sel_rows, list(sel_rows[0]))
    write("pairs.csv", pair_rows, list(pair_rows[0]))
    calib = [{"qid": q, "question": cands[q]["question"], "status": checks[q]["status"],
              "review_decision": review.get(q, {}).get("decision", ""), "reason_not_selected":
                  ("author drop" if review.get(q, {}).get("decision", "").strip().lower() == "drop" else
                   "eligible lookup not drawn" if q in sel["eligible"] else "not eligible")}
             for q in sorted(cands) if q not in sel["selected"]]
    write("calibration_queries.csv", calib, list(calib[0]))
    log = {"seed": SEED, "n_target": N_TARGET, "table_rows": n_total, "review_file": REVIEW,
           "review_sha256": C.sha256_file(PROJECT_ROOT / REVIEW), "question_embeddings": emb_path, "question_embeddings_sha256": emb_sha,
           "n_candidates": len(cands), "n_eligible": len(sel["eligible"]),
           "eligible_by_basis": {k: sum(e["basis"] == k for e in sel["eligible"].values())
                                 for k in sorted({e["basis"] for e in sel["eligible"].values()})},
           "n_calculation_eligible": len(sel["calculations"]), "n_lookup_eligible": len(sel["lookups_eligible"]),
           "calculations_kept": sel["calculations"], "lookups_drawn": sel["lookups_drawn"], "selected": sel["selected"],
           "shortfall": sel["shortfall"], "n_pairs": len(pair_rows), "calibration_qids": [r["qid"] for r in calib],
           "gold_number_cut_more_than_units": cut_rows,
           "review_decisions": {d: sum(r["decision"].strip().lower() == d for r in review.values()) for d in ("keep", "fix", "drop")}}
    (out / "selection_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in log.items() if k not in ("selected", "calibration_qids")}, indent=1))


if __name__ == "__main__":
    main()
