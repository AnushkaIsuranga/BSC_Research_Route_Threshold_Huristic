"""Write outputs/data_checksums.json: SHA-256 and size of every file under outputs/ (DB dumps and result
files included), excluding the checksum file itself. Refuses to overwrite an existing checksum file.

  python -m src.utils.freeze_checksums [--out outputs/data_checksums.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="outputs/data_checksums.json")
    ap.add_argument("--root", default="outputs")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists; not overwriting")
    files = {}
    for p in sorted(Path(a.root).rglob("*")):
        if p.is_file() and p.resolve() != out.resolve() and "__pycache__" not in p.parts:
            files[p.as_posix()] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    out.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "root": a.root, "n_files": len(files),
                               "files": files}, indent=2), encoding="utf-8")
    print(f"{len(files)} files hashed -> {out}")


if __name__ == "__main__":
    main()
