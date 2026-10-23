"""Amendment 5 + addendum 1: confusion tables of the proxy class against the human labels (read-only; no model call, no DB access).

  python -m src.phase_d_validation.label_confusion --labelled outputs/hallucination_classification_2026-10-23/labelling_sheet_check.csv \
      --key outputs/hallucination_classification_2026-10-23/labelling_key.csv --out-dir outputs/hallucination_classification_2026-10-23/label_analysis

Gate: the labelled copy is verified against the committed original sheet (git blob) before use: sample_id, question and
retrieved_passages must be identical; gold_answer / model_answer may differ only by numeric formatting (every differing cell must
be numerically equivalent); same rows in the same order. Accepted label values: check in {S, C, N}, gold_derivable in {Y, N};
anything else stops the analysis. Tables: (1) proxy class x S/C/N (+ supported/unsupported), (2) proxy class x gold_derivable;
each per row (40) and per distinct question (a question counts once in every (class, label) cell where one of its rows falls).
Rows with notes mentioning rounding, scale, a suspected gold error or a count-vs-percentage mismatch are counted separately
(only if the file has a note column).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from src.phase_d_validation.paired_stats import wilson

PROXY = ("wrong_ungrounded", "wrong_grounded")
SCN = ("S", "C", "N")
GD = ("Y", "N")
ORIG_COMMIT = "5327010"
ORIG_SHEET = "outputs/hallucination_classification_2026-10-23/labelling_sheet.csv"
REGISTERED_SHA = "84b841fc5e5dd11388a3fc8ada7cc10efe915731b645806097d94001b70694ed"
NOTE_RULES = {"rounding": [r"round"], "scale": [r"scale", r"million", r"thousand"],
              "suspected gold error": [r"gold.*(error|wrong|incorrect)", r"(error|wrong|incorrect).*gold"],
              "count vs percentage": [r"count.*(percent|%|percentage)", r"(percent|%|percentage).*count"]}


def read_csv(data: bytes | str) -> list[list[str]]:
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    return list(csv.reader(io.StringIO(text, newline="")))


def number(s: str):
    s = s.strip().replace(" ", "").replace(",", "").replace("$", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    pct = s.endswith("%")
    s = s.rstrip("%")
    try:
        v = float(s)
    except ValueError:
        return None
    return (-v if neg else v), pct


def verify_labelled_copy(chk: list[list[str]], orig: list[list[str]]) -> dict:
    """Raises ValueError if the labelled copy cannot be used."""
    cols = orig[0]
    if chk[0][:len(cols)] != cols:
        raise ValueError(f"labelled copy header {chk[0][:len(cols)]} does not start with the original header {cols}")
    if len(chk) != len(orig) or [r[0] for r in chk] != [r[0] for r in orig]:
        raise ValueError("labelled copy has different rows or row order")
    report = {"rows": len(orig) - 1, "identical_columns": {}, "formatting_only_cells": []}
    for j, c in enumerate(cols):
        diffs = [i for i in range(1, len(orig)) if orig[i][j] != chk[i][j]]
        report["identical_columns"][c] = len(orig) - 1 - len(diffs)
        if not diffs:
            continue
        if c not in ("gold_answer", "model_answer"):
            raise ValueError(f"column {c} differs from the committed sheet in rows {diffs[:5]}; only number formatting may differ")
        for i in diffs:
            a, b = number(orig[i][j]), number(chk[i][j])
            if a is None or b is None or abs(a[0] - b[0]) > 1e-9 or a[1] != b[1]:
                raise ValueError(f"{c} of {orig[i][0]} differs by more than formatting: {orig[i][j]!r} vs {chk[i][j]!r}")
            report["formatting_only_cells"].append({"sample_id": orig[i][0], "column": c, "committed": orig[i][j], "labelled_copy": chk[i][j]})
    return report


def load_labels(chk: list[list[str]]) -> dict[str, dict]:
    h = chk[0]
    need = ("check", "gold_derivable")
    for n in need:
        if n not in h:
            raise ValueError(f"column {n!r} missing in the labelled copy")
    ic, ig = h.index("check"), h.index("gold_derivable")
    note_cols = [i for i, n in enumerate(h) if n.strip().lower() in ("note", "notes", "comment", "comments")]
    out = {}
    for r in chk[1:]:
        s, g = r[ic].strip().upper(), r[ig].strip().upper()
        if s not in SCN:
            raise ValueError(f"{r[0]}: invalid check value {r[ic]!r} (accepted: S, C, N)")
        if g not in GD:
            raise ValueError(f"{r[0]}: invalid gold_derivable value {r[ig]!r} (accepted: Y, N)")
        out[r[0]] = {"scn": s, "gd": g, "note": " ".join(r[i] for i in note_cols).strip() if note_cols else None}
    return out


def share(k: int, n: int) -> dict:
    lo, hi = wilson(k, n) if n else (None, None)
    return {"n": k, "of": n, "share": (k / n) if n else None, "ci95": [lo, hi]}


def tables(rows: list[dict]) -> dict:
    """rows: dicts with query_id, proxy, scn, gd. Returns per-row and per-distinct-question tables."""
    out = {"per_row": {}, "per_question": {}}
    for name, field, vals in (("proxy_x_scn", "scn", SCN), ("proxy_x_gold_derivable", "gd", GD)):
        pr, pq = {}, {}
        for cls in PROXY:
            sub = [r for r in rows if r["proxy"] == cls]
            pr[cls] = {"rows": len(sub), "cells": {v: share(sum(1 for r in sub if r[field] == v), len(sub)) for v in vals}}
            qs = {r["query_id"] for r in sub}
            pq[cls] = {"distinct_questions": len(qs),
                       "cells": {v: share(len({r["query_id"] for r in sub if r[field] == v}), len(qs)) for v in vals}}
        out["per_row"][name], out["per_question"][name] = pr, pq
    sup = {}
    for per, key in (("per_row", None), ("per_question", None)):
        sup[per] = {}
        for cls in PROXY:
            sub = [r for r in rows if r["proxy"] == cls]
            if per == "per_row":
                k = sum(1 for r in sub if r["scn"] in ("S", "C"))
                sup[per][cls] = {"unsupported_N": share(len(sub) - k, len(sub)), "supported_S_or_C": share(k, len(sub)), "rows": len(sub)}
            else:
                qs = {r["query_id"] for r in sub}
                kq = {r["query_id"] for r in sub if r["scn"] in ("S", "C")}
                nq = {r["query_id"] for r in sub if r["scn"] == "N"}
                sup[per][cls] = {"unsupported_N": share(len(nq), len(qs)), "supported_S_or_C": share(len(kq), len(qs)), "distinct_questions": len(qs)}
    out["supported_vs_unsupported"] = sup
    # questions whose rows disagree within a proxy class (for transparency)
    by = defaultdict(lambda: defaultdict(set))
    for r in rows:
        by[(r["proxy"], r["query_id"])]["scn"].add(r["scn"])
        by[(r["proxy"], r["query_id"])]["gd"].add(r["gd"])
    out["questions_with_mixed_labels_within_class"] = {"scn": sum(1 for v in by.values() if len(v["scn"]) > 1), "gold_derivable": sum(1 for v in by.values() if len(v["gd"]) > 1),
                                                      "question_class_pairs": len(by)}
    return out


def note_counts(rows: list[dict]) -> dict:
    if not rows or rows[0].get("note") is None:
        return {"available": False, "reason": "the labelled file has no note column (its check column holds one letter per row)"}
    res = {"available": True, "rows_with_any_note": sum(1 for r in rows if r["note"]), "by_topic": {}}
    for topic, pats in NOTE_RULES.items():
        hit = [r for r in rows if any(re.search(p, r["note"] or "", re.I) for p in pats)]
        res["by_topic"][topic] = {"rows": len(hit), "distinct_questions": len({r["query_id"] for r in hit}),
                                  "by_proxy_class": dict(Counter(r["proxy"] for r in hit))}
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labelled", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    blob = subprocess.run(["git", "show", f"{ORIG_COMMIT}:{ORIG_SHEET}"], capture_output=True, check=True).stdout
    orig = read_csv(blob)
    buf = io.StringIO(newline="")
    csv.writer(buf).writerows(orig)
    if hashlib.sha256(buf.getvalue().encode("utf-8")).hexdigest() != REGISTERED_SHA:
        raise SystemExit("committed original sheet does not re-serialise to the registered SHA-256; stopping")
    chk_bytes = Path(a.labelled).read_bytes()
    chk = read_csv(chk_bytes)
    verification = verify_labelled_copy(chk, orig)
    labels = load_labels(chk)
    key = list(csv.DictReader(open(a.key, encoding="utf-8", newline="")))
    if [k["sample_id"] for k in key] != [r[0] for r in orig[1:]]:
        raise SystemExit("key file rows differ from the sheet")
    rows = [{"sample_id": k["sample_id"], "query_id": k["query_id"], "arm": k["arm"], "proxy": k["proxy_class"], **labels[k["sample_id"]]} for k in key]
    result = {"labelled_file": a.labelled, "labelled_file_sha256": hashlib.sha256(chk_bytes).hexdigest(), "verification": verification,
              "n_rows": len(rows), "n_distinct_questions": len({r["query_id"] for r in rows}),
              "proxy_class_counts_rows": dict(Counter(r["proxy"] for r in rows)),
              "tables": tables(rows), "notes": note_counts(rows)}
    (out / "label_confusion.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (out / "labelled_rows_joined.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sample_id", "query_id", "arm", "proxy", "scn", "gd", "note"])
        w.writeheader()
        w.writerows(rows)
    print(json.dumps({k: result[k] for k in ("n_rows", "n_distinct_questions", "proxy_class_counts_rows")}, indent=1))


if __name__ == "__main__":
    main()
