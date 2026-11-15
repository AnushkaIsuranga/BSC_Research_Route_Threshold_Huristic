"""Build and freeze the straddle-T pair manifest per Phase G Amendment 12.

Selection only (BEGIN READ ONLY for DB gold verification; no router, timing, or LLM calls).
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import PROJECT_ROOT, db_settings

SEED = 20261115
SMOKE_SEED = 20261116
FINQA_N = 100
K_EXPECTED = 15

BANDS = ("far_below", "near_below", "near_above", "far_above")
PRIMARY_TIERS = {"natural", "plausible_constructed"}
NATURAL_TIERS = {"natural"}
RANDOM_TIERS = {"random_constructed"}

POOL_DIR = PROJECT_ROOT / "outputs/straddle_t_feasibility_2026-11-15/pool"
OUT_DIR = PROJECT_ROOT / "outputs/straddle_t_manifest_2026-11-15"

PAIR_COLS = [
    "pair_id",
    "qid",
    "band",
    "T_name",
    "T_value",
    "analysis_group",
    "pool_id",
    "where_clause",
    "n_rows",
    "s",
    "tier",
    "boundary_flag",
    "natural_available",
    "gold_in_filter",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assign_band(s: float, T: float) -> str:
    if s <= T / 2.0:
        return "far_below"
    if s <= T:
        return "near_below"
    if s <= 2.0 * T:
        return "near_above"
    return "far_above"


def analysis_group_for(band: str) -> str:
    return "below_T" if band in ("far_below", "near_below") else "above_T"


def parse_edgar_where(wc: str) -> tuple[set[str] | None, set[int] | None, set[str] | None]:
    ciks, yrs, secs = None, None, None
    m_cik = re.search(r"cik\s*=\s*'([^']+)'", wc)
    m_cik_in = re.search(r"cik\s+IN\s*\(([^)]+)\)", wc)
    if m_cik:
        ciks = {m_cik.group(1)}
    elif m_cik_in:
        ciks = set(re.findall(r"'([^']+)'", m_cik_in.group(1)))
    m_fy_eq = re.search(r"fiscal_year\s*=\s*(\d+)", wc)
    m_fy_in = re.search(r"fiscal_year\s+IN\s*\(([^)]+)\)", wc)
    m_fy_bw = re.search(r"fiscal_year\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)", wc)
    if m_fy_eq:
        yrs = {int(m_fy_eq.group(1))}
    elif m_fy_in:
        yrs = {int(x) for x in re.findall(r"\d+", m_fy_in.group(1))}
    elif m_fy_bw:
        yrs = set(range(int(m_fy_bw.group(1)), int(m_fy_bw.group(2)) + 1))
    m_sec_eq = re.search(r"section\s*=\s*'([^']+)'", wc)
    m_sec_in = re.search(r"section\s+IN\s*\(([^)]+)\)", wc)
    if m_sec_eq:
        secs = {m_sec_eq.group(1)}
    elif m_sec_in:
        secs = set(re.findall(r"'([^']+)'", m_sec_in.group(1)))
    return ciks, yrs, secs


def parse_finqa_where(wc: str) -> tuple[set[str] | None, tuple[int, int] | None]:
    tks, yr_rng = None, None
    m_tk_eq = re.search(r"metadata->>'ticker'\s*=\s*'([^']+)'", wc)
    m_tk_in = re.search(r"metadata->>'ticker'\s+IN\s*\(([^)]+)\)", wc)
    if m_tk_eq:
        tks = {m_tk_eq.group(1)}
    elif m_tk_in:
        tks = set(re.findall(r"'([^']+)'", m_tk_in.group(1)))
    m_yr_eq = re.search(r"\(metadata->>'year'\)::int\s*=\s*(\d+)", wc)
    m_yr_bw = re.search(r"\(metadata->>'year'\)::int\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)", wc)
    if m_yr_eq:
        y = int(m_yr_eq.group(1))
        yr_rng = (y, y)
    elif m_yr_bw:
        yr_rng = (int(m_yr_bw.group(1)), int(m_yr_bw.group(2)))
    return tks, yr_rng


def edgar_matches_q(f: dict, q: dict) -> bool:
    ciks, yrs, secs = f["_parsed"]
    if ciks is not None and str(q["cik"]) not in ciks:
        return False
    if yrs is not None and int(q["fiscal_year"]) not in yrs:
        return False
    if secs is not None and str(q["section"]) not in secs:
        return False
    return True


def finqa_matches_q(f: dict, q: dict) -> bool:
    tks, yr_rng = f["_parsed"]
    if tks is not None and q["ticker"] not in tks:
        return False
    if yr_rng is not None and not (yr_rng[0] <= q["year"] <= yr_rng[1]):
        return False
    return True


def step0_verify() -> tuple[float, float, int, dict[str, str]]:
    tags = subprocess.check_output(
        ["git", "tag", "-l", "phase-g-amendment-12*"],
        cwd=PROJECT_ROOT,
        text=True,
    ).splitlines()
    assert "phase-g-amendment-12" in tags, f"Missing tag phase-g-amendment-12; got {tags}"
    assert "phase-g-amendment-12-addendum-1" in tags, f"Missing tag phase-g-amendment-12-addendum-1; got {tags}"

    amend12_sha = sha256_file(PROJECT_ROOT / "docs/preregistration/PHASE_G_AMENDMENT_12.md")
    expected_amend12 = "443c27cbf4462fbe58d09b2035c4383f872125e9d9d356859c04493bcd49e0f5"
    assert amend12_sha == expected_amend12, f"Amendment 12 SHA mismatch: {amend12_sha} != {expected_amend12}"

    pool_checks: dict[str, str] = {}
    for line in (POOL_DIR / "POOL_CHECKSUMS.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        expected, fname = line.split(None, 1)
        actual = sha256_file(POOL_DIR / fname)
        assert actual == expected, f"Pool checksum mismatch for {fname}: {actual} != {expected}"
        pool_checks[fname] = actual

    t_edgar = float(json.loads((PROJECT_ROOT / "config/policy_v3_1_edgar.json").read_text(encoding="utf-8"))["T_default"])
    t_hm = float(json.loads((PROJECT_ROOT / "config/policy_v3_1_hm.json").read_text(encoding="utf-8"))["T_default"])
    k_val = int(json.loads((PROJECT_ROOT / "config/router_edgar.json").read_text(encoding="utf-8"))["k"])
    assert k_val == K_EXPECTED, f"Expected k={K_EXPECTED}, got {k_val}"
    print(f"T_edgar = {t_edgar}")
    print(f"T_hm    = {t_hm}")
    print(f"k       = {k_val}")
    return t_edgar, t_hm, k_val, pool_checks


def load_usable_pool(csv_path: Path, is_edgar: bool, t_edgar: float, t_hm: float) -> list[dict]:
    usable = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            n_rows = int(row["n_rows"])
            s = float(row["s"])
            degen = row["degenerate_all_rows"] == "True"
            if n_rows < 15 or degen or s > 0.95:
                continue
            row["n_rows"] = n_rows
            row["s"] = s
            row["degenerate_all_rows"] = degen
            if is_edgar:
                assert row["band_T_edgar"] == assign_band(s, t_edgar)
                assert row["band_T_hm"] == assign_band(s, t_hm)
                row["_parsed"] = parse_edgar_where(row["where_clause"])
            else:
                assert row["band_T_hm"] == assign_band(s, t_hm)
                row["_parsed"] = parse_finqa_where(row["where_clause"])
            usable.append(row)
    return usable


def draw_pairs(
    questions: list[dict],
    filters: list[dict],
    match_fn,
    dataset: str,
    t_name: str,
    t_val: float,
    band_col: str,
    bands_to_draw: tuple[str, ...],
    allowed_tiers: set[str],
    rng_suffix: str = "",
) -> tuple[list[dict], dict[str, int], dict[str, int]]:
    rows = []
    elig_counts = {b: 0 for b in BANDS}
    inelig_counts = {b: 0 for b in BANDS}

    for band in BANDS:
        for q in questions:
            qid = q["qid"]
            cands = [
                f
                for f in filters
                if f[band_col] == band and f["tier"] in allowed_tiers and match_fn(f, q)
            ]
            nat_cands = [
                f
                for f in filters
                if f[band_col] == band and f["tier"] in NATURAL_TIERS and match_fn(f, q)
            ]
            if not cands:
                inelig_counts[band] += 1
                continue
            elig_counts[band] += 1
            if band not in bands_to_draw:
                continue
            cands.sort(key=lambda x: x["pool_id"])
            rng = random.Random(f"{SEED}|{dataset}|{t_name}|{band}|{qid}{rng_suffix}")
            chosen = rng.choice(cands)
            rows.append({
                "pair_id": f"{dataset}_{t_name}{rng_suffix.replace('|', '_')}|{band}|{qid}",
                "qid": qid,
                "band": band,
                "T_name": t_name,
                "T_value": t_val,
                "analysis_group": analysis_group_for(band),
                "pool_id": chosen["pool_id"],
                "where_clause": chosen["where_clause"],
                "n_rows": chosen["n_rows"],
                "s": chosen["s"],
                "tier": chosen["tier"],
                "boundary_flag": abs(chosen["s"] - t_val) / t_val <= 0.25,
                "natural_available": len(nat_cands) > 0,
                "gold_in_filter": None,  # verified by SQL below
                "_q": q,
                "_dataset": dataset,
            })
    return rows, elig_counts, inelig_counts


def verify_gold_sql(all_manifests: list[list[dict]]) -> tuple[int, str, str, str]:
    conn = psycopg2.connect(**db_settings())
    edgar_sql = (
        "SELECT EXISTS (SELECT 1 FROM edgar_chunks "
        "WHERE ({wc}) AND cik = %s AND fiscal_year = %s AND section = %s AND text_hash = %s)"
    )
    finqa_sql = (
        "SELECT EXISTS (SELECT 1 FROM finqa_evidence "
        "WHERE ({wc}) AND metadata->>'ticker' = %s AND (metadata->>'year')::int = %s)"
    )
    cache: dict[tuple, bool] = {}
    ro_state = "unknown"
    try:
        with conn:
            pass
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute("BEGIN READ ONLY")
            cur.execute("SHOW transaction_read_only")
            ro_state = cur.fetchone()[0]
            assert ro_state == "on", f"Expected transaction_read_only=on, got {ro_state}"
            for manifest in all_manifests:
                for r in manifest:
                    q = r["_q"]
                    if r["_dataset"] == "edgar":
                        key = ("edgar", r["where_clause"], q["cik"], q["fiscal_year"], q["section"], q["gold_text_hash"])
                        if key not in cache:
                            cur.execute(
                                edgar_sql.format(wc=r["where_clause"]),
                                (str(q["cik"]), int(q["fiscal_year"]), str(q["section"]), q["gold_text_hash"]),
                            )
                            cache[key] = bool(cur.fetchone()[0])
                    else:
                        key = ("finqa", r["where_clause"], q["ticker"], q["year"])
                        if key not in cache:
                            cur.execute(
                                finqa_sql.format(wc=r["where_clause"]),
                                (q["ticker"], int(q["year"])),
                            )
                            cache[key] = bool(cur.fetchone()[0])
                    r["gold_in_filter"] = cache[key]
            cur.execute("ROLLBACK")
    finally:
        conn.close()
    return len(cache), ro_state, edgar_sql, finqa_sql


def write_manifest_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PAIR_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in PAIR_COLS})


def main() -> None:
    t_edgar, t_hm, k_val, pool_checks = step0_verify()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    edgar_pool = load_usable_pool(POOL_DIR / "edgar_pool.csv", True, t_edgar, t_hm)
    finqa_pool = load_usable_pool(POOL_DIR / "finqa_pool.csv", False, t_edgar, t_hm)

    edgar_qs = list(csv.DictReader((PROJECT_ROOT / "outputs/edgar_eval_set_2026-11-01/selected.csv").open(encoding="utf-8")))
    finqa_raw = json.loads((PROJECT_ROOT / "data/raw/finqa_test.json").read_text(encoding="utf-8"))
    finqa_qs = []
    for ex in finqa_raw:
        qid = ex["id"]
        tk, yr = qid.split("/")[0], int(qid.split("/")[1])
        finqa_qs.append({"qid": qid, "ticker": tk, "year": yr})

    # Step 2A: EDGAR primary T_edgar
    edgar_prim, ep_elig, ep_inelig = draw_pairs(
        edgar_qs, edgar_pool, edgar_matches_q, "edgar", "T_edgar", t_edgar, "band_T_edgar", BANDS, PRIMARY_TIERS
    )
    # Step 2B: EDGAR secondary T_hm (skip near_below)
    edgar_sec, es_elig, es_inelig = draw_pairs(
        edgar_qs, edgar_pool, edgar_matches_q, "edgar", "T_hm", t_hm, "band_T_hm",
        ("far_below", "near_above", "far_above"), PRIMARY_TIERS,
    )
    with (OUT_DIR / "edgar_not_testable.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "T_name", "band", "n_distinct_filters", "n_eligible_questions", "n_total_questions", "reason"])
        w.writeheader()
        w.writerow({
            "table": "edgar_chunks",
            "T_name": "T_hm",
            "band": "near_below",
            "n_distinct_filters": sum(1 for r in edgar_pool if r["band_T_hm"] == "near_below" and r["tier"] in PRIMARY_TIERS),
            "n_eligible_questions": es_elig["near_below"],
            "n_total_questions": len(edgar_qs),
            "reason": "6 distinct filters, 10 of 40 questions eligible (declared not testable in Amendment 12 Section 4)",
        })

    # Step 3: FinQA T_hm (605 eligible in all 4 bands -> draw 100)
    eligible_4band = []
    for q in finqa_qs:
        bands_ok = {
            f["band_T_hm"]
            for f in finqa_pool
            if f["tier"] in PRIMARY_TIERS and finqa_matches_q(f, q)
        }
        if len(bands_ok) == 4:
            eligible_4band.append(q)
    assert len(eligible_4band) == 605, f"Expected 605 FinQA 4-band eligible questions, got {len(eligible_4band)}"
    eligible_4band.sort(key=lambda q: q["qid"])
    finqa_100 = random.Random(f"{SEED}|finqa|questions").sample(eligible_4band, FINQA_N)

    finqa_prim, fp_elig, fp_inelig = draw_pairs(
        finqa_100, finqa_pool, finqa_matches_q, "finqa", "T_hm", t_hm, "band_T_hm", BANDS, PRIMARY_TIERS
    )
    finqa_rand, fr_elig, fr_inelig = draw_pairs(
        finqa_100, finqa_pool, finqa_matches_q, "finqa", "T_hm", t_hm, "band_T_hm", BANDS, RANDOM_TIERS
    )
    for r in finqa_rand:
        r["pair_id"] = r["pair_id"].replace("finqa_T_hm|", "finqa_T_hm_random|")

    # Step 4: Sensitivity (natural_only)
    nat_edgar_edgar, nee_elig, nee_inelig = draw_pairs(
        edgar_qs, edgar_pool, edgar_matches_q, "edgar", "T_edgar", t_edgar, "band_T_edgar", BANDS, NATURAL_TIERS, "|natural"
    )
    nat_edgar_hm, neh_elig, neh_inelig = draw_pairs(
        edgar_qs, edgar_pool, edgar_matches_q, "edgar", "T_hm", t_hm, "band_T_hm",
        ("far_below", "near_above", "far_above"), NATURAL_TIERS, "|natural"
    )
    nat_finqa_hm, nfh_elig, nfh_inelig = draw_pairs(
        finqa_100, finqa_pool, finqa_matches_q, "finqa", "T_hm", t_hm, "band_T_hm", BANDS, NATURAL_TIERS, "|natural"
    )

    all_manifests = [edgar_prim, edgar_sec, finqa_prim, finqa_rand, nat_edgar_edgar, nat_edgar_hm, nat_finqa_hm]
    n_sql_checks, ro_state, edgar_sql, finqa_sql = verify_gold_sql(all_manifests)

    # Step 5: Smoke-test manifest (seed 20261116)
    rng_smoke = random.Random(SMOKE_SEED)
    edgar_fb = sorted([r for r in edgar_prim if r["band"] == "far_below"], key=lambda r: r["pair_id"])
    edgar_nb = sorted([r for r in edgar_prim if r["band"] == "near_below"], key=lambda r: r["pair_id"])
    edgar_na = sorted([r for r in edgar_prim if r["band"] == "near_above"], key=lambda r: r["pair_id"])
    edgar_fa = sorted([r for r in edgar_prim if r["band"] == "far_above"], key=lambda r: r["pair_id"])
    smoke_edgar = (
        rng_smoke.sample(edgar_fb, 2)
        + rng_smoke.sample(edgar_nb, 3)
        + rng_smoke.sample(edgar_na, 3)
        + rng_smoke.sample(edgar_fa, 2)
    )
    finqa_sorted = sorted(finqa_prim, key=lambda r: r["pair_id"])
    smoke_finqa = rng_smoke.sample(finqa_sorted, 4)
    smoke_rows = smoke_edgar + smoke_finqa

    # Step 6: Assertions
    for m_name, m in [
        ("edgar_pairs_primary_T_edgar", edgar_prim),
        ("edgar_pairs_secondary_T_hm", edgar_sec),
        ("finqa_pairs_primary_T_hm", finqa_prim),
        ("finqa_pairs_secondary_random", finqa_rand),
        ("natural_only_edgar_T_edgar", nat_edgar_edgar),
        ("natural_only_edgar_T_hm", nat_edgar_hm),
        ("natural_only_finqa_T_hm", nat_finqa_hm),
        ("smoke_test_pairs", smoke_rows),
    ]:
        seen = set()
        for r in m:
            assert r["s"] <= 0.95, f"{m_name}: s > 0.95 in {r['pair_id']}"
            assert r["n_rows"] >= 15, f"{m_name}: n_rows < 15 in {r['pair_id']}"
            assert r["gold_in_filter"] is True, f"{m_name}: gold_in_filter False in {r['pair_id']}"
            assert r["band"] == assign_band(r["s"], r["T_value"]), f"{m_name}: band mismatch in {r['pair_id']}"
            key = (r["qid"], r["band"], r["T_name"])
            if m_name != "smoke_test_pairs":
                assert key not in seen, f"{m_name}: duplicate {key}"
                seen.add(key)

    edgar_prim_fa_pools = {r["pool_id"] for r in edgar_prim if r["band"] == "far_above"}
    assert edgar_prim_fa_pools == {"edgar_pool_10236"}, f"Expected only edgar_pool_10236, got {edgar_prim_fa_pools}"
    for b in BANDS:
        assert sum(1 for r in edgar_prim if r["band"] == b) == ep_elig[b]
        assert sum(1 for r in finqa_prim if r["band"] == b) == 100
        if b != "near_below":
            assert sum(1 for r in edgar_sec if r["band"] == b) == es_elig[b]

    # Write manifest CSVs
    outputs = {
        "edgar_pairs_primary_T_edgar.csv": edgar_prim,
        "edgar_pairs_secondary_T_hm.csv": edgar_sec,
        "finqa_pairs_primary_T_hm.csv": finqa_prim,
        "finqa_pairs_secondary_random.csv": finqa_rand,
        "natural_only_edgar_T_edgar.csv": nat_edgar_edgar,
        "natural_only_edgar_T_hm.csv": nat_edgar_hm,
        "natural_only_finqa_T_hm.csv": nat_finqa_hm,
        "smoke_test_pairs.csv": smoke_rows,
    }
    for fname, rows in outputs.items():
        write_manifest_csv(OUT_DIR / fname, rows)

    counts_rows = []
    for label, rows, elig, inelig in [
        ("edgar_pairs_primary_T_edgar", edgar_prim, ep_elig, ep_inelig),
        ("edgar_pairs_secondary_T_hm", edgar_sec, es_elig, es_inelig),
        ("finqa_pairs_primary_T_hm", finqa_prim, fp_elig, fp_inelig),
        ("finqa_pairs_secondary_random", finqa_rand, fr_elig, fr_inelig),
        ("natural_only_edgar_T_edgar", nat_edgar_edgar, nee_elig, nee_inelig),
        ("natural_only_edgar_T_hm", nat_edgar_hm, neh_elig, neh_inelig),
        ("natural_only_finqa_T_hm", nat_finqa_hm, nfh_elig, nfh_inelig),
    ]:
        for b in BANDS:
            n_drawn = sum(1 for r in rows if r["band"] == b)
            counts_rows.append({
                "manifest": label,
                "band": b,
                "n_drawn": n_drawn,
                "n_eligible": elig[b],
                "n_ineligible": inelig[b],
                "status": "not_testable" if (label == "edgar_pairs_secondary_T_hm" and b == "near_below") else ("empty" if n_drawn == 0 else "ok"),
            })
    with (OUT_DIR / "counts_per_band.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["manifest", "band", "n_drawn", "n_eligible", "n_ineligible", "status"])
        w.writeheader()
        w.writerows(counts_rows)

    # MANIFEST_REPORT.md
    report_lines = [
        "# Straddle-T Manifest Report (Amendment 12)",
        "",
        f"- **Parameters:** `SEED = {SEED}`, `SMOKE_SEED = {SMOKE_SEED}`, `FINQA_N = {FINQA_N}`, `k = {k_val}`",
        f"- **Thresholds:** `T_edgar = {t_edgar}`, `T_hm = {t_hm}`",
        f"- **Read-only DB check:** `SHOW transaction_read_only` -> `{ro_state}` (`{n_sql_checks}` unique SQL gold checks executed inside `BEGIN READ ONLY` + `ROLLBACK`)",
        f"- **FinQA 4-band eligible count:** `605` (sampled `{FINQA_N}`)",
        "",
        "## SQL used for gold containment checks",
        f"- **EDGAR:** `{edgar_sql}`",
        f"- **FinQA:** `{finqa_sql}`",
        "",
        "## Pool SHA-256 verification (`POOL_CHECKSUMS.txt`)",
    ]
    for fn, digest in sorted(pool_checks.items()):
        report_lines.append(f"- `{fn}`: `{digest}` (MATCH)")
    report_lines += ["", "## Counts per manifest and band", "", "| Manifest | Band | Drawn | Eligible | Ineligible | Status |", "| --- | --- | ---: | ---: | ---: | --- |"]
    for cr in counts_rows:
        report_lines.append(f"| `{cr['manifest']}` | `{cr['band']}` | {cr['n_drawn']} | {cr['n_eligible']} | {cr['n_ineligible']} | {cr['status']} |")
    report_lines.append(f"\n- **Smoke test (`smoke_test_pairs.csv`):** {len(smoke_rows)} pairs (10 EDGAR: 2 `far_below`, 3 `near_below`, 3 `near_above`, 2 `far_above`; 4 FinQA).")
    (OUT_DIR / "MANIFEST_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    # MANIFEST_CHECKSUMS.txt
    ck_lines = []
    for p in sorted(OUT_DIR.iterdir()):
        if p.name == "MANIFEST_CHECKSUMS.txt" or not p.is_file():
            continue
        ck_lines.append(f"{sha256_file(p)}  outputs/straddle_t_manifest_2026-11-15/{p.name}")
    script_path = PROJECT_ROOT / "scripts/straddle_t_build_manifest.py"
    ck_lines.append(f"{sha256_file(script_path)}  scripts/straddle_t_build_manifest.py")
    (OUT_DIR / "MANIFEST_CHECKSUMS.txt").write_text("\n".join(ck_lines) + "\n", encoding="utf-8")
    print(f"Manifest built successfully: {len(ck_lines)} files checksummed.")


if __name__ == "__main__":
    main()
