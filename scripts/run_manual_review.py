"""FinQA Phase 2 Manual Review CLI - fixed version.

Fixes applied vs. the original script:
  1. ROOT CAUSE FIX: quota is tracked by the tier you actually assign a
     row to, not by which shortlist file you happen to be looping over.
     Overriding a boundary_candidate to "broad" now correctly counts
     against the broad quota, not the boundary one.
  2. Tier input is validated against {narrow, boundary, broad} and
     normalized to lowercase - no more "Broad" vs "broad", no more a
     stray description silently accepted as a tier value.
  3. Rationale and evidence scope are required - blank input re-prompts
     instead of saving an incomplete row.
  4. Duplicate/near-duplicate question detection - warns before you
     accept a row whose question text already exists in your selection.
  5. Live running tally shown after every decision.
  6. Autosave/checkpoint after every accepted row - a crash, Ctrl+C, or
     'q' mid-session no longer loses prior work, and reruns resume where
     you left off (already-decided IDs are skipped automatically).
  7. Explicit end-of-session summary that tells you exactly what's still
     short, instead of silently saving an incomplete file.
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime

OUTPUT_DIR = "outputs/phase2_selection_output"
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "_review_checkpoint.csv")

SHORTLIST_FILES = {
    "narrow": os.path.join(OUTPUT_DIR, "narrow_candidate_shortlist.csv"),
    "boundary": os.path.join(OUTPUT_DIR, "boundary_candidate_shortlist.csv"),
    "broad": os.path.join(OUTPUT_DIR, "broad_candidate_shortlist.csv"),
}

QUOTAS = {"narrow": 15, "boundary": 20, "broad": 15}
VALID_TIERS = set(QUOTAS)

CHECKPOINT_FIELDS = [
    "candidate_rank", "id", "question", "answer", "program",
    "gold_evidence_units", "gold_evidence_keys", "evidence_modality",
    "temporal_span", "entity_category_span", "aggregation_scope",
    "op_count", "candidate_bucket", "manual_tier", "manual_rationale",
    "manual_evidence_scope",
]


def load_checkpoint() -> tuple[list[dict], set[str], dict[str, int]]:
    """Resume from a prior session if a checkpoint exists."""
    rows: list[dict] = []
    decided_ids: set[str] = set()
    tier_counts = {t: 0 for t in QUOTAS}

    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append(row)
                decided_ids.add(row["id"])
                tier_counts[row["manual_tier"]] += 1
        print(f"Resuming from checkpoint: {len(rows)} rows already decided.")
        print(f"  Current tallies: {tier_counts}\n")

    return rows, decided_ids, tier_counts


def save_checkpoint(rows: list[dict]) -> None:
    with open(CHECKPOINT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CHECKPOINT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def normalize_question(q: str) -> str:
    return " ".join(q.strip().lower().split())


def prompt_tier(default_tier: str, tier_counts: dict) -> str | None:
    """Returns a validated tier with room in its quota, or None if the
    reviewer wants to skip this candidate entirely."""
    while True:
        raw = input(f"Manual Tier (default: {default_tier}) ['s'=skip]: ").strip().lower()
        if raw == "s":
            return None
        tier = raw if raw else default_tier

        if tier not in VALID_TIERS:
            print(f"  '{tier}' is not a valid tier. Choose one of: {sorted(VALID_TIERS)}")
            continue

        if tier_counts[tier] >= QUOTAS[tier]:
            print(f"  '{tier}' is already full ({tier_counts[tier]}/{QUOTAS[tier]}). "
                  f"Pick a different tier or 's' to skip this candidate.")
            continue

        return tier


def prompt_required(label: str) -> str:
    while True:
        val = input(f"{label}: ").strip()
        if val:
            return val
        print(f"  {label} cannot be blank - this field is required.")


def run_review() -> None:
    all_rows, decided_ids, tier_counts = load_checkpoint()

    print("=== FinQA Phase 2 Manual Review CLI (fixed) ===")
    print("'s' to skip a candidate, 'q' to quit and save progress.\n")

    for default_tier, filepath in SHORTLIST_FILES.items():
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            continue

        with open(filepath, newline="", encoding="utf-8") as f:
            candidates = list(csv.DictReader(f))

        print(f"\n--- {default_tier.upper()} shortlist ({len(candidates)} candidates available) ---")

        for row in candidates:
            if sum(tier_counts.values()) >= sum(QUOTAS.values()):
                print("\nAll 50 slots filled. Done.")
                save_checkpoint(all_rows)
                finalize(all_rows, tier_counts)
                return

            # Stop offering candidates from THIS shortlist once its own
            # tier's quota is met (mirrors the original script's intent),
            # but - unlike the original - this now checks the ACTUAL
            # count of rows tagged with this tier, not just how many
            # decisions were made in this loop. An override to a
            # different tier no longer silently counts against this one.
            if tier_counts[default_tier] >= QUOTAS[default_tier]:
                print(f"  '{default_tier}' quota already met ({tier_counts[default_tier]}/{QUOTAS[default_tier]}) "
                      f"- moving to next shortlist.")
                break

            if row["id"] in decided_ids:
                continue

            print(f"\n[{default_tier.upper()}] Rank {row['candidate_rank']} | ID: {row['id']}")
            print(f"Modality: {row['evidence_modality']} | Op Count: {row['op_count']} | "
                  f"Evidence units: {row['gold_evidence_units']}")
            print(f"Question: {row['question']}")
            print(f"Program:  {row['program']}")
            print(f"Evidence: {row['gold_evidence_keys']}")
            print(f"Running tally: {tier_counts}  (target: {QUOTAS})")
            print("-" * 40)

            action = input("Press Enter to review, 's' skip, 'q' quit: ").strip().lower()
            if action == "q":
                save_checkpoint(all_rows)
                finalize(all_rows, tier_counts, quit_early=True)
                return
            if action == "s":
                continue

            tier = prompt_tier(default_tier, tier_counts)
            if tier is None:
                continue

            norm_q = normalize_question(row["question"])
            existing = [r for r in all_rows if normalize_question(r["question"]) == norm_q]
            if existing:
                print(f"  WARNING: {len(existing)} already-selected row(s) have this exact question:")
                for e in existing:
                    print(f"    - {e['id']} (tier={e['manual_tier']})")
                confirm = input("  Accept anyway? (y/N): ").strip().lower()
                if confirm != "y":
                    print("  Skipped due to duplicate.")
                    continue

            scope = prompt_required("Manual Evidence Scope (e.g. 'single table cell')")
            rationale = prompt_required("Manual Rationale (e.g. 'Requires integrating two years')")

            row["manual_tier"] = tier
            row["manual_evidence_scope"] = scope
            row["manual_rationale"] = rationale

            all_rows.append(row)
            decided_ids.add(row["id"])
            tier_counts[tier] += 1
            save_checkpoint(all_rows)  # autosave after every single accepted row

            print(f"  Saved as '{tier}'. Tally now: {tier_counts}")

    finalize(all_rows, tier_counts)


def finalize(rows: list[dict], tier_counts: dict, quit_early: bool = False) -> None:
    print("\n" + "=" * 50)
    if quit_early:
        print("Session ended early ('q'). Progress has been checkpointed.")
    print(f"Total rows decided: {len(rows)} / {sum(QUOTAS.values())}")
    for tier, quota in QUOTAS.items():
        status = "OK" if tier_counts[tier] == quota else "SHORT" if tier_counts[tier] < quota else "OVER"
        print(f"  {tier}: {tier_counts[tier]} / {quota}  [{status}]")

    if all(tier_counts[t] == QUOTAS[t] for t in QUOTAS):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = os.path.join(OUTPUT_DIR, f"finqa_phase2_selected_50_{timestamp}.csv")
        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CHECKPOINT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nAll quotas met. Final selection saved to: {out_file}")
        print("This is your freeze point - copy it elsewhere and do not edit it further")
        print("except to correct transcription errors (see your freeze-rule protocol).")
    else:
        print("\nQuotas not yet met - re-run this script to continue.")
        print(f"(Resuming reads from: {CHECKPOINT_FILE})")


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        run_review()
    except KeyboardInterrupt:
        print("\n\nInterrupted - progress up to the last accepted row has been saved.")
        print(f"Re-run this script to resume from: {CHECKPOINT_FILE}")
        sys.exit(0)