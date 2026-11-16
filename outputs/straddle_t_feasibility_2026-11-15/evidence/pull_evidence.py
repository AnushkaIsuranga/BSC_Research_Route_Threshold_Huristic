"""Read-only evidence pull for Amendment 12 (2026-11-15)."""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def assign_band(s: float, T: float) -> str:
    if s <= T / 2.0:
        return "far_below"
    if s <= T:
        return "near_below"
    if s <= 2.0 * T:
        return "near_above"
    return "far_above"


def bin_s(s: float) -> str:
    if s < 0.05:
        return "0-0.05"
    if s < 0.10:
        return "0.05-0.1"
    if s < 0.20:
        return "0.1-0.2"
    if s < 0.30:
        return "0.2-0.3"
    if s < 0.40:
        return "0.3-0.4"
    if s < 0.60:
        return "0.4-0.6"
    return "0.6+"


def main() -> None:
    t_edgar = float(json.loads((REPO / "config/policy_v3_1_edgar.json").read_text(encoding="utf-8"))["T_default"])
    t_hm = float(json.loads((REPO / "config/policy_v3_1_hm.json").read_text(encoding="utf-8"))["T_default"])

    # 1a) EDGAR Amendment 11 retrieval results
    edgar_res = [
        json.loads(ln)
        for ln in (REPO / "outputs/edgar_retrieval_comparison_2026-11-01/results.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    target_modes = ["always_exact", "default_hnsw", "always_iterative", "router", "router_hmT"]
    by_mode_breadth = defaultdict(list)
    by_mode_band = defaultdict(list)
    per_pair = defaultdict(dict)

    for r in edgar_res:
        m = r["mode"]
        if m not in target_modes:
            continue
        s = float(r["selectivity"])
        b_edgar = assign_band(s, t_edgar)
        by_mode_breadth[(m, r["breadth"])].append(r)
        by_mode_band[(m, b_edgar)].append(r)
        per_pair[r["pair_id"]][m] = r

    # Write per-pair summary CSV (160 pairs)
    pair_rows = []
    for pid, md in sorted(per_pair.items()):
        ref = next(iter(md.values()))
        s = float(ref["selectivity"])
        row = {
            "pair_id": pid,
            "qid": ref["qid"],
            "breadth": ref["breadth"],
            "s": s,
            "band_T_edgar": assign_band(s, t_edgar),
            "route_router": md.get("router", {}).get("trace", {}).get("route", ""),
            "route_router_hmT": md.get("router_hmT", {}).get("trace", {}).get("route", ""),
        }
        for m in ["always_exact", "default_hnsw", "always_iterative", "router", "router_hmT"]:
            mr = md.get(m, {})
            row[f"{m}_lat_ms"] = mr.get("latency_ms", "")
            row[f"{m}_recall15"] = mr.get("recall15", "")
        pair_rows.append(row)

    with open(OUT / "edgar_160_pairs_summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pair_rows[0].keys()))
        w.writeheader()
        w.writerows(pair_rows)

    def summarize_group(rows):
        lats = [float(r["latency_ms"]) for r in rows if r["latency_ms"] is not None]
        recs = [float(r["recall15"]) for r in rows if r["recall15"] is not None]
        over500 = sum(1 for x in lats if x > 500.0)
        return {
            "n_pairs": len(rows),
            "mean_recall15": round(statistics.mean(recs), 4) if recs else None,
            "median_latency_ms": round(statistics.median(lats), 2) if lats else None,
            "n_over_500ms": over500,
        }

    sum_rows = []
    for m in target_modes:
        for b in ["cik+year+section", "cik+year", "year+section", "section"]:
            st = summarize_group(by_mode_breadth[(m, b)])
            sum_rows.append({"group_by": "breadth", "key": b, "mode": m, **st})
        for band in ["far_below", "near_below", "near_above", "far_above"]:
            rows = by_mode_band[(m, band)]
            if rows:
                st = summarize_group(rows)
                sum_rows.append({"group_by": "band_T_edgar", "key": band, "mode": m, **st})

    with open(OUT / "edgar_1a_summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["group_by", "key", "mode", "n_pairs", "mean_recall15", "median_latency_ms", "n_over_500ms"])
        w.writeheader()
        w.writerows(sum_rows)

    print("=== 1a EDGAR SUMMARY ===")
    for r in sum_rows:
        print(r)

    # 1c) H&M exact > 500 ms per table from outputs/phase_a_arms/results.jsonl
    arms_res = [
        json.loads(ln)
        for ln in (REPO / "outputs/phase_a_arms/results.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    hm_exact = defaultdict(lambda: defaultdict(list))
    for r in arms_res:
        if r["arm"] == "forced-exact":
            hm_exact[(r["table"], r["filter_id"], float(r["selectivity"]))]["lat"].append(float(r["latency_ms"]))
    hm_over = defaultdict(list)
    for (tbl, fid, s), d in hm_exact.items():
        med = statistics.median(d["lat"])
        if med > 500.0:
            hm_over[tbl].append((s, fid, round(med, 2)))
    print("\n=== 1c H&M FORCED-EXACT > 500 ms (by cell median) ===")
    for tbl in sorted(hm_over):
        vals = sorted(hm_over[tbl])
        print(tbl, "count_cells>500ms:", len(vals), "min_s:", vals[0][0], "max_s:", vals[-1][0], "cells:", vals)

    # 2) Default HNSW recall & rows_returned by selectivity bin
    # H&M: arm == 'forced-hnsw' across phase_a_arms, phase_a_holdout, phase_a_holdout2
    hm_hnsw = []
    for p_str in ["outputs/phase_a_arms/results.jsonl", "outputs/phase_a_holdout/results.jsonl", "outputs/phase_a_holdout2/results.jsonl"]:
        for ln in (REPO / p_str).read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r["arm"] == "forced-hnsw" and r.get("error") is None:
                hm_hnsw.append({
                    "dataset": "H&M",
                    "s": float(r["selectivity"]),
                    "recall": float(r["recall"]),
                    "rows": int(r["rows_returned"]),
                })

    edgar_hnsw = [
        {
            "dataset": "EDGAR",
            "s": float(r["selectivity"]),
            "recall": float(r["recall15"]),
            "rows": int(r["rows_returned"]),
        }
        for r in edgar_res
        if r["mode"] == "default_hnsw" and r.get("error") is None
    ]

    bin_order = ["0-0.05", "0.05-0.1", "0.1-0.2", "0.2-0.3", "0.3-0.4", "0.4-0.6", "0.6+"]
    bin_rows = []
    for ds_name, items in [("H&M", hm_hnsw), ("EDGAR", edgar_hnsw)]:
        by_b = defaultdict(list)
        for it in items:
            by_b[bin_s(it["s"])].append(it)
        for b in bin_order:
            lst = by_b[b]
            if not lst:
                continue
            mean_s = statistics.mean(x["s"] for x in lst)
            mean_rows = statistics.mean(x["rows"] for x in lst)
            mean_rec = statistics.mean(x["recall"] for x in lst)
            exp_40s = 40.0 * mean_s
            ratio = mean_rows / exp_40s if exp_40s > 0 else None
            bin_rows.append({
                "dataset": ds_name,
                "bin": b,
                "n": len(lst),
                "mean_s": round(mean_s, 5),
                "mean_recall": round(mean_rec, 4),
                "mean_rows": round(mean_rows, 2),
                "expected_40s": round(exp_40s, 2),
                "rows_over_40s": round(ratio, 3) if ratio is not None else "",
            })

    with open(OUT / "default_hnsw_bins.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["dataset", "bin", "n", "mean_s", "mean_recall", "mean_rows", "expected_40s", "rows_over_40s"])
        w.writeheader()
        w.writerows(bin_rows)

    print("\n=== 2) DEFAULT HNSW BINS ===")
    for r in bin_rows:
        print(r)

    # Smallest s at which mean rows_returned >= 15 (grouped by distinct selectivity)
    for ds_name, items in [("H&M", hm_hnsw), ("EDGAR", edgar_hnsw)]:
        by_s = defaultdict(list)
        for it in items:
            by_s[round(it["s"], 6)].append(it["rows"])
        above_15 = sorted((s, statistics.mean(rs)) for s, rs in by_s.items() if statistics.mean(rs) >= 15.0)
        print(f"{ds_name} smallest s with mean_rows >= 15:", above_15[0] if above_15 else "NONE (k=10 cap on H&M!)")

    # 3) Overlap of 160 existing EDGAR pairs with pool/edgar_pool.csv
    pool_rows = list(csv.DictReader(open(REPO / "outputs/straddle_t_feasibility_2026-11-15/pool/edgar_pool.csv", encoding="utf-8")))
    pool_by_where = {r["where_clause"]: r for r in pool_rows}

    def pair_filter_to_where(filt_json_str: str) -> str:
        specs = json.loads(filt_json_str)
        parts = []
        for col, vals in specs:
            v = vals[0]
            if col == "fiscal_year":
                parts.append(f"fiscal_year = {int(v)}")
            else:
                parts.append(f"{col} = '{v}'")
        return " AND ".join(parts)

    pairs_manifest = list(csv.DictReader(open(REPO / "outputs/edgar_eval_set_2026-11-01/pairs.csv", encoding="utf-8")))
    overlap_rows = []
    band_counts = defaultdict(int)
    usable_overlap = 0
    for pr in pairs_manifest:
        wc = pair_filter_to_where(pr["filter"])
        match = pool_by_where.get(wc)
        s = float(pr["selectivity"])
        b_edgar = assign_band(s, t_edgar)
        band_counts[b_edgar] += 1
        is_usable = bool(match and int(match["n_rows"]) >= 15 and match["degenerate_all_rows"] == "False" and match["near_all"] == "False")
        if is_usable:
            usable_overlap += 1
        overlap_rows.append({
            "pair_id": pr["pair_id"],
            "breadth": pr["breadth"],
            "where_clause": wc,
            "band_T_edgar": b_edgar,
            "pool_id": match["pool_id"] if match else "",
            "n_rows": match["n_rows"] if match else pr["n_match"],
            "usable_in_pool": is_usable,
        })

    with open(OUT / "edgar_160_pool_overlap.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(overlap_rows[0].keys()))
        w.writeheader()
        w.writerows(overlap_rows)

    print("\n=== 3) OVERLAP WITH POOL ===")
    print("Total existing pairs:", len(pairs_manifest), "Usable in pool:", usable_overlap)
    print("Band counts under T_edgar:", dict(band_counts))
    nb_pool = sorted({(r["pool_id"], r["where_clause"], r["n_rows"]) for r in overlap_rows if r["band_T_edgar"] == "near_below"})
    print("near_below pool filters (count=" + str(sum(1 for r in overlap_rows if r["band_T_edgar"] == "near_below")) + " pairs):", nb_pool)


if __name__ == "__main__":
    main()
