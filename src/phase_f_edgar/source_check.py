"""Task 1 (Phase F): source and size check of the downloaded EDGAR-CORPUS files (2018-2020). No database, no paid call.

  python -m src.phase_f_edgar.source_check --out-dir outputs/edgar_source_check_2026-10-31

Writes
  download_manifest.json  every file: URL at the pinned revision, size, sha256 computed here, expected LFS sha256
  report_index.csv        one row per record: file, byte offset, filename, cik, year, character length of every section
  summary.json            fields, reports per year, non-empty kept sections, CIKs in all three years, fiscal-year check,
                          tokens of 20 seeded reports (Qwen3 tokenizer) and the chunk/cost projection
The OpenRouter price is read from the public model list (no key, no paid call).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import requests

from src import PROJECT_ROOT
from src.phase_f_edgar import common as C

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
YEAR_ENDED = re.compile(rf"(?:fiscal\s+)?years?\s+ended\s+(?:{MONTHS})\s+\d{{1,2}},?\s+(\d{{4}})", re.I)
TARGET_REPORTS = 1300


def detected_fiscal_year(rec: dict) -> int | None:
    """Latest 'year ended <Month> <day>, <YYYY>' among the first 10 matches of section 7 (MD&A), else section 1."""
    for sec in ("section_7", "section_1"):
        ys = [int(m.group(1)) for _, m in zip(range(10), YEAR_ENDED.finditer(rec.get(sec) or ""))]
        if ys:
            return max(ys)
    return None


def price_per_token() -> float:
    r = requests.get("https://openrouter.ai/api/v1/embeddings/models", timeout=30)
    r.raise_for_status()
    for m in r.json()["data"]:
        if m["id"] == C.EMBED_MODEL:
            return float(m["pricing"]["prompt"])
    raise RuntimeError(f"{C.EMBED_MODEL} not listed by OpenRouter")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", default=str(C.RAW_DIR))
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-sample", type=int, default=20)
    a = ap.parse_args()
    raw, out = Path(a.raw_dir), PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=False)

    manifest = []
    for rel, exp in C.EXPECTED_SHA256.items():
        p = raw / rel
        got = C.sha256_file(p)
        manifest.append({"file": rel, "url": f"https://huggingface.co/datasets/{C.HF_REPO}/resolve/{C.HF_REVISION}/{rel}",
                         "bytes": p.stat().st_size, "sha256": got, "expected_lfs_sha256": exp, "match": got == exp})
    tok_sha = C.sha256_file(C.TOKENIZER_PATH)
    manifest.append({"file": "qwen3_tokenizer/tokenizer.json",
                     "url": f"https://huggingface.co/{C.TOKENIZER_REPO}/resolve/{C.TOKENIZER_REVISION}/tokenizer.json",
                     "bytes": C.TOKENIZER_PATH.stat().st_size, "sha256": tok_sha, "expected_lfs_sha256": C.TOKENIZER_SHA256,
                     "match": tok_sha == C.TOKENIZER_SHA256})
    (out / "download_manifest.json").write_text(json.dumps({"dataset": C.HF_REPO, "revision": C.HF_REVISION,
                                                            "files": manifest}, indent=1), encoding="utf-8", newline="\n")
    if not all(m["match"] for m in manifest):
        raise SystemExit("sha256 mismatch: " + str([m["file"] for m in manifest if not m["match"]]))

    # ---- one pass over all records
    field_sets, index = Counter(), []
    fy_diff = Counter()
    sec_keys = None
    with open(out / "report_index.csv", "w", newline="", encoding="utf-8") as fcsv:
        w = None
        for rel in C.EXPECTED_SHA256:
            with open(raw / rel, "rb") as f:
                off = 0
                for line in f:
                    rec = json.loads(line)
                    keys = tuple(rec)
                    field_sets[keys] += 1
                    if sec_keys is None:
                        sec_keys = [k for k in keys if k.startswith("section_")]
                        w = csv.writer(fcsv, lineterminator="\n")
                        w.writerow(["file", "offset", "filename", "cik", "year", "fiscal_year_detected"] + [f"len_{k}" for k in sec_keys])
                    fy = detected_fiscal_year(rec)
                    fy_diff[None if fy is None else fy - int(rec["year"])] += 1
                    row = [rel, off, rec["filename"], rec["cik"], rec["year"], fy] + [len(rec.get(k) or "") for k in sec_keys]
                    w.writerow(row)
                    nonempty = {s: bool((rec.get(f"section_{s}") or "").strip()) for s in C.KEEP_SECTIONS}
                    index.append({"file": rel, "offset": off, "cik": rec["cik"], "year": int(rec["year"]),
                                  "folder_year": int(rel[:4]), "filename": rec["filename"], "nonempty": nonempty})
                    off += len(line)

    per_year = Counter(r["year"] for r in index)
    folder_mismatch = sum(1 for r in index if r["year"] != r["folder_year"])
    dup = Counter((r["cik"], r["year"]) for r in index)
    nonempty = {y: {s: sum(1 for r in index if r["year"] == y and r["nonempty"][s]) for s in C.KEEP_SECTIONS} for y in C.YEARS}
    for y in C.YEARS:
        nonempty[y]["all_five"] = sum(1 for r in index if r["year"] == y and all(r["nonempty"].values()))
    years_by_cik = defaultdict(set)
    for r in index:
        years_by_cik[r["cik"]].add(r["year"])
    eligible = sorted(c for c, ys in years_by_cik.items() if set(C.YEARS) <= ys)

    # ---- 20 seeded reports from companies with reports in all three years
    tok = C.load_tokenizer()
    pool = [r for r in index if r["cik"] in set(eligible)]
    sample = random.Random(C.SEED).sample(pool, a.n_sample)
    per_report = []
    for r in sample:
        rec = C.read_record(raw / r["file"], r["offset"])
        secs = {s: len(tok.encode(rec.get(f"section_{s}") or "", add_special_tokens=False).ids) for s in C.KEEP_SECTIONS}
        all_tokens = sum(len(tok.encode(rec.get(k) or "", add_special_tokens=False).ids) for k in sec_keys)
        chunks = {s: C.n_chunks_for(t) for s, t in secs.items()}
        emb_tokens = sum(secs[s] + max(0, chunks[s] - 1) * C.OVERLAP_TOKENS for s in C.KEEP_SECTIONS)
        per_report.append({"filename": r["filename"], "cik": r["cik"], "year": r["year"], "tokens_all_sections": all_tokens,
                           "tokens_kept": secs, "tokens_kept_total": sum(secs.values()), "chunks": sum(chunks.values()),
                           "embedded_tokens": emb_tokens})
    price = price_per_token()
    mean = lambda k: statistics.fmean(p[k] for p in per_report)
    proj_chunks = mean("chunks") * TARGET_REPORTS
    proj_tokens = mean("embedded_tokens") * TARGET_REPORTS
    lo_hi = lambda k: [min(p[k] for p in per_report) * TARGET_REPORTS, max(p[k] for p in per_report) * TARGET_REPORTS]
    summary = {
        "fields": {"field_sets": [{"fields": list(k), "records": v} for k, v in field_sets.items()]},
        "records_total": len(index), "reports_per_year": dict(sorted(per_year.items())),
        "year_field_differs_from_folder": folder_mismatch,
        "cik_year_with_more_than_one_report": sum(1 for v in dup.values() if v > 1),
        "nonempty_kept_sections_per_year": nonempty,
        "ciks_per_year": {y: len({r["cik"] for r in index if r["year"] == y}) for y in C.YEARS},
        "ciks_in_all_three_years": len(eligible),
        "fiscal_year_check": {"rule": "latest 'year ended <Month> <day>, <YYYY>' in the first 10 matches of section 7, else section 1",
                              "detected_minus_year_field": {str(k): v for k, v in sorted(fy_diff.items(), key=lambda x: (x[0] is None, x[0] or 0))}},
        "token_sample": {"tokenizer": f"{C.TOKENIZER_REPO}@{C.TOKENIZER_REVISION} tokenizer.json (tokenizers library), no special tokens",
                         "seed": C.SEED, "pool": "all reports of CIKs with reports in 2018, 2019 and 2020", "n": len(sample),
                         "reports": per_report,
                         "tokens_all_sections": {"mean": mean("tokens_all_sections"), "median": statistics.median(p["tokens_all_sections"] for p in per_report)},
                         "tokens_kept_total": {"mean": mean("tokens_kept_total"), "median": statistics.median(p["tokens_kept_total"] for p in per_report)},
                         "tokens_per_section_mean": {s: statistics.fmean(p["tokens_kept"][s] for p in per_report) for s in C.KEEP_SECTIONS},
                         "tokens_per_section_median": {s: statistics.median(p["tokens_kept"][s] for p in per_report) for s in C.KEEP_SECTIONS}},
        "projection": {"reports": TARGET_REPORTS, "chunk_tokens": C.CHUNK_TOKENS, "overlap": C.OVERLAP_TOKENS,
                       "chunks_mean_based": proj_chunks, "chunks_range_min_max_report": lo_hi("chunks"),
                       "embedded_tokens_mean_based": proj_tokens, "embedded_tokens_range": lo_hi("embedded_tokens"),
                       "price_usd_per_token": price, "embedding_cost_usd_mean_based": proj_tokens * price,
                       "embedding_cost_usd_range": [x * price for x in lo_hi("embedded_tokens")]},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "token_sample"}, indent=1))
    print(json.dumps({k: v for k, v in summary["token_sample"].items() if k != "reports"}, indent=1))


if __name__ == "__main__":
    main()
