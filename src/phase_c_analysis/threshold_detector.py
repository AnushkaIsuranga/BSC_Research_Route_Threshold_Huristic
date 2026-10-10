import json
import os
import argparse
import statistics
from collections import defaultdict

def get_all_danger_zones(metrics, condition_fn):
    """Finds all contiguous danger zones across sorted selectivity metrics."""
    zones = []
    start = None
    end = None
    in_zone = False
    
    for sel, rec, lat in metrics:
        if condition_fn(rec, lat):
            if not in_zone:
                start = sel
                in_zone = True
            end = sel
        else:
            if in_zone:
                zones.append((start, end))
                in_zone = False
    if in_zone:
        zones.append((start, end))
        
    return zones

def extract_thresholds(sweep_file: str, filters_file: str, recall_stat: str = "mean"):
    if not os.path.exists(sweep_file) or not os.path.exists(filters_file):
        print(f"Missing sweep or filter data: {sweep_file} or {filters_file}")
        return {}

    with open(filters_file) as f:
        filters = json.load(f)
    
    # Map f_000, f_001 etc to their actual selectivities
    filter_sel = {f'f_{i:03d}': f['actual'] for i, f in enumerate(filters)}
    
    data = defaultdict(lambda: defaultdict(list))
    with open(sweep_file) as f:
        for line in f:
            if not line.strip(): continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Link filter_id back to selectivity
            fid = d['filter_id']
            if fid in filter_sel:
                data[d['table_name']][filter_sel[fid]].append(d)
            
    thresholds = {}
    for table_name in data.keys():
        metrics = []
        for sel in sorted(data[table_name].keys()):
            runs = data[table_name][sel]
            recalls = [r['recall'] for r in runs if r.get('recall') is not None]
            if not recalls:
                continue
            if recall_stat == "mean":
                selected_recall = statistics.mean(recalls)
            elif recall_stat == "min":
                selected_recall = min(recalls)
            elif recall_stat == "median":
                selected_recall = statistics.median(recalls)
            else:
                raise ValueError(f"Unsupported recall statistic: {recall_stat}")
            # We use median latency to filter out single-run spikes
            med_lat = sorted([r['latency_ms'] for r in runs])[len(runs)//2]
            metrics.append((sel, selected_recall, med_lat))
            
        recall_zones = get_all_danger_zones(metrics, lambda rec, lat: rec < 0.9)
        latency_zones = get_all_danger_zones(metrics, lambda rec, lat: lat > 500)
                
        # Derive margin from the observed overall danger-zone span per table.
        all_zones = recall_zones + latency_zones
        if all_zones:
            overall_start = min(z[0] for z in all_zones)
            overall_end = max(z[1] for z in all_zones)
            span_width = overall_end - overall_start
            # Use 10% of the overall danger zone span as the margin, minimum 0.005
            margin = max(0.005, span_width * 0.1)
        else:
            # Fallback for tables with no danger zone
            margin = 0.005
            
        thresholds[table_name] = {
            'recall_danger_zones': recall_zones,
            'latency_danger_zones': latency_zones,
            'margin': margin
        }
        
    return thresholds

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract routing thresholds from sweep data.")
    parser.add_argument("--sweep", default="outputs/sweep_results.jsonl", help="Path to sweep_results.jsonl")
    parser.add_argument("--filters", default="outputs/filters.json", help="Path to filters.json")
    parser.add_argument("--out", default="outputs/thresholds.json", help="Path to save thresholds.json")
    parser.add_argument("--recall-stat", choices=["mean", "min", "median"], default="mean")
    args = parser.parse_args()
    
    t = extract_thresholds(args.sweep, args.filters, recall_stat=args.recall_stat)
    print("Detected Thresholds:")
    print(json.dumps(t, indent=2))
    
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(t, f, indent=2)
    print(f"Saved to {args.out}")
