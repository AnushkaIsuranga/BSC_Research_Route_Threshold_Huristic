"""Read-only report of H&M single-attribute frequencies in the 20–33% gap."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg2

from src import db_settings


COLUMNS = ("index_group_name", "product_type_name", "garment_group_name", "perceived_colour_master_name", "graphical_appearance_name")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--table", default="hm_clothes_100"); parser.add_argument("--out", default="outputs/phase_a_gap_frequency_report.json"); args = parser.parse_args()
    conn = psycopg2.connect(**db_settings()); report = {"table": args.table, "range": [0.20, 0.33], "columns": {}}
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {args.table}"); total = cur.fetchone()[0]; report["row_count"] = total
        for column in COLUMNS:
            cur.execute(f"SELECT {column}, COUNT(*)::int AS n FROM {args.table} WHERE {column} IS NOT NULL GROUP BY {column} ORDER BY n DESC")
            values = [{"value": value, "count": n, "frequency": n / total} for value, n in cur.fetchall()]
            report["columns"][column] = [row for row in values if 0.20 <= row["frequency"] <= 0.33]
    conn.close(); Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8"); print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
