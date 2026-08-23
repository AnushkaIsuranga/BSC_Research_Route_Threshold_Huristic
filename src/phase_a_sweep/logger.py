import json
import os
import uuid
from datetime import datetime, timezone

class SweepLogger:
    def __init__(self, output_dir="outputs"):
        self.output_dir = output_dir
        self.filters_file = os.path.join(output_dir, "filters_reference.json")
        self.baselines_file = os.path.join(output_dir, "baselines_reference.json")
        self.results_file = os.path.join(output_dir, "sweep_results.jsonl")
        
        os.makedirs(self.output_dir, exist_ok=True)

    def freeze_filters(self, filters_list):
        """
        Takes the raw list of filters, assigns a stable 'filter_id' to each,
        and saves them to filters_reference.json.
        Returns the frozen list with IDs.
        """
        if os.path.exists(self.filters_file):
            with open(self.filters_file, "r") as f:
                frozen = json.load(f)
            if len(frozen) != len(filters_list):
                raise ValueError(
                    f"filters_reference.json has {len(frozen)} filters but the "
                    f"provided filters_list has {len(filters_list)} — filters.json "
                    f"may have been regenerated. Delete filters_reference.json and "
                    f"sweep_results.jsonl together if this is intentional, since old "
                    f"results no longer match the new filter_ids."
                )
            return frozen
                
        frozen = []
        for i, filt in enumerate(filters_list):
            frozen_filt = filt.copy()
            frozen_filt["filter_id"] = f"f_{i:03d}"
            frozen.append(frozen_filt)
            
        with open(self.filters_file, "w") as f:
            json.dump(frozen, f, indent=2)
            
        return frozen

    def log_baseline(self, table, query_vector_idx, baseline_ms):
        """
        Logs a baseline to baselines_reference.json. 
        Updates the file atomically.
        """
        baselines = {}
        if os.path.exists(self.baselines_file):
            with open(self.baselines_file, "r") as f:
                baselines = json.load(f)
                
        key = f"{table}_v{query_vector_idx}"
        baselines[key] = {
            "table_name": table,
            "query_vector_idx": query_vector_idx,
            "baseline_ms": baseline_ms
        }
        
        # Write to a temporary file and rename for atomic update
        tmp_file = self.baselines_file + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(baselines, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, self.baselines_file)

    def get_completed_combinations(self):
        """
        Reads sweep_results.jsonl and returns a set of (filter_id, table_name, query_vector_idx)
        that have already been logged, so the orchestrator can skip them on resume.
        """
        completed = set()
        if not os.path.exists(self.results_file):
            return completed
            
        with open(self.results_file, "r") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    completed.add((data["filter_id"], data["table_name"], data["query_vector_idx"]))
                except json.JSONDecodeError:
                    continue
        return completed

    def log_result(self, filter_id, table, query_vector_idx, success, scan_strategy=None, 
                   latency_ms=None, filter_time_ms=None, rows_removed=None, recall=None, error_msg=None,
                   index_used=None, k=None, hnsw_ef_search=None, planning_time_ms=None, recall_error=None):
        """
        Appends a single result to sweep_results.jsonl incrementally and fsyncs to disk.
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "filter_id": filter_id,
            "table_name": table,
            "query_vector_idx": query_vector_idx,
            "k": k,
            "hnsw_ef_search": hnsw_ef_search,
            "success": success,
            "scan_strategy": scan_strategy if success else None,
            "index_used": index_used if success else None,
            "planning_time_ms": planning_time_ms if success else None,
            "latency_ms": latency_ms if success else None,
            "filter_time_ms": filter_time_ms if success else None,
            "rows_removed": rows_removed if success else None,
            "recall": recall if success else None,
            "error_msg": error_msg,
            "recall_error": recall_error
        }
        
        with open(self.results_file, "a") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
            os.fsync(f.fileno())
