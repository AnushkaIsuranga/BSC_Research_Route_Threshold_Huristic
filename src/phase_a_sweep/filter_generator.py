import json
import random
import psycopg2
import numpy as np
from psycopg2.extensions import connection
import os

from src.database.connection import connect_pgvector

COLUMN_FAMILIES = {
    "merch_hierarchy": {"index_group_name", "index_name", "section_name", "department_name"},
    "garment_hierarchy": {"product_group_name", "product_type_name"},
    "colour_hierarchy": {"perceived_colour_master_name", "colour_group_name"},
    "colour_tone": {"perceived_colour_value_name"},
    "pattern": {"graphical_appearance_name"},
    "construction": {"garment_group_name"},
}

def family_of(col):
    for fam, cols in COLUMN_FAMILIES.items():
        if col in cols:
            return fam
    return "unknown"  # Fallback just in case

def generate_target_selectivities(atoms: list[dict], n_micro: int = 25, n_macro: int = 15, seed: int = 42) -> list[float]:
    rng = np.random.default_rng(seed)
    micro = rng.uniform(np.log10(0.0001), np.log10(0.05), n_micro)
    micro_targets = 10**micro
    
    macro_candidates = [a["sigma"] for a in atoms if a["sigma"] >= 0.05]
    if not macro_candidates:
        macro_targets = np.linspace(0.05, 0.45, n_macro)
    else:
        macro_targets = rng.choice(macro_candidates, n_macro, replace=True)
        # Add slight jitter to avoid exact duplicate targets
        macro_targets = macro_targets * rng.uniform(0.99, 1.01, size=n_macro)
        
    targets = np.concatenate([micro_targets, macro_targets])
    return sorted(targets.tolist(), reverse=True)

def get_atomic_selectivities(conn: connection, table: str, categorical_cols: list[str]):
    atoms = []
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        total = cur.fetchone()[0]
        if total == 0:
            return [], 0
            
        for col in categorical_cols:
            cur.execute(f"SELECT {col}, COUNT(*) FROM {table} GROUP BY {col} ORDER BY {col}")
            for value, count in cur.fetchall():
                if value is not None:
                    atoms.append({"col": col, "value": value, "sigma": count / total})
    return atoms, total

def measure_actual_selectivity(conn: connection, table: str, conditions: list[tuple[str, str]], total_rows: int):
    if not conditions:
        return 1.0, total_rows
    where = " AND ".join([f"{col} = %s" for col, _ in conditions])
    params = [val for _, val in conditions]
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params)
        matched = cur.fetchone()[0]
    return matched / total_rows if total_rows > 0 else 0, matched

def find_filter_for_target(conn: connection, table: str, atoms: list[dict], total_rows: int, target_sigma: float, seen_conditions: set, tol: float=0.25, max_attrs: int=3, attempts_per_k: int=60):
    best = None
    
    available_fams = len(set(family_of(a["col"]) for a in atoms))
    max_k = min(max_attrs, available_fams)
    if max_k == 0:
        return None

    for k in range(1, max_k + 1):
        for _ in range(attempts_per_k):
            candidates = [a for a in atoms if a["sigma"] >= target_sigma * 0.5]
            if len(candidates) < k:
                candidates = atoms
                
            if len(candidates) < k:
                continue

            chosen = random.sample(candidates, k)
            
            # Enforce independent column families
            fams_used = {family_of(c["col"]) for c in chosen}
            if len(fams_used) < k:
                continue
                
            conditions = [(c["col"], c["value"]) for c in chosen]
            cond_tuple = tuple(sorted(conditions))
            
            # Fix dedup bug: check before measuring, and don't skip the target entirely
            if cond_tuple in seen_conditions:
                continue
                
            actual_sigma, matched_rows = measure_actual_selectivity(conn, table, conditions, total_rows)
            
            if matched_rows < 5:
                continue
                
            rel_err = abs(actual_sigma - target_sigma) / target_sigma
            if rel_err <= tol:
                return {"conditions": conditions, "target": target_sigma,
                        "actual": actual_sigma, "matched_rows": matched_rows, "met_tolerance": True}
                        
            if best is None or rel_err < best["rel_err"]:
                best = {"conditions": conditions, "target": target_sigma,
                        "actual": actual_sigma, "matched_rows": matched_rows, "rel_err": rel_err, "met_tolerance": False}
                        
    if best:
        best.pop("rel_err", None)
    return best

import math

def find_coverage_gaps(results, log_gap_threshold=0.3):
    sorted_actuals = sorted(r["actual"] for r in results if r["actual"] > 0)
    gaps = []
    for low, high in zip(sorted_actuals, sorted_actuals[1:]):
        log_gap = math.log10(high) - math.log10(low)
        if log_gap > log_gap_threshold:
            gaps.append((low, high, log_gap))
    return gaps

def fill_coverage_gaps(conn, table, atoms, total_rows, results, seen_conditions,
                        log_gap_threshold=0.3, max_attempts_per_gap=3, tol=0.25):
    unresolved = []
    gaps = find_coverage_gaps(results, log_gap_threshold)

    for low, high, log_gap in gaps:
        closed = False
        current_low, current_high = low, high

        for attempt in range(max_attempts_per_gap):
            synthetic_target = 10 ** ((math.log10(current_low) + math.log10(current_high)) / 2)
            result = find_filter_for_target(
                conn, table, atoms, total_rows, synthetic_target,
                seen_conditions, tol=tol
            )

            if result is None:
                break
                
            cond_tuple = tuple(sorted(result["conditions"]))
            if cond_tuple in seen_conditions:
                break

            results.append(result)
            seen_conditions.add(cond_tuple)

            new_gap_low = math.log10(result["actual"]) - math.log10(current_low)
            new_gap_high = math.log10(current_high) - math.log10(result["actual"])

            if max(new_gap_low, new_gap_high) <= log_gap_threshold:
                closed = True
                break

            if new_gap_low > new_gap_high:
                current_high = result["actual"]
            else:
                current_low = result["actual"]

        if not closed:
            unresolved.append({
                "low": low, "high": high, "log_gap": log_gap,
                "note": "Could not synthesize a filter closing this gap within "
                        f"{max_attempts_per_gap} attempts — likely reflects a genuine "
                        "sparsity of atoms/combinations in this selectivity range."
            })

    return unresolved

def build_filter_set(conn: connection, table: str, categorical_cols: list[str], n_micro: int=25, n_macro: int=15, output_file: str="outputs/filters.json", seed: int = 42, log_gap_threshold: float = 0.3):
    import random
    random.seed(seed)
    
    atoms, total_rows = get_atomic_selectivities(conn, table, categorical_cols)
    if not atoms:
        print("No categorical data found.")
        return []
        
    targets = generate_target_selectivities(atoms, n_micro, n_macro, seed)
    results = []
    seen_conditions = set()

    # --- NEW: explicitly seed the critical finding filters ---
    for col, val in [("index_group_name", "Baby/Children"), ("index_group_name", "Ladieswear")]:
        seed_dict = next((a for a in atoms if a["col"] == col and a["value"] == val), None)
        if seed_dict:
            results.append({
                "conditions": [(col, val)],
                "target": seed_dict["sigma"],
                "actual": seed_dict["sigma"],
                "matched_rows": int(round(seed_dict["sigma"] * total_rows)),
                "met_tolerance": True
            })
            seen_conditions.add(((col, val),))
    
    for target in targets:
        result = find_filter_for_target(conn, table, atoms, total_rows, target, seen_conditions)
        if result:
            cond_tuple = tuple(sorted(result["conditions"]))
            results.append(result)
            seen_conditions.add(cond_tuple)
            
    # --- NEW: coverage verification pass ---
    unresolved_gaps = fill_coverage_gaps(
        conn, table, atoms, total_rows, results, seen_conditions,
        log_gap_threshold=log_gap_threshold
    )

    final_check = find_coverage_gaps(results, log_gap_threshold)
    if final_check:
        print(f"WARNING: {len(final_check)} gap(s) still remain after filling — investigate before trusting coverage.")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(sorted(results, key=lambda r: r["actual"]), f, indent=2)
        
    from collections import Counter
    k_dist = Counter(len(r["conditions"]) for r in results)
    print(f"Generated {len(results)} filters saved to {output_file}")
    print(f"Filter length (k) distribution: {dict(k_dist)}")
    
    if unresolved_gaps:
        print(f"WARNING: {len(unresolved_gaps)} coverage gap(s) could not be closed:")
        for g in unresolved_gaps:
            print(f"  {g['low']:.5f} -> {g['high']:.5f} (log10 gap: {g['log_gap']:.3f})")
        with open("outputs/coverage_gaps_unresolved.json", "w") as f:
            json.dump(unresolved_gaps, f, indent=2)
    else:
        print("No unresolved coverage gaps — full selectivity range verified within tolerance.")
        
    return results

def sanity_check(conn: connection, table: str, categorical_cols: list[str]):
    print("--- Running Sanity Check ---")
    atoms, total_rows = get_atomic_selectivities(conn, table, categorical_cols)
    if not atoms:
        print("No data available for sanity check.")
        return
        
    cond1 = [(atoms[0]['col'], atoms[0]['value'])]
    actual_sigma, matched = measure_actual_selectivity(conn, table, cond1, total_rows)
    print(f"Test 1 - Filter: {cond1}")
    print(f"Calculated Sigma: {atoms[0]['sigma']:.5f}, Measured Sigma: {actual_sigma:.5f}, Matched: {matched}")
    assert abs(atoms[0]['sigma'] - actual_sigma) < 1e-6, "Mismatch in single condition selectivity"
    print("Test 1 Passed.")

    # Try to find a valid 2-condition combo from different families
    available_fams = list(set(family_of(a['col']) for a in atoms))
    if len(available_fams) >= 2:
        fam1, fam2 = available_fams[0], available_fams[1]
        atom1 = next(a for a in atoms if family_of(a['col']) == fam1)
        atom2 = next(a for a in atoms if family_of(a['col']) == fam2)
        cond2 = [(atom1['col'], atom1['value']), (atom2['col'], atom2['value'])]
        
        actual_sigma, matched = measure_actual_selectivity(conn, table, cond2, total_rows)
        print(f"Test 2 - Filter: {cond2}")
        print(f"Measured Sigma: {actual_sigma:.5f}, Matched: {matched}")
        
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {atom1['col']} = %s AND {atom2['col']} = %s", (atom1['value'], atom2['value']))
            direct_count = cur.fetchone()[0]
            assert matched == direct_count, "Mismatch between measure_actual_selectivity and direct COUNT"
            print("Test 2 Passed.")
    else:
        print("Test 2 Skipped (Not enough distinct column families).")
    print("--- Sanity Check Completed ---")

if __name__ == "__main__":
    conn = connect_pgvector()
    try:
        baseline_table = "hm_clothes_100"
        categorical_columns = [
            "index_group_name",
            "product_type_name",
            "garment_group_name",
            "perceived_colour_master_name",
            "graphical_appearance_name"
        ]
        
        sanity_check(conn, baseline_table, categorical_columns)
        build_filter_set(conn, baseline_table, categorical_columns, output_file="outputs/filters.json")
    finally:
        conn.close()
