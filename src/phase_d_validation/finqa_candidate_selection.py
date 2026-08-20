"""Create auditable FinQA Phase 2 candidate shortlists."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src import PROCESSED_DATA_DIR, ensure_dir

YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
QUARTER_RE = re.compile(
    r"\bq[1-4]\b|\b(?:first|second|third) quarter\b|\bfourth quarter\b",
    re.IGNORECASE,
)
AGGREGATION_RE = re.compile(
    r"\b(?:average|total|combined|overall|cumulative|sum|across|"
    r"percentage change|percent change|growth rate|each year|over the)\b",
    re.IGNORECASE,
)
WEIGHTED_AVERAGE_RE = re.compile(r"weighted[\s-]+average", re.IGNORECASE)
OP_RE = re.compile(r"[a-z_]+\(")


def evidence_modality(gold_inds: dict[str, Any]) -> str:
    keys = [str(key).lower() for key in gold_inds]
    has_table = any(key.startswith("table_") for key in keys)
    has_text = any(key.startswith(("pre_text_", "post_text_", "text_")) for key in keys)
    if has_table and has_text:
        return "hybrid"
    if has_table:
        return "table"
    if has_text:
        return "text"
    return "other"


def entity_category_span(question: str) -> int:
    """Conservative support signal, not a definitive entity count."""
    normalized = question.lower()
    conjunctions = len(re.findall(r"\b(?:and|or|versus|vs\.?|compared to)\b", normalized))
    list_markers = len(re.findall(r",", normalized))
    return min(2, conjunctions + (1 if list_markers else 0))


def aggregation_scope(question: str, program: str) -> str:
    question_for_matching = WEIGHTED_AVERAGE_RE.sub("", question)
    if AGGREGATION_RE.search(question_for_matching):
        return "explicit_aggregation"
    if len(OP_RE.findall(program)) >= 3:
        return "multi_step_calculation"
    return "local_or_unsignaled"


def temporal_span(question: str) -> int:
    years = set(YEAR_RE.findall(question))
    quarters = set(match.lower() for match in QUARTER_RE.findall(question))
    return len(years) + len(quarters)


def shortlist_bucket(evidence_units: int) -> str:
    if evidence_units == 1:
        return "narrow_candidate"
    if evidence_units == 2:
        return "boundary_candidate"
    return "broad_candidate"


def rank_key(row: dict[str, Any], seed: int) -> tuple[Any, ...]:
    """Rank candidates within, never across, evidence-unit buckets."""
    tie_breaker = random.Random(f"{seed}:{row['id']}").random()
    if row["candidate_bucket"] == "narrow_candidate":
        return (row["temporal_span"], row["entity_category_span"], row["op_count"], tie_breaker)
    if row["candidate_bucket"] == "boundary_candidate":
        return (-row["temporal_span"], -row["entity_category_span"], -row["op_count"], tie_breaker)

    modality_priority = {"hybrid": 0, "table": 1, "text": 1, "other": 2}[row["evidence_modality"]]
    return (-row["gold_evidence_units"], modality_priority, -row["temporal_span"], -row["op_count"], tie_breaker)


def build_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        qa = entry.get("qa", {})
        gold_inds = qa.get("gold_inds", {})
        if not isinstance(gold_inds, dict) or not gold_inds:
            raise ValueError(f"{entry.get('id', '<missing id>')} has missing/empty qa.gold_inds")

        question = str(qa.get("question", "")).strip()
        program = str(qa.get("program", "")).strip()
        evidence_units = len(gold_inds)
        rows.append(
            {
                "id": entry.get("id", ""),
                "question": question,
                "answer": qa.get("answer", ""),
                "program": program,
                "gold_evidence_units": evidence_units,
                "gold_evidence_keys": " | ".join(gold_inds.keys()),
                "evidence_modality": evidence_modality(gold_inds),
                "temporal_span": temporal_span(question),
                "entity_category_span": entity_category_span(question),
                "aggregation_scope": aggregation_scope(question, program),
                "op_count": len(OP_RE.findall(program)),
                "candidate_bucket": shortlist_bucket(evidence_units),
                "manual_tier": "",
                "manual_rationale": "",
                "manual_evidence_scope": "",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write to {path}")
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_selection_method(path: Path, rows: list[dict[str, Any]], seed: int) -> None:
    counts = Counter(row["candidate_bucket"] for row in rows)
    modalities = Counter(row["evidence_modality"] for row in rows)
    path.write_text(
        "# FinQA Phase 2 candidate-selection method\n\n"
        "Primary signal: `qa.gold_inds` count (dataset-provided gold evidence units).\n\n"
        "Candidate buckets: 1 unit = narrow; 2 units = boundary; 3+ units = broad. "
        "These are candidate buckets only; final labels require documented manual review.\n\n"
        "For broad candidates, table-plus-text (`hybrid`) evidence is surfaced before single-modality "
        "examples after evidence-unit count. Temporal span, entity/category span, aggregation scope, "
        "and program operation count are recorded supporting/balance signals, not tier determinants.\n\n"
        f"Seed: `{seed}`.\n\n"
        f"Candidate counts: {dict(sorted(counts.items()))}.\n\n"
        f"Modality counts: {dict(sorted(modalities.items()))}.\n",
        encoding="utf-8",
    )


def create_candidate_shortlists(
    input_path: Path,
    output_dir: Path = PROCESSED_DATA_DIR,
    seed: int = 42,
    narrow_limit: int = 568,
    boundary_limit: int = 454,
    broad_limit: int = 125,
) -> None:
    with input_path.open(encoding="utf-8") as source:
        entries = json.load(source)

    rows = build_rows(entries)
    if len(rows) != 1147:
        raise ValueError(f"Expected 1,147 FinQA test rows; received {len(rows)}")

    ensure_dir(output_dir)
    write_csv(output_dir / "finqa_phase2_feature_pool.csv", rows)

    limits = {
        "narrow_candidate": narrow_limit,
        "boundary_candidate": boundary_limit,
        "broad_candidate": broad_limit,
    }
    for bucket, limit in limits.items():
        ranked = sorted(
            (row for row in rows if row["candidate_bucket"] == bucket),
            key=lambda row: rank_key(row, seed),
        )
        shortlisted = [{"candidate_rank": rank, **row} for rank, row in enumerate(ranked[:limit], start=1)]
        write_csv(output_dir / f"{bucket}_shortlist.csv", shortlisted)

    write_selection_method(output_dir / "selection_method.md", rows, seed)
    counts = Counter(row["candidate_bucket"] for row in rows)
    modalities = Counter(row["evidence_modality"] for row in rows)
    print(f"Wrote {len(rows)} feature rows to {output_dir}")
    print(f"Candidate buckets: {dict(sorted(counts.items()))}")
    print(f"Evidence modalities: {dict(sorted(modalities.items()))}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="Official FinQA test.json")
    parser.add_argument("--output-dir", type=Path, default=PROCESSED_DATA_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--narrow-limit", type=int, default=568)
    parser.add_argument("--boundary-limit", type=int, default=454)
    parser.add_argument("--broad-limit", type=int, default=125)
    args = parser.parse_args()

    create_candidate_shortlists(
        input_path=args.input,
        output_dir=args.output_dir,
        seed=args.seed,
        narrow_limit=args.narrow_limit,
        boundary_limit=args.boundary_limit,
        broad_limit=args.broad_limit,
    )

if __name__ == "__main__":
    main()
