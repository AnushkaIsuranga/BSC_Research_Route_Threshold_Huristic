# LEGACY — not used in final results. Sept-era statistics on outputs/phase_d_results*.csv (normal-approximation CIs of means); superseded by paired_stats.py.
import csv
import math
import sys
import statistics
from pathlib import Path
from typing import List, Dict

from math import sqrt
import scipy.stats

def calculate_95_ci(data):
    if len(data) < 2:
        return (0.0, 0.0)
    mean = statistics.mean(data)
    sem = statistics.stdev(data) / sqrt(len(data))
    # 95% CI using t-distribution
    margin = sem * scipy.stats.t.ppf((1 + 0.95) / 2., len(data)-1)
    return (mean - margin, mean + margin)

def mean(data):
    return statistics.mean(data) if data else 0.0

def run_stats(file_path: str):
    res_file = Path(file_path)
    if not res_file.exists():
        print(f"File {res_file} not found.")
        return
        
    naive_latencies = []
    dm_latencies = []
    latency_reductions = []
    
    naive_errors = []
    dm_errors = []
    error_reductions = []
    
    error_count = 0
    total_count = 0
    
    with res_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_count += 1
            if row.get('naive_route') == 'error' or row.get('dm_route') == 'error':
                error_count += 1
                continue
                
            nl = float(row['naive_latency_ms'])
            dml = float(row['dm_latency_ms'])
            naive_latencies.append(nl)
            dm_latencies.append(dml)
            latency_reductions.append(nl - dml)
            
            ne = float(row['naive_error'])
            de = float(row['dm_error'])
            naive_errors.append(ne)
            dm_errors.append(de)
            error_reductions.append(ne - de)
            
    mean_nl = mean(naive_latencies)
    mean_dml = mean(dm_latencies)
    mean_reduction = mean(latency_reductions)
    ci_lower, ci_upper = calculate_95_ci(latency_reductions)
    
    mean_ne = mean(naive_errors) * 100
    mean_de = mean(dm_errors) * 100
    mean_err_reduction = mean(error_reductions) * 100
    err_ci_lower, err_ci_upper = calculate_95_ci([e * 100 for e in error_reductions])
    
    # Statistical significance testing for paired binary errors (McNemar)
    b = sum(1 for n, d in zip(naive_errors, dm_errors) if n == 1 and d == 0)
    c = sum(1 for n, d in zip(naive_errors, dm_errors) if n == 0 and d == 1)
    
    if b + c > 0:
        mcnemar_stat = (abs(b - c) - 1)**2 / (b + c)
        mcnemar_p = scipy.stats.chi2.sf(mcnemar_stat, 1)
    else:
        mcnemar_p = 1.0

    # Wilcoxon signed-rank test for continuous latency data
    try:
        wilcoxon_res = scipy.stats.wilcoxon(naive_latencies, dm_latencies, zero_method="zsplit")
        wilcoxon_p = wilcoxon_res.pvalue
    except ValueError:
        wilcoxon_p = 1.0
    
    summary = (
        f"=== Phase D Statistical Summary ({res_file.name}) ===\n"
        f"Queries evaluated: {len(naive_latencies)} (Errors filtered out: {error_count}/{total_count})\n\n"
        f"Naive Router Mean Latency:           {mean_nl:.2f} ms\n"
        f"Decision Matrix Mean Latency:        {mean_dml:.2f} ms\n"
        f"Mean Latency Reduction:              {mean_reduction:.2f} ms\n"
        f"95% CI for Latency Reduction:        [{ci_lower:.2f} ms, {ci_upper:.2f} ms]\n"
        f"Wilcoxon Signed-Rank p-value:        {wilcoxon_p:.4f}\n\n"
        f"Naive Router Error Rate:             {mean_ne:.1f}%\n"
        f"Decision Matrix Error Rate:          {mean_de:.1f}%\n"
        f"Mean Error Rate Reduction:           {mean_err_reduction:.1f}%\n"
        f"95% CI for Error Rate Reduction:     [{err_ci_lower:.1f}%, {err_ci_upper:.1f}%]\n"
        f"McNemar's Test p-value:              {mcnemar_p:.4f}\n"
        "====================================\n"
    )
    
    print(summary)
    
    out_file = res_file.with_name(f"summary_{res_file.name}.txt")
    with open(out_file, "w") as f:
        f.write(summary)
    print(f"Saved to {out_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        for file in sys.argv[1:]:
            run_stats(file)
    else:
        run_stats("outputs/phase_d_results.csv")
