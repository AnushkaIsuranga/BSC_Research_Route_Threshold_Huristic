"""Phase F Task 6: join the author's checked labels to the drafted label sheet.

  python -m src.phase_f_edgar.join_labels_edgar --out-dir outputs/edgar_analysis_labels_joined_2026-11-01

Only sample_id, author_label and author_note are taken from the author's file (Excel reformatted some data cells when it was
saved); every other column comes from the original sheet. Stops unless the two files hold the same 40 sample_ids and every
author_label is S, C, N or X (X = refusal, added by the author; DEVIATION_LOG.md 2026-11-01).
"""

from __future__ import annotations

import argparse
import csv

from src import PROJECT_ROOT

ORIGINAL = "outputs/edgar_analysis_2026-11-01/label_sheet.csv"
AUTHOR = "outputs/edgar_analysis_review_2026-11-01/label_sheet_author.csv"
LABELS = ("S", "C", "N", "X")
N_ROWS = 40


def read_csv(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def join(original: list[dict], author: list[dict], n_rows: int = N_ROWS) -> list[dict]:
    """Original rows with author_label / author_note from the author's rows (matched on sample_id); raises ValueError."""
    ids_o = [r["sample_id"] for r in original]
    ids_a = [r["sample_id"].strip() for r in author]
    if len(ids_o) != n_rows or len(ids_a) != n_rows or len(set(ids_a)) != n_rows or set(ids_o) != set(ids_a):
        raise ValueError(f"sample_ids differ: original {len(ids_o)}, author {len(ids_a)} ({len(set(ids_a))} distinct), "
                         f"only original {sorted(set(ids_o) - set(ids_a))}, only author {sorted(set(ids_a) - set(ids_o))}")
    by_id = {r["sample_id"].strip(): r for r in author}
    bad = {i: r["author_label"] for i, r in by_id.items() if r["author_label"].strip() not in LABELS}
    if bad:
        raise ValueError(f"author_label not in {LABELS}: {bad}")
    return [{**r, "author_label": by_id[r["sample_id"]]["author_label"].strip(), "author_note": by_id[r["sample_id"]]["author_note"].strip()}
            for r in original]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    original = read_csv(PROJECT_ROOT / ORIGINAL)
    rows = join(original, read_csv(PROJECT_ROOT / AUTHOR))
    with open(out / "label_sheet_joined.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(original[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    changed = [(r["sample_id"], r["drafted_label"], r["author_label"]) for r in rows if r["drafted_label"] != r["author_label"]]
    print(f"{len(rows)} rows joined; changed from the draft: {changed}")


if __name__ == "__main__":
    main()
