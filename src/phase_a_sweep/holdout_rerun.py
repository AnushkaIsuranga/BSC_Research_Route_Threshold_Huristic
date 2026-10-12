"""Post-hoc robustness rerun of the held-out design (see DEVIATION_LOG.md, 2026-10-12).

Reuses holdout_run.py unchanged (same filters, vectors 20-39, 3 arms, T=0.1 analysis) but with a new
seed, a new output folder and a new run id. The original outputs/phase_a_holdout is only read
(filters.json is copied). Host CPU load is sampled at the start of each table (the planner-default
warm-up call that holdout_run makes once per table) and at run start/end.

  python -m src.phase_a_sweep.holdout_rerun
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.phase_a_sweep import holdout_run as H

SEED = 20261014
RUN_ID = "holdout_rerun_20261014"
ORIG = Path("outputs/phase_a_holdout")
OUT = Path("outputs/phase_a_holdout_rerun")
load_log: list[dict] = []


def host_load() -> dict:
    p = subprocess.run(["typeperf", r"\Processor(_Total)\% Processor Time", "-sc", "3"], capture_output=True, text=True)
    vals = []
    for ln in p.stdout.splitlines():
        parts = ln.strip().split(",")
        if len(parts) == 2 and parts[0].startswith('"') and parts[1].strip('"').replace(".", "", 1).isdigit():
            vals.append(float(parts[1].strip('"')))
    top = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 Name,@{n='cpu_s';e={[int]$_.CPU}} | ConvertTo-Json -Compress"],
                         capture_output=True, text=True).stdout.strip()
    return {"utc": datetime.now(timezone.utc).isoformat(), "cpu_total_pct_3_samples": vals, "top5_cumulative_cpu": top}


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; every run writes to a new folder")
    OUT.mkdir(parents=True)
    shutil.copy2(ORIG / "filters.json", OUT / "filters.json")
    H.SEED, H.OUT_DIR = SEED, OUT
    load_log.append({"event": "run_start", **host_load()})

    real_apply = H.apply_arm

    def apply_arm_logged(cur, arm):
        if arm == "planner-default":
            load_log.append({"event": "table_start_warmup", **host_load()})
        return real_apply(cur, arm)
    H.apply_arm = apply_arm_logged
    try:
        H.run(selftest=False)
    finally:
        load_log.append({"event": "run_end", **host_load()})
        (OUT / "host_load.json").write_text(json.dumps({"run_id": RUN_ID, "seed": SEED, "samples": load_log}, indent=2), encoding="utf-8")
        print("host load samples:", len(load_log))


if __name__ == "__main__":
    main()
