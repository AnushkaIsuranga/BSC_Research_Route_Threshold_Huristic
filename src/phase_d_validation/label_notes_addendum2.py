"""Amendment 5 addendum 2: post-hoc note counts on the labelled copy with a note column (read-only; no model call, no DB access).

  python -m src.phase_d_validation.label_notes_addendum2 \
      --labelled outputs/hallucination_labels_addendum2_2026-10-23/labelling_sheet_check_with_notes.csv \
      --out-dir outputs/hallucination_labels_addendum2_2026-10-23 --report reports/hallucination_labels_addendum2_2026-10-23.md

Join by sample_id only (other columns of the labelled copy are ignored). Gate: the check / gold_derivable values must be identical,
row by row, to those used in 3c167ba (label_analysis/labelled_rows_joined.csv); any difference stops. Note topics use the keyword
rule of addendum 1 section 3 (NOTE_RULES in label_confusion.py). The addendum 1 confusion tables are copied verbatim from the
committed report of 3c167ba.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from src.phase_d_validation.label_confusion import NOTE_RULES, ORIG_COMMIT, ORIG_SHEET, PROXY

RESULT_COMMIT = "3c167ba"
JOINED = "outputs/hallucination_classification_2026-10-23/label_analysis/labelled_rows_joined.csv"
A1_REPORT = "reports/hallucination_labels_2026-10-23.md"
METHOD = "model-drafted labels verified by the author"


def git_blob(commit: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{commit}:{path}"], capture_output=True, check=True).stdout.decode("utf-8")


def dict_rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text, newline="")))


def join_and_check(labelled: list[dict], committed_ids: list[str], used: list[dict]) -> list[dict]:
    """Rows of `used` (3c167ba) with the note of `labelled` attached; raises ValueError on any id or label difference."""
    by = {}
    for r in labelled:
        if r["sample_id"] in by:
            raise ValueError(f"duplicate sample_id {r['sample_id']} in the labelled copy")
        by[r["sample_id"]] = r
    if sorted(by) != sorted(committed_ids) or [u["sample_id"] for u in used] != committed_ids:
        raise ValueError("sample_ids of the labelled copy, the committed sheet and the 3c167ba rows differ")
    if "note" not in labelled[0]:
        raise ValueError("labelled copy has no note column")
    out = []
    for u in used:
        r = by[u["sample_id"]]
        if (r["check"].strip().upper(), r["gold_derivable"].strip().upper()) != (u["scn"], u["gd"]):
            raise ValueError(f"{u['sample_id']}: labels {r['check']!r}/{r['gold_derivable']!r} differ from 3c167ba {u['scn']}/{u['gd']}")
        out.append({**u, "note": r["note"].strip()})
    return out


def topics(note: str) -> list[str]:
    return [t for t, pats in NOTE_RULES.items() if any(re.search(p, note, re.I) for p in pats)]


def note_counts(rows: list[dict]) -> dict:
    res = {"rows": len(rows), "distinct_questions": len({r["query_id"] for r in rows}),
           "rows_with_any_note": sum(1 for r in rows if r["note"]),
           "questions_with_any_note": len({r["query_id"] for r in rows if r["note"]}), "by_topic": {}}
    for t in list(NOTE_RULES) + ["any of the four", "other note only", "no note"]:
        if t == "any of the four":
            hit = [r for r in rows if topics(r["note"])]
        elif t == "other note only":
            hit = [r for r in rows if r["note"] and not topics(r["note"])]
        elif t == "no note":
            hit = [r for r in rows if not r["note"]]
        else:
            hit = [r for r in rows if t in topics(r["note"])]
        res["by_topic"][t] = {"rows": len(hit), "distinct_questions": len({r["query_id"] for r in hit}),
                              "rows_by_proxy_class": {c: sum(1 for r in hit if r["proxy"] == c) for c in PROXY},
                              "questions_by_proxy_class": {c: len({r["query_id"] for r in hit if r["proxy"] == c}) for c in PROXY},
                              "rows_by_scn": dict(sorted(Counter(r["scn"] for r in hit).items())),
                              "sample_ids": [r["sample_id"] for r in hit]}
    return res


def a1_tables(report: str) -> str:
    """The table sections of the addendum 1 report, verbatim, with headings relabelled by the labelling method."""
    start = report.index("## Per row (40 rows)")
    end = report.index("Within a proxy class, questions with rows")
    block = report[start:end].rstrip() + "\n"
    return block.replace("## Per row (40 rows)", f"### Per row, 40 rows ({METHOD})") \
                .replace("## Per distinct question", f"### Per distinct question ({METHOD})", 1)


def build_report(res: dict, a1_block: str) -> str:
    n = res["notes"]
    L: list[str] = []
    w = L.append
    w("# Amendment 5 addendum 2: note counts (post hoc), 2026-10-23\n")
    w("Governed by `docs/preregistration/PHASE_D_AMENDMENT_5_ADDENDUM_2.md` (tag `phase-d-amendment-5-addendum-2-2026-10-23`), **written after the Addendum 1 results "
      f"(commit `{RESULT_COMMIT}`) were computed; it changes none of them.** Labels are **{METHOD}**: drafted by a language model from a different model family than the "
      "answer model (Gemini 3.8 Flash), blind to the key file, with the calculation written per row, then checked row by row by the author. "
      "The note counts below are **post hoc and descriptive only**; the scoring rule is unchanged. No model call, no database access.\n")
    w("## Input and checks\n")
    w(f"- Labelled copy with notes: `{res['labelled_file']}` (SHA-256 `{res['labelled_file_sha256']}`), joined to the committed sheet (`{ORIG_COMMIT}`) by `sample_id` only; its other columns are ignored.")
    w(f"- `check` and `gold_derivable` identical to the labels used in `{RESULT_COMMIT}`: **{res['label_check']['identical']}/{res['label_check']['rows']} rows**.")
    w(f"- Rows with a note: {n['rows_with_any_note']} of {n['rows']} ({n['questions_with_any_note']} of {n['distinct_questions']} distinct questions).")
    w("- Topic rule (fixed in Addendum 1 section 3, case-insensitive): rounding = `round`; scale = `scale`/`million`/`thousand`; suspected gold error = `gold` with `error`/`wrong`/`incorrect`; "
      "count vs percentage = `count` with `percent`/`%`/`percentage`. A row can match more than one topic.\n")
    w("## Note counts (per row, 40; per distinct question, 17)\n")
    w("| topic | rows | of which wrong_ungrounded / wrong_grounded | S/C/N of those rows | distinct questions | of which wrong_ungrounded / wrong_grounded | sample_ids |")
    w("|---|---|---|---|---|---|---|")
    for t, d in n["by_topic"].items():
        rp, qp = d["rows_by_proxy_class"], d["questions_by_proxy_class"]
        scn = ", ".join(f"{k} {v}" for k, v in d["rows_by_scn"].items()) or "-"
        w(f"| {t} | {d['rows']} | {rp['wrong_ungrounded']} / {rp['wrong_grounded']} | {scn} | {d['distinct_questions']} | {qp['wrong_ungrounded']} / {qp['wrong_grounded']} | {', '.join(d['sample_ids'])} |")
    w("")
    w("Per-question counting as in Addendum 1: a question counts once in every row of the table in which one of its rows falls. \"other note only\" = a note that matches none of the four topics "
      "(e.g. ambiguous question wording, interpretation difference, gold not reproducible, unsupported number).\n")
    w(f"## Addendum 1 confusion tables (copied unchanged from `{A1_REPORT}`, commit `{RESULT_COMMIT}`, for reference)\n")
    w(f"Where that report says \"human labels\", read \"{METHOD}\".\n")
    w(a1_block)
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labelled", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    raw = Path(a.labelled).read_bytes()
    labelled = dict_rows(raw.decode("utf-8-sig"))
    committed_ids = [r["sample_id"] for r in dict_rows(git_blob(ORIG_COMMIT, ORIG_SHEET))]
    used = dict_rows(git_blob(RESULT_COMMIT, JOINED))
    rows = join_and_check(labelled, committed_ids, used)
    res = {"labelled_file": Path(a.labelled).as_posix(), "labelled_file_sha256": hashlib.sha256(raw).hexdigest(),
           "label_check": {"rows": len(rows), "identical": len(rows), "against": f"{RESULT_COMMIT}:{JOINED}"},
           "notes": note_counts(rows), "rows": [{k: r[k] for k in ("sample_id", "query_id", "proxy", "scn", "gd", "note")} | {"topics": topics(r["note"])} for r in rows]}
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "note_counts.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    Path(a.report).write_text(build_report(res, a1_tables(git_blob(RESULT_COMMIT, A1_REPORT))), encoding="utf-8")
    print(json.dumps({t: (d["rows"], d["distinct_questions"]) for t, d in res["notes"]["by_topic"].items()}, indent=1))


if __name__ == "__main__":
    main()
