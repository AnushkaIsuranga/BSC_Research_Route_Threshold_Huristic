"""Phase F question verification (Task 2): review sheet = every needs_review row plus 10 auto_pass rows (seed 20261101).

  python -m src.phase_f_edgar.review_sheet --verify-dir outputs/edgar_questions_verify_2026-11-01 \
      --candidates outputs/edgar_questions_draft_2026-10-31/candidates.csv

Order: first the rows whose drafted number is not in the gold chunk (any type), then q057, q033, q055 if they need review,
each group by qid; then the remaining rows in random order (same seeded generator, after the 10 passing rows are drawn).
Chunk text in full, one row per question; empty decision (keep / fix / drop), corrected_answer, corrected_type, note.
Writes review_sheet.csv (UTF-8, LF) into --verify-dir; refuses to overwrite.
"""

from __future__ import annotations

import argparse
import csv
import random

from src import PROJECT_ROOT

SEED = 20261101
N_PASS = 10
PRIORITY = ("edgar_q057", "edgar_q033", "edgar_q055")
FIELDS = ["qid", "drafted_filter", "type", "question", "gold_chunk_text", "drafted_answer", "independent_answer", "failing_checks",
          "alt_source", "status", "decision", "corrected_answer", "corrected_type", "note"]


def order_rows(checks: list[dict], seed: int = SEED, n_pass: int = N_PASS) -> tuple[list[dict], list[str]]:
    """Return (rows in sheet order, qids of the sampled auto_pass rows)."""
    rng = random.Random(seed)
    passing = sorted(r["qid"] for r in checks if r["status"] == "auto_pass")
    sampled = sorted(rng.sample(passing, min(n_pass, len(passing))))
    chosen = [r for r in checks if r["status"] == "needs_review" or r["qid"] in sampled]
    first = sorted((r for r in chosen if r["A_number_in_chunk_any_type"] == "N"), key=lambda r: r["qid"])
    taken = {r["qid"] for r in first}
    for q in PRIORITY:
        r = next((x for x in chosen if x["qid"] == q and x["status"] == "needs_review"), None)
        if r and q not in taken:
            first.append(r)
            taken.add(q)
    rest = sorted((r for r in chosen if r["qid"] not in taken), key=lambda r: r["qid"])
    rng.shuffle(rest)
    return first + rest, sampled


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify-dir", required=True)
    ap.add_argument("--candidates", required=True)
    a = ap.parse_args()
    d = PROJECT_ROOT / a.verify_dir
    out = d / "review_sheet.csv"
    if out.exists():
        raise SystemExit(f"{out} exists; not overwriting")
    checks = list(csv.DictReader(open(d / "checks.csv", encoding="utf-8", newline="")))
    cands = {r["qid"]: r for r in csv.DictReader(open(PROJECT_ROOT / a.candidates, encoding="utf-8", newline=""))}
    if set(cands) != {r["qid"] for r in checks}:
        raise SystemExit("checks.csv and candidates.csv cover different qids")
    rows, sampled = order_rows(checks)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            c = cands[r["qid"]]
            w.writerow({"qid": r["qid"], "drafted_filter": c["filter"], "type": c["type"], "question": c["question"],
                        "gold_chunk_text": c["gold_chunk_text"], "drafted_answer": c["drafted_answer"],
                        "independent_answer": r["B_independent_answer"], "failing_checks": r["failing_checks"],
                        "alt_source": r["F_alt_source"], "status": r["status"], "decision": "", "corrected_answer": "",
                        "corrected_type": "", "note": ""})
    n_review = sum(r["status"] == "needs_review" for r in checks)
    print(f"{out}: {len(rows)} rows = {n_review} needs_review + {len(sampled)} auto_pass sampled {sampled}")


if __name__ == "__main__":
    main()
