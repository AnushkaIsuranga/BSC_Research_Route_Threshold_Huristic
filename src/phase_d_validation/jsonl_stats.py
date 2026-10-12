# LEGACY — not used in final results. summarises the Sept-era JSONL schema (dm_* / naive_* columns); superseded by paired_stats.py.
"""Derive Phase-D statistics from the authoritative local-run JSONL."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import scipy.stats


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = successes / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - m, c + m


def summarize(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures = [r for r in rows if r.get("error")]
    valid = [r for r in rows if not r.get("error")]
    primary_dm = sum(not r.get("dm_correct", 0) for r in rows) / len(rows) if rows else 0
    primary_naive = sum(not r.get("naive_correct", 0) for r in rows) / len(rows) if rows else 0
    sens_dm = sum(not r.get("dm_correct", 0) for r in valid) / len(valid) if valid else 0
    sens_naive = sum(not r.get("naive_correct", 0) for r in valid) / len(valid) if valid else 0
    b = sum(r.get("naive_correct") == 0 and r.get("dm_correct") == 1 for r in valid)
    c = sum(r.get("naive_correct") == 1 and r.get("dm_correct") == 0 for r in valid)
    mcnemar_p = scipy.stats.chi2.sf((abs(b - c) - 1) ** 2 / (b + c), 1) if b + c else 1.0
    dm_lat = [r.get("dm_e2e_latency_ms", r["dm_latency_ms"]) for r in valid]; naive_lat = [r.get("naive_e2e_latency_ms", r["naive_latency_ms"]) for r in valid]
    try: wilcoxon_p = scipy.stats.wilcoxon(naive_lat, dm_lat, zero_method="zsplit").pvalue
    except ValueError: wilcoxon_p = 1.0
    lo, hi = wilson(sum(r.get("dm_correct", 0) for r in rows), len(rows))
    return {"rows": len(rows), "failures": len(failures), "primary_error_rate": {"dm": primary_dm, "naive": primary_naive}, "sensitivity_error_rate": {"dm": sens_dm, "naive": sens_naive}, "wilson_dm_accuracy": [lo, hi], "mcnemar_continuity_corrected_p": mcnemar_p, "wilcoxon_latency_p": wilcoxon_p}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("jsonl", type=Path); args = parser.parse_args(); print(json.dumps(summarize(args.jsonl), indent=2))
