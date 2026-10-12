# LEGACY — not used in final results. aggregates Sept-era phase_d_results_*.csv files; superseded by paired_stats.py.
import csv
import json
from pathlib import Path
from src.phase_d_validation.stats_calculator import mean

def run_aggregator():
    results_dir = Path("outputs")
    csv_files = list(results_dir.glob("phase_d_results_*.csv"))
    
    if not csv_files:
        print("No result CSVs found. Run comparison_runner.py with multiple models first.")
        return
        
    manifest_path = results_dir / "phase_d_manifest.json"
    manifest = {}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
    print("=== Multi-Model Performance Summary ===")
    print(f"| {'Model':<35} | {'Naive Error Rate':<17} | {'DM Error Rate':<13} | {'Gap (Improvement)':<17} | {'McNemar p':<11} |")
    print(f"|{'-'*37}|{'-'*19}|{'-'*15}|{'-'*19}|{'-'*13}|")
    
    for file_path in csv_files:
        # Extract model safe name from filename
        safe_name = file_path.stem.replace("phase_d_results_", "")
        
        # Look up true model name from manifest, fallback to heuristic
        display_name = manifest.get(safe_name, safe_name.replace("_", "/"))
        
        naive_errors = []
        dm_errors = []
        
        with file_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('naive_route') == 'error' or row.get('dm_route') == 'error':
                    continue
                naive_errors.append(float(row['naive_error']))
                dm_errors.append(float(row['dm_error']))
                
        if not naive_errors:
            print(f"| {display_name:<35} | {'No valid data':<17} | {'-':<13} | {'-':<17} | {'-':<11} |")
            continue
            
        mean_ne = mean(naive_errors) * 100
        mean_de = mean(dm_errors) * 100
        gap = mean_ne - mean_de
        
        # Calculate McNemar's p-value for the table
        import scipy.stats
        b = sum(1 for n, d in zip(naive_errors, dm_errors) if n == 1 and d == 0)
        c = sum(1 for n, d in zip(naive_errors, dm_errors) if n == 0 and d == 1)
        if b + c > 0:
            mcnemar_stat = (abs(b - c) - 1)**2 / (b + c)
            mcnemar_p = scipy.stats.chi2.sf(mcnemar_stat, 1)
            p_val = f"{mcnemar_p:.4f}"
        else:
            p_val = "1.0000"
        
        print(f"| {display_name:<35} | {mean_ne:>16.1f}% | {mean_de:>12.1f}% | {gap:>16.1f}% | {p_val:>11} |")
        
    print("=========================================================================================================")

if __name__ == "__main__":
    run_aggregator()
