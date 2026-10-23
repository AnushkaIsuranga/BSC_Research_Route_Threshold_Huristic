"""Build labelling_sheet_v2.csv: the committed original labelling sheet plus an empty last column `gold_derivable`
(Amendment 5, addendum 1). Source = the committed original (not the working-tree file), verified against the SHA-256 registered
in outputs/data_checksums.json; verification of byte-identity apart from the new column is done before the file is written.

  python -m src.phase_d_validation.make_labelling_sheet_v2 --out outputs/hallucination_classification_2026-10-23/labelling_sheet_v2.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

SOURCE_COMMIT = "5327010"
SHEET = "outputs/hallucination_classification_2026-10-23/labelling_sheet.csv"
NEW_COLUMN = "gold_derivable"


def serialise(rows: list[list[str]]) -> bytes:
    """Same writer settings as the original sheet (csv default: minimal quoting, CRLF record terminator)."""
    out = io.StringIO(newline="")
    csv.writer(out).writerows(rows)
    return out.getvalue().encode("utf-8")


def parse(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))


def add_column(rows: list[list[str]]) -> list[list[str]]:
    if rows[0][-1] == NEW_COLUMN:
        raise ValueError("column already present")
    return [rows[0] + [NEW_COLUMN]] + [r + [""] for r in rows[1:]]


def drop_last_column(rows: list[list[str]]) -> list[list[str]]:
    return [r[:-1] for r in rows]


def verify(original_rows: list[list[str]], v2_rows: list[list[str]], registered_sha: str | None = None) -> dict:
    orig_bytes = serialise(original_rows)
    back_bytes = serialise(drop_last_column(v2_rows))
    checks = {
        "header_is_original_plus_new_column": v2_rows[0] == original_rows[0] + [NEW_COLUMN],
        "same_number_of_rows": len(v2_rows) == len(original_rows),
        "every_original_field_identical": all(v[:-1] == o for v, o in zip(v2_rows, original_rows)),
        "new_column_empty": all(r[-1] == "" for r in v2_rows[1:]),
        "row_order_unchanged": [r[0] for r in v2_rows] == [r[0] for r in original_rows],
        "v2_minus_new_column_is_byte_identical_to_original": back_bytes == orig_bytes,
    }
    if registered_sha is not None:
        checks["original_reserialises_to_registered_sha256"] = hashlib.sha256(orig_bytes).hexdigest() == registered_sha
    return checks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists; not overwriting")
    registered = json.loads(Path("outputs/data_checksums.json").read_text(encoding="utf-8"))["files"][SHEET]["sha256"]
    blob = subprocess.run(["git", "show", f"{SOURCE_COMMIT}:{SHEET}"], capture_output=True, check=True).stdout
    original = parse(blob)
    v2 = add_column(original)
    checks = verify(original, v2, registered)
    if not all(checks.values()):
        raise SystemExit(f"verification failed, nothing written: {checks}")
    out.write_bytes(serialise(v2))
    written = parse(out.read_bytes())
    again = verify(original, written, registered)
    if not all(again.values()):
        out.unlink()
        raise SystemExit(f"verification of the written file failed, removed: {again}")
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    print(json.dumps({"out": out.as_posix(), "sha256": sha, "rows": len(written) - 1, "columns": written[0], "registered_original_sha256": registered,
                      "checks": again}, indent=2))


if __name__ == "__main__":
    main()
