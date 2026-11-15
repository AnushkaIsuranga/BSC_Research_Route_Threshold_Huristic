"""Phase G (Amendment 12 & Addenda 1-2): Straddle-T retrieval-only runner.

Reuses V.retrieve() (src/phase_e_router/policy_v3_1.py), R.retrieve() (src/phase_e_router/retriever.py),
and src/phase_f_edgar/vecadvisor_adapter.py without modifying any existing file.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import random
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import PROJECT_ROOT, db_settings
from src.phase_e_router import policy_v3 as P
from src.phase_e_router import policy_v3_1 as V
from src.phase_e_router import retriever as R
from src.phase_e_router.cells import env_meta, git
from src.phase_f_edgar import session_tools as S
from src.phase_f_edgar import vecadvisor_adapter as VA

K = 15
TIMED_REPS = 5
EDGAR_TABLE = "edgar_chunks"
FINQA_TABLE = "finqa_evidence_qwen3"
STATS_TABLES = ("edgar_chunks", "finqa_evidence", "finqa_evidence_qwen3")

MANIFEST_DIR = PROJECT_ROOT / "outputs/straddle_t_manifest_2026-11-15"
MANIFEST_SETS = {
    "primary": [
        "edgar_pairs_primary_T_edgar.csv",
        "finqa_pairs_primary_T_hm.csv",
    ],
    "secondary": [
        "edgar_pairs_secondary_T_hm.csv",
        "finqa_pairs_secondary_random.csv",
    ],
    "sensitivity": [
        "natural_only_edgar_T_edgar.csv",
        "natural_only_edgar_T_hm.csv",
        "natural_only_finqa_T_hm.csv",
    ],
    "smoke": [
        "smoke_test_pairs.csv",
    ],
}
MANIFEST_SETS["union"] = (
    MANIFEST_SETS["primary"] + MANIFEST_SETS["secondary"] + MANIFEST_SETS["sensitivity"]
)

FINQA_VECTOR_FILES = (
    (
        "outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json",
        "930cadc0bdea177b0951a6891c227606cc47a3b4a1ce8c437563635f9be9ff23",
    ),
    (
        "outputs/embedding_build_2026-10-13/query_embeddings_qwen3_confirmation_1075.json",
        "c5215bea79bbd486b084d276a0bc2a5e1fb632a8e66a6ae3385f16d4bc7f36ea",
    ),
    (
        "outputs/straddle_t_vectors_2026-11-15/query_embeddings_qwen3_missing2.json",
        "a17ae419606b209e407b07cc3323311ff6ce5bbb4a112331cd09d31bb8e70b3e",
    ),
)

SHOW_GUCS = (
    "hnsw.ef_search",
    "hnsw.iterative_scan",
    "hnsw.max_scan_tuples",
    "hnsw.scan_mem_multiplier",
    "enable_indexscan",
    "enable_seqscan",
    "enable_bitmapscan",
    "enable_sort",
    "jit",
    "statement_timeout",
)

FIXED_ARMS = ("always_exact", "default_hnsw", "always_iterative", "vecadvisor")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest_checksums(manifest_dir: Path = MANIFEST_DIR, root: Path = PROJECT_ROOT) -> dict[str, str]:
    ck_file = manifest_dir / "MANIFEST_CHECKSUMS.txt"
    if not ck_file.exists():
        raise RuntimeError(f"Missing MANIFEST_CHECKSUMS.txt at {ck_file}")
    verified = {}
    for line in ck_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        expected, rel_path = line.split(None, 1)
        target = root / rel_path
        if not target.exists():
            raise RuntimeError(f"Checksummed file missing: {rel_path}")
        actual = sha256_file(target)
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch for {rel_path}: {actual} != {expected}")
        verified[rel_path] = actual
    return verified


def resolve_manifest_files(manifests_arg: str) -> tuple[list[str], list[str]]:
    names = [x.strip() for x in manifests_arg.split(",") if x.strip()]
    if not names:
        raise ValueError("No manifest set specified")
    files = []
    for n in names:
        if n not in MANIFEST_SETS:
            raise ValueError(f"Unknown manifest set {n!r}; allowed: {sorted(MANIFEST_SETS)}")
        for f in MANIFEST_SETS[n]:
            if f not in files:
                files.append(f)
    return names, files


def validate_quiet_rule_flag(manifest_sets: list[str], skip_quiet_rule: bool) -> None:
    if skip_quiet_rule and manifest_sets != ["smoke"]:
        raise ValueError("--skip-quiet-rule is allowed ONLY for --manifests smoke")


def load_manifest_rows(manifest_files: list[str], manifest_dir: Path = MANIFEST_DIR) -> list[dict[str, Any]]:
    rows = []
    for fname in manifest_files:
        path = manifest_dir / fname
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                rec = dict(r)
                rec["manifest"] = fname
                rec["n_rows"] = int(r["n_rows"])
                rec["s"] = float(r["s"])
                rec["T_value"] = float(r["T_value"])
                rec["table"] = EDGAR_TABLE if r["qid"].startswith("edgar_") else FINQA_TABLE
                rows.append(rec)
    return rows


def build_configs() -> dict[str, R.RouterConfig]:
    cfg_edgar = R.RouterConfig.load("config/router_edgar.json", require_policy=True)
    cfg_edgar_hm = R.RouterConfig.load(
        "config/router_edgar.json",
        policy_path="config/policy_v3_1_hm.json",
        require_policy=True,
    )
    base_raw = json.loads((PROJECT_ROOT / "config/router_edgar.json").read_text(encoding="utf-8"))
    finqa_raw = {
        **base_raw,
        "tables": [FINQA_TABLE],
        "filter_columns": ["metadata->>'ticker'", "metadata->>'year'"],
        "policy_file": "config/policy_v3_1_hm.json",
    }
    cfg_finqa_hm = R.RouterConfig(finqa_raw)
    pol_hm = json.loads((PROJECT_ROOT / "config/policy_v3_1_hm.json").read_text(encoding="utf-8"))
    cfg_finqa_hm.T_default = pol_hm["T_default"]
    cfg_finqa_hm.T_tuned = pol_hm["T_tuned"]
    return {
        "edgar_T_edgar": cfg_edgar,
        "edgar_T_hm": cfg_edgar_hm,
        "finqa_T_hm": cfg_finqa_hm,
    }


def parse_edgar_filter(where_clause: str) -> list[list[Any]]:
    filters: list[list[Any]] = []
    m_cik_eq = re.search(r"cik\s*=\s*'([^']+)'", where_clause)
    m_cik_in = re.search(r"cik\s+IN\s*\(([^)]+)\)", where_clause)
    if m_cik_eq:
        filters.append(["cik", [m_cik_eq.group(1)]])
    elif m_cik_in:
        filters.append(["cik", re.findall(r"'([^']+)'", m_cik_in.group(1))])

    m_fy_eq = re.search(r"fiscal_year\s*=\s*(\d+)", where_clause)
    m_fy_in = re.search(r"fiscal_year\s+IN\s*\(([^)]+)\)", where_clause)
    m_fy_bw = re.search(r"fiscal_year\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)", where_clause)
    if m_fy_eq:
        filters.append(["fiscal_year", [int(m_fy_eq.group(1))]])
    elif m_fy_in:
        filters.append(["fiscal_year", [int(x) for x in re.findall(r"\d+", m_fy_in.group(1))]])
    elif m_fy_bw:
        y1, y2 = int(m_fy_bw.group(1)), int(m_fy_bw.group(2))
        filters.append(["fiscal_year", list(range(y1, y2 + 1))])

    m_sec_eq = re.search(r"section\s*=\s*'([^']+)'", where_clause)
    m_sec_in = re.search(r"section\s+IN\s*\(([^)]+)\)", where_clause)
    if m_sec_eq:
        filters.append(["section", [m_sec_eq.group(1)]])
    elif m_sec_in:
        filters.append(["section", re.findall(r"'([^']+)'", m_sec_in.group(1))])

    if not filters:
        raise ValueError(f"Could not parse EDGAR where_clause: {where_clause!r}")
    return filters


def parse_finqa_filter(where_clause: str) -> list[list[Any]]:
    filters: list[list[Any]] = []
    m_tk_eq = re.search(r"metadata->>'ticker'\s*=\s*'([^']+)'", where_clause)
    m_tk_in = re.search(r"metadata->>'ticker'\s+IN\s*\(([^)]+)\)", where_clause)
    if m_tk_eq:
        filters.append(["metadata->>'ticker'", [m_tk_eq.group(1)]])
    elif m_tk_in:
        filters.append(["metadata->>'ticker'", re.findall(r"'([^']+)'", m_tk_in.group(1))])

    m_yr_eq = re.search(r"\(metadata->>'year'\)::int\s*=\s*(\d+)", where_clause)
    m_yr_bw = re.search(r"\(metadata->>'year'\)::int\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)", where_clause)
    m_yr_in = re.search(r"metadata->>'year'\s+IN\s*\(([^)]+)\)", where_clause)
    if m_yr_eq:
        filters.append(["metadata->>'year'", [str(int(m_yr_eq.group(1)))]])
    elif m_yr_bw:
        y1, y2 = int(m_yr_bw.group(1)), int(m_yr_bw.group(2))
        filters.append(["metadata->>'year'", [str(y) for y in range(y1, y2 + 1)]])
    elif m_yr_in:
        filters.append(["metadata->>'year'", re.findall(r"'([^']+)'", m_yr_in.group(1))])

    if not filters:
        raise ValueError(f"Could not parse FinQA where_clause: {where_clause!r}")
    return filters


def parse_filter_for_row(row: dict[str, Any]) -> list[list[Any]]:
    if row["table"] == EDGAR_TABLE:
        return parse_edgar_filter(row["where_clause"])
    return parse_finqa_filter(row["where_clause"])


def load_all_query_vectors(required_qids: set[str] | None = None) -> dict[str, list[float]]:
    vecs = dict(S.load_question_vectors())
    for rel_path, expected_sha in FINQA_VECTOR_FILES:
        p = PROJECT_ROOT / rel_path
        if not p.exists():
            raise RuntimeError(f"Cached vector file missing: {rel_path}")
        actual_sha = sha256_file(p)
        if actual_sha != expected_sha:
            raise RuntimeError(f"Vector cache SHA-256 mismatch for {rel_path}: {actual_sha} != {expected_sha}")
        data = json.loads(p.read_text(encoding="utf-8"))
        for q in data["queries"]:
            vecs[q["query_id"]] = q["vector"]
    if required_qids is not None:
        missing = sorted(required_qids - set(vecs.keys()))
        if missing:
            raise RuntimeError(f"Missing cached query vectors for {len(missing)} questions: {missing}")
    return vecs


def connect_readonly(cfg: R.RouterConfig):
    conn = R.connect()
    R.configure_session(conn, cfg)
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
        cur.execute("SHOW default_transaction_read_only")
        ro = cur.fetchone()[0]
        if ro != "on":
            raise RuntimeError(f"Failed to set default_transaction_read_only = on (got {ro!r})")
    conn.commit()
    conn.set_session(readonly=True)
    return conn


def verify_all_manifest_filters_sql(conn, rows: list[dict[str, Any]], cfgs: dict[str, R.RouterConfig]) -> int:
    seen: dict[tuple[str, str], int] = {}
    with conn.cursor() as cur:
        for r in rows:
            key = (r["table"], r["pool_id"])
            if key in seen:
                if seen[key] != r["n_rows"]:
                    raise RuntimeError(f"Inconsistent n_rows for {key}")
                continue
            cfg = cfgs["edgar_T_edgar"] if r["table"] == EDGAR_TABLE else cfgs["finqa_T_hm"]
            parsed = parse_filter_for_row(r)
            w, wp = R.where_clause(parsed, cfg)
            cur.execute(f"SELECT count(*) FROM {r['table']} WHERE {w}", wp)
            cnt = int(cur.fetchone()[0])
            if cnt != int(r["n_rows"]):
                raise RuntimeError(
                    f"Filter count mismatch on {r['table']} {r['pool_id']} ({r['where_clause']}): "
                    f"SQL returned {cnt}, manifest has {r['n_rows']}"
                )
            seen[key] = cnt
    conn.commit()
    return len(seen)


def read_session_gucs(cur) -> dict[str, str]:
    out = {}
    for g in SHOW_GUCS:
        cur.execute(f"SHOW {g}")
        out[g] = str(cur.fetchone()[0])
    return out


@contextlib.contextmanager
def capture_route_show():
    captured: dict[str, str] = {}
    orig_set_local = R._set_local

    def wrapped_set_local(cur, settings: dict):
        orig_set_local(cur, settings)
        captured.clear()
        captured.update(read_session_gucs(cur))

    R._set_local = wrapped_set_local
    try:
        yield captured
    finally:
        R._set_local = orig_set_local


def table_stats_snapshot(conn) -> dict[str, Any]:
    snap: dict[str, Any] = {"utc": datetime.now(timezone.utc).isoformat(), "tables": {}}
    with conn.cursor() as cur:
        cur.execute("SHOW autovacuum")
        snap["autovacuum"] = cur.fetchone()[0]
        cur.execute("SHOW default_transaction_read_only")
        snap["default_transaction_read_only"] = cur.fetchone()[0]
        for t in STATS_TABLES:
            cur.execute(
                """
                SELECT n_mod_since_analyze, last_analyze, last_autoanalyze,
                       n_tup_ins, n_tup_upd, n_tup_del
                FROM pg_stat_user_tables
                WHERE relname = %s
                """,
                (t,),
            )
            r = cur.fetchone()
            snap["tables"][t] = {
                "n_mod_since_analyze": r[0] if r else None,
                "last_analyze": r[1].isoformat() if (r and r[1]) else None,
                "last_autoanalyze": r[2].isoformat() if (r and r[2]) else None,
                "n_tup_ins": r[3] if r else None,
                "n_tup_upd": r[4] if r else None,
                "n_tup_del": r[5] if r else None,
            }
    conn.commit()
    return snap


def compute_recall_at_15(returned_ids: list[int], truth_ids: list[int] | None, gt_valid: bool, k: int = K) -> float | None:
    if not gt_valid or truth_ids is None:
        return None
    t = truth_ids[:k]
    if not t:
        return None
    return len(set(returned_ids[:k]) & set(t)) / len(t)


def deduce_Execution_keys(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return unique (qid, pool_id) keys for fixed arms and (qid, pool_id, T_name) keys for router arms."""
    fixed_keys: dict[tuple[str, str], dict[str, Any]] = {}
    router_keys: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        fk = (r["qid"], r["pool_id"])
        if fk not in fixed_keys:
            fixed_keys[fk] = r
        rk = (r["qid"], r["pool_id"], r["T_name"])
        if rk not in router_keys:
            router_keys[rk] = r
    return {"fixed_keys": fixed_keys, "router_keys": router_keys}


def router_arm_name(t_name: str) -> str:
    return "router" if t_name == "T_edgar" else "router_hmT"


def config_for_row(row: dict[str, Any], cfgs: dict[str, R.RouterConfig]) -> R.RouterConfig:
    if row["table"] == EDGAR_TABLE:
        return cfgs["edgar_T_edgar"] if row["T_name"] == "T_edgar" else cfgs["edgar_T_hm"]
    return cfgs["finqa_T_hm"]


def execute_arm_once(
    conn,
    arm: str,
    row: dict[str, Any],
    qv: list[float],
    cfgs: dict[str, R.RouterConfig],
    va_cache: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[tuple[int, float]], dict[str, Any]]:
    table = row["table"]
    filters = parse_filter_for_row(row)
    cfg = config_for_row(row, cfgs)

    if arm == "vecadvisor":
        if table == FINQA_TABLE:
            raise RuntimeError("vecadvisor should not be called on finqa_evidence_qwen3")
        key = (row["qid"], row["pool_id"])
        if key not in va_cache:
            va_cache[key] = VA.decide(filters, qv, table=EDGAR_TABLE, k=K, ef_search=cfg["ef_search"])
        d = va_cache[key]
        rows, ms, shape = VA.execute(conn, d, EDGAR_TABLE, filters, K, R.vec_literal(qv), cfg)
        tr = {
            "mode": "vecadvisor",
            "table": EDGAR_TABLE,
            "k": K,
            "decided": d["strategy"],
            "routes_executed": [shape],
            "route_ms": [ms],
            "guard": False,
            "guard_triggered": False,
            "vecadvisor_params": d["params"],
            "vecadvisor_unavailable": d["unavailable"],
            "vecadvisor_unavailable_reason": d["unavailable_reason"],
            "decision_ms_separate": d["decision_ms"],
            "rows_returned": len(rows),
            "total_ms": ms,
        }
        return rows, tr

    mode = "router" if arm in ("router", "router_hmT") else arm
    rows, tr = V.retrieve(qv, filters, K, mode, cfg, conn=conn, table=table)
    tr["mode"] = arm
    return rows, tr


def measure_item(
    conn,
    arm: str,
    row: dict[str, Any],
    qv: list[float],
    cfgs: dict[str, R.RouterConfig],
    truth_map: dict[tuple[str, str], tuple[bool, list[int] | None]],
    va_cache: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    table = row["table"]
    fk = (row["qid"], row["pool_id"])
    gt_valid, truth_ids = truth_map.get(fk, (False, None))

    if arm == "vecadvisor" and table == FINQA_TABLE:
        with conn.cursor() as cur:
            gucs = read_session_gucs(cur)
        conn.commit()
        return {
            "route_taken": None,
            "guard_fired": False,
            "s_est": None,
            "s_count": None,
            "estimate_skipped": None,
            "rows_returned": 0,
            "recall_at_15": None,
            "valid": False,
            "error": "cannot parse JSONB expression filter",
            "vecadvisor_unavailable": True,
            "vecadvisor_unavailable_reason": "cannot parse JSONB expression filter",
            "latency_runs_ms": [],
            "latency_median_ms": None,
            "gucs": gucs,
        }

    with capture_route_show() as show_gucs:
        rows, tr = execute_arm_once(conn, arm, row, qv, cfgs, va_cache)
    ids = [r_[0] for r_ in rows]
    rec15 = compute_recall_at_15(ids, truth_ids, gt_valid, K)

    # 1 warm-up execution
    execute_arm_once(conn, arm, row, qv, cfgs, va_cache)

    # 5 timed executions (end-to-end wall-clock of retrieve())
    walls: list[float] = []
    for _ in range(TIMED_REPS):
        t0 = time.perf_counter()
        execute_arm_once(conn, arm, row, qv, cfgs, va_cache)
        walls.append((time.perf_counter() - t0) * 1000.0)

    routes_exec = tr.get("routes_executed") or []
    route_taken = routes_exec[-1] if routes_exec else tr.get("plan_name") or tr.get("decided")
    s_count = (tr["count"] / tr["N"]) if (tr.get("count") is not None and tr.get("N")) else None
    return {
        "route_taken": route_taken,
        "guard_fired": bool(tr.get("guard_triggered", False)),
        "s_est": tr.get("s_est"),
        "s_count": s_count,
        "estimate_skipped": tr.get(V.SKIP_FIELD),
        "rows_returned": len(ids),
        "recall_at_15": rec15,
        "valid": True,
        "error": None,
        "vecadvisor_unavailable": tr.get("vecadvisor_unavailable", False),
        "vecadvisor_unavailable_reason": tr.get("vecadvisor_unavailable_reason"),
        "latency_runs_ms": walls,
        "latency_median_ms": statistics.median(walls),
        "gucs": dict(show_gucs),
    }


def run_session(args: argparse.Namespace) -> None:
    manifest_sets, manifest_files = resolve_manifest_files(args.manifests)
    validate_quiet_rule_flag(manifest_sets, args.skip_quiet_rule)
    verify_manifest_checksums()

    out_dir = PROJECT_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_manifest_rows(manifest_files)
    req_qids = {r["qid"] for r in rows}
    vecs = load_all_query_vectors(req_qids)
    cfgs = build_configs()

    conn = connect_readonly(cfgs["edgar_T_edgar"])
    try:
        n_verified_filters = verify_all_manifest_filters_sql(conn, rows, cfgs)
        stats_before = table_stats_snapshot(conn)

        if args.skip_quiet_rule:
            quiet_info = {"skipped": True, "reason": "--skip-quiet-rule on smoke manifest"}
        else:
            quiet_info = S.quiet_start(out_dir)

        session_id = args.session_id or f"{'_'.join(manifest_sets)}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        run_id = f"straddle_t_{session_id}"
        order_seed = f"20261115|run_order|{session_id}"
        rng = random.Random(order_seed)

        env = env_meta(conn)
        git_commit = env["git_commit"]
        git_dirty = bool(git("status", "--porcelain"))

        # Precompute exact ground truth once per distinct (qid, pool_id)
        truth_map: dict[tuple[str, str], tuple[bool, list[int] | None]] = {}
        distinct_qp: dict[tuple[str, str], dict[str, Any]] = {}
        for r in rows:
            distinct_qp.setdefault((r["qid"], r["pool_id"]), r)

        for fk, r in distinct_qp.items():
            cfg = cfgs["edgar_T_edgar"] if r["table"] == EDGAR_TABLE else cfgs["finqa_T_hm"]
            filters = parse_filter_for_row(r)
            qv_str = R.vec_literal(vecs[r["qid"]])
            try:
                truth_ids = S.exact_topk(conn, r["table"], filters, K, qv_str, cfg)
                truth_map[fk] = (True, truth_ids)
            except Exception:
                conn.rollback()
                truth_map[fk] = (False, None)

        # Build shuffled schedule of (row_idx, arm)
        pair_indices = list(range(len(rows)))
        rng.shuffle(pair_indices)
        schedule: list[tuple[int, str]] = []
        for idx in pair_indices:
            r = rows[idx]
            r_arm = router_arm_name(r["T_name"])
            arms = list(FIXED_ARMS) + [r_arm]
            rng.shuffle(arms)
            for arm in arms:
                schedule.append((idx, arm))

        results_path = out_dir / "results.jsonl"
        done_keys: set[tuple[str, str, str]] = set()
        fixed_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
        router_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
        va_cache: dict[tuple[str, str], dict[str, Any]] = {}

        if results_path.exists():
            for line in results_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                done_keys.add((d["manifest"], d["pair_id"], d["arm"]))
                gucs = {g: d[g] for g in SHOW_GUCS if g in d}
                cached_meas = {
                    "route_taken": d["route_taken"],
                    "guard_fired": d["guard_fired"],
                    "s_est": d["s_est"],
                    "s_count": d["s_count"],
                    "estimate_skipped": d["estimate_skipped"],
                    "rows_returned": d["rows_returned"],
                    "recall_at_15": d["recall_at_15"],
                    "valid": d["valid"],
                    "error": d["error"],
                    "vecadvisor_unavailable": d.get("vecadvisor_unavailable", False),
                    "vecadvisor_unavailable_reason": d.get("vecadvisor_unavailable_reason"),
                    "latency_runs_ms": d["latency_runs_ms"],
                    "latency_median_ms": d["latency_median_ms"],
                    "gucs": gucs,
                }
                if d["arm"] in FIXED_ARMS:
                    fixed_cache[(d["qid"], d["pool_id"], d["arm"])] = cached_meas
                else:
                    router_cache[(d["qid"], d["pool_id"], d["T_name"])] = cached_meas

        meta_path = out_dir / "run_meta.json"
        S.write_json(
            meta_path,
            {
                "run_id": run_id,
                "session_id": session_id,
                "manifest_sets": manifest_sets,
                "manifest_files": manifest_files,
                "order_seed": order_seed,
                "skip_quiet_rule": args.skip_quiet_rule,
                "quiet_check": quiet_info,
                "n_verified_filters": n_verified_filters,
                "n_schedule_items": len(schedule),
                "k": K,
                "timed_reps": TIMED_REPS,
                "pg_version": env["pg_version"],
                "pgvector_version": env["pgvector_version"],
                "git_commit": git_commit,
                "git_dirty": git_dirty,
                "started_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        loads = S.LoadLogger(out_dir / "host_load.json")
        loads.sample("start")
        loads.start()

        try:
            with results_path.open("a", encoding="utf-8", newline="\n") as fh:
                for idx, arm in schedule:
                    r = rows[idx]
                    item_key = (r["manifest"], r["pair_id"], arm)
                    if item_key in done_keys:
                        continue

                    f_key = (r["qid"], r["pool_id"], arm)
                    r_key = (r["qid"], r["pool_id"], r["T_name"])
                    retried = False
                    reused = False

                    if arm in FIXED_ARMS and f_key in fixed_cache:
                        meas = fixed_cache[f_key]
                        reused = True
                    elif arm not in FIXED_ARMS and r_key in router_cache:
                        meas = router_cache[r_key]
                        reused = True
                    else:
                        for attempt in range(2):
                            try:
                                meas = measure_item(conn, arm, r, vecs[r["qid"]], cfgs, truth_map, va_cache)
                                break
                            except Exception as exc:
                                conn.rollback()
                                if attempt == 0:
                                    retried = True
                                    continue
                                with conn.cursor() as cur:
                                    gucs = read_session_gucs(cur)
                                conn.commit()
                                meas = {
                                    "route_taken": None,
                                    "guard_fired": False,
                                    "s_est": None,
                                    "s_count": None,
                                    "estimate_skipped": None,
                                    "rows_returned": 0,
                                    "recall_at_15": None,
                                    "valid": False,
                                    "error": f"{type(exc).__name__}: {exc}"[:500],
                                    "vecadvisor_unavailable": arm == "vecadvisor",
                                    "vecadvisor_unavailable_reason": "error" if arm == "vecadvisor" else None,
                                    "latency_runs_ms": [],
                                    "latency_median_ms": None,
                                    "gucs": gucs,
                                }
                        if arm in FIXED_ARMS:
                            fixed_cache[f_key] = meas
                        else:
                            router_cache[r_key] = meas

                    out_row = {
                        "run_id": run_id,
                        "session_id": session_id,
                        "manifest": r["manifest"],
                        "pair_id": r["pair_id"],
                        "qid": r["qid"],
                        "table": r["table"],
                        "band": r["band"],
                        "T_name": r["T_name"],
                        "T_value": r["T_value"],
                        "analysis_group": r["analysis_group"],
                        "pool_id": r["pool_id"],
                        "where_clause": r["where_clause"],
                        "n_rows": r["n_rows"],
                        "s": r["s"],
                        "tier": r["tier"],
                        "arm": arm,
                        "route_taken": meas["route_taken"],
                        "guard_fired": meas["guard_fired"],
                        "s_est": meas["s_est"],
                        "s_count": meas["s_count"],
                        "estimate_skipped": meas["estimate_skipped"],
                        "rows_returned": meas["rows_returned"],
                        "recall_at_15": meas["recall_at_15"],
                        "valid": meas["valid"],
                        "error": meas["error"],
                        "retried": retried,
                        "reused_measurement": reused,
                        "vecadvisor_unavailable": meas["vecadvisor_unavailable"],
                        "vecadvisor_unavailable_reason": meas["vecadvisor_unavailable_reason"],
                        "latency_runs_ms": meas["latency_runs_ms"],
                        "latency_median_ms": meas["latency_median_ms"],
                        "cache_state": "warm_after_normal_and_warmup",
                        **meas["gucs"],
                        "pg_version": env["pg_version"],
                        "pgvector_version": env["pgvector_version"],
                        "git_commit": git_commit,
                        "git_dirty": git_dirty,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    fh.write(json.dumps(out_row) + "\n")
                    fh.flush()
                    done_keys.add(item_key)
        finally:
            loads.stop_evt.set()
            loads.sample("end")

        stats_after = table_stats_snapshot(conn)
        S.write_json(
            out_dir / "session_stats.json",
            {"before": stats_before, "after": stats_after},
        )
        if va_cache:
            S.write_json(
                out_dir / "vecadvisor_decisions.json",
                {f"{k[0]}|{k[1]}": v for k, v in va_cache.items()},
            )
    finally:
        conn.close()


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifests", required=True, help="Manifest set(s): primary, secondary, sensitivity, smoke, union")
    ap.add_argument("--out-dir", required=True, help="Output directory for results.jsonl and session files")
    ap.add_argument("--session-id", default=None, help="Optional session identifier")
    ap.add_argument("--skip-quiet-rule", action="store_true", help="Allowed ONLY for --manifests smoke")
    return ap


def main() -> None:
    ap = build_arg_parser()
    args = ap.parse_args()
    run_session(args)


if __name__ == "__main__":
    main()
