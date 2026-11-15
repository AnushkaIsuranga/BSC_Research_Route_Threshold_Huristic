"""Read-only pool deduplication, tiering, coverage, and checksums (2026-11-15).

Uses BEGIN READ ONLY for all database access.
Writes outputs only under outputs/straddle_t_feasibility_2026-11-15/pool/.
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import psycopg2
from src import db_settings

BASE = REPO / "outputs" / "straddle_t_feasibility_2026-11-15"
POOL_DIR = Path(__file__).resolve().parent
BANDS = ("far_below", "near_below", "near_above", "far_above")


def open_read_only_conn():
    conn = psycopg2.connect(**db_settings())
    cur = conn.cursor()
    cur.execute("SET default_transaction_read_only = on")
    cur.execute("BEGIN READ ONLY")
    cur.execute("SHOW transaction_read_only")
    assert cur.fetchone()[0] == "on"
    cur.close()
    return conn


def assign_band(s: float, T: float) -> str:
    if s <= T / 2.0:
        return "far_below"
    if s <= T:
        return "near_below"
    if s <= 2.0 * T:
        return "near_above"
    return "far_above"


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
            tks = {part.split(" = '")[1][:-1]}
        elif part.startswith("metadata->>'ticker' IN ("):
            tks = {x.strip().strip("'") for x in part[len("metadata->>'ticker' IN (") : -1].split(",")}
        elif part.startswith("(metadata->>'year')::int = "):
            y = int(part.split("=")[1].strip())
            yr_rng = (y, y)
    return tks, yr_rng


def classify_edgar_tier_rule(row: dict) -> tuple[str, str]:
    if row["type"] == "natural":
        cols = []
        wc = row["where_clause"]
        if "cik = " in wc:
            cols.append("cik")
        if "fiscal_year = " in wc:
            cols.append("fiscal_year")
        if "section = " in wc:
            cols.append("section")
        return "natural", "eq:" + "+".join(cols)
    wc = row["where_clause"]
    has_yr_range = "fiscal_year IN (" in wc
    has_yr_single = "fiscal_year = " in wc
    has_sec_in = "section IN (" in wc
    has_sec_single = "section = " in wc
    if has_yr_range and not (has_sec_in or has_sec_single):
        return "plausible_constructed", "year_range"
    if has_sec_in and not (has_yr_range or has_yr_single):
        return "plausible_constructed", "section_in_list"
    if has_yr_range and has_sec_single:
        return "plausible_constructed", "year_range+single_section"
    if has_yr_single and has_sec_in:
        return "plausible_constructed", "single_year+section_in_list"
    if has_yr_range and has_sec_in:
        return "plausible_constructed", "year_range+section_in_list"
    return "plausible_constructed", "other"


def classify_finqa_tier_rule(row: dict) -> tuple[str, str]:
    if row["type"] == "natural":
        cols = []
        wc = row["where_clause"]
        if "metadata->>'ticker' = " in wc:
            cols.append("ticker")
        if "(metadata->>'year')::int = " in wc:
            cols.append("year")
        return "natural", "eq:" + "+".join(cols)
    wc = row["where_clause"]
    if "BETWEEN" in wc:
        return "plausible_constructed", "year_range_between"
    if "metadata->>'ticker' IN (" in wc:
        return "random_constructed", "ticker_in_list_seed_20261115"
    return "plausible_constructed", "other"


def hash_ids(ids: list[int]) -> str:
    payload = ",".join(map(str, ids)).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def dedupe_filters(rows: list[dict], total_rows: int) -> tuple[list[dict], int]:
    by_hash: dict[str, list[dict]] = defaultdict(list)
    mismatches = 0
    for r in rows:
        if len(r["_ids"]) != r["n_rows"]:
            mismatches += 1
        by_hash[r["matched_set_sha256"]].append(r)

    deduped = []
    for h, group in by_hash.items():
        group.sort(key=lambda x: (0 if x["type"] == "natural" else 1, len(x["where_clause"]), x["filter_id"]))
        rep = dict(group[0])
        rep["merged_filter_ids"] = ";".join(g["filter_id"] for g in group)
        rep["degenerate_all_rows"] = rep["n_rows"] == total_rows
        rep["near_all"] = rep["s"] > 0.95
        deduped.append(rep)
    return deduped, mismatches


def main() -> None:
    t_edgar = float(json.loads((REPO / "config/policy_v3_1_edgar.json").read_text(encoding="utf-8"))["T_default"])
    t_hm = float(json.loads((REPO / "config/policy_v3_1_hm.json").read_text(encoding="utf-8"))["T_default"])
    print(f"T_edgar = {t_edgar}")
    print(f"T_hm    = {t_hm}")

    edgar_raw = list(csv.DictReader(open(BASE / "edgar_filters.csv", encoding="utf-8")))
    finqa_raw = list(csv.DictReader(open(BASE / "finqa_filters.csv", encoding="utf-8")))
    for r in edgar_raw + finqa_raw:
        r["n_rows"] = int(r["n_rows"])
        r["s"] = float(r["s"])

    conn = open_read_only_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, cik, fiscal_year, section FROM edgar_chunks ORDER BY id")
        edgar_rows = cur.fetchall()
        cur.execute("SELECT id, metadata->>'ticker', (metadata->>'year')::int FROM finqa_evidence ORDER BY id")
        finqa_rows = cur.fetchall()
        cur.close()
    finally:
        conn.rollback()
        conn.close()

    edgar_total = len(edgar_rows)
    finqa_total = len(finqa_rows)

    # Index EDGAR rows for fast exact sorted id-list lookup
    e_by_cik = defaultdict(list)
    e_by_yr = defaultdict(list)
    e_by_sec = defaultdict(list)
    e_by_cy = defaultdict(list)
    e_by_cs = defaultdict(list)
    e_by_ys = defaultdict(list)
    e_by_cys = defaultdict(list)
    for rid, cik, fy, sec in edgar_rows:
        e_by_cik[cik].append(rid)
        e_by_yr[fy].append(rid)
        e_by_sec[sec].append(rid)
        e_by_cy[(cik, fy)].append(rid)
        e_by_cs[(cik, sec)].append(rid)
        e_by_ys[(fy, sec)].append(rid)
        e_by_cys[(cik, fy, sec)].append(rid)

    for r in edgar_raw:
        tier, rule = classify_edgar_tier_rule(r)
        r["tier"] = tier
        r["rule"] = rule
        ciks, yrs, secs = parse_edgar_where(r["where_clause"])
        r["_ciks"], r["_years"], r["_sections"] = ciks, yrs, secs
        if ciks and yrs and secs and len(ciks) == 1 and len(yrs) == 1 and len(secs) == 1:
            ids = e_by_cys[(next(iter(ciks)), next(iter(yrs)), next(iter(secs)))]
        elif ciks and yrs and not secs and len(ciks) == 1 and len(yrs) == 1:
            ids = e_by_cy[(next(iter(ciks)), next(iter(yrs)))]
        elif ciks and secs and not yrs and len(ciks) == 1 and len(secs) == 1:
            ids = e_by_cs[(next(iter(ciks)), next(iter(secs)))]
        elif yrs and secs and not ciks and len(yrs) == 1 and len(secs) == 1:
            ids = e_by_ys[(next(iter(yrs)), next(iter(secs)))]
        elif ciks and not yrs and not secs and len(ciks) == 1:
            ids = e_by_cik[next(iter(ciks))]
        elif yrs and not ciks and not secs and len(yrs) == 1:
            ids = e_by_yr[next(iter(yrs))]
        elif secs and not ciks and not yrs and len(secs) == 1:
            ids = e_by_sec[next(iter(secs))]
        else:
            ids = [
                rid
                for rid, cik, fy, sec in edgar_rows
                if (ciks is None or cik in ciks) and (yrs is None or fy in yrs) and (secs is None or sec in secs)
            ]
        r["_ids"] = ids
        r["matched_set_sha256"] = hash_ids(ids)

    # Index FinQA rows
    f_by_tk = defaultdict(list)
    f_by_yr = defaultdict(list)
    f_by_ty = defaultdict(list)
    for rid, tk, yr in finqa_rows:
        f_by_tk[tk].append(rid)
        f_by_yr[yr].append(rid)
        f_by_ty[(tk, yr)].append(rid)

    for r in finqa_raw:
        tier, rule = classify_finqa_tier_rule(r)
        r["tier"] = tier
        r["rule"] = rule
        tks, yr_rng = parse_finqa_where(r["where_clause"])
        r["_tickers"], r["_year_range"] = tks, yr_rng
        if tks and yr_rng and len(tks) == 1 and yr_rng[0] == yr_rng[1]:
            ids = f_by_ty[(next(iter(tks)), yr_rng[0])]
        elif tks and not yr_rng and len(tks) == 1:
            ids = f_by_tk[next(iter(tks))]
        elif yr_rng and not tks and yr_rng[0] == yr_rng[1]:
            ids = f_by_yr[yr_rng[0]]
        else:
            ids = [
                rid
                for rid, tk, yr in finqa_rows
                if (tks is None or tk in tks) and (yr_rng is None or yr_rng[0] <= yr <= yr_rng[1])
            ]
        r["_ids"] = ids
        r["matched_set_sha256"] = hash_ids(ids)

    edgar_dedup, e_mis = dedupe_filters(edgar_raw, edgar_total)
    finqa_dedup, f_mis = dedupe_filters(finqa_raw, finqa_total)
    print(f"ID-count mismatches: edgar={e_mis}, finqa={f_mis}")

    # Before/after dedupe table
    dedupe_stats = []
    for tname, raw_l, ded_l in [("edgar_chunks", edgar_raw, edgar_dedup), ("finqa_evidence", finqa_raw, finqa_dedup)]:
        dedupe_stats.append({"table": tname, "group": "ALL", "key": "ALL", "before": len(raw_l), "after": len(ded_l)})
        for tier in ("natural", "plausible_constructed", "random_constructed"):
            b = sum(1 for r in raw_l if r["tier"] == tier)
            a = sum(1 for r in ded_l if r["tier"] == tier)
            if b or a:
                dedupe_stats.append({"table": tname, "group": "tier", "key": tier, "before": b, "after": a})
        rules = sorted({r["rule"] for r in raw_l})
        for rule in rules:
            b = sum(1 for r in raw_l if r["rule"] == rule)
            a = sum(1 for r in ded_l if r["rule"] == rule)
            dedupe_stats.append({"table": tname, "group": "rule", "key": rule, "before": b, "after": a})

    with open(POOL_DIR / "dedupe_summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "group", "key", "before", "after"])
        w.writeheader()
        w.writerows(dedupe_stats)

    # Sort and assign stable pool_id
    edgar_dedup.sort(key=lambda r: (r["s"], r["where_clause"]))
    for i, r in enumerate(edgar_dedup, 1):
        r["pool_id"] = f"edgar_pool_{i:05d}"
        r["band_T_edgar"] = assign_band(r["s"], t_edgar)
        r["band_T_hm"] = assign_band(r["s"], t_hm)

    finqa_dedup.sort(key=lambda r: (r["s"], r["where_clause"]))
    for i, r in enumerate(finqa_dedup, 1):
        r["pool_id"] = f"finqa_pool_{i:05d}"
        r["band_T_hm"] = assign_band(r["s"], t_hm)

    # Write pool CSVs (all distinct filters, with degenerate_all_rows & near_all flags)
    with open(POOL_DIR / "edgar_pool.csv", "w", encoding="utf-8", newline="") as f:
        cols = [
            "pool_id", "where_clause", "n_rows", "s", "tier", "rule",
            "band_T_edgar", "band_T_hm", "merged_filter_ids",
            "matched_set_sha256", "degenerate_all_rows", "near_all",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in edgar_dedup:
            w.writerow({k: r[k] for k in cols})

    with open(POOL_DIR / "finqa_pool.csv", "w", encoding="utf-8", newline="") as f:
        cols = [
            "pool_id", "where_clause", "n_rows", "s", "tier", "rule",
            "band_T_hm", "merged_filter_ids", "matched_set_sha256",
            "degenerate_all_rows", "near_all",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in finqa_dedup:
            w.writerow({k: r[k] for k in cols})

    # Step 3: Usable distinct non-degenerate filters
    edgar_use = [r for r in edgar_dedup if r["n_rows"] >= 15 and not r["degenerate_all_rows"]]
    finqa_use = [r for r in finqa_dedup if r["n_rows"] >= 15 and not r["degenerate_all_rows"]]

    # 3a) Band population
    band_pop = []
    for tname, tlabel, flist, bcol in [
        ("edgar_chunks", "T_edgar", edgar_use, "band_T_edgar"),
        ("edgar_chunks", "T_hm", edgar_use, "band_T_hm"),
        ("finqa_evidence", "T_hm", finqa_use, "band_T_hm"),
    ]:
        for excl_na, label_na in [(False, "incl_near_all"), (True, "excl_near_all")]:
            sub = [r for r in flist if not (excl_na and r["near_all"])]
            for b in BANDS:
                b_rows = [r for r in sub if r[bcol] == b]
                nat = sum(1 for r in b_rows if r["tier"] == "natural")
                pc = sum(1 for r in b_rows if r["tier"] == "plausible_constructed")
                rc = sum(1 for r in b_rows if r["tier"] == "random_constructed")
                band_pop.append({
                    "table": tname, "threshold": tlabel, "near_all_mode": label_na, "band": b,
                    "total": len(b_rows), "natural": nat, "plausible_constructed": pc, "random_constructed": rc,
                    "min_s": f"{min((r['s'] for r in b_rows), default=0):.6f}" if b_rows else "EMPTY",
                    "max_s": f"{max((r['s'] for r in b_rows), default=0):.6f}" if b_rows else "EMPTY",
                })
    with open(POOL_DIR / "band_population.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "threshold", "near_all_mode", "band", "total", "natural", "plausible_constructed", "random_constructed", "min_s", "max_s"])
        w.writeheader()
        w.writerows(band_pop)

    # 3b & 3c) Gold-containment & eligible question lists
    sel_rows = list(csv.DictReader(open(REPO / "outputs/edgar_eval_set_2026-11-01/selected.csv", encoding="utf-8")))
    finqa_test = json.loads((REPO / "data/raw/finqa_test.json").read_text(encoding="utf-8"))

    tier_sets = [
        ("all_tiers", {"natural", "plausible_constructed", "random_constructed"}),
        ("nat_plus_plausible", {"natural", "plausible_constructed"}),
        ("natural_only", {"natural"}),
    ]

    cov_rows = []
    elig_rows = []
    for tlabel, bcol in [("T_edgar", "band_T_edgar"), ("T_hm", "band_T_hm")]:
        for tset_name, allowed in tier_sets:
            per_b = {b: [] for b in BANDS}
            elig_b = {b: [] for b in BANDS}
            for q in sel_rows:
                qid, qc, qy, qs = q["qid"], str(q["cik"]), int(q["fiscal_year"]), str(q["section"])
                cnt = {b: 0 for b in BANDS}
                for r in edgar_use:
                    if r["tier"] not in allowed:
                        continue
                    ciks, yrs, secs = r["_ciks"], r["_years"], r["_sections"]
                    if ciks is not None and qc not in ciks:
                        continue
                    if yrs is not None and qy not in yrs:
                        continue
                    if secs is not None and qs not in secs:
                        continue
                    cnt[r[bcol]] += 1
                for b in BANDS:
                    per_b[b].append(cnt[b])
                    if cnt[b] > 0:
                        elig_b[b].append(qid)
            for b in BANDS:
                vals = per_b[b]
                cov_rows.append({
                    "table": "edgar_chunks", "threshold": tlabel, "tier_set": tset_name, "band": b,
                    "n_questions": len(vals), "eligible_questions": len(elig_b[b]),
                    "min": min(vals), "median": statistics.median(vals), "max": max(vals),
                    "mean": round(statistics.mean(vals), 3), "zero_count": sum(1 for v in vals if v == 0),
                })
                elig_rows.append({
                    "table": "edgar_chunks", "threshold": tlabel, "tier_set": tset_name, "band": b,
                    "n_eligible": len(elig_b[b]), "eligible_qids": ";".join(elig_b[b]),
                })

    for tset_name, allowed in tier_sets:
        per_b = {b: [] for b in BANDS}
        elig_b = {b: [] for b in BANDS}
        for ex in finqa_test:
            qid = ex["id"]
            qt, qy = qid.split("/")[0], int(qid.split("/")[1])
            cnt = {b: 0 for b in BANDS}
            for r in finqa_use:
                if r["tier"] not in allowed:
                    continue
                tks, yr_rng = r["_tickers"], r["_year_range"]
                if tks is not None and qt not in tks:
                    continue
                if yr_rng is not None and not (yr_rng[0] <= qy <= yr_rng[1]):
                    continue
                cnt[r["band_T_hm"]] += 1
            for b in BANDS:
                per_b[b].append(cnt[b])
                if cnt[b] > 0:
                    elig_b[b].append(qid)
        for b in BANDS:
            vals = per_b[b]
            cov_rows.append({
                "table": "finqa_evidence", "threshold": "T_hm", "tier_set": tset_name, "band": b,
                "n_questions": len(vals), "eligible_questions": len(elig_b[b]),
                "min": min(vals), "median": statistics.median(vals), "max": max(vals),
                "mean": round(statistics.mean(vals), 3), "zero_count": sum(1 for v in vals if v == 0),
            })
            elig_rows.append({
                "table": "finqa_evidence", "threshold": "T_hm", "tier_set": tset_name, "band": b,
                "n_eligible": len(elig_b[b]), "eligible_qids": ";".join(elig_b[b]),
            })

    with open(POOL_DIR / "coverage_summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "threshold", "tier_set", "band", "n_questions", "eligible_questions", "min", "median", "max", "mean", "zero_count"])
        w.writeheader()
        w.writerows(cov_rows)

    with open(POOL_DIR / "eligible_questions.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "threshold", "tier_set", "band", "n_eligible", "eligible_qids"])
        w.writeheader()
        w.writerows(elig_rows)

    # 3d) Gaps > 0.02 and within 25% of T
    gaps = []
    for name, flist in [("edgar_chunks", edgar_use), ("finqa_evidence", finqa_use)]:
        pts = sorted({0.0, 1.0} | {r["s"] for r in flist})
        for a, b in zip(pts, pts[1:]):
            if b - a > 0.02:
                gaps.append({"table": name, "gap_start": round(a, 6), "gap_end": round(b, 6), "gap_width": round(b - a, 6)})
    with open(POOL_DIR / "pool_s_gaps.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "gap_start", "gap_end", "gap_width"])
        w.writeheader()
        w.writerows(gaps)

    for name, flist in [("edgar_chunks", edgar_use), ("finqa_evidence", finqa_use)]:
        for tname, tval in [("T_edgar", t_edgar), ("T_hm", t_hm)]:
            cnt = sum(1 for r in flist if abs(r["s"] - tval) / tval <= 0.25)
            print(f"Within 25% of {tname} on {name}: {cnt}")

    # Step 4: POOL_CHECKSUMS.txt for every file in pool/
    checksum_lines = []
    for p in sorted(POOL_DIR.iterdir()):
        if p.is_file() and p.name != "POOL_CHECKSUMS.txt":
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            checksum_lines.append(f"{h}  {p.name}")
    (POOL_DIR / "POOL_CHECKSUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print("Wrote POOL_CHECKSUMS.txt")


if __name__ == "__main__":
    main()
