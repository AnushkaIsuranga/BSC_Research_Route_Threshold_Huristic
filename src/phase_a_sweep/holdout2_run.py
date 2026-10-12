"""Second held-out run (PHASE_A_HOLDOUT2_PROTOCOL.md): reuses holdout_run.py unchanged with new filters h2a-h2e,
vectors 0-based lines 40-59, seed 20261017, output outputs/phase_a_holdout2/.

  python -m src.phase_a_sweep.holdout2_run --build-filters
  python -m src.phase_a_sweep.holdout2_run --selftest        # replay of a main-run filter (vectors 0-1), no held-out data
  python -m src.phase_a_sweep.holdout2_run                   # the run (refuses if the machine/files are not as required)

Host CPU load is sampled at run start/end and at the planner-default warm-up that holdout_run makes once per table.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.phase_a_sweep import holdout_run as H

SEED = 20261017
OUT = Path("outputs/phase_a_holdout2")
VEC_FIRST2, VEC_COUNT2 = 40, 20
SPECS = [
    {"filter_id": "h2a", "target": 0.23, "conditions": [("graphical_appearance_name", ["Melange", "Stripe", "Denim", "Front print", "Placement print", "Check"])]},
    {"filter_id": "h2b", "target": 0.26, "conditions": [("garment_group_name", ["Accessories", "Jersey Basic", "Knitwear"])]},
    {"filter_id": "h2c", "target": 0.33, "conditions": [("perceived_colour_master_name", ["White", "Pink", "Beige", "Green", "Khaki green"])]},
    {"filter_id": "h2d", "target": 0.38, "conditions": [("product_type_name", ["Dress", "Sweater", "T-shirt", "Top", "Blouse", "Jacket"])]},
    {"filter_id": "h2e", "target": 0.45, "conditions": [("product_type_name", ["Dress", "Sweater", "T-shirt", "Top", "Blouse", "Jacket", "Shorts", "Shirt"])]},
]
EXPECTED_ROWS = {"h2a": 24213, "h2b": 26932, "h2c": 34284, "h2d": 39590, "h2e": 46919}
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-filters", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    H.SEED, H.OUT_DIR, H.HO_SPECS = SEED, OUT, SPECS
    orig_load = H.load_vectors
    H.load_vectors = lambda first=VEC_FIRST2, count=VEC_COUNT2: orig_load(first, count) if not a.selftest else orig_load(0, 2)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.build_filters:
        H.build_filters()
        got = {f["filter_id"]: f["matched_rows"] for f in json.loads((OUT / "filters.json").read_text(encoding="utf-8"))}
        if got != EXPECTED_ROWS:
            raise SystemExit(f"filter row counts differ from the protocol: {got}")
        print("filter counts match the protocol")
        return
    if a.selftest:
        H.run(selftest=True)
        return
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
        (OUT / "host_load.json").write_text(json.dumps({"seed": SEED, "samples": load_log}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
