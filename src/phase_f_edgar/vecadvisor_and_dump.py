"""Task 3 (Phase F), last steps: VecAdvisor `analyze` on edgar_chunks (read-only, from .venv-vecadvisor) and a pg_dump of
edgar_chunks only (custom format; git-ignored like the other dumps, sha256 in outputs/data_checksums.json).

  python -m src.phase_f_edgar.vecadvisor_and_dump --out-dir outputs/edgar_vecadvisor_2026-10-31 \
      --dump-dir outputs/db_dumps_edgar_2026-10-31

The DSN is built from the .env settings and redacted (user and password -> ***) in everything written.
"""

from __future__ import annotations

import argparse
import json
import subprocess

from src import PROJECT_ROOT, db_settings
from src.phase_f_edgar import common as C

VECADVISOR = PROJECT_ROOT / ".venv-vecadvisor/Scripts/vecadvisor.exe"
CONTAINER = "vector_db"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--dump-dir", required=True)
    ap.add_argument("--container", default=CONTAINER)
    a = ap.parse_args()
    out, dump_dir = PROJECT_ROOT / a.out_dir, PROJECT_ROOT / a.dump_dir
    out.mkdir(parents=True, exist_ok=False)
    dump_dir.mkdir(parents=True, exist_ok=False)
    s = db_settings()
    dsn = f"postgresql://{s['user']}:{s['password']}@{s['host']}:{s['port']}/{s['dbname']}"
    redact = lambda t: t.replace(dsn, f"postgresql://***:***@{s['host']}:{s['port']}/{s['dbname']}").replace(s["password"], "***")

    version = subprocess.run([str(VECADVISOR), "--version"], capture_output=True, text=True, check=True).stdout.strip()
    r = subprocess.run([str(VECADVISOR), "analyze", "--dsn", dsn, "--table", C.TABLE, "--vector", "embedding"],
                       capture_output=True, text=True, encoding="utf-8")
    (out / "version.txt").write_text(version + "\n", encoding="utf-8", newline="\n")
    (out / "analyze_edgar_chunks.json").write_text(redact(r.stdout), encoding="utf-8", newline="\n")
    if r.stderr.strip():
        (out / "analyze_edgar_chunks.stderr.txt").write_text(redact(r.stderr), encoding="utf-8", newline="\n")
    if r.returncode != 0:
        raise SystemExit(f"vecadvisor analyze exited {r.returncode}; see {out}")
    d = json.loads(r.stdout)
    print(json.dumps({"version": version, "rows": d.get("rows"), "vector_dim": d.get("vector_dim"),
                      "indexes": d.get("indexes")}, indent=1, default=str))

    tmp = f"/tmp/{C.TABLE}.dump"
    subprocess.run(["docker", "exec", a.container, "pg_dump", "-U", s["user"], "-d", s["dbname"], "-Fc", "-t", C.TABLE, "-f", tmp],
                   check=True)
    subprocess.run(["docker", "cp", f"{a.container}:{tmp}", str(dump_dir / f"{C.TABLE}.dump")], check=True)
    subprocess.run(["docker", "exec", a.container, "rm", tmp], check=True)
    print(f"dump: {dump_dir / f'{C.TABLE}.dump'} ({(dump_dir / f'{C.TABLE}.dump').stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
