"""Append NEW entries to outputs/data_checksums.json (existing entries are never changed; an existing path is an error).

  python -m src.utils.append_checksums --label <name> path [path ...]
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.utils.freeze_checksums import sha256

ap = argparse.ArgumentParser()
ap.add_argument("--label", required=True)
ap.add_argument("paths", nargs="+")
ap.add_argument("--file", default="outputs/data_checksums.json")
a = ap.parse_args()
d = json.loads(Path(a.file).read_text(encoding="utf-8"))
new = {}
for p in a.paths:
    p = Path(p)
    if not p.is_file():
        raise SystemExit(f"{p} is not a file")
    key = p.as_posix()
    if key in d["files"]:
        raise SystemExit(f"{key} already has an entry; existing entries are not changed")
    new[key] = {"sha256": sha256(p), "bytes": p.stat().st_size}
d["files"].update(new)
d.setdefault("additions", []).append({"label": a.label, "added_utc": datetime.now(timezone.utc).isoformat(), "paths": sorted(new)})
d["n_files"] = len(d["files"])
Path(a.file).write_text(json.dumps(d, indent=2), encoding="utf-8")
for k, v in new.items():
    print(f"{v['sha256']}  {v['bytes']:>12,}  {k}")
