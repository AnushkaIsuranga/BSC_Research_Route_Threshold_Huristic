"""Shared helpers for the Phase F timed sessions (Amendment 11): quiet-rule start check with the stop condition, a host-load
logger writing LF, query vectors and exact ground truth on edgar_chunks."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from src import PROJECT_ROOT
from src.phase_e_router import retriever as R
from src.phase_e_router.cells import host_load, quiet_check

QUESTION_EMBEDDINGS = "outputs/edgar_questions_verify_2026-11-01/question_embeddings.json"
QUIET_ATTEMPTS, QUIET_WAIT_S = 3, 300


COST_LOG = "outputs/edgar_cost_log_2026-11-01/cost_log.jsonl"
SESSION_CAP_USD = 6.00


def cost_spent(path: str = COST_LOG) -> float:
    p = PROJECT_ROOT / path
    if not p.exists():
        return 0.0
    return sum(json.loads(ln)["cost_usd"] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())


def cost_add(step: str, cost_usd: float, detail: dict | None = None, path: str = COST_LOG) -> float:
    """Append one paid call (or batch) to the session's running cost log; returns the new total. Raises if the cap is passed."""
    p = PROJECT_ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    total = cost_spent(path) + cost_usd
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "step": step, "cost_usd": cost_usd,
                             "running_total_usd": total, **(detail or {})}) + "\n")
    if total > SESSION_CAP_USD:
        raise SystemExit(f"STOP: session spend USD {total:.4f} exceeds the USD {SESSION_CAP_USD} cap")
    return total


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8", newline="\n")


def quiet_start(out: Path, attempts: int = QUIET_ATTEMPTS, wait_s: int = QUIET_WAIT_S, check=quiet_check, sleep=time.sleep) -> dict:
    """Addendum 2 quiet check; on refusal retry after 5 minutes; three refusals in a row stop the session (stop condition).
    Every check is stored."""
    log = []
    for i in range(attempts):
        q = check()
        q["attempt"] = i + 1
        q["utc"] = datetime.now(timezone.utc).isoformat()
        log.append(q)
        write_json(out / f"quiet_checks_{int(time.time())}_{i + 1}.json", q)
        print("quiet check:", {k: q[k] for k in ("attempt", "cpu_mean", "blocking_processes", "quiet")}, flush=True)
        if q["quiet"]:
            return {"passed": q, "attempts": log}
        if i < attempts - 1:
            sleep(wait_s)
    raise SystemExit(f"STOP: quiet-rule start check failed {attempts} times in a row, {wait_s // 60} minutes apart: "
                     f"{[round(x['cpu_mean'], 1) for x in log]}")


class LoadLogger(threading.Thread):
    """Host CPU (processor counter + Win32 disclosure) and top-5 processes every 5 min, written as LF JSON."""

    def __init__(self, path: Path, every_s: int = 300):
        super().__init__(daemon=True)
        self.path, self.every, self.stop_evt, self.samples = path, every_s, threading.Event(), []

    def sample(self, tag):
        try:
            s = host_load()
        except Exception as e:                                    # recorded, never silently dropped
            s = {"utc": datetime.now(timezone.utc).isoformat(), "error": repr(e)}
        s["tag"] = tag
        self.samples.append(s)
        write_json(self.path, self.samples)

    def run(self):
        while not self.stop_evt.wait(self.every):
            self.sample("periodic")


def load_question_vectors() -> dict:
    """{qid: vector} from the checksummed question embeddings (sha256 checked against outputs/data_checksums.json)."""
    from src.phase_f_edgar.common import sha256_file
    sums = json.loads((PROJECT_ROOT / "outputs/data_checksums.json").read_text(encoding="utf-8"))["files"]
    sha = sha256_file(PROJECT_ROOT / QUESTION_EMBEDDINGS)
    if sums[QUESTION_EMBEDDINGS]["sha256"] != sha:
        raise SystemExit(f"{QUESTION_EMBEDDINGS} sha256 differs from data_checksums.json")
    d = json.loads((PROJECT_ROOT / QUESTION_EMBEDDINGS).read_text(encoding="utf-8"))
    return {q["query_id"]: q["vector"] for q in d["queries"]}


def exact_topk(conn, table, filters, k, qv, cfg) -> list[int]:
    """Ground truth: exact route (enable_indexscan = off, ORDER BY distance, id), checked to use no HNSW index."""
    plan = R.explain_route(conn, R.R_EXACT, table, filters, k, qv, cfg)
    chk = R.check_plan(R.R_EXACT, plan, cfg)
    if not chk["ok"]:
        raise SystemExit(f"ground-truth plan is not exact: {chk}")
    rows, _ = R.run_route(conn, R.R_EXACT, table, filters, k, qv, cfg)
    return [r[0] for r in rows]


def recall_at(ids, truth, k) -> float | None:
    """|top-k returned ∩ top-k exact| / min(k, |exact|); None if the filter matches no row."""
    t = truth[:k]
    if not t:
        return None
    return len(set(ids[:k]) & set(t)) / len(t)
