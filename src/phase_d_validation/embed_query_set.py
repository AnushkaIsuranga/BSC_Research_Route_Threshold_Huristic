"""Embed a set of FinQA questions with the Amendment 1 query recipe and cache them (new file; existing caches untouched).

Recipe: qwen/qwen3-embedding-8b via OpenRouter, `dimensions=1024` (API parameter), input
"Instruct: Given a financial question, retrieve the report passages and table rows that answer it\\nQuery: {question}".
Key from the environment only; every call logged (provider, tokens, cost); cumulative cost cap.

  python -m src.phase_d_validation.embed_query_set --subset outputs/scaleup_confirmation_2026-10-13/confirmation_1075.csv \
      --out-dir outputs/embedding_build_2026-10-13 --name qwen3_confirmation_1075 --cost-cap-usd 1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from src.phase_d_validation.embedding_tools import OpenRouterEmbedder, qwen3_query

MODEL, DIM = "qwen/qwen3-embedding-8b", 1024


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--cost-cap-usd", type=float, default=1.0)
    ap.add_argument("--batch", type=int, default=100)
    a = ap.parse_args()
    out = Path(a.out_dir)
    cache = out / f"query_embeddings_{a.name}.json"
    if cache.exists():
        raise SystemExit(f"{cache} exists; not overwriting")
    out.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(a.subset, encoding="utf-8")))
    inputs = [qwen3_query(r["question"]) for r in rows]
    emb = OpenRouterEmbedder(MODEL, out / f"api_calls_{a.name}.jsonl", a.cost_cap_usd, dimensions=DIM)
    vecs = []
    for i in range(0, len(inputs), a.batch):
        got = emb.embed(inputs[i:i + a.batch], f"{a.name} queries {i}-{i + len(inputs[i:i + a.batch]) - 1} (instruct template)")
        if any(len(v) != DIM for v in got):
            raise RuntimeError("unexpected embedding dimension")
        vecs.extend(got)
    cache.write_text(json.dumps({"model": MODEL, "dimension": DIM, "variant": "qwen3", "subset": a.subset,
                                 "subset_sha256": hashlib.sha256(Path(a.subset).read_bytes()).hexdigest(),
                                 "queries": [{"query_id": r["id"], "input_text": t, "input_sha256": hashlib.sha256(t.encode()).hexdigest(),
                                              "vector": v} for r, t, v in zip(rows, inputs, vecs)]}), encoding="utf-8")
    sha = hashlib.sha256(cache.read_bytes()).hexdigest()
    print(json.dumps({"cache": cache.as_posix(), "sha256": sha, "n": len(vecs), "prompt_tokens": emb.tokens, "cost_usd": emb.spent}, indent=2))


if __name__ == "__main__":
    main()
