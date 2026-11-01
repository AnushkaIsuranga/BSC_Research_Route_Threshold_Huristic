"""Phase F Task 7 report inputs (descriptive, exploratory; read-only over committed outputs).

  python -m src.phase_f_edgar.report_inputs_edgar --out-dir outputs/edgar_report_inputs_2026-11-01

decision_overhead.json: the router's per-query decision steps from the 5 timed route traces of each pair (stats check,
planner estimate, capped count where the band needed one; per-pair median, then the median over pairs by breadth), the
non-decision remainder (latency minus the executed route time) and router minus always_exact median latency by breadth.
host_load.json: every host-load reading of the calibration (Task 3) and comparison (Task 4) sessions above LOAD_PCT, the
items whose result timestamp lies within WINDOW_S of it, and the processes with the most CPU seconds since the previous reading.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime

from src import PROJECT_ROOT
from src.phase_f_edgar import session_tools as S
from src.phase_f_edgar.compare_edgar import BREADTHS

COMPARISON = "outputs/edgar_retrieval_comparison_2026-11-01"
CALIBRATION = "outputs/edgar_calibration_2026-11-01"
SESSIONS = {"task3_calibration": (CALIBRATION, "host_load_1793502842.json"),
            "task4_comparison": (COMPARISON, "host_load_1793506980.json")}
LOAD_PCT, WINDOW_S = 40.0, 60.0
STEPS = ("stats_check_ms", "estimate_ms", "count_ms")


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def pair_steps(timed_traces: list[dict]) -> dict:
    """Per-pair medians over the timed traces; a step absent from every trace is None."""
    out = {s: med([t.get(s) for t in timed_traces]) for s in STEPS}
    out["route_ms"] = med([sum(t.get("route_ms") or []) for t in timed_traces])
    return out


def loaded(readings: list[dict], items: list[dict], pct=LOAD_PCT, window=WINDOW_S) -> list[dict]:
    ts = lambda s: datetime.fromisoformat(s).timestamp()
    out, prev = [], None
    for h in readings:
        if prev is not None and h["cpu_total_pct"] > pct:
            before = {p["Name"] + "|" + str(p["Id"]): p["CPU"] for p in prev["top5"]}
            delta = sorted(((p["Name"], round(p["CPU"] - before[p["Name"] + "|" + str(p["Id"])], 1)) for p in h["top5"]
                            if p["Name"] + "|" + str(p["Id"]) in before), key=lambda x: -x[1])
            near = [i for i in items if abs(ts(i["timestamp"]) - ts(h["utc"])) <= window]
            out.append({"utc": h["utc"], "cpu_total_pct": round(h["cpu_total_pct"], 1), "tag": h["tag"],
                        "items_within_window": len(near), "item_ids": sorted({i["id"] for i in near}),
                        "top_cpu_seconds_since_previous": delta[:3]})
        elif prev is None and h["cpu_total_pct"] > pct:
            out.append({"utc": h["utc"], "cpu_total_pct": round(h["cpu_total_pct"], 1), "tag": h["tag"], "items_within_window": None})
        prev = h
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    comp = [json.loads(ln) for ln in (PROJECT_ROOT / COMPARISON / "results.jsonl").read_text(encoding="utf-8").splitlines()]

    by_b = defaultdict(list)
    for r in comp:
        if r["mode"] == "router":
            st = pair_steps(r["timed_traces"])
            st["decision_ms"] = round(sum(st[s] or 0 for s in STEPS), 3)
            st["latency_ms"] = r["latency_ms"]
            st["other_ms"] = round(r["latency_ms"] - (st["route_ms"] or 0) - st["decision_ms"], 3)
            by_b[r["breadth"]].append(st)
    lat = lambda m, b: statistics.median(r["latency_ms"] for r in comp if r["mode"] == m and r["breadth"] == b)
    overhead = {"traces_hold": [s for s in STEPS if any(s in t for r in comp if r["mode"] == "router" for t in r["timed_traces"])],
                "by_breadth": {b: {"n_pairs": len(by_b[b]), "pairs_with_count": sum(1 for x in by_b[b] if x["count_ms"] is not None),
                                   **{f"median_{k}": med([x[k] for x in by_b[b]]) for k in STEPS + ("decision_ms", "route_ms", "other_ms", "latency_ms")},
                                   "router_median_latency_ms": round(lat("router", b), 3),
                                   "always_exact_median_latency_ms": round(lat("always_exact", b), 3),
                                   "router_minus_always_exact_ms": round(lat("router", b) - lat("always_exact", b), 3)}
                               for b in BREADTHS}}
    S.write_json(out / "decision_overhead.json", overhead)

    host = {"load_pct": LOAD_PCT, "window_s": WINDOW_S}
    for name, (folder, fn) in SESSIONS.items():
        readings = json.loads((PROJECT_ROOT / folder / fn).read_text(encoding="utf-8"))
        items = []
        for ln in (PROJECT_ROOT / folder / "results.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(ln)
            iid = r["pair_id"] + "|" + r["mode"] if "pair_id" in r else f"{r['filter_id']}|{r['qid']}|{r['route']}"
            items.append({"id": iid, "timestamp": r["timestamp"]})
        host[name] = {"readings": len(readings), "max_pct": round(max(h["cpu_total_pct"] for h in readings), 1),
                      "above": loaded(readings, items)}
    S.write_json(out / "host_load.json", host)
    print(json.dumps(overhead, indent=1))
    print(json.dumps({k: v for k, v in host.items() if not isinstance(v, dict)} |
                     {k: [{x: y for x, y in e.items() if x != "item_ids"} for e in v["above"]] for k, v in host.items() if isinstance(v, dict)}, indent=1))


if __name__ == "__main__":
    main()
