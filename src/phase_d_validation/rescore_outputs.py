"""Re-score every existing Phase D output under the primary (Amendment 2) and strict (Amendment 1) rules.

Raw files are only read. Derived files go to a NEW folder:  outputs/rescored_<date>/<run>.jsonl + summary.json

  python -m src.phase_d_validation.rescore_outputs --out-dir outputs/rescored_2026-10-12
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.phase_d_validation.scoring import score_answer

RUNS = {
    "sept30_first_ollama": ("outputs/phase_d_results_ollama.jsonl", "legacy"),
    "sept30_corrected_ollama": ("outputs/phase_d_results_ollama_corrected.jsonl", "legacy"),
    "sept30_pilot_ollama": ("outputs/phase_d_pilot.jsonl", "legacy"),
    "oct12_local_nomic_k6": ("outputs/phase_d_local_2026-10-12/results.jsonl", "new"),
    "oct12_local_v3_amendment1": ("outputs/phase_d_local_2026-10-12_v3/results.jsonl", "new"),
    "oct12_gemini_pilot": ("outputs/phase_d_gemini_pilot_2026-10-12/results.jsonl", "new"),
}


def records(path: str, kind: str):
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        if kind == "legacy":
            for arm, pre in (("decision_matrix", "dm"), ("naive_llm", "naive")):
                yield {"pass": 1, "arm": arm, "query_id": r["id"], "gold": r["gold_answer"], "raw": r[f"{pre}_answer"],
                       "stored_label": r[f"{pre}_correct"], "error": r.get("error")}
        else:
            yield {"pass": r["pass"], "arm": r["arm"], "query_id": r["query_id"], "gold": r["gold_answer"], "raw": r["raw_output"],
                   "stored_label": r["correct"], "error": r.get("error"), "route_parse_failure": r.get("route_parse_failure", 0)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = Path(a.out_dir)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, (path, kind) in RUNS.items():
        per = {}
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in records(path, kind):
                if r["error"] or r["raw"] is None:      # no answer (naive-router schema failure / error row): label kept as stored
                    strict = primary = None
                    pf_s = pf_p = None
                else:
                    s, p = score_answer(r["raw"], r["gold"], "strict"), score_answer(r["raw"], r["gold"], "primary")
                    strict, primary, pf_s, pf_p = int(s.correct), int(p.correct), int(s.parse_failure), int(p.parse_failure)
                row = {"run": name, "pass": r["pass"], "arm": r["arm"], "query_id": r["query_id"], "gold": r["gold"], "raw_answer": r["raw"],
                       "stored_label": r["stored_label"], "strict_label": strict, "primary_label": primary,
                       "parse_failure_strict": pf_s, "parse_failure_primary": pf_p}
                f.write(json.dumps(row) + "\n")
                d = per.setdefault(f"{r['arm']}|pass{r['pass']}", {"n": 0, "stored_correct": 0, "strict_correct": 0, "primary_correct": 0,
                                                                    "stored_vs_strict_differ": 0, "primary_vs_strict_flips_to_correct": 0,
                                                                    "primary_vs_strict_flips_to_wrong": 0, "parse_failures_strict": 0,
                                                                    "parse_failures_primary": 0, "no_answer_rows": 0})
                d["n"] += 1
                d["stored_correct"] += int(bool(r["stored_label"]))
                if strict is None:
                    d["no_answer_rows"] += 1
                    continue
                d["strict_correct"] += strict
                d["primary_correct"] += primary
                d["stored_vs_strict_differ"] += int(bool(r["stored_label"]) != bool(strict))
                d["primary_vs_strict_flips_to_correct"] += int(primary == 1 and strict == 0)
                d["primary_vs_strict_flips_to_wrong"] += int(primary == 0 and strict == 1)
                d["parse_failures_strict"] += pf_s
                d["parse_failures_primary"] += pf_p
        summary[name] = {"source": path, "arms": per}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for name, s in summary.items():
        print(name)
        for k, d in s["arms"].items():
            print(f"  {k:26s} stored {d['stored_correct']:3d}  strict {d['strict_correct']:3d}  primary {d['primary_correct']:3d}  "
                  f"stored!=strict {d['stored_vs_strict_differ']}  flips strict->primary: +{d['primary_vs_strict_flips_to_correct']} -{d['primary_vs_strict_flips_to_wrong']}  "
                  f"parse-fail strict {d['parse_failures_strict']} primary {d['parse_failures_primary']}")


if __name__ == "__main__":
    main()
