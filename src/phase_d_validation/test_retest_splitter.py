"""Create blind and answer-key splits for FinQA test-retest review."""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from src import PHASE2_OUTPUT_DIR, ensure_dir


def split_selected_queries(input_path: Path, output_dir: Path = PHASE2_OUTPUT_DIR, seed: int = 23) -> None:
    with input_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))

    if len(rows) != 50:
        raise ValueError(f"Expected 50 selected rows; received {len(rows)}")

    shuffled = rows[:]
    random.Random(seed).shuffle(shuffled)
    rounds = {1: shuffled[:25], 2: shuffled[25:]}
    ensure_dir(output_dir)

    for round_num, round_rows in rounds.items():
        blind_path = output_dir / f"test_retest_round{round_num}_BLIND.csv"
        key_path = output_dir / f"test_retest_round{round_num}_ANSWER_KEY.csv"

        with blind_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(["id", "question", "program", "gold_evidence_keys", "your_retier (narrow/boundary/broad)"])
            for row in round_rows:
                writer.writerow([row["id"], row["question"], row["program"], row["gold_evidence_keys"], ""])

        with key_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(["id", "question", "original_tier", "original_rationale"])
            for row in round_rows:
                writer.writerow([row["id"], row["question"], row["manual_tier"], row["manual_rationale"]])

        print(f"Round {round_num}: {len(round_rows)} items -> {blind_path}, {key_path}")

    ids1 = {row["id"] for row in rounds[1]}
    ids2 = {row["id"] for row in rounds[2]}
    assert ids1.isdisjoint(ids2), "Overlap detected."
    assert ids1 | ids2 == {row["id"] for row in rows}, "Coverage incomplete."
    print("Verified: 0 overlap between rounds, full 50-question coverage across both.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Frozen finqa_phase2_selected_50 CSV")
    parser.add_argument("--output-dir", type=Path, default=PHASE2_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=23)
    args = parser.parse_args()

    split_selected_queries(args.input, args.output_dir, args.seed)

if __name__ == "__main__":
    main()
