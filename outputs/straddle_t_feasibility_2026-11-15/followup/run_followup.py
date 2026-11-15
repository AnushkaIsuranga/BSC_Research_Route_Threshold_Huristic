"""Read-only follow-up analysis for straddle-T feasibility (2026-11-15)."""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BANDS = ("far_below", "near_below", "near_above", "far_above")


def parse_edgar_where(wc: str):
    ciks = yrs = secs = None
    for part in wc.split(" AND "):
        part = part.strip()
        if part.startswith("cik = '"):
            ciks = {part.split("'")[1]}
        elif part.startswith("fiscal_year = "):
            yrs = {int(part.split("=")[1].strip())}
        elif part.startswith("fiscal_year IN ("):
            yrs = {int(x.strip()) for x in part[len("fiscal_year IN (") : -1].split(",")}
        elif part.startswith("section = '"):
            secs = {part.split("'")[1]}
        elif part.startswith("section IN ("):
            secs = {x.strip().strip("'") for x in part[len("section IN (") : -1].split(",")}
    return ciks, yrs, secs


def parse_finqa_where(wc: str):
    tks = yr_rng = None
    if "BETWEEN" in wc:
        ab = wc.split("BETWEEN")[1].strip().split("AND")
        yr_rng = (int(ab[0].strip()), int(ab[1].strip()))
        return tks, yr_rng
    for part in wc.split(" AND "):
        part = part.strip()
        if part.startswith("metadata->>'ticker' = '"):
            tks = {part.split("'")[1]}
        elif part.startswith("metadata->>'ticker' IN ("):
            tks = {x.strip().strip("'") for x in part[len("metadata->>'ticker' IN (") : -1].split(",")}
        elif part.startswith("(metadata->>'year')::int = "):
            y = int(part.split("=")[1].strip())
            yr_rng = (y, y)
    return tks, yr_rng


def edgar_rule(wc: str) -> str:
    has_yr_range = "fiscal_year IN (" in wc
    has_yr_single = "fiscal_year = " in wc
    has_sec_in = "section IN (" in wc
    has_sec_single = "section = " in wc
    if has_yr_range and not (has_sec_in or has_sec_single):
        return "year_range"
    if has_sec_in and not (has_yr_range or has_yr_single):
        return "section_in_list"
    if has_yr_range and has_sec_single:
        return "year_range + single_section"
    if has_yr_single and has_sec_in:
        return "single_year + section_in_list"
    if has_yr_range and has_sec_in:
        return "year_range + section_in_list"
    return "other"


def finqa_rule(wc: str) -> str:
    if "BETWEEN" in wc:
        return "year_range_between"
    if "metadata->>'ticker' IN (" in wc:
        return "ticker_in_list_seed_20261115"
    return "other"


def main() -> None:
    t_edgar = float(json.loads((REPO / "config/policy_v3_1_edgar.json").read_text(encoding="utf-8"))["T_default"])
    t_hm = float(json.loads((REPO / "config/policy_v3_1_hm.json").read_text(encoding="utf-8"))["T_default"])

    edgar_all = list(csv.DictReader(open(BASE / "edgar_filters.csv", encoding="utf-8")))
    finqa_all = list(csv.DictReader(open(BASE / "finqa_filters.csv", encoding="utf-8")))
    for r in edgar_all + finqa_all:
        r["n_rows"] = int(r["n_rows"])
        r["s"] = float(r["s"])
        r["usable"] = r["usable"] == "True"

    edgar_u = [r for r in edgar_all if r["usable"]]
    finqa_u = [r for r in finqa_all if r["usable"]]

    # Part 2
    p2_rows = []
    for r in edgar_u:
        if r["band_edgar"] == "far_above":
            p2_rows.append({
                "table": "edgar_chunks",
                "filter_id": r["filter_id"],
                "where_clause": r["where_clause"],
                "n_rows": r["n_rows"],
                "s": r["s"],
                "type": r["type"],
                "is_full_table": r["n_rows"] == 158308,
            })
    for r in finqa_u:
        if r["s"] > 0.95:
            p2_rows.append({
                "table": "finqa_evidence",
                "filter_id": r["filter_id"],
                "where_clause": r["where_clause"],
                "n_rows": r["n_rows"],
                "s": r["s"],
                "type": r["type"],
                "is_full_table": r["n_rows"] == 35862,
            })
    with open(OUT / "far_above_and_high_s.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "filter_id", "where_clause", "n_rows", "s", "type", "is_full_table"])
        w.writeheader()
        w.writerows(p2_rows)

    # Part 3
    edgar_parsed = [(r, *parse_edgar_where(r["where_clause"])) for r in edgar_u]
    finqa_parsed = [(r, *parse_finqa_where(r["where_clause"])) for r in finqa_u]
    sel_rows = list(csv.DictReader(open(REPO / "outputs/edgar_eval_set_2026-11-01/selected.csv", encoding="utf-8")))
    finqa_test = json.loads((REPO / "data/raw/finqa_test.json").read_text(encoding="utf-8"))

    p3_rows = []
    for t_label, b_col in [("T_edgar", "band_edgar"), ("T_hm", "band_hm")]:
        for subset_name, only_nat in [("all", False), ("natural", True)]:
            per_b = {b: [] for b in BANDS}
            for q in sel_rows:
                qc, qy, qs = str(q["cik"]), int(q["fiscal_year"]), str(q["section"])
                cnt = {b: 0 for b in BANDS}
                for r, ciks, yrs, secs in edgar_parsed:
                    if only_nat and r["type"] != "natural":
                        continue
                    if ciks is not None and qc not in ciks:
                        continue
                    if yrs is not None and qy not in yrs:
                        continue
                    if secs is not None and qs not in secs:
                        continue
                    cnt[r[b_col]] += 1
                for b in BANDS:
                    per_b[b].append(cnt[b])
            for b in BANDS:
                vals = per_b[b]
                p3_rows.append({
                    "dataset": "edgar_chunks",
                    "threshold": t_label,
                    "filter_subset": subset_name,
                    "band": b,
                    "n_questions": len(vals),
                    "min": min(vals),
                    "median": statistics.median(vals),
                    "max": max(vals),
                    "mean": round(statistics.mean(vals), 3),
                    "zero_count": sum(1 for v in vals if v == 0),
                })

    for subset_name, only_nat in [("all", False), ("natural", True)]:
        per_b = {b: [] for b in BANDS}
        for ex in finqa_test:
            qt, qy = ex["id"].split("/")[0], int(ex["id"].split("/")[1])
            cnt = {b: 0 for b in BANDS}
            for r, tks, yr_rng in finqa_parsed:
                if only_nat and r["type"] != "natural":
                    continue
                if tks is not None and qt not in tks:
                    continue
                if yr_rng is not None and not (yr_rng[0] <= qy <= yr_rng[1]):
                    continue
                cnt[r["band_hm"]] += 1
            for b in BANDS:
                per_b[b].append(cnt[b])
        for b in BANDS:
            vals = per_b[b]
            p3_rows.append({
                "dataset": "finqa_evidence",
                "threshold": "T_hm",
                "filter_subset": subset_name,
                "band": b,
                "n_questions": len(vals),
                "min": min(vals),
                "median": statistics.median(vals),
                "max": max(vals),
                "mean": round(statistics.mean(vals), 3),
                "zero_count": sum(1 for v in vals if v == 0),
            })

    with open(OUT / "per_question_gold_containment.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["dataset", "threshold", "filter_subset", "band", "n_questions", "min", "median", "max", "mean", "zero_count"],
        )
        w.writeheader()
        w.writerows(p3_rows)

    # Part 4
    p4_rows = []
    for name, flist in [("edgar_chunks", edgar_u), ("finqa_evidence", finqa_u)]:
        pts = sorted({0.0, 1.0} | {r["s"] for r in flist})
        for a, b in zip(pts, pts[1:]):
            if b - a > 0.02:
                p4_rows.append({
                    "table": name,
                    "gap_start": round(a, 6),
                    "gap_end": round(b, 6),
                    "gap_width": round(b - a, 6),
                })
    with open(OUT / "s_gaps.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "gap_start", "gap_end", "gap_width"])
        w.writeheader()
        w.writerows(p4_rows)

    near_t = []
    for name, flist in [("edgar_chunks", edgar_u), ("finqa_evidence", finqa_u)]:
        for tname, tval in [("T_edgar", t_edgar), ("T_hm", t_hm)]:
            cnt = sum(1 for r in flist if abs(r["s"] - tval) / tval <= 0.25)
            near_t.append((name, tname, tval, cnt, 0.75 * tval, 1.25 * tval))

    # Part 5
    p5_rows = []
    for t_label, b_col in [("T_edgar", "band_edgar"), ("T_hm", "band_hm")]:
        counts = {}
        for r in edgar_u:
            if r["type"] != "constructed":
                continue
            rule = edgar_rule(r["where_clause"])
            counts.setdefault(rule, {b: 0 for b in BANDS})[r[b_col]] += 1
        for rule, bc in sorted(counts.items()):
            p5_rows.append({"table": "edgar_chunks", "threshold": t_label, "rule": rule, **bc, "total": sum(bc.values())})

    counts_f = {}
    for r in finqa_u:
        if r["type"] != "constructed":
            continue
        rule = finqa_rule(r["where_clause"])
        counts_f.setdefault(rule, {b: 0 for b in BANDS})[r["band_hm"]] += 1
    for rule, bc in sorted(counts_f.items()):
        p5_rows.append({"table": "finqa_evidence", "threshold": "T_hm", "rule": rule, **bc, "total": sum(bc.values())})

    with open(OUT / "constructed_rules_by_band.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "threshold", "rule", *BANDS, "total"])
        w.writeheader()
        w.writerows(p5_rows)

    print("PART 2:", p2_rows)
    print("PART 3:")
    for r in p3_rows:
        print(r)
    print("PART 4 GAPS:", p4_rows)
    print("PART 4 NEAR T:", near_t)
    print("PART 5:")
    for r in p5_rows:
        print(r)


if __name__ == "__main__":
    main()
