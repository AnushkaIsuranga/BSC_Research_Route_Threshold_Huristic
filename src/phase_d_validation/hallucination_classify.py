"""Hallucination-oriented classification of wrong answers (Amendment 5; existing outputs only, no model/API call, no DB write).

  python -m src.phase_d_validation.hallucination_classify outputs/phase_d_gemini_full_2026-10-12/results.jsonl \
      --hit-field retrieval_hit_passage --label gemini_full --out-dir outputs/hallucination_classification_2026-10-23 \
      [--label-sample --evidence-table finqa_evidence_qwen3]

The grounding field (--hit-field) is explicit and required: retrieval_hit_passage for runs from Amendment 1 onward,
retrieval_hit for the 12 Oct baseline (the only field in its rows). A missing/null grounding field stops the script.

Classes (assigned in this order, per arm x question x pass; `correct` = primary scoring rule):
  correct                 correct == 1
  abstain_or_parse_fail   correct == 0 and parse_failure == 1
  wrong_ungrounded        correct == 0, parse_failure == 0, grounding field == 0   (hallucination PROXY, not proof)
  wrong_grounded          correct == 0, parse_failure == 0, grounding field == 1
also reported: correct_ungrounded (correct == 1, grounding field == 0). The same classes are recomputed with the strict
page-id field `retrieval_hit` as a sensitivity table ("strict page-id test, shown for transparency only").
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from src.phase_d_validation.paired_stats import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, bootstrap_mean_diff, mcnemar_exact, wilson

CLASSES = ("correct", "abstain_or_parse_fail", "wrong_ungrounded", "wrong_grounded")
PAIR_CLASSES = ("wrong_ungrounded", "wrong_grounded", "abstain_or_parse_fail")
SAMPLE_SEED = 20261023
SAMPLE_PER_CLASS = 20
ROW_BUCKETS = (("0", 0, 0), ("1-3", 1, 3), ("4-7", 4, 7), ("8-14", 8, 14), ("15+", 15, 10**9))


def classify_row(r: dict, hit_field: str) -> str:
    """Class of one result row. Raises ValueError (naming the row) if `correct`, `parse_failure` or the grounding field is null."""
    where = f"pass {r.get('pass')} arm {r.get('arm')} query {r.get('query_id')}"
    for f in ("correct", "parse_failure", hit_field):
        if r.get(f) is None:
            extra = " (naive router schema failure: no retrieval happened)" if r.get("route_parse_failure") else ""
            raise ValueError(f"field {f!r} is missing/null in a row ({where}){extra}; stopping, no guessing")
    if r["correct"] == 1:
        return "correct"
    if r["parse_failure"] == 1:
        return "abstain_or_parse_fail"
    return "wrong_ungrounded" if r[hit_field] == 0 else "wrong_grounded"


def classify_run(rows: list[dict], hit_field: str, run: str = "") -> list[dict]:
    out = []
    for r in rows:
        cls = classify_row(r, hit_field)
        strict = classify_row({**r, "retrieval_hit": r.get("retrieval_hit")}, "retrieval_hit")   # sensitivity: strict page-id test
        out.append({"run": run, "arm": r["arm"], "pass": r["pass"], "query_id": r["query_id"], "route": r.get("route"),
                    "rows_returned": r.get("rows_returned"), "correct": r["correct"], "parse_failure": r["parse_failure"],
                    "retrieval_hit": r.get("retrieval_hit"), "retrieval_hit_passage": r.get("retrieval_hit_passage"),
                    "grounding_field": hit_field, "grounding_value": r[hit_field], "class": cls,
                    "correct_ungrounded": int(r["correct"] == 1 and r[hit_field] == 0), "strict_class": strict,
                    "strict_correct_ungrounded": int(r["correct"] == 1 and r["retrieval_hit"] == 0),
                    "parsed_answer": r.get("parsed_answer"), "gold_answer": r.get("gold_answer"), "raw_output": r.get("raw_output")})
    return out


def _rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"n": k, "of": n, "rate": (k / n) if n else None, "ci95": [lo, hi]}


def counts_table(cl: list[dict], class_key: str = "class", ungrounded_key: str = "correct_ungrounded") -> list[dict]:
    """Counts and Wilson rates per arm and per pass, plus 'all' = pooled over the passes present."""
    groups: dict[tuple, list] = defaultdict(list)
    for r in cl:
        groups[(r["arm"], r["pass"])].append(r)
        groups[(r["arm"], "all")].append(r)
    rows = []
    for (arm, ps), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]).zfill(3))):
        c = Counter(r[class_key] for r in rs)
        for k in CLASSES:
            rows.append({"arm": arm, "pass": ps, "class": k, **_rate(c.get(k, 0), len(rs))})
        rows.append({"arm": arm, "pass": ps, "class": "correct_ungrounded (subset of correct)", **_rate(sum(r[ungrounded_key] for r in rs), len(rs))})
    return rows


def paired_comparison(cl: list[dict], x: str = "policy_v2", y: str = "naive_llm") -> dict:
    """Per-question paired comparison of the rate of each class (secondary, descriptive; no margin)."""
    cell = {(r["arm"], r["query_id"], r["pass"]): r["class"] for r in cl if r["arm"] in (x, y)}
    passes = sorted({p for (_, _, p) in cell})
    qids = sorted({q for (_, q, _) in cell})
    for a in (x, y):
        for q in qids:
            for p in passes:
                if (a, q, p) not in cell:
                    raise ValueError(f"missing row arm={a} query={q} pass={p}")
    res = {"x": x, "y": y, "passes": passes, "n_questions": len(qids), "classes": {}}
    for k in PAIR_CLASSES:
        ind = lambda a, q, p: int(cell[(a, q, p)] == k)
        p1 = passes[0]
        b = sum(1 for q in qids if ind(x, q, p1) and not ind(y, q, p1))
        c = sum(1 for q in qids if ind(y, q, p1) and not ind(x, q, p1))
        mx = [statistics.fmean(ind(x, q, p) for p in passes) for q in qids]
        my = [statistics.fmean(ind(y, q, p) for p in passes) for q in qids]
        d, lo, hi = bootstrap_mean_diff(mx, my, BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED)
        res["classes"][k] = {"pass1": {"pass": p1, "b_x_only": b, "c_y_only": c, "mcnemar_exact_p": mcnemar_exact(b, c),
                                       "rate_x": sum(ind(x, q, p1) for q in qids) / len(qids), "rate_y": sum(ind(y, q, p1) for q in qids) / len(qids)},
                             "pooled": {"mean_rate_x": statistics.fmean(mx), "mean_rate_y": statistics.fmean(my), "diff_x_minus_y": d,
                                        "ci95": [lo, hi], "method": f"paired bootstrap over questions, {BOOTSTRAP_RESAMPLES} resamples, seed {BOOTSTRAP_SEED}"}}
    return res


def route_split(cl: list[dict], arm: str) -> list[dict]:
    out = []
    for scope in ("pass1", "all"):
        rs = [r for r in cl if r["arm"] == arm and (scope == "all" or r["pass"] == 1)]
        for route in sorted({str(r["route"]) for r in rs}):
            sub = [r for r in rs if str(r["route"]) == route]
            c = Counter(r["class"] for r in sub)
            rr = [r["rows_returned"] for r in sub if r["rows_returned"] is not None]
            out.append({"arm": arm, "scope": scope, "route": route, "n": len(sub), **{k: c.get(k, 0) for k in CLASSES},
                        "mean_rows_returned": statistics.fmean(rr) if rr else None})
    return out


def rows_returned_ungrounded(cl: list[dict]) -> list[dict]:
    """Per arm: all wrong_ungrounded rows, how many have rows_returned logged (older runs do not log it), and for those the
    0-row cases and the distribution of rows returned."""
    out = []
    for arm in sorted({r["arm"] for r in cl}):
        allu = [r for r in cl if r["arm"] == arm and r["class"] == "wrong_ungrounded"]
        rs = [r for r in allu if r["rows_returned"] is not None]
        vals = [r["rows_returned"] for r in rs]
        row = {"arm": arm, "n_wrong_ungrounded": len(allu), "n_with_rows_returned_logged": len(rs),
               "zero_row_cases": sum(1 for v in vals if v == 0),
               "mean_rows": statistics.fmean(vals) if vals else None, "median_rows": statistics.median(vals) if vals else None}
        for name, lo, hi in ROW_BUCKETS:
            row[f"rows_{name}"] = sum(1 for v in vals if lo <= v <= hi)
        out.append(row)
    return out


def build_label_sample(cl: list[dict], source_rows: list[dict], fetch_passages, question_of, seed: int = SAMPLE_SEED,
                       per_class: int = SAMPLE_PER_CLASS, pass_no: int = 1) -> tuple[list[dict], list[dict]]:
    """Blind labelling sheet + separate key. `cl` = classified rows; `source_rows` = the raw results rows (for retrieved_ids and
    raw_output); `fetch_passages(ids) -> list[str]` returns passage texts in the given order (read-only DB lookup);
    `question_of(query_id) -> str`. The sheet has no class, arm or route."""
    src = {(r["arm"], r["query_id"], r["pass"]): r for r in source_rows}
    pool = {k: sorted([r for r in cl if r["pass"] == pass_no and r["class"] == k], key=lambda r: (r["query_id"], r["arm"]))
            for k in ("wrong_ungrounded", "wrong_grounded")}
    rng = random.Random(seed)
    picked = []
    for k in ("wrong_ungrounded", "wrong_grounded"):
        picked += rng.sample(pool[k], min(per_class, len(pool[k])))
    rng.shuffle(picked)
    sheet, key = [], []
    for i, r in enumerate(picked, 1):
        sid = f"S{i:03d}"
        raw = src[(r["arm"], r["query_id"], r["pass"])]
        texts = fetch_passages(raw["retrieved_ids"])
        sheet.append({"sample_id": sid, "question": question_of(r["query_id"]), "gold_answer": raw["gold_answer"],
                      "model_answer": raw["raw_output"],
                      "retrieved_passages": "\n\n".join(f"[{j}] {t}" for j, t in enumerate(texts, 1))})
        key.append({"sample_id": sid, "query_id": r["query_id"], "arm": r["arm"], "pass": r["pass"], "proxy_class": r["class"]})
    return sheet, key


def _write_csv(path: Path, rows: list[dict]) -> None:
    flat = []
    for r in rows:
        f = dict(r)
        if "ci95" in f:
            f["ci95_lo"], f["ci95_hi"] = f.pop("ci95")
        flat.append(f)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(flat[0]))
        w.writeheader()
        w.writerows(flat)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--hit-field", required=True, choices=["retrieval_hit_passage", "retrieval_hit"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--label-sample", action="store_true", help="also write the blind labelling sheet and key (Gemini pass 1)")
    ap.add_argument("--evidence-table", default="finqa_evidence_qwen3")
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in Path(a.results).read_text(encoding="utf-8").splitlines() if l.strip()]
    cl = classify_run(rows, a.hit_field, a.label)
    _write_csv(out / f"classified_rows_{a.label}.csv", cl)
    arms = sorted({r["arm"] for r in cl})
    summary = {"label": a.label, "results": a.results, "grounding_field": a.hit_field, "n_rows": len(cl), "arms": arms,
               "passes": sorted({r["pass"] for r in cl}),
               "counts": counts_table(cl),
               "sensitivity_strict_page_id_test_for_transparency_only": counts_table(cl, "strict_class", "strict_correct_ungrounded"),
               "paired": {}, "route_split": [], "rows_returned_wrong_ungrounded": rows_returned_ungrounded(cl)}
    for x, y in (("policy_v2", "naive_llm"), ("policy_v2", "naive_informed")):
        if x in arms and y in arms:
            summary["paired"][f"{x}_vs_{y}"] = paired_comparison(cl, x, y)
    for arm in ("naive_llm", "naive_informed"):
        if arm in arms:
            summary["route_split"] += route_split(cl, arm)
    _write_csv(out / f"summary_counts_{a.label}.csv", summary["counts"])
    _write_csv(out / f"summary_sensitivity_strict_{a.label}.csv", summary["sensitivity_strict_page_id_test_for_transparency_only"])
    _write_csv(out / f"summary_rows_returned_wrong_ungrounded_{a.label}.csv", summary["rows_returned_wrong_ungrounded"])
    if summary["route_split"]:
        _write_csv(out / f"summary_route_split_{a.label}.csv", summary["route_split"])
    if a.label_sample:
        import psycopg2

        from src import db_settings
        from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset
        questions = {q["id"]: q["question"] for q in load_finqa_subset(get_frozen_filepath())}
        conn = psycopg2.connect(**db_settings())
        conn.set_session(readonly=True, autocommit=True)      # read-only SELECTs only

        def fetch(ids):
            with conn.cursor() as cur:
                cur.execute(f"SELECT id, content FROM {a.evidence_table} WHERE id = ANY(%s)", (list(ids),))
                by = dict(cur.fetchall())
            missing = [i for i in ids if i not in by]
            if missing:
                raise RuntimeError(f"evidence ids not found in {a.evidence_table}: {missing[:5]}")
            return [by[i] for i in ids]
        sheet, key = build_label_sample(cl, rows, fetch, questions.__getitem__)
        _write_csv(out / "labelling_sheet.csv", sheet)
        _write_csv(out / "labelling_key.csv", key)
        summary["label_sample"] = {"seed": SAMPLE_SEED, "n": len(sheet), "by_proxy_class": dict(Counter(k["proxy_class"] for k in key))}
        conn.close()
    (out / f"summary_{a.label}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("label", "n_rows", "arms", "passes")} | ({"label_sample": summary["label_sample"]} if "label_sample" in summary else {})))


if __name__ == "__main__":
    main()
