"""Phase F question verification (Task 1): automatic checks A-F on the 60 drafted candidates, one row per candidate.
No routing-mode comparison and no answer evaluation is run. Paid steps (question embeddings, gpt-oss-120b re-answers) need
--allow-paid; --budget-usd (at most 0.50) caps both together.

  python -m src.phase_f_edgar.verify_questions --allow-paid --budget-usd 0.5 \
      --candidates outputs/edgar_questions_draft_2026-10-31/candidates.csv --out-dir outputs/edgar_questions_verify_2026-11-01

A number_in_chunk (lookup only): the drafted answer's first number, normalised ($, commas, %/percent, "(x)" = -x, a trailing
  thousand/million/billion), equals a number in the gold chunk, either as written or after applying both sides' scale words.
  A percent answer only matches a percent in the text, and a non-percent answer only a non-percent.
B independent_answer: gpt-oss-120b on Vertex (Amendment 8 endpoint, temperature 0, max_tokens 4096, one attempt) answers from
  the gold chunk alone. The number span (sign, $, number, %, scale word) is cut from both answers and scored with
  src.phase_d_validation.scoring.score_answer(rule="primary") (Amendment 2: scale word stripped without rescaling).
  "not answerable", no number in the reply, or a call error = N.
C company_match: the question names company_name (legal-form words ignored), or that name appears in the gold chunk or in
  section 1 of the same report (cik, fiscal_year); both sub-results are recorded. subsidiary_flag: in section 1 or the gold
  chunk, the name is followed by "(is a ...) subsidiary of" or preceded by "subsidiary/subsidiaries" in the same sentence.
D retrievable at four breadths: question embedded with the Amendment 1 query recipe (qwen3_query instruct prefix,
  qwen/qwen3-embedding-8b, dimensions=1024); exact search (enable_indexscan = off; EXPLAIN must not use the HNSW index),
  ORDER BY embedding <-> q, id LIMIT 15; gold = every row with the gold chunk's text_hash that passes the filter.
E generic_fact: Y if >= 5 chunks under the drafted filter, other than gold-text chunks, contain the drafted number (rule A).
F alt_source: chunks of the same cik (any year, section), other than gold-text chunks, that contain the drafted number.
status = auto_pass if (A = Y or B = Y) and C = Y and D(cik+year+section) = Y and no subsidiary flag and E = N.

Writes checks.csv, question_embeddings.json, filters.json, judge_calls.jsonl, api_calls_embeddings.jsonl, prompt_independent.json,
run_meta.json (all UTF-8, LF).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src import PROJECT_ROOT
from src.phase_d_validation.scoring import score_answer

# ---------------------------------------------------------------- numbers

_SPAN = re.compile(
    r"(?P<lp>\()?\s?(?P<neg>[-−])?\s?(?P<dol>\$)?\s?(?P<lp2>\()?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
    r"(?P<rp>\s?\))?(?:\s?(?P<pct>%|percent\b))?(?:\s?(?P<scale>thousand|million|billion)\b)?", re.IGNORECASE)
_MULT = {"thousand": 1e3, "million": 1e6, "billion": 1e9}


@dataclass(frozen=True)
class Num:
    raw: float          # signed value as written, scale word not applied
    full: float         # raw x scale word
    pct: bool
    scaled: bool
    span: str           # canonical text for the deterministic scorer, e.g. "-$3.9 million", "12%"


def _to_num(m: re.Match) -> Num:
    v = float(m["num"].replace(",", ""))
    neg = bool(m["neg"]) or bool((m["lp"] or m["lp2"]) and m["rp"])
    v = -v if neg else v
    scale = (m["scale"] or "").lower()
    pct = bool(m["pct"])
    span = f"{'-' if neg else ''}{'$' if m['dol'] else ''}{m['num']}{'%' if pct else ''}{' ' + scale if scale else ''}"
    return Num(v, v * _MULT.get(scale, 1.0), pct, bool(scale), span)


def first_number(text: str) -> Num | None:
    m = _SPAN.search(text or "")
    return _to_num(m) if m else None


def numbers_in(text: str) -> list[Num]:
    return [_to_num(m) for m in _SPAN.finditer(text or "")]


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def num_matches(a: Num, c: Num) -> bool:
    if a.pct != c.pct:
        return False
    return _close(a.raw, c.raw) or ((a.scaled or c.scaled) and _close(a.full, c.full))


def number_in_text(a: Num, text: str) -> bool:
    return any(num_matches(a, c) for c in numbers_in(text))


def _fmt(x: float) -> str:
    x = abs(x)
    return str(int(round(x))) if _close(x, round(x)) else f"{x:.6f}".rstrip("0").rstrip(".")


def like_patterns(a: Num) -> list[str]:
    """Superset prefilter for SQL (applied to text with commas removed): any text that rule A can match contains one of these."""
    forms = {_fmt(a.raw)} | {_fmt(a.full / d) for d in (1, 1e3, 1e6, 1e9)}
    forms = {f.lstrip("0") if f.startswith("0.") else f for f in forms}   # "0.5" may be written ".5"
    return sorted(f"%{f}%" for f in forms if f)


# ---------------------------------------------------------------- company names

_LEGAL = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "lp", "plc", "the", "sa", "nv", "ag"}


def norm_words(text: str) -> list[str]:
    t = (text or "").lower().replace("�", "'").replace("’", "'").replace("'s", " ")
    return re.findall(r"[a-z0-9&]+", t)


def core_name(name: str) -> list[str]:
    w = norm_words(name)
    while w and w[-1] in _LEGAL:
        w = w[:-1]
    while w and w[0] in _LEGAL:
        w = w[1:]
    return w


def name_in(name_core: list[str], text: str) -> bool:
    if not name_core:
        return False
    return f" {' '.join(name_core)} " in f" {' '.join(norm_words(text))} "


def _name_regex(name_core: list[str]) -> re.Pattern:
    return re.compile(r"\b" + r"[\W_]+".join(re.escape(w) for w in name_core) + r"\b", re.IGNORECASE)


# "<name> is/became a (wholly owned) (bank) subsidiary" or "<name>, a/our/its ... subsidiary"; "subsidiary(,) <name>".
# "subsidiaries of <name>" and "<name> and its subsidiaries" describe a parent and are not flagged.
_SUB_AFTER = re.compile(r"^\s*(?:\([^)]{0,60}\)\s*)?,?\s*(?:(?:is|became)\s+(?:a|an|the)|,?\s*(?:a|an|our|its|the))\s+"
                        r"(?:[\w-]+\s+){0,3}?subsidiary\b", re.IGNORECASE)
_SUB_BEFORE = re.compile(r"\bsubsidiar(?:y|ies)\b\s*[,:]?\s*(?:the\s+)?[“\"]?$", re.IGNORECASE)


def subsidiary_evidence(name_core: list[str], texts: list[str]) -> str:
    """First sentence fragment where the name is described as a subsidiary, or ''."""
    if not name_core:
        return ""
    rx = _name_regex(name_core)
    for t in texts:
        t = (t or "").replace("�", "'")
        for m in rx.finditer(t):
            nxt = re.match(r"\s*([A-Z][\w&-]*)", t[m.end():])
            if nxt and nxt.group(1).lower() not in _LEGAL:
                continue                     # part of a longer name ("ACNB Bank", "Unitil Power"): another entity
            after = re.sub(r"^(?:,?\s*(?:inc|incorporated|corp|corporation|co|company|ltd|llc|lp|plc)\b\.?)+", "", t[m.end():m.end() + 120],
                           flags=re.IGNORECASE)
            before = t[max(0, m.start() - 60):m.start()]
            if _SUB_BEFORE.search(before) or _SUB_AFTER.search(after):
                return re.sub(r"\s+", " ", t[max(0, m.start() - 60):m.end() + 100])
    return ""


# ---------------------------------------------------------------- status and filters

BREADTHS = {"cik+year+section": ("cik", "fiscal_year", "section"), "cik+year": ("cik", "fiscal_year"),
            "year+section": ("fiscal_year", "section"), "section": ("section",)}
GENERIC_MIN = 5


def failing_checks(row: dict) -> list[str]:
    out = []
    if not (row["A_number_in_chunk"] == "Y" or row["B_agree"] == "Y"):
        out.append(f"A/B (A={row['A_number_in_chunk']}, B={row['B_agree']})")
    if row["C_company_match"] != "Y":
        out.append("C_company_match")
    if row["C_subsidiary_flag"] == "Y":
        out.append("C_subsidiary_flag")
    if row["D_gold_in_top15_cik+year+section"] != "Y":
        out.append("D_cik+year+section")
    if row["E_generic_fact"] != "N":
        out.append(f"E_generic_fact ({row['E_n_other_chunks']} chunks)")
    return out


def build_filter(meta: dict, breadth: str) -> list:
    return [[col, [meta[col]]] for col in BREADTHS[breadth]]


# ---------------------------------------------------------------- paid clients

JUDGE_MODEL = "openai/gpt-oss-120b-maas"
PROJECT, LOCATION = "bsc-research-project-511410", "us-central1"
BASE_URL = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{LOCATION}/endpoints/openapi"
PRICE_IN, PRICE_OUT = 0.15e-6, 0.60e-6
JUDGE_SETTINGS = {"temperature": 0.0, "max_tokens": 4096}
JUDGE_SYSTEM = ("You answer a question about one excerpt from a company's annual report (Form 10-K). Use only the excerpt. "
                "Reply with a single number and its units (for example: $3.9 million, 12%, 1,500 shares) and nothing else. "
                "If the excerpt does not contain what is needed to answer, reply exactly: not answerable")
JUDGE_USER = "Excerpt:\n\"\"\"\n{text}\n\"\"\"\n\nQuestion: {question}"
BUDGET_MAX = 0.50
EMBED_CAP = 0.05


def judge_verdict(reply: str | None, gold: Num | None) -> tuple[str, str, str]:
    """(agree Y/N, predicted span, reason)."""
    if reply is None:
        return "N", "", "no reply"
    r = reply.strip()
    if re.search(r"not answerable", r, re.IGNORECASE):
        return "N", "", "not answerable"
    p = first_number(r)
    if p is None:
        return "N", "", "no number in reply"
    if gold is None:
        return "N", p.span, "drafted answer has no number"
    s = score_answer(p.span, gold.span, rule="primary")
    return ("Y" if s.correct else "N"), p.span, ("" if s.correct else "different number")


def access_token() -> str:
    gcloud = "gcloud.cmd" if sys.platform == "win32" else "gcloud"
    return subprocess.run([gcloud, "auth", "application-default", "print-access-token"], capture_output=True, text=True,
                          check=True).stdout.strip()


def main():
    import numpy as np
    import psycopg2
    from openai import OpenAI
    from pgvector.psycopg2 import register_vector

    from src import db_settings
    from src.phase_d_validation.embedding_tools import OpenRouterEmbedder, QWEN3_TASK, qwen3_query
    from src.phase_f_edgar import common as C

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--budget-usd", type=float, required=True)
    ap.add_argument("--allow-paid", action="store_true")
    a = ap.parse_args()
    if not a.allow_paid:
        raise SystemExit("question embeddings and gpt-oss-120b answers are paid: needs --allow-paid")
    if a.budget_usd > BUDGET_MAX:
        raise SystemExit(f"budget above the USD {BUDGET_MAX} cap")
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)
    cand_path = PROJECT_ROOT / a.candidates
    cands = list(csv.DictReader(open(cand_path, encoding="utf-8", newline="")))
    if len(cands) != 60:
        raise SystemExit(f"{len(cands)} candidates, expected 60")

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    register_vector(conn)
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {C.TABLE}")
    n_total = cur.fetchone()[0]

    # ---- free checks: A, C, E, F
    rows, metas = [], {}
    for c in cands:
        gold_ids = json.loads(c["gold_chunk_ids"])
        cur.execute(f"SELECT id, cik, company_name, fiscal_year, section, text, text_hash FROM {C.TABLE} WHERE id = ANY(%s) ORDER BY id",
                    (gold_ids,))
        g = cur.fetchall()
        if len(g) != len(gold_ids) or len({x[6] for x in g}) != 1 or g[0][5] != c["gold_chunk_text"]:
            raise SystemExit(f"{c['qid']}: gold ids do not resolve to one text equal to gold_chunk_text")
        _, cik, name, fy, sec, text, h = g[0]
        if (str(fy), sec, name) != (c["fiscal_year"], c["section"], c["company_name"]):
            raise SystemExit(f"{c['qid']}: chunk metadata differs from the candidate row")
        meta = {"cik": cik, "fiscal_year": fy, "section": sec, "text_hash": h}
        metas[c["qid"]] = meta
        num = first_number(c["drafted_answer"])
        in_chunk = number_in_text(num, text) if num else False
        abs_only = (not in_chunk and num is not None and
                    number_in_text(Num(abs(num.raw), abs(num.full), num.pct, num.scaled, num.span), text.replace("(", " ").replace(")", " ")))
        is_lookup = c["type"] == "lookup"
        A = ("Y" if in_chunk else "N") if is_lookup else "n/a"
        old = c["auto_check_answer_number_in_text"]

        core = core_name(name)
        cur.execute(f"SELECT text FROM {C.TABLE} WHERE cik = %s AND fiscal_year = %s AND section = '1' ORDER BY chunk_index", (cik, fy))
        s1 = [x[0] for x in cur.fetchall()]
        q_names = name_in(core, c["question"])
        in_chunk_name = name_in(core, text)
        in_s1 = any(name_in(core, t) for t in s1)
        sub = subsidiary_evidence(core, s1 + [text])

        def count_with_number(where: str, params: list) -> int:
            if num is None:
                return -1
            cur.execute(f"SELECT text FROM {C.TABLE} WHERE {where} AND text_hash <> %s AND replace(text, ',', '') LIKE ANY(%s)",
                        [*params, h, like_patterns(num)])
            return sum(number_in_text(num, t) for (t,) in cur.fetchall())

        dfilt = build_filter(meta, c["filter_breadth"])
        if json.dumps(dfilt) != c["filter"]:
            raise SystemExit(f"{c['qid']}: rebuilt drafted filter {json.dumps(dfilt)} differs from {c['filter']}")
        n_e = count_with_number(" AND ".join(f"{col} = %s" for col, _ in dfilt), [v[0] for _, v in dfilt])
        n_f = count_with_number("cik = %s", [cik])
        rows.append({
            "qid": c["qid"], "type": c["type"], "drafted_breadth": c["filter_breadth"], "drafted_filter": c["filter"],
            "drafted_answer": c["drafted_answer"], "drafted_number": num.span if num else "",
            "A_number_in_chunk": A, "A_number_in_chunk_any_type": "Y" if in_chunk else "N",
            "A_abs_value_only_match": "Y" if abs_only else "N",
            "auto_check_answer_number_in_text": old,
            "A_disagrees_with_auto_check": ("Y" if is_lookup and (A == "Y") != (old == "True") else "N"),
            "C_company_name": name, "C_question_names_company": "Y" if q_names else "N", "C_name_in_chunk": "Y" if in_chunk_name else "N",
            "C_name_in_section1": "Y" if in_s1 else ("N" if s1 else "no section 1"),
            "C_company_match": "Y" if (q_names or in_chunk_name or in_s1) else "N",
            "C_subsidiary_flag": "Y" if sub else "N", "C_subsidiary_evidence": sub,
            "E_n_other_chunks": n_e, "E_generic_fact": ("n/a" if n_e < 0 else ("Y" if n_e >= GENERIC_MIN else "N")),
            "F_alt_source": n_f if n_f >= 0 else "n/a",
        })
        print(f"{c['qid']} A={A} C={rows[-1]['C_company_match']} sub={rows[-1]['C_subsidiary_flag']} E={n_e} F={n_f}", flush=True)

    # ---- D: question embeddings (Amendment 1 query recipe) and exact top-15 at four breadths
    class LFEmbedder(OpenRouterEmbedder):
        def _log(self, rec):
            with self.log_path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(rec) + "\n")

    emb = LFEmbedder(C.EMBED_MODEL, out / "api_calls_embeddings.jsonl", min(EMBED_CAP, a.budget_usd), dimensions=C.EMBED_DIM)
    inputs = [qwen3_query(c["question"]) for c in cands]
    vecs = emb.embed(inputs, "EDGAR candidate questions (Amendment 1 query recipe: qwen3 instruct prefix)")
    if len(vecs) != len(inputs) or any(len(v) != C.EMBED_DIM or not all(map(math.isfinite, v)) or not any(v) for v in vecs):
        raise SystemExit("bad question embeddings (count, dimension, non-finite or zero)")
    norms = [float(np.linalg.norm(v)) for v in vecs]
    (out / "question_embeddings.json").write_text(json.dumps({
        "model": C.EMBED_MODEL, "dimension": C.EMBED_DIM, "variant": "qwen3", "query_task": QWEN3_TASK,
        "input_template": "Instruct: {task}\\nQuery: {question}", "source": "src.phase_d_validation.embedding_tools.qwen3_query",
        "candidates": a.candidates, "candidates_sha256": C.sha256_file(cand_path),
        "queries": [{"query_id": c["qid"], "input_text": t, "input_sha256": hashlib.sha256(t.encode()).hexdigest(), "vector": v}
                    for c, t, v in zip(cands, inputs, vecs)]}), encoding="utf-8", newline="\n")

    filters_out = {}
    for c, r, v in zip(cands, rows, vecs):
        meta, qv = metas[c["qid"]], np.asarray(v, dtype=np.float32)
        per = {}
        for b in BREADTHS:
            f = build_filter(meta, b)
            where = " AND ".join(f"{col} = %s" for col, _ in f)
            params = [x[0] for _, x in f]
            cur.execute(f"SELECT count(*) FROM {C.TABLE} WHERE {where}", params)
            n_match = cur.fetchone()[0]
            cur.execute(f"SELECT id FROM {C.TABLE} WHERE {where} AND text_hash = %s ORDER BY id", [*params, meta["text_hash"]])
            gold = [x[0] for x in cur.fetchall()]
            sql = f"SELECT id, embedding <-> %s AS d FROM {C.TABLE} WHERE {where} ORDER BY d, id LIMIT 15"
            cur.execute("BEGIN")
            cur.execute("SET LOCAL enable_indexscan = off")
            cur.execute("EXPLAIN " + sql, [qv, *params])
            plan = "\n".join(x[0] for x in cur.fetchall())
            if "embedding_idx" in plan or "hnsw" in plan.lower():
                raise SystemExit(f"{c['qid']} {b}: plan uses the HNSW index:\n{plan}")
            cur.execute(sql, [qv, *params])
            top = cur.fetchall()
            cur.execute("COMMIT")
            ranks = [i for i, (rid, _) in enumerate(top, 1) if rid in set(gold)]
            per[b] = {"filter": f, "n_match": n_match, "selectivity": n_match / n_total, "gold_ids": gold,
                      "top15_ids": [x[0] for x in top], "gold_rank": ranks[0] if ranks else None,
                      "plan_node": plan.splitlines()[0].strip() if plan else ""}
            r[f"D_selectivity_{b}"] = n_match / n_total
            r[f"D_gold_in_top15_{b}"] = "Y" if ranks else "N"
            r[f"D_gold_rank_{b}"] = ranks[0] if ranks else ""
        filters_out[c["qid"]] = {"drafted_breadth": c["filter_breadth"], "cik": meta["cik"], "fiscal_year": meta["fiscal_year"],
                                 "section": meta["section"], "gold_text_hash": meta["text_hash"], "breadths": per}
    (out / "filters.json").write_text(json.dumps({"table": C.TABLE, "table_rows": n_total, "k": 15,
                                                  "search": "exact (SET LOCAL enable_indexscan = off; EXPLAIN checked for no HNSW)",
                                                  "questions": filters_out}, indent=1), encoding="utf-8", newline="\n")
    print(f"D done; embedding cost USD {emb.spent:.6f}, {emb.tokens} tokens", flush=True)

    # ---- B: independent answers from gpt-oss-120b (one attempt per question)
    (out / "prompt_independent.json").write_text(json.dumps({"system": JUDGE_SYSTEM, "user_template": JUDGE_USER,
                                                             "model": JUDGE_MODEL, "settings": JUDGE_SETTINGS}, indent=1),
                                                 encoding="utf-8", newline="\n")
    client = OpenAI(base_url=BASE_URL, api_key=access_token(), max_retries=0, timeout=180)
    spent, max_call, errors = emb.spent, 0.0, 0
    with open(out / "judge_calls.jsonl", "w", encoding="utf-8", newline="\n") as fj:
        for c, r in zip(cands, rows):
            if spent + 2 * max(max_call, 0.002) > a.budget_usd:
                raise SystemExit(f"budget: spent USD {spent:.4f}; next call could exceed USD {a.budget_usd}")
            t0 = time.perf_counter()
            rec = {"qid": c["qid"], "utc": datetime.now(timezone.utc).isoformat()}
            reply = None
            try:
                resp = client.chat.completions.create(model=JUDGE_MODEL, messages=[
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": JUDGE_USER.format(text=c["gold_chunk_text"], question=c["question"])}], **JUDGE_SETTINGS)
                u = resp.usage
                cost = (u.prompt_tokens or 0) * PRICE_IN + (u.completion_tokens or 0) * PRICE_OUT
                reply = resp.choices[0].message.content
                rec |= {"input_tokens": u.prompt_tokens, "output_tokens": u.completion_tokens, "cost_usd": cost,
                        "finish_reason": resp.choices[0].finish_reason, "content": reply, "error": None}
                if resp.choices[0].finish_reason == "length":
                    reply, rec["error"] = None, "truncated (finish_reason=length)"
            except Exception as exc:   # one attempt, recorded, counted N
                cost = 0.0
                rec |= {"error": f"{type(exc).__name__}: {exc}"[:1000], "cost_usd": 0.0}
            rec["latency_s"] = round(time.perf_counter() - t0, 2)
            fj.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fj.flush()
            spent += cost
            max_call = max(max_call, cost)
            if rec["error"]:
                errors += 1
                if errors >= 5:
                    raise SystemExit(f"5 independent-answer calls failed; stopping (last: {rec['error']})")
            agree, pspan, why = judge_verdict(reply, first_number(c["drafted_answer"]))
            if rec["error"]:
                why = rec["error"]
            r.update({"B_independent_answer": (reply or "").strip(), "B_independent_number": pspan, "B_agree": agree, "B_reason": why})
            print(f"{c['qid']} B={agree} {pspan!r} vs {r['drafted_number']!r} {why}", flush=True)

    for r in rows:
        f = failing_checks(r)
        r["status"] = "needs_review" if f else "auto_pass"
        r["failing_checks"] = "; ".join(f)
    fields = ["qid", "type", "drafted_breadth", "status", "failing_checks", "drafted_answer", "drafted_number",
              "A_number_in_chunk", "A_number_in_chunk_any_type", "A_abs_value_only_match", "auto_check_answer_number_in_text",
              "A_disagrees_with_auto_check", "B_independent_answer", "B_independent_number", "B_agree", "B_reason",
              "C_company_name", "C_question_names_company", "C_name_in_chunk", "C_name_in_section1", "C_company_match",
              "C_subsidiary_flag", "C_subsidiary_evidence"] + \
             [f"D_{k}_{b}" for b in BREADTHS for k in ("selectivity", "gold_in_top15", "gold_rank")] + \
             ["E_n_other_chunks", "E_generic_fact", "F_alt_source", "drafted_filter"]
    with open(out / "checks.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    meta = {"utc": datetime.now(timezone.utc).isoformat(), "candidates": a.candidates, "candidates_sha256": C.sha256_file(cand_path),
            "table_rows": n_total, "embedding": {"model": C.EMBED_MODEL, "dimensions": C.EMBED_DIM, "query_task": QWEN3_TASK,
                                                 "tokens": emb.tokens, "cost_usd": emb.spent, "norm_min": min(norms), "norm_max": max(norms)},
            "judge": {"model": JUDGE_MODEL, "base_url": BASE_URL, "settings": JUDGE_SETTINGS, "client_max_retries": 0,
                      "price_per_token": [PRICE_IN, PRICE_OUT], "errors": errors},
            "cost_usd_total": spent, "budget_usd": a.budget_usd,
            "status_counts": {s: sum(r["status"] == s for r in rows) for s in ("auto_pass", "needs_review")}}
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
