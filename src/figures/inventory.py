"""Task 0 (figures session, 2026-11-01): source inventory for every planned figure and table (read only).

  python -m src.figures.inventory

For each source file: tracked in git and unchanged from HEAD; SHA-256 against outputs/data_checksums.json (files outside
outputs/, i.e. config and code, have no entry there and are checked against git only); the columns / JSON keys the item
needs. Writes reports/figures_2026-11-01/SOURCES.md and returns non-zero if any checksum mismatches.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys

from src import PROJECT_ROOT
from src.utils.freeze_checksums import sha256

CHECKSUMS = "outputs/data_checksums.json"
OUT = "reports/figures_2026-11-01/SOURCES.md"

E_CAL = "outputs/edgar_calibration_2026-11-01/"
E_CMP = "outputs/edgar_retrieval_comparison_2026-11-01/"
E_AN = "outputs/edgar_analysis_2026-11-01/"
E_EX = "outputs/edgar_analysis_exploratory_2026-11-01/"
H_CAL = "outputs/phase_e_calibration_hm_2026-10-30/"
GEM = "outputs/phase_d_gemini_full_2026-10-12/"
AHN = "outputs/phase_d_always_hnsw_2026-10-31/"
HAL = "outputs/hallucination_classification_2026-10-23/"

# item -> list of (path, required CSV columns or JSON key paths ("a.b.c"), or None)
ITEMS = {
    "Fig 4.1a FinQA census selectivities": [("outputs/finqa_selectivity_census/all_1147_selectivity.csv", ["selectivity"])],
    "Fig 4.1b EDGAR pair selectivities": [("outputs/edgar_eval_set_2026-11-01/pairs.csv", ["breadth", "selectivity"]),
                                          ("config/policy_v3_hm.json", ["T_default"]), ("config/policy_v3_1_edgar.json", ["T_default"])],
    "Fig 4.2 H&M recall by arm": [("outputs/phase_a_arms/analysis/cell_summary.csv", ["table", "filter_id", "selectivity", "arm", "mean_recall"])],
    "Fig 4.3 exact latency": [(H_CAL + "cell_summary.csv", ["table", "s", "exact_ms", "iter_guard_ms"]),
                              (E_CAL + "cell_summary.csv", ["s", "exact_ms", "iter_guard_ms"]),
                              ("config/policy_v3_hm.json", ["T_default", "L_ms"]), ("config/policy_v3_1_edgar.json", ["T_default", "L_ms"])],
    "Fig 4.4 EDGAR calibration recall": [(E_CAL + "cell_summary.csv", ["s", "exact_recall15", "iter_recall15", "iter_guard_recall15", "tuned_recall15",
                                                                        "tuned_guard_recall15", "exact_pass", "iter_pass", "iter_guard_pass",
                                                                        "tuned_pass", "tuned_guard_pass"])],
    "Fig 4.5a EDGAR failures by T": [(E_CAL + "calibration.json", ["T_default.per_table.edgar_chunks.failures_by_T", "T_default.T"])],
    "Fig 4.5b H&M failures by T": [("config/policy_v3_hm.json", ["calibration_default.pooled.failures_by_T"])],
    "Fig 4.6a FinQA accuracy": [(HAL + "summary_counts_gemini_full.csv", ["arm", "pass", "class", "rate", "ci95_lo", "ci95_hi"]),
                                (AHN + "analysis/summary.json", ["arms.always_hnsw.pass1_accuracy", "arms.always_hnsw.accuracy"]),
                                (AHN + "analysis/classes.csv", ["arm", "pass", "query_id", "correct"]),
                                (GEM + "stats_primary.json", ["non_inferiority.margin"])],
    "Fig 4.6b EDGAR accuracy": [(E_AN + "answers_by_mode_breadth.csv", ["mode", "breadth", "correct", "correct_ci"])],
    "Fig 4.7a FinQA classes": [(HAL + "summary_counts_gemini_full.csv", ["arm", "pass", "class", "n", "of"]),
                               (AHN + "analysis/summary.json", ["arms.always_hnsw.classes", "arms.always_hnsw.n_rows"])],
    "Fig 4.7b/c EDGAR classes": [(E_AN + "answers_by_mode_breadth.csv", ["mode", "breadth", "correct", "abstained", "wrong_in_context", "wrong_not_in_context"]),
                                 (E_EX + "refusal_by_mode_breadth.csv", ["mode", "breadth", "ref_accuracy", "ref_abstained", "ref_wrong_in_context",
                                                                          "ref_wrong_not_in_context"])],
    "Fig 4.8 EDGAR recall vs latency": [(E_CMP + "summary_by_mode_breadth.csv", ["mode", "breadth", "mean_recall15", "median_latency_ms", "recall15_ge_0.90"])],
    "Fig 4.9 decision overhead": [("outputs/edgar_report_inputs_2026-11-01/decision_overhead.json", ["by_breadth"])],
    "Fig 5.1 thresholds": [("config/policy_v3_hm.json", ["calibration_default.pooled.lower", "calibration_default.pooled.upper", "T_default", "k", "ef_search"]),
                           ("config/policy_v3_1_edgar.json", ["T_default"]),
                           ("src/phase_c_analysis/amendment6_partb.py", None), ("src/phase_d_validation/amendment7_step1.py", None),
                           ("src/phase_f_edgar/compare_edgar.py", None),
                           ("outputs/phase_a_arms/analysis/cell_summary.csv", ["selectivity", "arm", "scan_nodes"]),
                           ("outputs/embedding_build_2026-10-12/audit_finqa_evidence_qwen3.json", ["db_rows", "dimension"]),
                           ("outputs/edgar_chunks_2026-10-31/summary.json", ["chunks_total"])],
    "Fig A.1 EDGAR per-vector spread": [(E_CAL + "results.jsonl", ["filter_id", "selectivity", "route", "recall15"])],
    "Fig A.2/A.4 EDGAR recall heatmap, route mix": [(E_CMP + "summary_by_mode_breadth.csv", ["mode", "breadth", "mean_recall15", "routes"])],
    "Fig A.3/A.5 EDGAR per-pair latency, router_hmT": [(E_CMP + "per_pair_mode.csv", ["pair_id", "breadth", "selectivity", "mode", "route", "recall15", "latency_ms"])],
    "Fig A.6/A.7 retrieval vs answer": [(E_AN + "answers_scored.csv", ["pair_id", "mode", "class", "correct", "gold_hit", "recall15", "rows_returned", "n_passages"])],
    "Fig A.8 accuracy under three rules": [(E_EX + "scale_rescore.json", ["accuracy_by_mode"]), (E_EX + "refusal_by_mode_breadth.csv", ["ref_accuracy"])],
    "Fig A.9 / T4.3 H&M pass counts": [("outputs/phase_e_comparison_hm_2026-10-31/summary.json", ["pass_counts"]),
                                       ("outputs/phase_a_amendment6_2026-10-23/partb_summary.json", ["pass_counts"]),
                                       ("outputs/phase_a_arms/analysis/policy_evaluation_cells.csv", ["policy", "pass"]),
                                       ("outputs/phase_a_holdout/analysis/policy_cells.csv", ["policy", "pass"]),
                                       ("outputs/phase_a_holdout2/analysis/policy_cells.csv", ["policy", "pass"])],
    "T4.1 corpus audit": [("outputs/embedding_build_2026-10-12/audit_finqa_evidence_qwen3.json",
                           ["db_rows", "db_unique", "unresolved_gold_pairs", "zero_vectors", "dimension"]),
                          ("outputs/edgar_chunks_2026-10-31/summary.json", ["chunks_total", "sampled_companies", "chunks_by_year"]),
                          ("outputs/edgar_eval_preflight_2026-11-01/stats.json", ["after.reltuples"]),
                          ("outputs/edgar_index_2026-10-31/checks.json", None)],
    "T4.2 calibrated T": [("config/policy_v3_hm.json", ["calibration_default.per_table", "calibration_default.pooled"]),
                          (E_CAL + "calibration.json", ["T_default.per_table.edgar_chunks", "T_tuned.per_table.edgar_chunks"])],
    "T4.4 FinQA accuracy": [(GEM + "stats_primary.json", ["pairs.policy_v2_vs_naive_llm", "pooled.policy_v2_vs_naive_llm"]),
                            (AHN + "analysis/summary.json", ["comparisons"]), (HAL + "summary_counts_gemini_full.csv", ["rate"])],
    "T4.5 FinQA latency and cost": [(GEM + "stats_primary.json", ["pairs.policy_v2_vs_naive_llm.latency_diff_ci95"]),
                                    ("outputs/headline_audit_2026-10-23/audit.json", ["recomputed.lat_diff", "recomputed.cost", "recomputed.pct"])],
    "T4.6 EDGAR per mode": [(E_CMP + "summary_by_mode_breadth.csv", ["mode"]), (E_AN + "answers_by_mode_breadth.csv", ["mode"])],
    "T4.7 label validation": [(HAL + "label_analysis/label_confusion.json", None), (E_EX + "agreement.json", ["all.confusion", "all.agreement"])],
    "Appendix tables": [(E_CMP + "vecadvisor_decisions.json", ["decisions"]), (E_CMP + "llm_decisions.json", None),
                        ("outputs/edgar_cost_log_2026-11-01/cost_log.jsonl", None), ("outputs/edgar_answers_2026-11-01/pass_decision.json", ["projection_usd"]),
                        (E_EX + "scale_changes.csv", ["answer_span", "gold_number"]), (E_EX + "zero_passages.csv", ["zero_passage_pairs"]),
                        (E_EX + "label_error_sources.json", ["S_wrong_source", "S_wrong_year"])],
}


def git_state(path: str) -> str:
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=PROJECT_ROOT, capture_output=True).returncode == 0
    if not tracked:
        return "NOT COMMITTED"
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path], cwd=PROJECT_ROOT).returncode == 0
    return "committed, clean" if clean else "MODIFIED vs HEAD"


def has_key(obj, dotted: str) -> bool:
    for part in dotted.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return False
        obj = obj[part]
    return True


def columns_ok(path: str, need) -> tuple[bool, list[str]]:
    if not need:
        return True, []
    p = PROJECT_ROOT / path
    if path.endswith(".csv"):
        with open(p, encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh))
        missing = [c for c in need if c not in header]
    elif path.endswith(".jsonl"):
        first = json.loads(p.open(encoding="utf-8").readline())
        missing = [c for c in need if c not in first]
    else:
        obj = json.loads(p.read_text(encoding="utf-8"))
        missing = [c for c in need if not has_key(obj, c)]
    return not missing, missing


def main():
    sums = json.loads((PROJECT_ROOT / CHECKSUMS).read_text(encoding="utf-8"))["files"]
    rows, mismatches, cache = [], [], {}
    for item, sources in ITEMS.items():
        for path, need in sources:
            if path not in cache:
                exists = (PROJECT_ROOT / path).is_file()
                g = git_state(path) if exists else "missing"
                if not exists:
                    cs = "file missing"
                elif path in sums:
                    ok = sha256(PROJECT_ROOT / path) == sums[path]["sha256"]
                    cs = "OK" if ok else "MISMATCH"
                    if not ok:
                        mismatches.append(path)
                else:
                    cs = "no entry (git only)" if not path.startswith("outputs/") else "no entry"
                cache[path] = (g, cs)
            g, cs = cache[path]
            col_ok, missing = columns_ok(path, need) if (PROJECT_ROOT / path).is_file() else (False, ["file missing"])
            rows.append((item, path, g, cs, "yes" if col_ok else "MISSING: " + ", ".join(missing)))
    lines = ["# Figure and table sources (Task 0, read only)", "",
             "Checksums against `outputs/data_checksums.json`; files outside `outputs/` (config, code) have no entry there and are "
             "checked against git (tracked and identical to HEAD). Generated by `src/figures/inventory.py`.", "",
             "| item | source | git | checksum | needed columns / keys |", "|---|---|---|---|---|"]
    lines += [f"| {a} | `{b}` | {c} | {d} | {e} |" for a, b, c, d, e in rows]
    gaps = [r for r in rows if r[2] != "committed, clean" or r[3] in ("MISMATCH", "file missing") or r[4] != "yes"]
    lines += ["", "## Gaps", ""] + ([f"- {a}: `{b}`: git {c}; checksum {d}; columns {e}" for a, b, c, d, e in gaps] or ["- none"])
    out = PROJECT_ROOT / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for r in gaps:
        print("GAP", r)
    print(f"{len(rows)} source rows, {len(cache)} files, {len(mismatches)} checksum mismatches")
    if mismatches:
        print("MISMATCH:", mismatches)
        sys.exit(1)


if __name__ == "__main__":
    main()
