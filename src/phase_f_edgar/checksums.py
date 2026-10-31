"""Append NEW Phase F entries to outputs/data_checksums.json, recording each file's line endings (existing entries are
never changed; an existing path is an error). Same format as src.utils.append_checksums plus a `line_endings` field
(LF, CRLF, mixed, or none) so that a later CRLF conversion is recognisable. The outputs/edgar_* folders are marked
-text in .gitattributes, so git stores and checks them out byte-for-byte.

  python -m src.phase_f_edgar.checksums --label <name> path [path ...]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.utils.freeze_checksums import sha256


def line_endings(path: Path) -> str:
    data = path.read_bytes()
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    if crlf and lf:
        return "mixed"
    return "CRLF" if crlf else ("LF" if lf else "none")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--file", default="outputs/data_checksums.json")
    a = ap.parse_args()
    d = json.loads(Path(a.file).read_text(encoding="utf-8"))
    new = {}
    for p in map(Path, a.paths):
        if not p.is_file():
            raise SystemExit(f"{p} is not a file")
        key = p.as_posix()
        if key in d["files"]:
            raise SystemExit(f"{key} already has an entry; existing entries are not changed")
        new[key] = {"sha256": sha256(p), "bytes": p.stat().st_size, "line_endings": line_endings(p)}
    d["files"].update(new)
    d.setdefault("additions", []).append({"label": a.label, "added_utc": datetime.now(timezone.utc).isoformat(), "paths": sorted(new)})
    d["n_files"] = len(d["files"])
    Path(a.file).write_text(json.dumps(d, indent=2), encoding="utf-8")
    for k, v in new.items():
        print(f"{v['sha256']}  {v['bytes']:>12,}  {v['line_endings']:<5}  {k}")


if __name__ == "__main__":
    main()
