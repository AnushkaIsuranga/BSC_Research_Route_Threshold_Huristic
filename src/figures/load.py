"""Loaders for the dissertation figures and tables (2026-11-01). One function per committed source; each returns a tidy
DataFrame (or a dict for nested JSON) and does no plotting. Paths are the committed files listed in
reports/figures_2026-11-01/SOURCES.md; nothing here connects to a database or the network.
"""

from __future__ import annotations

import ast
import json
import re
from functools import lru_cache

import pandas as pd

from src import PROJECT_ROOT

E_CAL = "outputs/edgar_calibration_2026-11-01/"
E_CMP = "outputs/edgar_retrieval_comparison_2026-11-01/"
E_AN = "outputs/edgar_analysis_2026-11-01/"
E_EX = "outputs/edgar_analysis_exploratory_2026-11-01/"
E_RI = "outputs/edgar_report_inputs_2026-11-01/"
H_CAL = "outputs/phase_e_calibration_hm_2026-10-30/"
H_CMP = "outputs/phase_e_comparison_hm_2026-10-31/"
ARMS = "outputs/phase_a_arms/analysis/"
GEM = "outputs/phase_d_gemini_full_2026-10-12/"
AHN = "outputs/phase_d_always_hnsw_2026-10-31/"
HAL = "outputs/hallucination_classification_2026-10-23/"
HM_TABLES = ("hm_clothes_0", "hm_clothes_25", "hm_clothes_50", "hm_clothes_75", "hm_clothes_100")   # least to most correlated
BREADTHS = ("cik+year+section", "cik+year", "year+section", "section")


def path(rel: str):
    return PROJECT_ROOT / rel


def _csv(rel: str) -> pd.DataFrame:
    return pd.read_csv(path(rel), encoding="utf-8")


@lru_cache(maxsize=None)
def _json(rel: str):
    return json.loads(path(rel).read_text(encoding="utf-8"))


def _jsonl(rel: str) -> list[dict]:
    return [json.loads(ln) for ln in path(rel).read_text(encoding="utf-8").splitlines() if ln.strip()]


def _ci(s: str) -> tuple[float, float]:
    lo, hi = s.strip("[]").split(",")
    return float(lo), float(hi)


# ------------------------------------------------------------------ EDGAR (Phase F, tag final-results-edgar-2026-11-01)

def edgar_pairs() -> pd.DataFrame:
    return _csv("outputs/edgar_eval_set_2026-11-01/pairs.csv")[["pair_id", "qid", "breadth", "selectivity", "n_match"]]


def edgar_config() -> dict:
    return _json("config/policy_v3_1_edgar.json")


def edgar_calibration() -> dict:
    return _json(E_CAL + "calibration.json")


def edgar_failures_by_T(which: str = "T_default") -> pd.DataFrame:
    f = edgar_calibration()[which]["per_table"]["edgar_chunks"]["failures_by_T"]
    return pd.DataFrame({"T": [float(k) for k in f], "failing_cells": list(f.values())}).sort_values("T").reset_index(drop=True)


def edgar_cal_cells() -> pd.DataFrame:
    return _csv(E_CAL + "cell_summary.csv")


def edgar_cal_results() -> pd.DataFrame:
    rows = _jsonl(E_CAL + "results.jsonl")
    return pd.DataFrame([{k: r.get(k) for k in ("filter_id", "selectivity", "qid", "route", "recall15", "rows_returned", "latency_ms",
                                                 "early_stop", "error")} for r in rows])


def edgar_summary() -> pd.DataFrame:
    df = _csv(E_CMP + "summary_by_mode_breadth.csv")
    df["routes"] = df["routes"].map(json.loads)
    return df


def edgar_per_pair() -> pd.DataFrame:
    return _csv(E_CMP + "per_pair_mode.csv")


def edgar_answers_by_mode() -> pd.DataFrame:
    df = _csv(E_AN + "answers_by_mode_breadth.csv")
    df[["correct_lo", "correct_hi"]] = pd.DataFrame(df["correct_ci"].map(_ci).tolist(), index=df.index)
    return df


def edgar_answers_scored() -> pd.DataFrame:
    return _csv(E_AN + "answers_scored.csv")


def edgar_predictions() -> dict:
    return _json(E_AN + "predictions.json")


def edgar_refusal_by_mode() -> pd.DataFrame:
    return _csv(E_EX + "refusal_by_mode_breadth.csv")


def edgar_refusal_rescore() -> dict:
    return _json(E_EX + "refusal_rescore.json")


def edgar_scale_rescore() -> dict:
    return _json(E_EX + "scale_rescore.json")


def edgar_scale_changes() -> pd.DataFrame:
    return _csv(E_EX + "scale_changes.csv")


def edgar_zero_passages() -> pd.DataFrame:
    return _csv(E_EX + "zero_passages.csv")


def edgar_agreement() -> dict:
    return _json(E_EX + "agreement.json")


def edgar_label_sources() -> dict:
    return _json(E_EX + "label_error_sources.json")


def edgar_overhead() -> pd.DataFrame:
    d = _json(E_RI + "decision_overhead.json")["by_breadth"]
    return pd.DataFrame([{"breadth": b, **v} for b, v in d.items()])


def edgar_vecadvisor() -> pd.DataFrame:
    return pd.DataFrame([{"pair_id": d["pair_id"], "strategy": d["strategy"], "top_ranked": d.get("top_ranked"),
                          "unavailable": d["unavailable"], "unavailable_reason": d.get("unavailable_reason"),
                          "decision_ms": d.get("decision_ms")} for d in _json(E_CMP + "vecadvisor_decisions.json")["decisions"]])


def edgar_llm_decisions() -> pd.DataFrame:
    d = _json(E_CMP + "llm_decisions.json")
    return pd.DataFrame(d["decisions"])


def edgar_cost_log() -> pd.DataFrame:
    return pd.DataFrame(_jsonl("outputs/edgar_cost_log_2026-11-01/cost_log.jsonl"))


def edgar_pass_decision() -> dict:
    return _json("outputs/edgar_answers_2026-11-01/pass_decision.json")


def edgar_corpus() -> dict:
    return _json("outputs/edgar_chunks_2026-10-31/summary.json")


def edgar_stats() -> dict:
    return _json("outputs/edgar_eval_preflight_2026-11-01/stats.json")


def edgar_index_checks() -> dict:
    return _json("outputs/edgar_index_2026-10-31/checks.json")


# ------------------------------------------------------------------ H&M (Phase A arms, Phase E, Amendment 6)

def hm_arms_cells() -> pd.DataFrame:
    return _csv(ARMS + "cell_summary.csv")


def hm_route_map() -> pd.DataFrame:
    return _csv(ARMS + "route_map.csv")


def hm_planner_switch() -> tuple[float, float]:
    """(largest selectivity where planner-default used only Bitmap Heap Scan on every table, smallest where it used only
    the HNSW Index Scan on every table), from the scan_nodes column of the three-arm run."""
    pd_ = hm_arms_cells().query("arm == 'planner-default'")
    by_s = pd_.groupby("selectivity")["scan_nodes"].apply(list)
    exact = [s for s, nodes in by_s.items() if all(n.startswith("Bitmap Heap Scan") for n in nodes)]
    hnsw = [s for s, nodes in by_s.items() if all(n.startswith("Index Scan") for n in nodes)]
    return max(exact), min(hnsw)


def hm_config() -> dict:
    return _json("config/policy_v3_hm.json")


def hm_cal_cells() -> pd.DataFrame:
    return _csv(H_CAL + "cell_summary.csv")


def hm_phase_e_pass_counts() -> pd.DataFrame:
    rows = []
    for mode, v in _json(H_CMP + "summary.json")["pass_counts"].items():
        rec = {"mode": mode}
        for key, col in (("in_sample", "in_sample"), ("ho1", "ho1"), ("ho2", "ho2")):
            if key in v:
                p, n = v[key].split("/")
                rec[col], rec[col + "_n"] = int(p), int(n)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["held_out"] = df["ho1"] + df["ho2"]
    return df


def hm_partb_pass_counts() -> pd.DataFrame:
    rows = []
    for rule, v in _json("outputs/phase_a_amendment6_2026-10-23/partb_summary.json")["pass_counts"].items():
        rows.append({"rule": rule, "in_sample": v["in-sample"]["pass"], "ho1": v["held-out 1"]["pass"], "ho2": v["held-out 2"]["pass"],
                     "ho1_rerun": v["held-out 1 quiet rerun (sensitivity)"]["pass"]})
    df = pd.DataFrame(rows)
    df["held_out"] = df["ho1"] + df["ho2"]
    return df


def hm_v1_pass_counts() -> dict:
    """P1 matrix v1: in-sample (three-arm run), held-out 1 (original) and held-out 2 policy cells."""
    cnt = lambda rel: int(_csv(rel).query("policy == 'P1'")["pass"].astype(bool).sum())
    d = {"in_sample": cnt(ARMS + "policy_evaluation_cells.csv"), "ho1": cnt("outputs/phase_a_holdout/analysis/policy_cells.csv"),
         "ho2": cnt("outputs/phase_a_holdout2/analysis/policy_cells.csv")}
    d["held_out"] = d["ho1"] + d["ho2"]
    return d


# ------------------------------------------------------------------ FinQA (Phase D)

def finqa_class_counts() -> pd.DataFrame:
    return _csv(HAL + "summary_counts_gemini_full.csv")


def finqa_stats() -> dict:
    return _json(GEM + "stats_primary.json")


def finqa_always_hnsw() -> dict:
    return _json(AHN + "analysis/summary.json")


def finqa_always_hnsw_classes() -> pd.DataFrame:
    return _csv(AHN + "analysis/classes.csv")


def finqa_label_confusion() -> dict:
    return _json(HAL + "label_analysis/label_confusion.json")


def finqa_audit() -> dict:
    return _json("outputs/embedding_build_2026-10-12/audit_finqa_evidence_qwen3.json")


def headline_audit() -> dict:
    return _json("outputs/headline_audit_2026-10-23/audit.json")


# ------------------------------------------------------------------ prior-system constants, read from the code

PRIOR_CODE = {"amendment6": "src/phase_c_analysis/amendment6_partb.py", "amendment7": "src/phase_d_validation/amendment7_step1.py",
              "phase_f": "src/phase_f_edgar/compare_edgar.py"}


def _find(rel: str, pattern: str) -> tuple[int, str]:
    for i, line in enumerate(path(rel).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, line):
            return i, line.strip()
    raise ValueError(f"{pattern!r} not found in {rel}")


def prior_constants() -> dict:
    """VBASE / Milvus thresholds and Qdrant's row limit per corpus, each with the file and line it is read from."""
    out = {}
    ln, txt = _find(PRIOR_CODE["amendment6"], r'"B1 VBASE')
    out["vbase"] = {"s": float(re.search(r"s < ([\d.]+)", txt).group(1)), "src": f"{PRIOR_CODE['amendment6']}:{ln}"}
    ln, txt = _find(PRIOR_CODE["amendment6"], r'"B2 Milvus')
    out["milvus"] = {"s": float(re.search(r"s <= ([\d.]+)", txt).group(1)), "src": f"{PRIOR_CODE['amendment6']}:{ln}"}
    # Qdrant: rows < 10000 / (DIMS / 256) (full_scan_threshold 10,000 KB over vector KB); per corpus, with that corpus' N
    ln_d, txt_d = _find(PRIOR_CODE["amendment6"], r"^DIMS = ")
    ln_n, txt_n = _find(PRIOR_CODE["amendment6"], r"^N_ROWS = ")
    ln_b, _ = _find(PRIOR_CODE["amendment6"], r"^B3_ROWS = ")
    dims, n = int(txt_d.split("=")[1]), int(txt_n.split("=")[1].strip().replace("_", ""))
    rows = 10000 / (dims / 256)
    out["qdrant_hm"] = {"rows": rows, "N": n, "s": rows / n, "src": f"{PRIOR_CODE['amendment6']}:{ln_b} (DIMS line {ln_d}, N_ROWS line {ln_n})"}
    ln_k, txt_k = _find(PRIOR_CODE["amendment7"], r"^N_TOTAL, DIMS, K = ")
    ln_q, _ = _find(PRIOR_CODE["amendment7"], r'"B3": EXACT if n < 10000 / \(DIMS / 256\)')
    n_f, dims_f, _ = [int(x.strip().replace("_", "")) for x in txt_k.split("=")[1].split(",")]
    rows_f = 10000 / (dims_f / 256)
    out["qdrant_finqa"] = {"rows": rows_f, "N": n_f, "s": rows_f / n_f, "src": f"{PRIOR_CODE['amendment7']}:{ln_q} (N_TOTAL, DIMS line {ln_k})"}
    ln_p, txt_p = _find(PRIOR_CODE["phase_f"], r"^PRIOR = ")
    rows_e = int(re.search(r'"qdrant": lambda s, n: n < (\d+)', txt_p).group(1))
    n_e = edgar_corpus()["chunks_total"]
    out["qdrant_edgar"] = {"rows": rows_e, "N": n_e, "s": rows_e / n_e,
                           "src": f"{PRIOR_CODE['phase_f']}:{ln_p} (N = chunks_total, outputs/edgar_chunks_2026-10-31/summary.json)"}
    return out


def literal(s):
    """Parse a Python-literal cell (e.g. a dict written by str())."""
    return ast.literal_eval(s) if isinstance(s, str) else s
