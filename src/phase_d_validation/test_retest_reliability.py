"""
Test-retest reliability check for the FinQA Phase 2 manual tiering, split
into two non-overlapping rounds of 25 (full coverage of all 50 selected
questions, each tested exactly once - no repeat-exposure contamination).

Protocol (locked before running either round - do not deviate):
  1. Wait ~3 days after your original tiering pass.
  2. Fill in test_retest_round1_BLIND.csv (25 items) blind - no peeking
     at test_retest_round1_ANSWER_KEY.csv.
  3. Run: python3 test_retest_reliability.py round1
  4. Wait ~3 more days.
  5. Fill in test_retest_round2_BLIND.csv (the OTHER 25 items) blind.
  6. Run: python3 test_retest_reliability.py round2
  7. Run: python3 test_retest_reliability.py ci
     -> pools both rounds into one n=50 agreement rate with a 95% CI.

Both rounds must be run and reported together - this protocol was fixed
in advance specifically to avoid selectively reporting whichever round
looks better.
"""
import csv
import math
import sys
from pathlib import Path

# Add project root to path so we can import from src
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src import PHASE2_OUTPUT_DIR


def _check_round(round_num: int) -> tuple[int, int, list]:
    """Shared logic for checking a single round. Returns (matches, total, mismatches)."""
    blind_path = PHASE2_OUTPUT_DIR / f"test_retest_round{round_num}_BLIND.csv"
    key_path = PHASE2_OUTPUT_DIR / f"test_retest_round{round_num}_ANSWER_KEY.csv"

    blind = list(csv.DictReader(open(blind_path)))
    key = {r["id"]: r for r in csv.DictReader(open(key_path))}

    matches = 0
    mismatches = []

    for row in blind:
        qid = row["id"]
        new_tier = row["your_retier (narrow/boundary/broad)"].strip().lower()
        old_tier = key[qid]["original_tier"].strip().lower()

        if new_tier not in ("narrow", "boundary", "broad"):
            print(f"WARNING: {qid} has no valid re-tier filled in yet ('{new_tier}'). "
                  f"Fill in {blind_path} before running this.")
            sys.exit(1)

        if new_tier == old_tier:
            matches += 1
        else:
            mismatches.append((qid, old_tier, new_tier))

    return matches, len(blind), mismatches


def check_round1():
    """Check round 1 (25 items) in isolation."""
    matches, total, mismatches = _check_round(1)
    print(f"Round 1 agreement: {matches}/{total} ({matches/total*100:.1f}%)")
    if mismatches:
        print(f"{len(mismatches)} disagreement(s):")
        for qid, old, new in mismatches:
            print(f"  [{qid}] original: {old}  ->  retier: {new}")
    print("\nDo not change the frozen file based on this. Proceed to round 2")
    print("after another ~3 day gap, then run the pooled 'ci' check.")


def check_round2():
    """Check round 2 (the other 25 items) in isolation."""
    matches, total, mismatches = _check_round(2)
    print(f"Round 2 agreement: {matches}/{total} ({matches/total*100:.1f}%)")
    if mismatches:
        print(f"{len(mismatches)} disagreement(s):")
        for qid, old, new in mismatches:
            print(f"  [{qid}] original: {old}  ->  retier: {new}")
    print("\nBoth rounds done - run 'ci' next to get the pooled n=50 result.")


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval - more reliable than a normal approximation at small n."""
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2)))) / denom
    return center - margin, center + margin


def compute_ci():
    """Pool both rounds into one n=50 agreement rate with a 95% Wilson CI.
    This is the number to report in your methodology section - not either
    round in isolation."""
    m1, t1, mm1 = _check_round(1)
    m2, t2, mm2 = _check_round(2)

    total_matches = m1 + m2
    total_n = t1 + t2
    lo, hi = wilson_ci(total_matches, total_n)

    print(f"Round 1: {m1}/{t1}")
    print(f"Round 2: {m2}/{t2}")
    print(f"\nPooled test-retest agreement: {total_matches}/{total_n} "
          f"({total_matches/total_n*100:.1f}%)")
    print(f"95% Wilson CI: [{lo:.3f}, {hi:.3f}]")

    all_mismatches = mm1 + mm2
    if all_mismatches:
        print(f"\n{len(all_mismatches)} total disagreement(s) across both rounds - "
              f"list these in your methodology write-up as documented instances,")
        print("not as rows to go back and fix:")
        for qid, old, new in all_mismatches:
            print(f"  [{qid}] original: {old}  ->  retier: {new}")

    print("\nReport this pooled number (not either round alone) in your methodology.")
    print("The frozen 50-question file itself is not to be modified based on this check.")


if __name__ == "__main__":
    commands = {"round1": check_round1, "round2": check_round2, "ci": compute_ci}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(f"Usage: python3 {sys.argv[0]} [round1|round2|ci]")
        sys.exit(1)
    commands[sys.argv[1]]()