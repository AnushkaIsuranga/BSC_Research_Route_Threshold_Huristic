"""Phase F evaluation, Task 2.3: offline route-decision checks of policy_v3.1 (no retrieval, no timing, no paid call;
read-only session).

  python -m src.phase_f_edgar.v31_checks --out-dir outputs/edgar_eval_v31_checks_2026-11-01

(a) H&M: every Amendment 9 filter (in-sample 13, held-out 1 and 2, 5 each) x the five tables; v3.1 band decision with
    config/policy_v3_1_hm.json vs policy_v3 (retriever._band_decision) with config/policy_v3_hm.json, for T_default and
    T_tuned. Any difference is a stop condition (exit code 1).
(b) FinQA: the 50 frozen questions on finqa_evidence_qwen3 (filter metadata->>'ticker' / 'year', T = H&M T_default as in
    reports/finqa_router_v3_route_check_2026-10-31.md), v3.1 route and reason next to the stored v3 route.
Writes hm_equivalence.csv, finqa_v31_routes.csv, summary.json (UTF-8, LF).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter

from src import PROJECT_ROOT
from src.phase_e_router import policy_v3_1 as V
from src.phase_e_router import retriever as R
from src.phase_e_router.cells import load_filters

FINQA_CHECK = "outputs/finqa_router_v3_route_check_2026-10-31/route_check.csv"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    cfg_v3 = R.RouterConfig.load(require_policy=True)
    cfg_v31 = R.RouterConfig.load(policy_path="config/policy_v3_1_hm.json", require_policy=True)
    if (cfg_v3.T_default, cfg_v3.T_tuned) != (cfg_v31.T_default, cfg_v31.T_tuned):
        raise SystemExit("policy_v3_1_hm.json T differs from policy_v3_hm.json")
    conn = R.connect()
    conn.set_session(readonly=True)

    hm, diffs = [], []
    for set_name in ("in_sample", "ho1", "ho2"):
        for f in load_filters(set_name):
            for t in cfg_v3["tables"]:
                for tname in ("T_default", "T_tuned"):
                    tr3, tr31 = {}, {}
                    r3 = R._band_decision(conn, t, f["conditions"], getattr(cfg_v3, tname), cfg_v3, tr3)
                    r31 = V.band_decision(conn, t, f["conditions"], getattr(cfg_v31, tname), cfg_v31, tr31)
                    row = {"set": set_name, "filter_id": f["filter_id"], "table": t, "T_name": tname, "T": tr3["T"],
                           "filter": f["description"], "v3_route": r3, "v31_route": r31, "same_route": r3 == r31,
                           "v3_band": tr3["band"], "v31_band": tr31["band"], "s_est": tr3.get("s_est"),
                           "v31_estimate_skipped_no_stats": tr31[V.SKIP_FIELD], "v31_stats_missing": ";".join(tr31["stats_missing"]),
                           "v3_count": tr3.get("count"), "v31_count": tr31.get("count"), "count_cap": tr3.get("count_cap")}
                    hm.append(row)
                    if not row["same_route"] or tr31[V.SKIP_FIELD]:
                        diffs.append(row)

    finqa_cfg = R.RouterConfig({"tables": ["finqa_evidence_qwen3"], "filter_columns": ["ticker", "year"],
                                "filter_expressions": {"ticker": "metadata->>'ticker'", "year": "metadata->>'year'"}})
    stored = list(csv.DictReader(open(PROJECT_ROOT / FINQA_CHECK, encoding="utf-8", newline="")))
    fq = []
    for s in stored:
        tr = {}
        route = V.band_decision(conn, "finqa_evidence_qwen3", [["ticker", [s["ticker"]]], ["year", [s["year"]]]],
                                cfg_v3.T_default, finqa_cfg, tr)
        reason = ("estimate skipped (no statistics on " + ", ".join(tr["stats_missing"]) + "); capped count "
                  f"{tr['count']} of cap {tr['count_cap']}" if tr[V.SKIP_FIELD] else f"estimate s_est {tr['s_est']:.6f}, band {tr['band']}")
        fq.append({"query_id": s["query_id"], "ticker": s["ticker"], "year": s["year"], "matching_rows": s["matching_rows_qwen3"],
                   "s_exact": s["s_exact"], "v3_route": s["route"], "v3_reason": f"estimate s_est {float(s['s_est']):.6f}, band {s['band']}",
                   "v31_route": route, "v31_reason": reason, "v31_estimate_skipped_no_stats": tr[V.SKIP_FIELD],
                   "v31_count": tr.get("count"), "v31_count_cap": tr.get("count_cap"), "same_route": route == s["route"]})
    conn.close()

    for name, rows in (("hm_equivalence.csv", hm), ("finqa_v31_routes.csv", fq)):
        with open(out / name, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    summary = {"T_hm": cfg_v3.T_default, "hm_rows": len(hm), "hm_route_differences": sum(not r["same_route"] for r in hm),
               "hm_rule_fired": sum(r["v31_estimate_skipped_no_stats"] for r in hm),
               "hm_routes": dict(Counter(r["v31_route"] for r in hm)),
               "finqa_rows": len(fq), "finqa_rule_fired": sum(r["v31_estimate_skipped_no_stats"] for r in fq),
               "finqa_v31_routes": dict(Counter(r["v31_route"] for r in fq)), "finqa_v3_routes": dict(Counter(r["v3_route"] for r in fq)),
               "finqa_route_differences": sum(not r["same_route"] for r in fq), "stored_v3_check": FINQA_CHECK}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=1))
    if diffs:
        print(f"STOP: v3.1 differs from v3 (or the rule fired) on {len(diffs)} H&M rows: {diffs[:3]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
