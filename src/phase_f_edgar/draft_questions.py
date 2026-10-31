"""Task 4 (Phase F): draft ~60 candidate questions over edgar_chunks with Gemini 3.8 Flash (paid; needs --allow-paid).
No retrieval and no answer evaluation is run with these questions.

  python -m src.phase_f_edgar.draft_questions --allow-paid --budget-usd 0.5 --out-dir outputs/edgar_questions_draft_2026-10-31

- 15 candidates per filter breadth: cik+year+section, cik+year, year+section, section.
- Gold chunk: seeded (seed "20261031-questions") over chunks that contain at least MIN_NUMBERS financial numbers, from
  companies with a non-null company_name, one candidate per company. The filter is built from the gold chunk's metadata
  at the given breadth, so the gold chunk always satisfies it; filter_selectivity = exact count / table rows.
- The model drafts question, answer and type (lookup = number appears in the text; calculation = computed from numbers
  in the text). The question always names the company and the fiscal year, whatever the filter breadth.
- gemini-3.8-flash via src.phase_d_validation.llm_client (Vertex, ADC), temperature 0, thinking LOW, JSON mode,
  2,048 max output tokens; model version recorded from each response.
Writes candidates.csv (UTF-8, LF line endings), responses.jsonl, prompt.json, run_meta.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
from datetime import datetime, timezone

import psycopg2

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.llm_client import PaidLockError, VertexGeminiBackend, load_generation_config, make_client
from src.phase_f_edgar import common as C

MODEL = "gemini-3.8-flash"
MAX_OUT = 2048
PER_BREADTH = 15
BREADTHS = {"cik+year+section": ("cik", "fiscal_year", "section"), "cik+year": ("cik", "fiscal_year"),
            "year+section": ("fiscal_year", "section"), "section": ("section",)}
MIN_NUMBERS = 3
NUMBER = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:%|percent\b|million\b|billion\b|thousand\b)")
SECTION_NAMES = {"1": "Item 1 (Business)", "1A": "Item 1A (Risk Factors)", "7": "Item 7 (Management's Discussion and Analysis)",
                 "7A": "Item 7A (Quantitative and Qualitative Disclosures About Market Risk)",
                 "8": "Item 8 (Financial Statements and Supplementary Data)"}

SYSTEM = ("You write evaluation questions for a retrieval system over excerpts of US companies' annual reports (Form 10-K). "
          "You are given one excerpt and its metadata. Write ONE question whose answer is a single number that is either stated "
          "in the excerpt or can be computed from numbers stated in the excerpt.\n"
          "Rules:\n"
          "- The question must name the company and the fiscal year given in the metadata, so it can be understood without the excerpt.\n"
          "- Paraphrase: do not copy phrases from the excerpt; use your own wording for the quantity asked about.\n"
          "- Use only information in the excerpt. Do not use outside knowledge.\n"
          "- The answer is one number with its unit or scale (for example \"$12.4 million\", \"7.5%\", \"1,250 employees\").\n"
          "- type is \"lookup\" if the answer number appears in the excerpt, or \"calculation\" if it must be computed from numbers "
          "in the excerpt (for example a difference, sum, ratio or percentage change); for a calculation, state the computation in basis.\n"
          "- Avoid questions whose answer depends on the date of the report itself or on page numbers.\n"
          "Reply with JSON only: {\"question\": str, \"answer\": str, \"type\": \"lookup\" | \"calculation\", \"basis\": str}. "
          "basis is one short sentence naming the numbers used.")
USER_TEMPLATE = ("Company: {company}\nCIK: {cik}\nFiscal year (as labelled in the corpus): {fiscal_year}\nSection: {section_name}\n\n"
                 "Excerpt:\n\"\"\"\n{text}\n\"\"\"")
FIELDS = ["qid", "question", "filter", "filter_breadth", "filter_selectivity", "gold_chunk_ids", "gold_chunk_text", "drafted_answer",
          "type", "company_name", "fiscal_year", "section", "auto_check_answer_number_in_text", "keep", "corrected_answer",
          "corrected_type", "note"]


class _Recorder:
    """Pass-through to the google-genai client that keeps the last response (for its model_version)."""

    def __init__(self, client):
        self._c, self.last = client, None
        self.models = self

    def generate_content(self, **kw):
        self.last = self._c.models.generate_content(**kw)
        return self.last


def number_in_text(answer: str, text: str) -> bool:
    nums = re.findall(r"\d[\d,]*(?:\.\d+)?", answer or "")
    flat = text.replace(",", "")
    return bool(nums) and all(n.replace(",", "") in flat for n in nums)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--budget-usd", type=float, required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    if not a.allow_paid:
        raise SystemExit("paid model calls need --allow-paid")
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)

    conn = psycopg2.connect(**db_settings())
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {C.TABLE}")
    n_total = cur.fetchone()[0]
    cur.execute(f"SELECT id, cik, company_name, fiscal_year, section, text, text_hash FROM {C.TABLE} "
                f"WHERE company_name IS NOT NULL ORDER BY id")
    pool = [r for r in cur.fetchall() if len(NUMBER.findall(r[5])) >= MIN_NUMBERS]
    rng = random.Random(f"{C.SEED}-questions")
    rng.shuffle(pool)
    picks, used_cik = [], set()
    plan = [b for b in BREADTHS for _ in range(PER_BREADTH)]
    for r in pool:
        if len(picks) == len(plan):
            break
        if r[1] in used_cik:
            continue
        used_cik.add(r[1])
        picks.append(r)
    if len(picks) < len(plan):
        raise SystemExit(f"only {len(picks)} eligible chunks from distinct companies")

    for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        if os.environ.get(var):
            raise PaidLockError(f"{var} is set: Vertex must use Application Default Credentials")
    cfg = load_generation_config()["models"][MODEL]
    from google import genai
    rec = _Recorder(genai.Client(vertexai=True, project=cfg["project"], location=cfg["location"],
                                 http_options=VertexGeminiBackend.http_options()))
    client = make_client(MODEL, allow_paid=True, budget_usd=a.budget_usd, genai_client=rec)
    (out / "prompt.json").write_text(json.dumps({"system": SYSTEM, "user_template": USER_TEMPLATE}, indent=1), encoding="utf-8", newline="\n")

    rows, versions = [], set()
    with open(out / "responses.jsonl", "w", encoding="utf-8", newline="\n") as fr:
        for i, (breadth, r) in enumerate(zip(plan, picks), 1):
            cid, cik, name, fy, sec, text, h = r
            filt = [[col, [{"cik": cik, "fiscal_year": fy, "section": sec}[col]]] for col in BREADTHS[breadth]]
            where = " AND ".join(f"{col} = %s" for col, _ in filt)
            cur.execute(f"SELECT count(*) FROM {C.TABLE} WHERE {where}", [v[0] for _, v in filt])
            n_match = cur.fetchone()[0]
            cur.execute(f"SELECT id FROM {C.TABLE} WHERE text_hash = %s AND {where} ORDER BY id", [h, *[v[0] for _, v in filt]])
            gold_ids = [x[0] for x in cur.fetchall()]
            user = USER_TEMPLATE.format(company=name, cik=cik, fiscal_year=fy, section_name=SECTION_NAMES[sec], text=text)
            resp = client.generate(SYSTEM, user, max_output_tokens=MAX_OUT, json_mode=True)
            version = getattr(rec.last, "model_version", None)
            versions.add(version)
            fr.write(json.dumps({"qid": f"edgar_q{i:03d}", "chunk_id": cid, "model_version": version, "text": resp.text,
                                 "finish_reason": resp.finish_reason, "input_tokens": resp.input_tokens,
                                 "output_tokens": resp.output_tokens, "thinking_tokens": resp.thinking_tokens,
                                 "cost_usd": resp.cost_usd, "latency_ms": resp.latency_ms}) + "\n")
            try:
                d = json.loads(resp.text)
            except json.JSONDecodeError as e:
                raise SystemExit(f"edgar_q{i:03d}: response is not JSON ({e}); stopping") from e
            if d.get("type") not in ("lookup", "calculation") or not d.get("question") or not d.get("answer"):
                raise SystemExit(f"edgar_q{i:03d}: response misses question/answer/type: {resp.text[:300]}")
            rows.append({"qid": f"edgar_q{i:03d}", "question": d["question"].strip(), "filter": json.dumps(filt),
                         "filter_breadth": breadth, "filter_selectivity": n_match / n_total, "gold_chunk_ids": json.dumps(gold_ids),
                         "gold_chunk_text": text, "drafted_answer": d["answer"].strip(), "type": d["type"],
                         "company_name": name, "fiscal_year": fy, "section": sec,
                         "auto_check_answer_number_in_text": number_in_text(d["answer"], text),
                         "keep": "", "corrected_answer": "", "corrected_type": "", "note": ""})
            print(f"{i}/{len(plan)} {breadth} s={n_match / n_total:.5f} {d['type']} ${client.spent_usd:.4f}", flush=True)
    conn.close()
    with open(out / "candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    raw = (out / "candidates.csv").read_bytes()
    meta = {"utc_end": datetime.now(timezone.utc).isoformat(), "model": MODEL, "model_id": cfg["model_id"],
            "model_versions_reported": sorted(v for v in versions if v), "temperature": cfg["temperature"],
            "thinking": cfg["thinking"], "max_output_tokens": MAX_OUT, "json_mode": True, "location": cfg["location"],
            "seed": f"{C.SEED}-questions", "min_numbers_in_chunk": MIN_NUMBERS, "eligible_chunks": len(pool),
            "table_rows": n_total, "candidates": len(rows), "per_breadth": PER_BREADTH, "cost_usd": client.spent_usd,
            "budget_usd": a.budget_usd, "types": {t: sum(r["type"] == t for r in rows) for t in ("lookup", "calculation")},
            "candidates_csv_line_endings": "LF" if b"\r\n" not in raw else "CRLF present",
            "note": "No retrieval or answer evaluation was run with these questions."}
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
