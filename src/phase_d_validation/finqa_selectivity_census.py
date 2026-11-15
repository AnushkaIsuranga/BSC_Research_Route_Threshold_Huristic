"""Read-only census and pre-registered supplementary-sample selection."""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
from src.phase_d_validation.local_ollama_runner import estimate_selectivity
from src.utils.finqa_utils import extract_ticker_year

SEED = 20260930
BANDS = (
    ("B1", 0.0, 0.02),
    ("B2", 0.02, 0.10),
    ("B3", 0.10, 0.329),
    ("B4", 0.329, 1.0 + 1e-12),
)


def band_for(value: float) -> str:
    for name, low, high in BANDS:
        if low <= value < high:
            return name
    raise ValueError(f"Selectivity outside configured bands: {value}")


def breadth(row: dict) -> str:
    count = len([key for key in row.get("gold_evidence_keys", "").split("|") if key.strip()])
    return "single" if count == 1 else "dual" if count == 2 else "multi"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="outputs/finqa_selectivity_census")
    parser.add_argument("--subset", default=None)
    args = parser.parse_args()
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    dataset = json.loads((PROJECT_ROOT / "data/raw/finqa_test.json").read_text(encoding="utf-8"))
    primary_path = Path(args.subset) if args.subset else get_frozen_filepath()
    primary = {row["id"] for row in load_finqa_subset(primary_path)}
    conn = psycopg2.connect(**db_settings()); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM finqa_evidence")
        corpus_size = cur.fetchone()[0]
    census = []
    for example in dataset:
        qid = example["id"]; ticker, year = extract_ticker_year(qid)
        selectivity = estimate_selectivity(conn, ticker, year, corpus_size)
        gold_keys = example.get("qa", {}).get("gold_inds", {})
        evidence_count = len(gold_keys)
        row = {"id": qid, "ticker": ticker, "year": year, "selectivity": selectivity, "matching_rows": round(selectivity * corpus_size), "corpus_size": corpus_size, "gold_evidence_count": evidence_count, "breadth": "single" if evidence_count == 1 else "dual" if evidence_count == 2 else "multi", "primary_50": qid in primary}
        row["band"] = band_for(selectivity); census.append(row)
    conn.close()

    census_path = out_dir / "all_1147_selectivity.csv"
    with census_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(census[0])); writer.writeheader(); writer.writerows(census)
    eligible = [row for row in census if not row["primary_50"]]
    rng = random.Random(SEED); selected = []
    for band, _, _ in BANDS:
        pool = [row for row in eligible if row["band"] == band]
        rng.shuffle(pool)
        chosen = pool[:10]
        selected.extend(chosen)
    selected_path = out_dir / "supplementary_selection.csv"
    with selected_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(census[0])); writer.writeheader(); writer.writerows(selected)
    summary = {"protocol_commit": "037eb184d09d6b3ad0160d94b7138576b38bfab4", "seed": SEED, "corpus_size": corpus_size, "query_count": len(census), "selectivity_min": min(row["selectivity"] for row in census), "selectivity_max": max(row["selectivity"] for row in census), "bands": {band: {"total": sum(row["band"] == band for row in census), "eligible": sum(row["band"] == band and not row["primary_50"] for row in census), "selected": sum(row["band"] == band for row in selected), "shortage_from_quota": max(0, 10 - sum(row["band"] == band and not row["primary_50"] for row in census))} for band, _, _ in BANDS}, "selected_count": len(selected), "primary_overlap": sum(row["primary_50"] for row in selected)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
