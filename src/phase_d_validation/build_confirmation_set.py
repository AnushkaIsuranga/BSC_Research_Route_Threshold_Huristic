"""Amendment 4 confirmation set: the 1,097 pool questions not in the frozen 50, minus every question whose gold answer the
frozen gold-answer parser cannot parse (excluded iff `score_answer` would raise on the gold value: not a boolean word and
`parse_financial_number(gold, strip_scale=True)` raises). The rule depends only on the gold answer, never on any arm or
model output. Read-only on inputs; writes a new folder.

  python -m src.phase_d_validation.build_confirmation_set --in outputs/scaleup_checks_2026-10-13/confirmation_subset.csv \
      --out-dir outputs/scaleup_confirmation_2026-10-13
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from src.phase_d_validation.scoring import UnparseableNumber, _bool_word, parse_financial_number


def reason(g: str) -> str:
    if not g.strip():
        return "empty gold answer"
    if ":" in g and len(g) < 15:
        return "ratio written as a:b"
    if len(g.split()) > 4:
        return "gold answer is a sentence"
    return "number with extra words"


def unparseable(g: str, strip: bool) -> bool:
    if _bool_word(g) is not None:
        return False
    try:
        parse_financial_number(g, strip_scale=strip)
        return False
    except UnparseableNumber:
        return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = Path(a.out_dir)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty")
    out.mkdir(parents=True)
    rows = list(csv.DictReader(open(a.inp, encoding="utf-8")))
    data = {e["id"]: e for e in json.loads(Path("data/raw/finqa_test.json").read_text(encoding="utf-8"))}
    keep, excl = [], []
    for r in rows:
        if unparseable(r["answer"], strip=True):
            excl.append({"id": r["id"], "gold_answer": r["answer"], "reason": reason(r["answer"]), "breadth": r["breadth"],
                         "finqa_exe_ans": data[r["id"]]["qa"]["exe_ans"]})
        else:
            keep.append(r)
    with (out / "confirmation_1075.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(keep)
    with (out / "excluded_unparseable_gold.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(excl[0]))
        w.writeheader()
        w.writerows(excl)
    strict_extra = [r["id"] for r in keep if unparseable(r["answer"], strip=False)]
    summary = {"input": a.inp, "input_rows": len(rows), "excluded": len(excl), "kept": len(keep),
               "kept_strata": dict(Counter(r["breadth"] for r in keep)), "excluded_strata": dict(Counter(e["breadth"] for e in excl)),
               "excluded_reasons": dict(Counter(e["reason"] for e in excl)),
               "kept_with_gold_parseable_only_under_primary_rule": strict_extra,
               "confirmation_1075_sha256": hashlib.sha256((out / "confirmation_1075.csv").read_bytes()).hexdigest()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
