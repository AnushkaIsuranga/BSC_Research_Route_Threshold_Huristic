"""Cell sets, query vectors, ground truth and machine-state helpers shared by the Amendment 9 scripts."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src import PROJECT_ROOT

TESTS_FILE = PROJECT_ROOT / "ann-filtering-benchmark-datasets" / "data" / "tests.jsonl"
SETS = {   # set -> (filters file, first vector index)
    "in_sample": ("outputs/phase_a_arms/filters.json", 0),
    "ho1": ("outputs/phase_a_holdout/filters.json", 20),
    "ho2": ("outputs/phase_a_holdout2/filters.json", 40),
}
N_VECTORS = 20
GT_DIR = PROJECT_ROOT / "outputs" / "ground_truth_hm"


def load_filters(set_name):
    path, _ = SETS[set_name]
    return json.loads((PROJECT_ROOT / path).read_text(encoding="utf-8"))


def vector_indices(set_name):
    start = SETS[set_name][1]
    return list(range(start, start + N_VECTORS))


def load_vectors(max_index=60):
    """{index: list[float]} for 0-based line indices < max_index, plus the SHA-256 of those lines."""
    out, raw = {}, []
    with open(TESTS_FILE, "r") as f:
        for i in range(max_index):
            line = f.readline()
            raw.append(line)
            out[i] = json.loads(line)["query"]
    return out, hashlib.sha256("".join(raw).encode()).hexdigest()


def load_ground_truth():
    """{(table, filter_id, vector_idx): [ids]} from outputs/ground_truth_hm/ground_truth.jsonl."""
    gt = {}
    with open(GT_DIR / "ground_truth.jsonl", encoding="utf-8") as f:
        for ln in f:
            d = json.loads(ln)
            gt[(d["table"], d["filter_id"], d["vector_idx"])] = d["ids"]
    return gt


def recall(ids, truth) -> float:
    if not truth:
        raise ValueError("empty ground truth")
    return len(set(ids) & set(truth)) / len(truth)


def git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=PROJECT_ROOT).stdout.strip()


def env_meta(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT version(), (SELECT extversion FROM pg_extension WHERE extname = 'vector')")
        pgv, vec = cur.fetchone()
        g = {}
        for name in ("shared_buffers", "work_mem", "effective_cache_size", "max_parallel_workers_per_gather", "jit",
                     "statement_timeout", "hnsw.max_scan_tuples", "hnsw.scan_mem_multiplier", "hnsw.ef_search"):
            cur.execute("SELECT current_setting(%s)", (name,))
            g[name] = cur.fetchone()[0]
    conn.commit()
    return {"git_commit": git("rev-parse", "HEAD"), "git_dirty_phase_e": bool(git("status", "--porcelain", "src/phase_e_router", "config/router_hm.json")),
            "pg_version": pgv, "pgvector_version": vec, "server_settings": g, "python": platform.python_version(),
            "platform": platform.platform(), "started_utc": datetime.now(timezone.utc).isoformat()}


def host_load() -> dict:
    """Host CPU % (Win32_Processor LoadPercentage) and top-5 processes by CPU seconds."""
    ps = ("$l=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average;"
          "$t=Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 Name,Id,CPU;"
          "@{load=$l; top=$t} | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    d = json.loads(r.stdout)
    return {"utc": datetime.now(timezone.utc).isoformat(), "cpu_load_pct": d["load"], "top5": d["top"]}


BLOCKING_PROCESSES = ("utweb", "utorrent", "qbittorrent", "ollama", "jupyter")


def quiet_check(samples=6, interval_s=5, max_load=25.0) -> dict:
    """Amendment 9 quiet-machine rule: no torrent client, Ollama or Jupyter; mean host CPU <= 25 % over 30 s."""
    import time
    ps = "Get-Process | Select-Object -ExpandProperty Name"
    names = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.lower().split()
    blocking = sorted({n for n in names if n.startswith(BLOCKING_PROCESSES)})
    loads = []
    for i in range(samples):
        loads.append(host_load()["cpu_load_pct"])
        if i < samples - 1:
            time.sleep(interval_s)
    mean = sum(loads) / len(loads)
    return {"blocking_processes": blocking, "cpu_samples": loads, "cpu_mean": mean,
            "quiet": not blocking and mean <= max_load}
