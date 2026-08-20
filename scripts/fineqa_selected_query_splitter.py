import csv
import random

random.seed(23)  # fixed, reproducible split - record this seed in your methodology

rows = list(csv.DictReader(open("./outputs/phase2_selection_output/finqa_phase2_selected_50_20260819_140501.csv")))
assert len(rows) == 50

shuffled = rows[:]
random.shuffle(shuffled)
half1 = shuffled[:25]
half2 = shuffled[25:]

def write_round(rows, round_num):
    blind_path = f"test_retest_round{round_num}_BLIND.csv"
    key_path = f"test_retest_round{round_num}_ANSWER_KEY.csv"
    
    with open(blind_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "question", "program", "gold_evidence_keys", "your_retier (narrow/boundary/broad)"])
        for r in rows:
            writer.writerow([r["id"], r["question"], r["program"], r["gold_evidence_keys"], ""])
            
    with open(key_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "question", "original_tier", "original_rationale"])
        for r in rows:
            writer.writerow([r["id"], r["question"], r["manual_tier"], r["manual_rationale"]])
            
    print(f"Round {round_num}: {len(rows)} items -> {blind_path}, {key_path}")

write_round(half1, 1)
write_round(half2, 2)

# sanity check: no overlap, full coverage
ids1 = {r["id"] for r in half1}
ids2 = {r["id"] for r in half2}

assert ids1.isdisjoint(ids2), "Overlap detected!"
assert ids1 | ids2 == {r["id"] for r in rows}, "Coverage incomplete!"

print("\nVerified: 0 overlap between rounds, full 50-question coverage across both.")