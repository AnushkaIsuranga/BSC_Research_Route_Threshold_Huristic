"""Read-only feasibility enumeration for the straddle-T evaluation.

Enforces BEGIN READ ONLY and default_transaction_read_only = on on every DB session.
Reads T_edgar and T_hm from config/policy_v3_1_edgar.json and config/policy_v3_1_hm.json.
Writes outputs only to outputs/straddle_t_feasibility_2026-11-15/.
"""

from __future__ import annotations

import csv
import itertools
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2

from src import PROJECT_ROOT, db_settings

OUT_DIR = PROJECT_ROOT / "outputs" / "straddle_t_feasibility_2026-11-15"
SEED = 20261115
MIN_ROWS = 15
BANDS = ("far_below", "near_below", "near_above", "far_above")


def open_read_only_conn():
    """Open a PostgreSQL connection locked to read-only transactions."""
    conn = psycopg2.connect(**db_settings())
    cur = conn.cursor()
    cur.execute("SET default_transaction_read_only = on")
    cur.execute("BEGIN READ ONLY")
    assert_read_only(cur)
    cur.close()
    return conn


def assert_read_only(cur) -> None:
    """Assert that the current session and transaction are read-only."""
    cur.execute("SHOW transaction_read_only")
    tx_ro = cur.fetchone()[0]
    cur.execute("SHOW default_transaction_read_only")
    def_ro = cur.fetchone()[0]
    if tx_ro != "on" or def_ro != "on":
        raise RuntimeError(f"Expected read-only session, got transaction_read_only={tx_ro!r}, default={def_ro!r}")


def assign_band(s: float, T: float) -> str:
    if s <= T / 2.0:
        return "far_below"
    if s <= T:
        return "near_below"
    if s <= 2.0 * T:
        return "near_above"
    return "far_above"


def load_thresholds() -> tuple[float, float]:
    edgar_cfg = json.loads((PROJECT_ROOT / "config/policy_v3_1_edgar.json").read_text(encoding="utf-8"))
    hm_cfg = json.loads((PROJECT_ROOT / "config/policy_v3_1_hm.json").read_text(encoding="utf-8"))
    t_edgar = float(edgar_cfg["T_default"])
    t_hm = float(hm_cfg["T_default"])
    print(f"Read T_edgar = {t_edgar} (from config/policy_v3_1_edgar.json)")
    print(f"Read T_hm    = {t_hm} (from config/policy_v3_1_hm.json)")
    if abs(t_edgar - 0.37869) > 1e-4:
        raise SystemExit(f"T_edgar={t_edgar} differs from expected ~0.37869")
    if abs(t_hm - 0.07119) > 1e-4:
        raise SystemExit(f"T_hm={t_hm} differs from expected ~0.07119")
    return t_edgar, t_hm


def step_a_edgar_manifest(t_edgar: float, t_hm: float) -> list[dict]:
    pairs_path = PROJECT_ROOT / "outputs/edgar_eval_set_2026-11-01/pairs.csv"
    with open(pairs_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    breadths = ["cik+year+section", "cik+year", "year+section", "section"]
    results = []
    for t_name, t_val in [("T_edgar", t_edgar), ("T_hm", t_hm)]:
        for b in breadths:
            b_rows = [r for r in rows if r["breadth"] == b]
            counts = {band: 0 for band in BANDS}
            for r in b_rows:
                counts[assign_band(float(r["selectivity"]), t_val)] += 1
            total = sum(counts.values())
            assert total == 40, f"Expected 40 for {b}, got {total}"
            results.append({"threshold": t_name, "T": t_val, "breadth": b, **counts, "total": total})
        grand = sum(x["total"] for x in results if x["threshold"] == t_name)
        assert grand == 160, f"Expected 160 grand total, got {grand}"
    return results


def step_b_edgar_filters(cur, t_edgar: float, t_hm: float) -> tuple[int, list[dict], dict]:
    cur.execute("SELECT COUNT(*) FROM edgar_chunks")
    total_rows = int(cur.fetchone()[0])

    # Check schema columns exist
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'edgar_chunks' AND column_name IN ('cik', 'fiscal_year', 'section')"
    )
    cols = {r[0] for r in cur.fetchall()}
    if cols != {"cik", "fiscal_year", "section"}:
        raise SystemExit(f"Unexpected edgar_chunks columns: {cols}")

    filters: list[dict] = []
    fid = 0

    # Natural filters via GROUPING SETS
    gs_sql = """
        SELECT cik, fiscal_year, section,
               GROUPING(cik) AS g_cik,
               GROUPING(fiscal_year) AS g_yr,
               GROUPING(section) AS g_sec,
               COUNT(*) AS n_rows
        FROM edgar_chunks
        GROUP BY GROUPING SETS (
            (cik, fiscal_year, section),
            (cik, fiscal_year),
            (fiscal_year, section),
            (cik, section),
            (cik),
            (fiscal_year),
            (section)
        )
        ORDER BY g_cik, g_yr, g_sec, cik NULLS LAST, fiscal_year NULLS LAST, section NULLS LAST
    """
    cur.execute(gs_sql)
    for cik, fy, sec, g_cik, g_yr, g_sec, n_rows in cur.fetchall():
        fid += 1
        clauses = []
        meta_ciks, meta_yrs, meta_secs = None, None, None
        if g_cik == 0:
            clauses.append(f"cik = '{cik}'" if cik is not None else "cik IS NULL")
            meta_ciks = (cik,)
        if g_yr == 0:
            clauses.append(f"fiscal_year = {int(fy)}" if fy is not None else "fiscal_year IS NULL")
            meta_yrs = (int(fy),)
        if g_sec == 0:
            clauses.append(f"section = '{sec}'" if sec is not None else "section IS NULL")
            meta_secs = (sec,)
        s = n_rows / total_rows
        filters.append({
            "filter_id": f"edgar_{fid:05d}",
            "where_clause": " AND ".join(clauses),
            "n_rows": int(n_rows),
            "s": s,
            "usable": int(n_rows) >= MIN_ROWS,
            "type": "natural",
            "band_edgar": assign_band(s, t_edgar),
            "band_hm": assign_band(s, t_hm),
            "_ciks": meta_ciks,
            "_years": meta_yrs,
            "_sections": meta_secs,
        })

    # Distinct values present for constructed widenings
    cur.execute("SELECT DISTINCT fiscal_year FROM edgar_chunks ORDER BY fiscal_year")
    years = [int(r[0]) for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT section FROM edgar_chunks ORDER BY section")
    sections = [r[0] for r in cur.fetchall()]

    year_ranges = []
    for w in range(2, len(years) + 1):
        for i in range(len(years) - w + 1):
            year_ranges.append(tuple(years[i : i + w]))

    section_subsets = []
    for sz in range(2, min(3, len(sections)) + 1):
        section_subsets.extend(itertools.combinations(sections, sz))

    # Construct bounded widened filter specs:
    # 1) year_range alone
    # 2) section_subset alone
    # 3) year_range + single section
    # 4) single year + section_subset
    # 5) year_range + section_subset
    constructed_specs = []
    for yr in year_ranges:
        constructed_specs.append((yr, None))
    for ss in section_subsets:
        constructed_specs.append((None, ss))
    for yr in year_ranges:
        for s1 in sections:
            constructed_specs.append((yr, (s1,)))
    for y1 in years:
        for ss in section_subsets:
            constructed_specs.append(((y1,), ss))
    for yr in year_ranges:
        for ss in section_subsets:
            constructed_specs.append((yr, ss))

    for yr, ss in constructed_specs:
        clauses, params = [], []
        if yr is not None:
            if len(yr) == 1:
                clauses.append("fiscal_year = %s")
                params.append(yr[0])
            else:
                clauses.append("fiscal_year = ANY(%s)")
                params.append(list(yr))
        if ss is not None:
            if len(ss) == 1:
                clauses.append("section = %s")
                params.append(ss[0])
            else:
                clauses.append("section = ANY(%s)")
                params.append(list(ss))
        where_sql = " AND ".join(clauses)
        cur.execute(f"SELECT COUNT(*) FROM edgar_chunks WHERE {where_sql}", params)
        n_rows = int(cur.fetchone()[0])

        # Readable WHERE clause
        r_clauses = []
        if yr is not None:
            r_clauses.append(f"fiscal_year = {yr[0]}" if len(yr) == 1 else f"fiscal_year IN ({', '.join(map(str, yr))})")
        if ss is not None:
            qsecs = ", ".join(f"'{x}'" for x in ss)
            r_clauses.append(f"section = '{ss[0]}'" if len(ss) == 1 else f"section IN ({qsecs})")
        fid += 1
        s = n_rows / total_rows
        filters.append({
            "filter_id": f"edgar_{fid:05d}",
            "where_clause": " AND ".join(r_clauses),
            "n_rows": n_rows,
            "s": s,
            "usable": n_rows >= MIN_ROWS,
            "type": "constructed",
            "band_edgar": assign_band(s, t_edgar),
            "band_hm": assign_band(s, t_hm),
            "_ciks": None,
            "_years": yr,
            "_sections": ss,
        })

    info = {
        "total_rows": total_rows,
        "years": years,
        "sections": sections,
        "n_natural": sum(1 for f in filters if f["type"] == "natural"),
        "n_constructed": sum(1 for f in filters if f["type"] == "constructed"),
        "gs_sql": gs_sql.strip(),
    }
    return total_rows, filters, info


def step_c_finqa_filters(cur, t_edgar: float, t_hm: float) -> tuple[int, list[dict], dict]:
    cur.execute("SELECT COUNT(*) FROM finqa_evidence")
    total_rows = int(cur.fetchone()[0])

    # Verify all metadata->>'year' cast cleanly to int
    cur.execute("SELECT COUNT(*) FROM finqa_evidence WHERE metadata->>'year' IS NULL OR metadata->>'year' !~ '^-?\\d+$'")
    bad_years = int(cur.fetchone()[0])
    if bad_years > 0:
        raise SystemExit(f"Found {bad_years} rows in finqa_evidence where metadata->>'year' does not cast to int")

    cur.execute("SELECT MIN((metadata->>'year')::int), MAX((metadata->>'year')::int), COUNT(DISTINCT metadata->>'ticker') FROM finqa_evidence")
    min_yr, max_yr, n_tickers = cur.fetchone()

    filters: list[dict] = []
    fid = 0

    gs_sql = """
        SELECT metadata->>'ticker' AS ticker,
               (metadata->>'year')::int AS year,
               GROUPING(metadata->>'ticker') AS g_ticker,
               GROUPING((metadata->>'year')::int) AS g_year,
               COUNT(*) AS n_rows
        FROM finqa_evidence
        GROUP BY GROUPING SETS (
            (metadata->>'ticker', (metadata->>'year')::int),
            (metadata->>'ticker'),
            ((metadata->>'year')::int)
        )
        ORDER BY g_ticker, g_year, ticker NULLS LAST, year NULLS LAST
    """
    cur.execute(gs_sql)
    for ticker, yr, g_t, g_y, n_rows in cur.fetchall():
        fid += 1
        clauses = []
        if g_t == 0:
            clauses.append(f"metadata->>'ticker' = '{ticker}'" if ticker is not None else "metadata->>'ticker' IS NULL")
        if g_y == 0:
            clauses.append(f"(metadata->>'year')::int = {int(yr)}" if yr is not None else "metadata->>'year' IS NULL")
        s = int(n_rows) / total_rows
        filters.append({
            "filter_id": f"finqa_{fid:05d}",
            "where_clause": " AND ".join(clauses),
            "n_rows": int(n_rows),
            "s": s,
            "usable": int(n_rows) >= MIN_ROWS,
            "type": "natural",
            "band_hm": assign_band(s, t_hm),
            "band_edgar_ref": assign_band(s, t_edgar),
            "_tickers": (ticker,) if g_t == 0 else None,
            "_year_range": (int(yr), int(yr)) if g_y == 0 else None,
        })

    # Distinct years and tickers for constructed filters
    cur.execute("SELECT DISTINCT (metadata->>'year')::int AS y FROM finqa_evidence ORDER BY y")
    years = [int(r[0]) for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT metadata->>'ticker' AS t FROM finqa_evidence ORDER BY t")
    tickers = [r[0] for r in cur.fetchall()]

    # Year ranges of width 2 up to all years (using contiguous slices of sorted distinct years)
    for w in range(2, len(years) + 1):
        for i in range(len(years) - w + 1):
            a, b = years[i], years[i + w - 1]
            cur.execute(
                "SELECT COUNT(*) FROM finqa_evidence WHERE (metadata->>'year')::int BETWEEN %s AND %s",
                (a, b),
            )
            n_rows = int(cur.fetchone()[0])
            fid += 1
            s = n_rows / total_rows
            filters.append({
                "filter_id": f"finqa_{fid:05d}",
                "where_clause": f"(metadata->>'year')::int BETWEEN {a} AND {b}",
                "n_rows": n_rows,
                "s": s,
                "usable": n_rows >= MIN_ROWS,
                "type": "constructed",
                "band_hm": assign_band(s, t_hm),
                "band_edgar_ref": assign_band(s, t_edgar),
                "_tickers": None,
                "_year_range": (a, b),
            })

    # Seeded ticker IN (...) lists of size 2..10 (25 draws per size = 225 lists)
    rng = random.Random(SEED)
    seen_sets: set[tuple[str, ...]] = set()
    for sz in range(2, 11):
        for _ in range(25):
            sample = tuple(sorted(rng.sample(tickers, sz)))
            if sample in seen_sets:
                continue
            seen_sets.add(sample)
            cur.execute("SELECT COUNT(*) FROM finqa_evidence WHERE metadata->>'ticker' = ANY(%s)", (list(sample),))
            n_rows = int(cur.fetchone()[0])
            fid += 1
            s = n_rows / total_rows
            qlist = ", ".join(f"'{t}'" for t in sample)
            filters.append({
                "filter_id": f"finqa_{fid:05d}",
                "where_clause": f"metadata->>'ticker' IN ({qlist})",
                "n_rows": n_rows,
                "s": s,
                "usable": n_rows >= MIN_ROWS,
                "type": "constructed",
                "band_hm": assign_band(s, t_hm),
                "band_edgar_ref": assign_band(s, t_edgar),
                "_tickers": sample,
                "_year_range": None,
            })

    info = {
        "total_rows": total_rows,
        "min_year": int(min_yr),
        "max_year": int(max_yr),
        "n_years": len(years),
        "n_tickers": int(n_tickers),
        "n_natural": sum(1 for f in filters if f["type"] == "natural"),
        "n_constructed": sum(1 for f in filters if f["type"] == "constructed"),
        "gs_sql": gs_sql.strip(),
    }
    return total_rows, filters, info


def step_d_band_summary(edgar_filters: list[dict], finqa_filters: list[dict]) -> list[dict]:
    specs = [
        ("edgar_chunks", "T_edgar", edgar_filters, "band_edgar"),
        ("edgar_chunks", "T_hm", edgar_filters, "band_hm"),
        ("finqa_evidence", "T_hm", finqa_filters, "band_hm"),
        ("finqa_evidence", "T_edgar_ref", finqa_filters, "band_edgar_ref"),
    ]
    summary = []
    for table, t_label, flist, band_col in specs:
        usable = [f for f in flist if f["usable"]]
        for band in BANDS:
            b_all = [f for f in usable if f[band_col] == band]
            n_nat = sum(1 for f in b_all if f["type"] == "natural")
            n_con = sum(1 for f in b_all if f["type"] == "constructed")
            min_s = min((f["s"] for f in b_all), default=None)
            max_s = max((f["s"] for f in b_all), default=None)
            summary.append({
                "table": table,
                "threshold": t_label,
                "band": band,
                "usable_total": len(b_all),
                "natural": n_nat,
                "constructed": n_con,
                "min_s": f"{min_s:.6f}" if min_s is not None else "",
                "max_s": f"{max_s:.6f}" if max_s is not None else "",
            })
    return summary


def step_e_gold_containment(cur, edgar_filters: list[dict], finqa_filters: list[dict]) -> tuple[list[dict], dict]:
    sel_path = PROJECT_ROOT / "outputs/edgar_eval_set_2026-11-01/selected.csv"
    cal_path = PROJECT_ROOT / "outputs/edgar_eval_set_2026-11-01/calibration_queries.csv"
    with open(sel_path, encoding="utf-8", newline="") as f:
        sel_reader = csv.DictReader(f)
        sel_cols = list(sel_reader.fieldnames or [])
        sel_rows = list(sel_reader)
    with open(cal_path, encoding="utf-8", newline="") as f:
        cal_reader = csv.DictReader(f)
        cal_cols = list(cal_reader.fieldnames or [])
        cal_rows = list(cal_reader)

    sel_qids = {r["qid"] for r in sel_rows}
    cal_qids = {r["qid"] for r in cal_rows}
    disjoint = len(sel_qids & cal_qids) == 0

    # EDGAR gold containment per band under T_edgar (and T_hm)
    usable_edgar = [f for f in edgar_filters if f["usable"]]
    edgar_q_counts = {b: 0 for b in BANDS}
    edgar_q_counts_hm = {b: 0 for b in BANDS}
    for q in sel_rows:
        q_cik = str(q["cik"])
        q_yr = int(q["fiscal_year"])
        q_sec = str(q["section"])
        hit_edgar = {b: 0 for b in BANDS}
        hit_hm = {b: 0 for b in BANDS}
        for f in usable_edgar:
            if f["_ciks"] is not None and q_cik not in f["_ciks"]:
                continue
            if f["_years"] is not None and q_yr not in f["_years"]:
                continue
            if f["_sections"] is not None and q_sec not in f["_sections"]:
                continue
            hit_edgar[f["band_edgar"]] += 1
            hit_hm[f["band_hm"]] += 1
        for b in BANDS:
            if hit_edgar[b] > 0:
                edgar_q_counts[b] += 1
            if hit_hm[b] > 0:
                edgar_q_counts_hm[b] += 1

    # FinQA gold containment check: verify if finqa_test.json (ticker, year) matches finqa_evidence rows
    finqa_test = json.loads((PROJECT_ROOT / "data/raw/finqa_test.json").read_text(encoding="utf-8"))
    cur.execute("SELECT DISTINCT metadata->>'ticker', (metadata->>'year')::int FROM finqa_evidence")
    db_ty_pairs = {(r[0], int(r[1])) for r in cur.fetchall()}

    usable_finqa = [f for f in finqa_filters if f["usable"]]
    finqa_matched_in_db = 0
    finqa_q_counts = {b: 0 for b in BANDS}
    for ex in finqa_test:
        parts = ex["id"].split("/")
        q_ticker = parts[0]
        q_yr = int(parts[1])
        if (q_ticker, q_yr) in db_ty_pairs:
            finqa_matched_in_db += 1
        hit = {b: 0 for b in BANDS}
        for f in usable_finqa:
            if f["_tickers"] is not None and q_ticker not in f["_tickers"]:
                continue
            if f["_year_range"] is not None:
                a, b_yr = f["_year_range"]
                if not (a <= q_yr <= b_yr):
                    continue
            hit[f["band_hm"]] += 1
        for b in BANDS:
            if hit[b] > 0:
                finqa_q_counts[b] += 1

    rows_out = []
    for b in BANDS:
        rows_out.append({
            "dataset": "edgar_chunks",
            "threshold": "T_edgar",
            "band": b,
            "n_questions": len(sel_rows),
            "questions_with_ge_1_filter": edgar_q_counts[b],
        })
    for b in BANDS:
        rows_out.append({
            "dataset": "edgar_chunks",
            "threshold": "T_hm",
            "band": b,
            "n_questions": len(sel_rows),
            "questions_with_ge_1_filter": edgar_q_counts_hm[b],
        })
    for b in BANDS:
        rows_out.append({
            "dataset": "finqa_evidence",
            "threshold": "T_hm",
            "band": b,
            "n_questions": len(finqa_test),
            "questions_with_ge_1_filter": finqa_q_counts[b],
        })

    meta = {
        "selected_cols": sel_cols,
        "cal_cols": cal_cols,
        "n_selected": len(sel_rows),
        "n_calibration": len(cal_rows),
        "disjoint": disjoint,
        "n_finqa_test": len(finqa_test),
        "finqa_ty_in_db": finqa_matched_in_db,
    }
    return rows_out, meta


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fieldnames})


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_edgar, t_hm = load_thresholds()
    step_a = step_a_edgar_manifest(t_edgar, t_hm)

    conn = open_read_only_conn()
    try:
        cur = conn.cursor()
        edgar_total, edgar_filters, edgar_info = step_b_edgar_filters(cur, t_edgar, t_hm)
        finqa_total, finqa_filters, finqa_info = step_c_finqa_filters(cur, t_edgar, t_hm)
        step_d = step_d_band_summary(edgar_filters, finqa_filters)
        step_e, meta_e = step_e_gold_containment(cur, edgar_filters, finqa_filters)
        cur.close()
    finally:
        conn.rollback()
        conn.close()

    # Write CSVs
    write_csv(
        OUT_DIR / "edgar_filters.csv",
        edgar_filters,
        ["filter_id", "where_clause", "n_rows", "s", "usable", "type", "band_edgar", "band_hm"],
    )
    write_csv(
        OUT_DIR / "finqa_filters.csv",
        finqa_filters,
        ["filter_id", "where_clause", "n_rows", "s", "usable", "type", "band_hm", "band_edgar_ref"],
    )
    write_csv(
        OUT_DIR / "band_summary.csv",
        step_d,
        ["table", "threshold", "band", "usable_total", "natural", "constructed", "min_s", "max_s"],
    )
    write_csv(
        OUT_DIR / "gold_containment_summary.csv",
        step_e,
        ["dataset", "threshold", "band", "n_questions", "questions_with_ge_1_filter"],
    )

    # Write REPORT.md
    lines = [
        "# Straddle-T Feasibility Enumeration Report (2026-11-15)",
        "",
        "## Config & Thresholds",
        f"- `T_edgar` = `{t_edgar}` (from `config/policy_v3_1_edgar.json`)",
        f"- `T_hm` = `{t_hm}` (from `config/policy_v3_1_hm.json`)",
        "- Contiguous bands: `far_below`: $s \\le T/2$; `near_below`: $T/2 < s \\le T$; `near_above`: $T < s \\le 2T$; `far_above`: $s > 2T$.",
        "",
        "## Table Row Counts",
        f"- `edgar_chunks`: `{edgar_total}` rows (years: {edgar_info['years']}, sections: {edgar_info['sections']})",
        f"- `finqa_evidence`: `{finqa_total}` rows (years: {finqa_info['min_year']}..{finqa_info['max_year']} across {finqa_info['n_years']} distinct years; {finqa_info['n_tickers']} distinct tickers)",
        "",
        "## Step A: Existing EDGAR Manifest (`pairs.csv`)",
        "| threshold | breadth | far_below | near_below | near_above | far_above | total |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in step_a:
        lines.append(f"| {r['threshold']} | {r['breadth']} | {r['far_below']} | {r['near_below']} | {r['near_above']} | {r['far_above']} | {r['total']} |")

    lines.extend([
        "",
        "## Step D: Band Population Summary (usable filters, n_rows >= 15)",
        "| table | threshold | band | usable_total | natural | constructed | min_s | max_s |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ])
    for r in step_d:
        lines.append(f"| {r['table']} | {r['threshold']} | {r['band']} | {r['usable_total']} | {r['natural']} | {r['constructed']} | {r['min_s']} | {r['max_s']} |")

    lines.extend([
        "",
        "## Step E: Gold-Containment Feasibility",
        f"- `selected.csv` ({meta_e['n_selected']} rows) columns: `{meta_e['selected_cols']}` (gold key: `cik`, `fiscal_year`, `section`, `gold_text_hash`)",
        f"- `calibration_queries.csv` ({meta_e['n_calibration']} rows) columns: `{meta_e['cal_cols']}`",
        f"- Disjointness confirmed: `{meta_e['disjoint']}`",
        f"- FinQA `finqa_test.json` ({meta_e['n_finqa_test']} questions): `(ticker, year)` present in `finqa_evidence` for `{meta_e['finqa_ty_in_db']}` / `{meta_e['n_finqa_test']}` questions.",
        "",
        "| dataset | threshold | band | n_questions | questions_with_ge_1_filter |",
        "|---|---|---|---:|---:|",
    ])
    for r in step_e:
        lines.append(f"| {r['dataset']} | {r['threshold']} | {r['band']} | {r['n_questions']} | {r['questions_with_ge_1_filter']} |")

    lines.extend([
        "",
        "## Exact SQL Used",
        "### EDGAR GROUPING SETS",
        "```sql",
        edgar_info["gs_sql"],
        "```",
        "",
        "### FinQA GROUPING SETS",
        "```sql",
        finqa_info["gs_sql"],
        "```",
    ])
    (OUT_DIR / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Console summary
    print(f"EDGAR filters generated: {len(edgar_filters)} (natural={edgar_info['n_natural']}, constructed={edgar_info['n_constructed']})")
    print(f"FinQA filters generated: {len(finqa_filters)} (natural={finqa_info['n_natural']}, constructed={finqa_info['n_constructed']})")
    print(f"FinQA years: {finqa_info['min_year']}..{finqa_info['max_year']}, distinct tickers: {finqa_info['n_tickers']}")
    print("Done. Wrote outputs to", OUT_DIR)


if __name__ == "__main__":
    main()
