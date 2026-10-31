"""Task 3 (Phase F): embed edgar_chunks with Qwen3-Embedding-8B via OpenRouter (paid; needs --allow-paid). Resumable.

  python -m src.phase_f_edgar.embed --allow-paid --budget-usd 2.5 --out-dir outputs/edgar_embed_2026-10-31 --limit 1000
  python -m src.phase_f_edgar.embed --allow-paid --budget-usd 2.5 --out-dir outputs/edgar_embed_2026-10-31

Settings as finqa_evidence_qwen3 (src/phase_d_validation/build_finqa_embedding_table.py): model qwen/qwen3-embedding-8b,
documents with no prefix, API parameter dimensions=1024, encoding_format float, 100 texts per call, the shared
OpenRouterEmbedder (key from the environment, never logged; every HTTP call in api_calls.jsonl).

- Deduplication: one embedding per distinct text_hash; every row with that hash gets the same vector.
- Checkpoint = the database: a text_hash is done when its rows have a non-NULL embedding. Each batch is written in one
  transaction (UPDATE ... WHERE embedding IS NULL), so a restart continues with the remaining hashes, never re-embeds or
  duplicates rows. checkpoint.json (written after each commit) mirrors the progress; batches.jsonl logs every batch.
- A batch is retried with exponential backoff (5 attempts: 5, 10, 20, 40 s) on HTTP/network errors and on any invalid
  response (wrong count, wrong dimension, non-finite or zero vector). Nothing invalid is ever written; after the last
  attempt the run stops.
- The budget is cumulative over all runs into the same --out-dir (sum of the costs in every api_calls*.jsonl there).
- --shard k --of n: this process embeds only the pending hashes with int(text_hash[:8], 16) % n == k, logs to
  api_calls_shard<k>of<n>.jsonl / batches_shard<k>of<n>.jsonl / checkpoint_shard<k>of<n>.json, and may spend at most
  (budget - spent so far) / n, so n shards running at once stay under the budget together.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import execute_values

from src import PROJECT_ROOT, db_settings
from src.phase_d_validation.embedding_tools import CostCapExceeded, OpenRouterEmbedder
from src.phase_f_edgar import common as C

BATCH = 100
ATTEMPTS, BACKOFF_S = 5, 5.0


class InvalidBatch(RuntimeError):
    pass


def validate(vecs, n: int) -> list[np.ndarray]:
    if len(vecs) != n:
        raise InvalidBatch(f"{len(vecs)} vectors for {n} texts")
    out = []
    for v in vecs:
        a = np.asarray(v, dtype=np.float64)
        if a.shape != (C.EMBED_DIM,):
            raise InvalidBatch(f"dimension {a.shape}, expected {C.EMBED_DIM}")
        if not np.all(np.isfinite(a)):
            raise InvalidBatch("non-finite value")
        if float(np.linalg.norm(a)) == 0.0:
            raise InvalidBatch("zero vector")
        out.append(a.astype(np.float32))
    return out


def embed_with_retry(client, texts, purpose, log, sleep=time.sleep):
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return validate(client.embed(texts, purpose), len(texts))
        except CostCapExceeded:
            raise
        except Exception as e:  # HTTP, network, JSON, validation
            log({"event": "batch_attempt_failed", "attempt": attempt, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            if attempt == ATTEMPTS:
                raise
            sleep(BACKOFF_S * 2 ** (attempt - 1))


def spent_so_far(*api_logs: Path) -> tuple[float, int]:
    cost = tok = 0
    for api_log in api_logs:
        if not api_log.exists():
            continue
        for line in api_log.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            cost += r.get("cost_usd") or 0.0
            tok += r.get("prompt_tokens") or 0
    return cost, tok


def in_shard(text_hash: str, shard: int, of: int) -> bool:
    return int(text_hash[:8], 16) % of == shard


def pending_hashes(cur) -> list[tuple[str, str]]:
    cur.execute(f"""SELECT text_hash, min(text) FROM {C.TABLE} GROUP BY text_hash
                    HAVING bool_or(embedding IS NULL) ORDER BY min(id)""")
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--budget-usd", type=float, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--limit", type=int, default=None, help="embed at most this many distinct texts in this run")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    a = ap.parse_args()
    if not a.allow_paid:
        raise SystemExit("paid API calls need --allow-paid")
    if not 0 <= a.shard < a.of:
        raise SystemExit("need 0 <= --shard < --of")
    out = PROJECT_ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    sfx = "" if a.of == 1 else f"_shard{a.shard}of{a.of}"
    api_log, batch_log, ckpt = out / f"api_calls{sfx}.jsonl", out / f"batches{sfx}.jsonl", out / f"checkpoint{sfx}.json"

    def log(rec):
        with batch_log.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), **rec}) + "\n")

    prior_cost, prior_tok = spent_so_far(*sorted(out.glob("api_calls*.jsonl")))
    client = OpenRouterEmbedder(C.EMBED_MODEL, api_log, cost_cap_usd=(a.budget_usd - prior_cost) / a.of, dimensions=C.EMBED_DIM)
    conn = psycopg2.connect(**db_settings())
    register_vector(conn)
    with conn.cursor() as cur:
        todo = [x for x in pending_hashes(cur) if in_shard(x[0], a.shard, a.of)]
    conn.commit()
    if a.limit is not None:
        todo = todo[:a.limit]
    log({"event": "run_start", "shard": a.shard, "of": a.of, "pending_texts": len(todo), "limit": a.limit, "prior_cost_usd": prior_cost,
         "budget_usd": a.budget_usd, "price_usd_per_token": client.price_per_token})
    t_run = time.perf_counter()
    done_texts = done_rows = 0
    for b in range(0, len(todo), BATCH):
        part = todo[b:b + BATCH]
        t0 = time.perf_counter()
        before = (client.spent, client.tokens)
        vecs = embed_with_retry(client, [t for _, t in part], "edgar_chunks documents (no prefix)", log)
        with conn.cursor() as cur:
            execute_values(cur, f"""UPDATE {C.TABLE} e SET embedding = v.emb::vector FROM (VALUES %s) AS v(h, emb)
                                    WHERE e.text_hash = v.h AND e.embedding IS NULL""",
                           [(h, v) for (h, _), v in zip(part, vecs)], page_size=BATCH)
            rows = cur.rowcount
        conn.commit()
        done_texts += len(part)
        done_rows += rows
        rec = {"event": "batch", "batch_start": b, "texts": len(part), "rows_updated": rows,
               "tokens": client.tokens - before[1], "cost_usd": client.spent - before[0], "seconds": round(time.perf_counter() - t0, 2),
               "run_texts_done": done_texts, "cumulative_cost_usd": prior_cost + client.spent}
        log(rec)
        ckpt.write_text(json.dumps({**rec, "pending_at_run_start": len(todo), "limit": a.limit,
                                    "cumulative_tokens": prior_tok + client.tokens}, indent=1), encoding="utf-8", newline="\n")
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FILTER (WHERE embedding IS NULL), count(*) FROM {C.TABLE}")
        null_rows, total = cur.fetchone()
    conn.close()
    summary = {"event": "run_end", "texts": done_texts, "rows_updated": done_rows, "tokens": client.tokens,
               "cost_usd": client.spent, "seconds": round(time.perf_counter() - t_run, 1),
               "cumulative_cost_usd": prior_cost + client.spent, "rows_without_embedding": null_rows, "rows_total": total}
    log(summary)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
