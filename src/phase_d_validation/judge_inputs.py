"""Amendment 8: build the RAGAS judge inputs for the 1,000 Gemini full-run rows (read-only DB lookup; no model call).

  .venv/Scripts/python -m src.phase_d_validation.judge_inputs --out outputs/ragas_judge_2026-10-23/judge_inputs.jsonl

Per row: user_input = the question, response = raw_output, retrieved_contexts = the retrieved passages exactly as the answer
prompt listed them ("[query_id::evidence_key] content", in retrieved order; router.make_execute_node joins them with "\n", and
RAGAS joins the list with "\n", giving the same text). Passages are read from finqa_evidence_qwen3 by id; each row's stored
evidence keys must match the ids. The 40 labelled rows carry their sample_id and the S/C/N label used in 3c167ba.
"""

from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import subprocess
from pathlib import Path

import psycopg2

from src import db_settings
from src.phase_d_validation.finqa_loader import get_frozen_filepath, load_finqa_subset

RESULTS = "outputs/phase_d_gemini_full_2026-10-12/results.jsonl"
KEY = "outputs/hallucination_classification_2026-10-23/labelling_key.csv"
LABELS = ("3c167ba", "outputs/hallucination_classification_2026-10-23/label_analysis/labelled_rows_joined.csv")
TABLE = "finqa_evidence_qwen3"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists; refusing to overwrite")
    rows = [json.loads(l) for l in open(RESULTS, encoding="utf-8")]
    if len(rows) != 1000:
        raise SystemExit(f"expected 1,000 rows, got {len(rows)}")
    questions = {q["id"]: q["question"] for q in load_finqa_subset(get_frozen_filepath())}
    key = {(k["pass"], k["arm"], k["query_id"]): k for k in csv.DictReader(open(KEY, encoding="utf-8", newline=""))}
    used = subprocess.run(["git", "show", f"{LABELS[0]}:{LABELS[1]}"], capture_output=True, check=True).stdout.decode("utf-8")
    labels = {r["sample_id"]: r for r in csv.DictReader(io.StringIO(used, newline=""))}
    conn = psycopg2.connect(**db_settings())
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    out.parent.mkdir(parents=True, exist_ok=True)
    seen, n_lab = set(), 0
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            rk = (str(r["pass"]), r["arm"], r["query_id"])
            if rk in seen:
                raise SystemExit(f"duplicate row {rk}")
            seen.add(rk)
            ids, keys = (x if isinstance(x, list) else ast.literal_eval(x) for x in (r["retrieved_ids"], r["retrieved_evidence_keys"]))
            if len(ids) != len(keys):
                raise SystemExit(f"{rk}: {len(ids)} ids vs {len(keys)} keys")
            cur.execute(f"SELECT id, query_id, evidence_key, content FROM {TABLE} WHERE id = ANY(%s)", (ids,))
            by = {i: (q, k, c) for i, q, k, c in cur.fetchall()}
            ctx = []
            for i, kk in zip(ids, keys):
                if i not in by or f"{by[i][0]}::{by[i][1]}" != kk:
                    raise SystemExit(f"{rk}: id {i} does not match stored key {kk}")
                ctx.append(f"[{kk}] {by[i][2]}")
            lab = key.get(rk)
            rec = {"pass": int(r["pass"]), "arm": r["arm"], "query_id": r["query_id"], "user_input": questions[r["query_id"]],
                   "response": r["raw_output"], "retrieved_contexts": ctx, "correct": r["correct"], "error": r["error"],
                   "sample_id": lab["sample_id"] if lab else None,
                   "label_scn": labels[lab["sample_id"]]["scn"] if lab else None, "proxy_class": lab["proxy_class"] if lab else None}
            n_lab += bool(lab)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if n_lab != 40:
        raise SystemExit(f"{n_lab} labelled rows matched, expected 40")
    print(f"wrote {len(rows)} rows ({n_lab} labelled) to {out}")


if __name__ == "__main__":
    main()
