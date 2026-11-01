"""Replace the outputs/data_checksums.json entries of figure/table files this session regenerated (figures-2026-11-01-v2).

  python -m src.figures.update_checksums --label <name> path [path ...]

Only paths under reports/figures_2026-11-01/ and reports/tables_2026-11-01/ that already have an entry are accepted; the old
entry is kept under the new entry's `previous` list and the replacement is recorded in `additions`. Every other entry is left
unchanged.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.phase_f_edgar.checksums import line_endings
from src.utils.freeze_checksums import sha256

ALLOWED = ("reports/figures_2026-11-01/", "reports/tables_2026-11-01/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--file", default="outputs/data_checksums.json")
    a = ap.parse_args()
    d = json.loads(Path(a.file).read_text(encoding="utf-8"))
    changed = []
    for p in map(Path, a.paths):
        key = p.as_posix()
        if not key.startswith(ALLOWED):
            raise SystemExit(f"{key} is outside {ALLOWED}")
        if key not in d["files"]:
            raise SystemExit(f"{key} has no entry to replace")
        old = d["files"][key]
        new = {"sha256": sha256(p), "bytes": p.stat().st_size, "line_endings": line_endings(p)}
        if new["sha256"] == old["sha256"]:
            continue
        new["previous"] = old.pop("previous", []) + [old]
        d["files"][key] = new
        changed.append(key)
        print(new["sha256"], f"{new['bytes']:>12,}", new["line_endings"], key)
    if changed:
        d.setdefault("additions", []).append({"label": a.label, "added_utc": datetime.now(timezone.utc).isoformat(), "replaced_paths": changed})
        Path(a.file).write_text(json.dumps(d, indent=2), encoding="utf-8")     # as src.phase_f_edgar.checksums writes it
    print(f"{len(changed)} entries replaced")


if __name__ == "__main__":
    main()
