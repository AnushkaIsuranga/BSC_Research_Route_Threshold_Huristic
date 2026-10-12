import csv
from pathlib import Path
from typing import List, Dict, Any

def load_finqa_subset(filepath: Path) -> List[Dict[str, Any]]:
    """Loads the frozen FinQA 50-query subset."""
    if not filepath.exists():
        raise FileNotFoundError(f"Cannot find FinQA selection file at {filepath}")
    
    with filepath.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def get_frozen_filepath() -> Path:
    base_dir = Path("outputs/phase2_selection_output")
    files = list(base_dir.glob("finqa_phase2_selected_50_*.csv"))
    if not files:
        raise FileNotFoundError("No selected_50 CSV found in outputs/phase2_selection_output.")
    # Sort by name to get the latest if there are multiple
    return sorted(files)[-1]

if __name__ == "__main__":
    fp = get_frozen_filepath()
    queries = load_finqa_subset(fp)
    print(f"Loaded {len(queries)} queries from {fp}.")
    print(f"First query ID: {queries[0]['id']}")
