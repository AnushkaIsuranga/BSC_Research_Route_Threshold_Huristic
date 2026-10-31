"""Phase F evaluation, Task 0: statistics snapshot of edgar_chunks before and after VACUUM ANALYZE, and a VecAdvisor 0.1.0a6
visibility check (no paid calls).

  python -m src.phase_f_edgar.eval_preflight --out-dir outputs/edgar_eval_preflight_2026-11-01

Writes stats.json (UTF-8, LF): reltuples, n_live_tup, n_dead_tup, last (auto)analyze, pg_stats rows for cik / fiscal_year /
section, extended statistics, before and after; and vecadvisor.json (version, whether analyze lists edgar_chunks_embedding_idx).
The DSN is redacted in everything written.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_f_edgar import common as C

VECADVISOR = PROJECT_ROOT / ".venv-vecadvisor/Scripts/vecadvisor.exe"
VECADVISOR_PY = PROJECT_ROOT / ".venv-vecadvisor/Scripts/python.exe"
COLUMNS = ("cik", "fiscal_year", "section")


def snapshot(cur) -> dict:
    cur.execute("SELECT reltuples FROM pg_class WHERE oid = %s::regclass", (C.TABLE,))
    (reltuples,) = cur.fetchone()
    cur.execute("SELECT n_live_tup, n_dead_tup, last_analyze, last_autoanalyze, last_vacuum, last_autovacuum "
                "FROM pg_stat_user_tables WHERE relname = %s", (C.TABLE,))
    live, dead, la, laa, lv, lav = cur.fetchone()
    cur.execute("SELECT count(*) FROM " + C.TABLE)
    (n,) = cur.fetchone()
    stats = {}
    for col in COLUMNS:
        cur.execute("SELECT n_distinct, null_frac, cardinality(most_common_vals::text::text[]) FROM pg_stats "
                    "WHERE tablename = %s AND attname = %s", (C.TABLE, col))
        r = cur.fetchone()
        stats[col] = None if r is None else {"present": True, "n_distinct": r[0], "null_frac": r[1], "n_mcv": r[2]}
    cur.execute("SELECT s.stxname, s.stxkind::text, d.stxdndistinct IS NOT NULL, d.stxddependencies IS NOT NULL, "
                "d.stxdmcv IS NOT NULL FROM pg_statistic_ext s LEFT JOIN pg_statistic_ext_data d ON d.stxoid = s.oid "
                "WHERE s.stxrelid = %s::regclass ORDER BY s.stxname", (C.TABLE,))
    ext = [{"name": a, "kinds": b, "ndistinct": c, "dependencies": d, "mcv": e} for a, b, c, d, e in cur.fetchall()]
    iso = lambda t: t.isoformat() if t else None
    return {"utc": datetime.now(timezone.utc).isoformat(), "count_star": n, "reltuples": reltuples, "n_live_tup": live,
            "n_dead_tup": dead, "last_analyze": iso(la), "last_autoanalyze": iso(laa), "last_vacuum": iso(lv),
            "last_autovacuum": iso(lav), "pg_stats": stats, "pg_stats_rows_for_all": all(stats.values()),
            "extended_statistics": ext}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    s = db_settings()
    conn = psycopg2.connect(**s)
    conn.autocommit = True
    cur = conn.cursor()
    before = snapshot(cur)
    cur.execute(f"VACUUM ANALYZE {C.TABLE}")
    after = snapshot(cur)
    (out / "stats.json").write_text(json.dumps({"table": C.TABLE, "command": f"VACUUM ANALYZE {C.TABLE};", "before": before,
                                                "after": after}, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"before": before, "after": after}, indent=1, default=str))

    dsn = f"postgresql://{s['user']}:{s['password']}@{s['host']}:{s['port']}/{s['dbname']}"
    redact = lambda t: t.replace(dsn, f"postgresql://***:***@{s['host']}:{s['port']}/{s['dbname']}").replace(s["password"], "***")
    imp = subprocess.run([str(VECADVISOR_PY), "-I", "-c", "import vecadvisor, importlib.metadata as m; print(m.version('vecadvisor'))"],
                         capture_output=True, text=True)
    r = subprocess.run([str(VECADVISOR), "analyze", "--dsn", dsn, "--table", C.TABLE, "--vector", "embedding"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"vecadvisor analyze exited {r.returncode}: {redact(r.stderr)[:500]}")
    d = json.loads(r.stdout)
    idx = [i for i in d.get("indexes", []) if "embedding_idx" in json.dumps(i)]
    res = {"import_ok": imp.returncode == 0, "version": imp.stdout.strip(), "import_stderr": redact(imp.stderr)[:500],
           "analyze_rows": d.get("rows"), "vector_dim": d.get("vector_dim"), "sees_embedding_idx": bool(idx), "embedding_idx": idx,
           "stats_health": d.get("stats_health")}
    (out / "vecadvisor.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8", newline="\n")
    (out / "vecadvisor_analyze_raw.json").write_text(redact(r.stdout), encoding="utf-8", newline="\n")
    print(json.dumps({k: res[k] for k in ("import_ok", "version", "analyze_rows", "vector_dim", "sees_embedding_idx")}, indent=1))


if __name__ == "__main__":
    main()
