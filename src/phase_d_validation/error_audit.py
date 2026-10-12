"""Error audit for individual FinQA queries (no LLM call): question, gold answer, FinQA program and its executed result,
gold evidence (FinQA text vs DB row), whether each gold passage was in the k=15 exact-route prompt of a given run, and the
answers of several runs. Read-only.

  python -m src.phase_d_validation.error_audit --out outputs/error_audit_2026-10-12/error_audit.md ID [ID ...]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import psycopg2

from src import db_settings

RUNS = {
    "30 Sept qwen (corrected file) DM": ("outputs/phase_d_results_ollama_corrected.jsonl", "legacy"),
    "12 Oct qwen nomic k=6, DM, pass 1": ("outputs/phase_d_local_2026-10-12/results.jsonl", "decision_matrix", 1),
    "v3 qwen Amendment 1, DM, pass 1": ("outputs/phase_d_local_2026-10-12_v3/results.jsonl", "decision_matrix", 1),
    "v3 qwen Amendment 1, DM, pass 2": ("outputs/phase_d_local_2026-10-12_v3/results.jsonl", "decision_matrix", 2),
    "Gemini pilot, DM": ("outputs/phase_d_gemini_pilot_2026-10-12/results.jsonl", "decision_matrix", 1),
    "Gemini pilot, policy_v2": ("outputs/phase_d_gemini_pilot_2026-10-12/results.jsonl", "policy_v2", 1),
    "Gemini pilot, naive_llm": ("outputs/phase_d_gemini_pilot_2026-10-12/results.jsonl", "naive_llm", 1),
}
PROMPT_RUN = ("outputs/phase_d_local_2026-10-12_v3/results.jsonl", "decision_matrix", 1)


def first_number(cell: str) -> float:
    m = re.search(r"-?\d[\d,]*\.?\d*", cell.replace("$ ", "$"))
    return float(m.group(0).replace(",", ""))


def execute(program: str, ex: dict) -> float:
    """Execute the (single-step) FinQA programs of the audited queries: add(a, b) and table_sum(row, none)."""
    m = re.fullmatch(r"add\(([^,]+), ([^)]+)\)", program)
    if m:
        return float(m.group(1)) + float(m.group(2))
    m = re.fullmatch(r"table_sum\((.+), none\)", program)
    if m:
        rows = [r for r in ex["table"] if r and r[0] == m.group(1)]
        return sum(first_number(c) for c in rows[0][1:])
    raise NotImplementedError(program)


def load_rows(spec, qid):
    path, arm, *rest = spec
    if arm == "legacy":
        for ln in open(path, encoding="utf-8"):
            r = json.loads(ln)
            if r["id"] == qid:
                return r["dm_answer"]
        return None
    for ln in open(path, encoding="utf-8"):
        r = json.loads(ln)
        if r["query_id"] == qid and r["arm"] == arm and r["pass"] == rest[0]:
            return r
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("ids", nargs="+")
    a = ap.parse_args()
    data = {e["id"]: e for e in json.loads(Path("data/raw/finqa_test.json").read_text(encoding="utf-8"))}
    conn = psycopg2.connect(**db_settings())
    cur = conn.cursor()
    o = ["# Error audit (no LLM calls)\n"]
    for qid in a.ids:
        ex = data[qid]
        qa = ex["qa"]
        o.append(f"## {qid}\n\n**Question:** {qa['question']}\n\n**Gold answer:** `{qa['answer']}`; FinQA `exe_ans` = `{qa['exe_ans']}`; **gold program:** `{qa['program']}`; steps: `{qa['steps']}`\n")
        res = execute(qa["program"], ex)
        ok = abs(res - float(qa["exe_ans"])) < 1e-9 and abs(res - float(qa["answer"].replace("%", "").replace(",", ""))) < 1e-9
        o.append(f"**Program executed here:** {res:g}. Equals FinQA `exe_ans` and the gold answer string: **{ok}**.\n")
        pr = load_rows(PROMPT_RUN, qid)
        cur.execute("SELECT id, evidence_key, content, md5(content) FROM finqa_evidence_qwen3 WHERE id = ANY(%s)", (pr["retrieved_ids"],))
        prompt_rows = {r[0]: r for r in cur.fetchall()}
        prompt_md5 = {r[3] for r in prompt_rows.values()}
        o.append("**Gold evidence** (FinQA `gold_inds` text; the DB row the pipeline stores; presence in the k = 15 exact-route prompt):\n")
        for key, txt in qa["gold_inds"].items():
            cur.execute("SELECT id, content, md5(content) FROM finqa_evidence_qwen3 WHERE query_id = %s AND evidence_key = %s", (qid, key))
            rid, content, m5 = cur.fetchone()
            i = int(key.split("_")[1])
            if key.startswith("text_"):
                raw = (ex["pre_text"] + ex["post_text"])[i]
                match = raw.strip() == content.strip()
                how = "raw FinQA text[index] == DB content"
            else:
                raw = " | ".join(map(str, ex["table"][i]))
                match = raw == content
                how = 'raw table row joined with " | " == DB content'
            o.append(f"- `{key}` (DB row id {rid}). FinQA gold_inds text: *{txt}* \n  DB content: `{content}`\n  Key mapping check ({how}): **{match}**. In the k = 15 prompt (by passage text): **{m5 in prompt_md5}**.\n")
        o.append("**Evidence rows in the k = 15 exact-route prompt** (v3, decision_matrix, pass 1), in prompt order:\n")
        for rid in pr["retrieved_ids"]:
            r = prompt_rows[rid]
            o.append(f"{pr['retrieved_ids'].index(rid) + 1}. `{r[1]}` (id {rid}): {r[2][:170]}")
        o.append("\n**Answers given:**\n")
        for name, spec in RUNS.items():
            r = load_rows(spec, qid)
            raw = r if isinstance(r, str) else (r["raw_output"] if r else None)
            o.append(f"- {name}: `{raw}`")
        o.append("")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(o), encoding="utf-8")
    print("\n".join(o))


if __name__ == "__main__":
    main()
