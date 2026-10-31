"""Phase E wrap-up (read-only; no database, no timed run, no paid call): load-spike check against the session CPU logs,
held-out coverage, ablation checks, and a tidy per-mode, per-cell CSV for figures. Writes outputs/phase_e_final_2026-10-31/.

  python -m src.phase_e_router.final_export
"""

from __future__ import annotations

import csv
import glob
import json
from collections import Counter, defaultdict
from datetime import datetime

from src import PROJECT_ROOT

CAL = PROJECT_ROOT / "outputs/phase_e_calibration_hm_2026-10-30"
CMP = PROJECT_ROOT / "outputs/phase_e_comparison_hm_2026-10-31"
OUT = PROJECT_ROOT / "outputs/phase_e_final_2026-10-31"
LOAD_LIMIT = 40.0          # the threshold named in the author's 31 Oct request (no such rule exists in the tagged addenda)
WINDOW_S = 60.0
NEAR = (400.0, 600.0)      # latency within 20 % of L = 500 ms
ROUTER_VARIANTS = ["router_tuned", "router_no_guard", "router_always_count", "fixed_t_0_1", "router_plus_probe"]
CAL_VARIANT = {"exact": ["exact"], "iterative_default": ["iter", "iter_guard"], "iterative_tuned": ["tuned", "tuned_guard"]}


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_log(path):
    v = [x for x in json.loads(open(path, encoding="utf-8").read()) if "cpu_total_pct" in x]
    gaps = sorted((ts(b["utc"]) - ts(a["utc"])).total_seconds() for a, b in zip(v, v[1:]))
    return v, {"n_samples": len(v), "median_interval_s": gaps[len(gaps) // 2], "max_interval_s": gaps[-1],
               "sample": "one 1 s reading of \\Processor(_Total)\\% Processor Time per entry",
               "max_pct": max(x["cpu_total_pct"] for x in v), "median_pct": sorted(x["cpu_total_pct"] for x in v)[len(v) // 2]}


def spike_check(log_path, results_path, key, cell_latency):
    v, meta = load_log(log_path)
    rows = [json.loads(ln) for ln in open(results_path, encoding="utf-8")]
    spikes = []
    for h in v:
        if h["cpu_total_pct"] <= LOAD_LIMIT:
            continue
        near = [r for r in rows if abs((ts(r["timestamp"]) - ts(h["utc"])).total_seconds()) <= WINDOW_S]
        cells = defaultdict(list)
        for r in near:
            cells[(r.get("set", "in_sample"), r["table"], r["filter_id"], r[key])].append(r["vector_idx"])
        items = []
        for c, vs in sorted(cells.items()):
            lat = cell_latency(c)
            items.append({"set": c[0], "table": c[1], "filter_id": c[2], key: c[3], "vectors": sorted(vs),
                          "cell_latency_ms": lat, "within_20pct_of_L": any(NEAR[0] <= x <= NEAR[1] for x in lat.values())})
        spikes.append({"utc": h["utc"], "cpu_total_pct": round(h["cpu_total_pct"], 1), "tag": h.get("tag"),
                       "items_within_60s": len(near), "cells": items,
                       "cells_within_20pct_of_L": sum(1 for x in items if x["within_20pct_of_L"])})
    return {"log": str(log_path.relative_to(PROJECT_ROOT)), "log_summary": meta, "rolling_60s_mean_computable": False,
            "samples_above_40pct": spikes}


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    cal_cells = {(c["table"], c["filter_id"]): c for c in json.loads((CAL / "cells.json").read_text(encoding="utf-8"))}
    cmp_cells = list(csv.DictReader(open(CMP / "cell_summary.csv", encoding="utf-8")))
    by = {(c["set"], c["table"], c["filter_id"], c["mode"]): c for c in cmp_cells}

    def cal_lat(c):
        cell = cal_cells[(c[1], c[2])]
        if c[3] == "probe":
            return {"probe": cell["probe"]["median_latency_ms"]}
        return {v: cell[v]["median_latency_ms"] for v in CAL_VARIANT[c[3]]}

    load = {"rule_in_tagged_addenda": None,
            "note": "Amendment 9 Addendum 2 (tag phase-e-amendment-9-addendum-2-2026-10-30) fixes the CPU measure of the start check "
                    "only; it contains no in-session pause or re-run rule. The logs hold one 1 s sample every ~5 min, so a 60 s rolling "
                    "mean cannot be computed; listed instead: every logged sample above 40 % and the items finished within 60 s of it.",
            "calibration": spike_check(CAL / "host_load.json", CAL / "results.jsonl", "route", cal_lat),
            "task4": spike_check(PROJECT_ROOT / glob.glob(str(CMP / "host_load*.json"))[0], CMP / "results.jsonl", "mode",
                                 lambda c: {c[3]: float(by[c]["median_ms"])})}
    (OUT / "load_spike_check.json").write_text(json.dumps(load, indent=1), encoding="utf-8")

    # held-out coverage
    rows = [json.loads(ln) for ln in open(CMP / "results.jsonl", encoding="utf-8")]
    T = json.loads((PROJECT_ROOT / "config/policy_v3_hm.json").read_text(encoding="utf-8"))["T_default"]
    routes = defaultdict(Counter)
    for r in rows:
        if r["set"] != "in_sample" and r["mode"] in ("router", "fixed_t_0_1"):
            routes[(r["mode"], r["filter_id"])][f"{r['trace'].get('band')}->{r['trace'].get('decided')}"] += 1
    sel = {}
    for path in ("outputs/phase_a_holdout/filters.json", "outputs/phase_a_holdout2/filters.json"):
        for f in json.loads((PROJECT_ROOT / path).read_text(encoding="utf-8")):
            sel[f["filter_id"]] = f["selectivity"]
    coverage = [{"filter_id": fid, "selectivity": s, "in_(T,0.1)": T < s < 0.1, "below_0.0105": s < 0.0105,
                 "router_band->route": dict(routes[("router", fid)]), "fixed_t_0_1_band->route": dict(routes[("fixed_t_0_1", fid)]),
                 "router_pass_cells": sum(1 for c in cmp_cells if c["mode"] == "router" and c["filter_id"] == fid and c["passed"] == "True"),
                 "always_iterative_pass_cells": sum(1 for c in cmp_cells if c["mode"] == "always_iterative" and c["filter_id"] == fid and c["passed"] == "True")}
                for fid, s in sel.items()]
    ai_fail = [{k: c[k] for k in ("set", "table", "filter_id", "selectivity", "mean_recall", "full_k_rate", "median_ms", "p95_ms", "reason")}
               for c in cmp_cells if c["mode"] == "always_iterative" and c["set"] != "in_sample" and c["passed"] != "True"]

    # ablation
    guard = Counter()
    for r in rows:
        for t in [r["trace"]] + list(r.get("timed_traces") or []):
            if t.get("guard_triggered"):
                guard[r["mode"]] += 1
    cells = sorted({k[:3] for k in by})
    diffs = {}
    for v in ROUTER_VARIANTS:
        lst = []
        for c in cells:
            a, b = by[c + ("router",)], by[c + (v,)]
            ra, rb, la, lb = (float(a["mean_recall"]), float(b["mean_recall"]), float(a["median_ms"]), float(b["median_ms"]))
            if abs(rb - ra) > 0.10 * ra or abs(lb - la) > 0.10 * la:
                lst.append({"cell": list(c), "s": float(a["selectivity"]), "router_recall": ra, "variant_recall": rb,
                            "router_ms": la, "variant_ms": lb, "router_passed": a["passed"], "variant_passed": b["passed"]})
        diffs[v] = {"cells_differing_gt10pct": len(lst), "recall_gt10pct": sum(1 for x in lst if abs(x["variant_recall"] - x["router_recall"]) > 0.1 * x["router_recall"]),
                    "verdict_changes": sum(1 for x in lst if x["router_passed"] != x["variant_passed"]),
                    "of_which_s_ge_T": sum(1 for x in lst if x["s"] >= T), "cells": lst}
    tuned_recall_diff = [list(c) + [by[c + ("router",)]["mean_recall"], by[c + ("router_tuned",)]["mean_recall"]] for c in cells
                         if by[c + ("router",)]["mean_recall"] != by[c + ("router_tuned",)]["mean_recall"]]
    (OUT / "heldout_and_ablation.json").write_text(json.dumps(
        {"T": T, "heldout_coverage": coverage, "always_iterative_heldout_failures": ai_fail,
         "guard_triggers_normal_and_timed_runs": dict(guard), "router_variant_differences": diffs,
         "router_tuned_recall_differs": tuned_recall_diff}, indent=1), encoding="utf-8")

    # tidy per-mode, per-cell CSV (Task 4 modes + calibration variants)
    fields = ["source", "set", "table", "filter_id", "selectivity", "mode", "passed", "reason", "mean_recall", "median_ms",
              "p95_ms", "early_stop_vectors", "full_k_rate"]
    with open(OUT / "per_mode_cell_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in cmp_cells:
            w.writerow({"source": "task4_end_to_end_ms", **{k: c.get(k) for k in fields if k != "source"}})
        for (t, fid), c in sorted(cal_cells.items()):
            for v in ("exact", "iter", "iter_guard", "tuned", "tuned_guard"):
                w.writerow({"source": "calibration_explain_analyze_ms", "set": "in_sample", "table": t, "filter_id": fid,
                            "selectivity": c["s"], "mode": f"calibration_{v}", "passed": c[v]["passed"], "reason": c[v]["reason"],
                            "mean_recall": c[v]["mean_recall"], "median_ms": c[v]["median_latency_ms"], "p95_ms": None,
                            "early_stop_vectors": c[v]["early_stop_vectors"], "full_k_rate": 1 - c[v]["underfill"] / 20})
    print(json.dumps({"load": {s: [(x["utc"][11:19], x["cpu_total_pct"], x["items_within_60s"], x["cells_within_20pct_of_L"])
                                   for x in load[s]["samples_above_40pct"]] for s in ("calibration", "task4")},
                      "guard": dict(guard), "variants": {v: {k: d[k] for k in d if k != "cells"} for v, d in diffs.items()}}, indent=1))


if __name__ == "__main__":
    main()
