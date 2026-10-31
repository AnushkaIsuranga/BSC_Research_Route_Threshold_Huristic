"""Task 2 (Phase F): seeded company sample, section chunking and company names. No database, no paid call.

  python -m src.phase_f_edgar.build_chunks --index outputs/edgar_source_check_2026-10-31/report_index.csv \
      --out-dir outputs/edgar_chunks_2026-10-31

- Companies (CIK) with exactly one report in each of 2018, 2019 and 2020; seeded sample (seed 20261031) of N_COMPANIES.
- Sections 1, 1A, 7, 7A, 8; ~400-token chunks with ~50-token overlap (Qwen3 tokenizer), never across sections.
- company_name: only from an anchored mention in the first 3,000 characters of section 1 (a corporate-suffix name
  followed by a self-reference parenthetical such as (the "Company") or (we, us), by "is/was incorporated|organized|formed",
  or preceded by "refers to / means"); the name is the capitalised tokens before the suffix, cut at heading words.
  Per CIK the name is kept only if the same name (case/punctuation-insensitive) is found in at least 2 of the
  3 years (its latest spelling; a different name in the third year is ignored); otherwise null. Nothing is crawled.
Writes chunks.jsonl (one line per chunk, LF), companies.csv, summary.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from src import PROJECT_ROOT
from src.phase_f_edgar import common as C

N_COMPANIES = 433            # x 3 years = 1,299 reports
NAME_WINDOW = 3000
SUFFIX_TOKENS = {"inc", "inc.", "incorporated", "corporation", "corp", "corp.", "company", "co.", "ltd", "ltd.", "limited", "llc",
                 "l.l.c.", "lp", "l.p.", "plc", "n.v.", "s.a.", "holdings", "holding", "group", "bancorp", "bancshares",
                 "trust", "partners", "bancorporation"}
STOP = {"item", "business", "overview", "general", "development", "corporate", "summary", "description", "introduction",
        "history", "organization", "background", "form", "our", "company", "unless", "in", "this", "annual", "report",
        "the", "about", "operations", "structure", "nature", "profile", "highlights", "explanatory",
        "note", "information", "segment", "segments", "products", "services"}
SUFFIX_RE = (r"(?:Incorporated|Inc\.|Inc\b|Corporation|Corp\.|Corp\b|Company\b|Co\.|Ltd\.|Ltd\b|Limited\b|L\.L\.C\.|LLC\b|"
             r"L\.P\.|LP\b|plc\b|PLC\b|N\.V\.|S\.A\.|Holdings\b|Holding\b|Group\b|Bancorporation\b|Bancorp\b|Bancshares\b|"
             r"Trust\b|Partners\b)")
Q = "[\"'“”‘’�]"
SELF_REF = re.compile(rf"^[^)]{{0,60}}?(?:{Q}\s*(?:the\s+)?(?:Company|Registrant|we|us|our)\b|\bthe\s+Company\b)|^\s*Company\s*\)", re.I)
# anchors: a definition parenthetical, an incorporation sentence, or "refers to / means <Name>"
SUBS = r"(?:,?\s+(?:and|together\s+with)\s+its\s+(?:wholly[- ]owned\s+|consolidated\s+)?subsidiaries,?)?"
ANCHOR_PAREN = re.compile(rf"{SUFFIX_RE}{SUBS}\s*\(")
ANCHOR_VERB = re.compile(rf"{SUFFIX_RE}{SUBS}(?:,\s+an?\s+[A-Za-z ]{{0,30}}?(?:corporation|company),)?\s+(?:is|was)\s+"
                         rf"(?:incorporated|organized|formed|a|an|the)\b")
ANCHOR_REFER = re.compile(rf"\b(?:refers?\s+to|means?)\s+((?:[A-Z0-9][\w&'.\-]*,?\s+){{0,6}}{SUFFIX_RE})")


CONNECTORS = {"and", "of", "&", "de"}
HARD_SUFFIX = {"inc", "inc.", "incorporated", "corp", "corp.", "corporation", "co.", "ltd", "ltd.", "limited", "llc", "l.l.c.",
               "lp", "l.p.", "plc", "n.v.", "s.a."}   # inside a name these end an earlier entity


def walk_back(prefix: str) -> str | None:
    """Name = the capitalised tokens that end `prefix` (which ends with a corporate suffix), stopping at heading words,
    lowercase words or a sentence end; at most 8 tokens, at least 2."""
    toks = prefix.split()
    if not toks or toks[-1].lower().rstrip(",") not in SUFFIX_TOKENS:
        return None
    name = [toks[-1]]
    for t in reversed(toks[:-1][-7:]):
        core = t.rstrip(",")
        if core.lower() in STOP or not (core[:1].isupper() or core[:1].isdigit() or core in CONNECTORS):
            break
        if core.lower() in HARD_SUFFIX:
            break                                   # an earlier entity's suffix ("X Inc. and Y, Inc.")
        if re.match(r"\d+[A-Z]?[.:]", core):
            break                                   # "1.Business" (item heading without a space)
        if core.endswith((".", ":", ")")) and not re.fullmatch(r"(?:[A-Z]\.)+", core):
            break
        name.insert(0, t)
    while name and name[0].rstrip(",") in CONNECTORS:
        name.pop(0)
    name = " ".join(name).strip(" ,")
    return name if len(name.split()) >= 2 else None


def extract_name(section_1: str) -> str | None:
    """Earliest anchored name in the first NAME_WINDOW characters of section 1, or None."""
    s = re.sub(r"\s+", " ", (section_1 or "")[:NAME_WINDOW])
    cands = []
    for m in ANCHOR_PAREN.finditer(s):
        if SELF_REF.search(s[m.end():m.end() + 80]):
            suf = re.match(SUFFIX_RE, s[m.start():]).end()
            cands.append((m.start(), walk_back(s[:m.start() + suf])))
    for m in ANCHOR_VERB.finditer(s):
        suf = re.match(SUFFIX_RE, s[m.start():]).end()
        cands.append((m.start(), walk_back(s[:m.start() + suf])))
    for m in ANCHOR_REFER.finditer(s):
        cands.append((m.start(1), walk_back(m.group(1))))
    cands = sorted(c for c in cands if c[1])
    return cands[0][1] if cands else None


def norm_name(n: str) -> str:
    return re.sub(r"[^a-z0-9]", "", n.lower())


def name_status(found: dict) -> str:
    """'agree' if the same name (case/punctuation-insensitive) was found in at least 2 of the 3 years."""
    if not found:
        return "none_found"
    if majority_name(found):
        return "agree"
    return "single_year" if len(found) == 1 else "conflict"


def majority_name(found: dict) -> str | None:
    """The name found in at least 2 years (its latest spelling), else None."""
    counts = Counter(norm_name(v) for v in found.values())
    key, n = counts.most_common(1)[0] if counts else (None, 0)
    if n < 2:
        return None
    return found[max(y for y, v in found.items() if norm_name(v) == key)]


FILTER_TYPES = {"cik+year+section": ("cik", "fiscal_year", "section"), "cik+year": ("cik", "fiscal_year"),
                "year+section": ("fiscal_year", "section"), "section": ("section",), "year": ("fiscal_year",)}


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]


def selectivity_table(chunks_path: Path, total: int) -> dict:
    """Distribution of s = rows matching / all rows over every distinct value combination of each filter type
    (combinations with zero rows, e.g. an empty section, do not appear)."""
    counts = {k: Counter() for k in FILTER_TYPES}
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            for k, cols in FILTER_TYPES.items():
                counts[k][tuple(r[c] for c in cols)] += 1
    out = {}
    for k, c in counts.items():
        s = [v / total for v in c.values()]
        out[k] = {"n_filters": len(s), "min": min(s), "p10": quantile(s, 0.1), "median": quantile(s, 0.5),
                  "p90": quantile(s, 0.9), "max": max(s), "rows_min": min(c.values()), "rows_median": quantile(list(c.values()), 0.5),
                  "rows_max": max(c.values())}
        if len(c) <= 15:
            out[k]["values"] = {"/".join(map(str, key)): v / total for key, v in sorted(c.items())}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", required=True)
    ap.add_argument("--raw-dir", default=str(C.RAW_DIR))
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    raw, out = Path(a.raw_dir), PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)

    rows = list(csv.DictReader(open(PROJECT_ROOT / a.index, encoding="utf-8")))
    by_cik = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_cik[r["cik"]][int(r["year"])].append(r)
    eligible = sorted(c for c, ys in by_cik.items() if all(len(ys.get(y, [])) == 1 for y in C.YEARS))
    in_all_three = sorted(c for c, ys in by_cik.items() if all(ys.get(y) for y in C.YEARS))
    n = min(N_COMPANIES, len(eligible))
    sample = sorted(random.Random(C.SEED).sample(eligible, n), key=int)

    tok = C.load_tokenizer()
    names, n_chunks = {}, Counter()
    sec_tokens, empty_sections = Counter(), Counter()
    with open(out / "chunks.jsonl", "w", encoding="utf-8", newline="\n") as fo:
        for cik in sample:
            found = {}
            recs = {}
            for y in C.YEARS:
                r = by_cik[cik][y][0]
                recs[y] = (r, C.read_record(raw / r["file"], int(r["offset"])))
                nm = extract_name(recs[y][1].get("section_1"))
                if nm:
                    found[y] = nm
            names[cik] = {"company_name": None, "found": found, "status": name_status(found)}
            if names[cik]["status"] == "agree":
                names[cik]["company_name"] = majority_name(found)
            for y in C.YEARS:
                r, rec = recs[y]
                for s in C.KEEP_SECTIONS:
                    chunks = C.chunk_section(rec.get(f"section_{s}") or "", tok)
                    if not chunks:
                        empty_sections[(y, s)] += 1
                    for i, ch in enumerate(chunks):
                        fo.write(json.dumps({"cik": cik, "company_name": names[cik]["company_name"], "fiscal_year": y,
                                             "section": s, "chunk_index": i, "text": ch["text"], "text_hash": C.text_hash(ch["text"]),
                                             "n_tokens": ch["n_tokens"], "source_filename": r["filename"]}) + "\n")
                        n_chunks[(y, s)] += 1
                        sec_tokens[(y, s)] += ch["n_tokens"]
    with open(out / "companies.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["cik", "company_name", "name_status", "names_found_by_year"])
        for cik in sample:
            w.writerow([cik, names[cik]["company_name"] or "", names[cik]["status"], json.dumps(names[cik]["found"])])
    total = sum(n_chunks.values())
    summary_sel = selectivity_table(out / "chunks.jsonl", total)
    (out / "selectivity_by_filter_type.json").write_text(json.dumps(summary_sel, indent=1), encoding="utf-8", newline="\n")
    summary = {"ciks_in_all_three_years": len(in_all_three), "ciks_exactly_one_report_each_year": len(eligible),
               "sampled_companies": n, "reports": 3 * n, "seed": C.SEED, "chunks_total": total,
               "chunks_by_year": {y: sum(v for (yy, _), v in n_chunks.items() if yy == y) for y in C.YEARS},
               "chunks_by_section": {s: sum(v for (_, ss), v in n_chunks.items() if ss == s) for s in C.KEEP_SECTIONS},
               "chunks_by_year_section": {f"{y}/{s}": n_chunks[(y, s)] for y in C.YEARS for s in C.KEEP_SECTIONS},
               "chunk_tokens_by_year_section": {f"{y}/{s}": sec_tokens[(y, s)] for y in C.YEARS for s in C.KEEP_SECTIONS},
               "empty_sections_by_year_section": {f"{y}/{s}": empty_sections[(y, s)] for y in C.YEARS for s in C.KEEP_SECTIONS},
               "company_name": dict(Counter(v["status"] for v in names.values())),
               "selectivity_by_filter_type": summary_sel,
               "chunker": {"tokens": C.CHUNK_TOKENS, "overlap": C.OVERLAP_TOKENS, "word_snap_tokens": C.SNAP_TOKENS}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
