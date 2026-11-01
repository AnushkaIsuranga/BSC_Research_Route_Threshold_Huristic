"""Phase F Task 6, after the labels were returned: proxy agreement and EXPLORATORY re-scores (not pre-registered).

  python -m src.phase_f_edgar.exploratory_edgar --out-dir outputs/edgar_analysis_exploratory_2026-11-01

Agreement (Amendment 11 section 6): the automatic class of each sampled wrong answer (wrong_in_context / wrong_not_in_context)
against the author-checked label; N = unsupported, S and C = supported (Amendment 5); X rows (refusals; DEVIATION_LOG.md
2026-11-01) are reported separately and left out of the S/C/N agreement.

Exploratory (the pre-registered classes, scores and P1-P5 verdicts in outputs/edgar_analysis_2026-11-01 are unchanged):
  a. refusal rule: an answer matching REFUSAL (it states that the evidence does not contain the figure) is `abstained`;
     accuracy, abstained and wrong_not_in_context by mode and breadth; P3 and P4 recomputed as analyze_edgar does.
  b. scale-aware scoring: answer and gold number (verify_questions.first_number) compared after applying their scale words
     (thousand, million, billion) with the primary rule's tolerance (rel 1 %, abs 1e-9); every pair whose result changes.
  c. pairs whose prompt held 0 passages, by mode and breadth.
  d. wrong-source / wrong-year S rows of the label sample, counted from the author's notes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.paired_stats import mcnemar_exact
from src.phase_d_validation.scoring import ABS_TOL, REL_TOL
from src.phase_f_edgar import session_tools as S
from src.phase_f_edgar.analyze_edgar import ANSWERS, cluster_boot
from src.phase_f_edgar.compare_edgar import BREADTHS, MODES
from src.phase_f_edgar.verify_questions import first_number, number_in_text

SCORED = "outputs/edgar_analysis_2026-11-01/answers_scored.csv"
KEY = "outputs/edgar_analysis_2026-11-01/label_key.csv"
LABELS = "outputs/edgar_analysis_labels_joined_2026-11-01/label_sheet_joined.csv"
REFUSAL = re.compile(
    r"\b(?:does|do) not (?:contain|include|provide|mention|specify|state)\b"
    r"|\bno mention of\b"
    r"|\bis not (?:explicitly |directly )?(?:stated|provided|mentioned|available|specified|given|disclosed|contained)\b",
    re.IGNORECASE)
WRONG_SOURCE = re.compile(r"another company|wrong source", re.IGNORECASE)
WRONG_YEAR = re.compile(r"wrong (?:report )?year", re.IGNORECASE)


def is_refusal(raw: str | None) -> bool:
    return bool(raw) and REFUSAL.search(raw) is not None


def refusal_class(cls: str, raw: str | None) -> str:
    """Class under the exploratory refusal rule (a correct answer is never re-classed)."""
    return "abstained" if cls != "correct" and is_refusal(raw) else cls


def scale_correct(raw: str | None, gold_number: str) -> bool:
    """First number of the answer vs the gold number, both with their scale words applied; primary-rule tolerance."""
    a, g = first_number(raw or ""), first_number(gold_number)
    if a is None or g is None:
        return False
    return math.isclose(a.full, g.full, rel_tol=REL_TOL, abs_tol=ABS_TOL)


def scale_class(cls: str, raw: str | None, gold_number: str, passages: list[str]) -> str:
    if cls == "abstained":
        return cls
    if scale_correct(raw, gold_number):
        return "correct"
    n = first_number(raw)
    return "wrong_in_context" if any(number_in_text(n, t) for t in passages) else "wrong_not_in_context"


def agreement(rows: list[dict]) -> dict:
    """rows: {proxy_class, label}. Confusion of proxy class x label; agreement over S/C/N rows (N <-> wrong_not_in_context)."""
    conf = {p: Counter(r["label"] for r in rows if r["proxy_class"] == p) for p in ("wrong_in_context", "wrong_not_in_context")}
    scn = [r for r in rows if r["label"] in ("S", "C", "N")]
    agree = sum(1 for r in scn if (r["label"] == "N") == (r["proxy_class"] == "wrong_not_in_context"))
    tp = sum(1 for r in scn if r["label"] == "N" and r["proxy_class"] == "wrong_not_in_context")
    n_lab, n_prx = sum(1 for r in scn if r["label"] == "N"), sum(1 for r in scn if r["proxy_class"] == "wrong_not_in_context")
    return {"confusion": {p: {l: c[l] for l in ("S", "C", "N", "X")} for p, c in conf.items()},
            "n_scn": len(scn), "n_x": sum(1 for r in rows if r["label"] == "X"), "agree": agree,
            "agreement": agree / len(scn) if scn else None,
            "N_and_proxy": tp, "N_labels": n_lab, "proxy_wrong_not_in_context": n_prx,
            "share_of_N_flagged_by_proxy": tp / n_lab if n_lab else None,
            "share_of_proxy_labelled_N": tp / n_prx if n_prx else None}


def rates(rows: list[dict], key: str) -> dict:
    n = len(rows)
    c = Counter(r[key] for r in rows)
    return {"n_pairs": n, "accuracy": c["correct"] / n, "abstained": c["abstained"] / n,
            "wrong_in_context": c["wrong_in_context"] / n, "wrong_not_in_context": c["wrong_not_in_context"] / n}


def p3_p4(rows: list[dict], key: str) -> dict:
    """P3 (exact McNemar router vs default_hnsw, pass 1) and P4 (wrong_not_in_context difference, cluster bootstrap)."""
    by = {(r["pair_id"], r["mode"]): r for r in rows if int(r["pass"]) == 1}
    pairs = sorted({p for p, _ in by})
    ok = lambda p, m: by[(p, m)][key] == "correct"
    b = sum(1 for p in pairs if ok(p, "router") and not ok(p, "default_hnsw"))
    c = sum(1 for p in pairs if not ok(p, "router") and ok(p, "default_hnsw"))
    pv = mcnemar_exact(b, c)
    per_q = defaultdict(lambda: ([], []))
    for p in pairs:
        q = by[(p, "router")]["qid"]
        per_q[q][0].append(float(by[(p, "router")][key] == "wrong_not_in_context"))
        per_q[q][1].append(float(by[(p, "default_hnsw")][key] == "wrong_not_in_context"))
    mean = lambda gs, i: statistics.fmean(v for g in gs for v in g[i])
    diff = lambda gs: mean(gs, 0) - mean(gs, 1)
    lo, hi = cluster_boot(dict(per_q), diff)
    est = diff(list(per_q.values()))
    return {"P3": {"b_router_only": b, "c_default_hnsw_only": c, "p_exact_mcnemar": pv, "held": pv < 0.05 and b > c,
                   "router_correct": sum(ok(p, "router") for p in pairs), "default_hnsw_correct": sum(ok(p, "default_hnsw") for p in pairs)},
            "P4": {"router_minus_default_hnsw_wrong_not_in_context": est, "ci95": [lo, hi], "held": est < 0,
                   "router_rate": mean(per_q.values(), 0), "default_hnsw_rate": mean(per_q.values(), 1)}}


def by_mode_breadth(rows: list[dict], key: str, prefix: str) -> list[dict]:
    out = []
    for m in MODES:
        for b in ("all",) + BREADTHS:
            rs = [r for r in rows if r["mode"] == m and (b == "all" or r["breadth"] == b)]
            out.append({"mode": m, "breadth": b, **{f"{prefix}{k}" if k != "n_pairs" else k: (round(v, 4) if k != "n_pairs" else v)
                                                     for k, v in rates(rs, key).items()}})
    return out


def write_csv(path, data):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(data[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    rd = lambda p: list(csv.DictReader(open(PROJECT_ROOT / p, encoding="utf-8", newline="")))
    rows = rd(SCORED)
    prompts = {json.loads(ln)["prompt_id"]: json.loads(ln)
               for ln in (PROJECT_ROOT / ANSWERS / "prompts.jsonl").read_text(encoding="utf-8").splitlines()}

    # ---- agreement
    key = {r["sample_id"]: r for r in rd(KEY)}
    labels = rd(LABELS)
    lab_rows = [{"sample_id": l["sample_id"], "mode": key[l["sample_id"]]["mode"], "proxy_class": key[l["sample_id"]]["proxy_class"],
                 "label": l["author_label"], "drafted_label": l["drafted_label"]} for l in labels]
    agr = {"all": agreement(lab_rows), **{m: agreement([r for r in lab_rows if r["mode"] == m]) for m in ("router", "default_hnsw")},
           "changed_from_draft": [(r["sample_id"], r["drafted_label"], r["label"]) for r in lab_rows if r["drafted_label"] != r["label"]]}
    S.write_json(out / "agreement.json", agr)
    write_csv(out / "agreement_rows.csv", lab_rows)

    # ---- passages (read-only) for the scale re-score
    ids = sorted({i for p in prompts.values() for i in p["passage_ids"]})
    conn = psycopg2.connect(**db_settings())
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SELECT id, text FROM edgar_chunks WHERE id = ANY(%s)", (ids,))
        text = dict(cur.fetchall())
    for r in rows:
        r["refusal"] = int(is_refusal(r["raw"]))
        r["class_refusal"] = refusal_class(r["class"], r["raw"])
        r["class_scale"] = scale_class(r["class"], r["raw"], r["gold_number"], [text[i] for i in prompts[r["prompt_id"]]["passage_ids"]])
    write_csv(out / "answers_exploratory.csv", [{k: r[k] for k in ("pair_id", "qid", "breadth", "mode", "pass", "prompt_id", "class",
                                                                      "refusal", "class_refusal", "class_scale", "answer_span",
                                                                      "gold_number", "n_passages", "raw")} for r in rows])

    # ---- a. refusal rule
    pre = by_mode_breadth(rows, "class", "pre_")
    ref = by_mode_breadth(rows, "class_refusal", "ref_")
    write_csv(out / "refusal_by_mode_breadth.csv", [{**p, **{k: v for k, v in r.items() if k.startswith("ref_")}} for p, r in zip(pre, ref)])
    refusal = {"rule": REFUSAL.pattern, "refusal_answers": sum(r["refusal"] for r in rows),
               "refusal_by_primary_class": dict(Counter(r["class"] for r in rows if r["refusal"])),
               "distinct_refusal_prompts": len({r["prompt_id"] for r in rows if r["refusal"]}),
               "primary": p3_p4(rows, "class"), "refusal_rule": p3_p4(rows, "class_refusal")}
    S.write_json(out / "refusal_rescore.json", refusal)

    # ---- b. scale-aware
    changes = [{k: r[k] for k in ("pair_id", "mode", "breadth", "class", "class_scale", "answer_span", "gold_number", "raw")}
               for r in rows if (r["class"] == "correct") != (r["class_scale"] == "correct")]
    write_csv(out / "scale_changes.csv", changes or [{"pair_id": ""}])
    scale = {"changed_answers": len(changes), "to_correct": sum(1 for c in changes if c["class_scale"] == "correct"),
             "to_wrong": sum(1 for c in changes if c["class"] == "correct"),
             "changes_by_mode": dict(Counter(c["mode"] for c in changes)),
             "distinct_answer_gold": sorted({(c["answer_span"], c["gold_number"], c["class"], c["class_scale"]) for c in changes}),
             "accuracy_by_mode": {m: {"primary": rates([r for r in rows if r["mode"] == m], "class")["accuracy"],
                                      "scale_aware": rates([r for r in rows if r["mode"] == m], "class_scale")["accuracy"]} for m in MODES},
             "scale_aware": p3_p4(rows, "class_scale")}
    S.write_json(out / "scale_rescore.json", scale)

    # ---- c. zero passages
    zero = []
    for m in MODES:
        for b in ("all",) + BREADTHS:
            rs = [r for r in rows if r["mode"] == m and (b == "all" or r["breadth"] == b)]
            z = [r for r in rs if int(r["n_passages"]) == 0]
            zero.append({"mode": m, "breadth": b, "n_pairs": len(rs), "zero_passage_pairs": len(z),
                         "gave_number": sum(1 for r in z if r["class"] != "abstained"),
                         "abstained_primary": sum(1 for r in z if r["class"] == "abstained"),
                         "refusal": sum(r["refusal"] for r in z), "correct": sum(1 for r in z if r["class"] == "correct")})
    write_csv(out / "zero_passages.csv", zero)

    # ---- d. wrong-source / wrong-year S rows from the author notes
    src_rows = [{"sample_id": l["sample_id"], "label": l["author_label"], "mode": key[l["sample_id"]]["mode"],
                 "wrong_source": bool(WRONG_SOURCE.search(l["author_note"])), "wrong_year": bool(WRONG_YEAR.search(l["author_note"])),
                 "author_note": l["author_note"]} for l in labels]
    s_rows = [r for r in src_rows if r["label"] == "S"]
    S.write_json(out / "label_error_sources.json", {
        "S_rows": len(s_rows), "S_wrong_source": [r["sample_id"] for r in s_rows if r["wrong_source"]],
        "S_wrong_year": [r["sample_id"] for r in s_rows if r["wrong_year"]],
        "other_labels_mentioning_wrong_source_or_year": [(r["sample_id"], r["label"]) for r in src_rows
                                                         if r["label"] != "S" and (r["wrong_source"] or r["wrong_year"] or "another company" in r["author_note"])],
        "rows": src_rows})
    print(json.dumps({"agreement": agr["all"], "refusal": {k: refusal[k] for k in ("refusal_answers", "refusal_by_primary_class")},
                      "scale": {k: scale[k] for k in ("changed_answers", "to_correct", "to_wrong")}}, indent=1))


if __name__ == "__main__":
    main()
