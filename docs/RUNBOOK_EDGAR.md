# Runbook: EDGAR 10-K corpus (table `edgar_chunks`)

How to rebuild, check and reset the 10-K corpus used for the final evaluation and the demo. Built 31 Oct 2026 (Phase F); code in `src/phase_f_edgar/`, tests in `tests/phase_f_edgar/`. All commands run from the repository root in Git Bash (Windows); on PowerShell replace `.venv/Scripts/python` with `.venv\Scripts\python.exe`.

**Demo.** The demo, to be built in the sibling folder `BSC_Research_Route_Threshold_Huristic(Demo)`, uses the `edgar_chunks` table in the same database and imports `src/phase_e_router` from this repository unchanged. Nothing in this runbook touches that folder.

## Prerequisites

- **Docker container** `vector_db` (`docker-compose.yml`: image `pgvector/pgvector:pg16`, PostgreSQL 16, pgvector 0.8.3, host port 5433, database `vector_db`). Check: `docker ps --filter name=vector_db`.
- **Python environments** (Python 3.11):
  - `.venv`: the project environment (`requirements.txt`) plus `tokenizers` (0.23.3, installed 31 Oct 2026 for the Qwen3 tokenizer; not yet in `requirements.txt`).
  - `.venv-vecadvisor`: VecAdvisor 0.1.0a6 only (used for `vecadvisor analyze`).
- **Environment variables** (in the git-ignored `.env`, loaded by `src.db_settings()`; never commit values):
  - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_HOST_PORT` (defaults in `src/__init__.py`).
  - `OPENROUTER_API_KEY` (embeddings); optional `OPENROUTER_API_BASE` (default `https://openrouter.ai/api/v1`).
  - Vertex AI for question drafting: Application Default Credentials (`gcloud auth application-default login`); project and location come from `config/generation.json` (`gemini-3.8-flash`: project `bsc-research-project-511410`, location `global`). `GOOGLE_API_KEY` / `GEMINI_API_KEY` must **not** be set (the client refuses to run if they are).
- **Paid steps** need `--allow-paid` and a `--budget-usd` cap: embedding, the self-retrieval check, question drafting.
- **Disk**: about 6 GB for the downloads, 0.4 GB for the chunk file, about 1.5 GB in the database volume.

## Steps

Times and costs are those of the 31 Oct 2026 build (4 shards in parallel for the embedding; machine in normal use).

| # | Step | Command | Writes | Time | Cost |
|---|---|---|---|---|---|
| 1 | Download | see below | `data/raw/edgar_corpus/` (git-ignored) | ~10 min | 0 |
| 2 | Source check | `.venv/Scripts/python -m src.phase_f_edgar.source_check --out-dir outputs/edgar_source_check_<date>` | `download_manifest.json`, `report_index.csv`, `summary.json` | ~5 min | 0 |
| 3 | Chunk | `.venv/Scripts/python -m src.phase_f_edgar.build_chunks --index outputs/edgar_source_check_2026-10-31/report_index.csv --out-dir outputs/edgar_chunks_<date>` | `chunks.jsonl` (354 MB, git-ignored), `companies.csv`, `selectivity_by_filter_type.json`, `summary.json` | ~5 min | 0 |
| 4 | Load | `.venv/Scripts/python -m src.phase_f_edgar.load_table --chunks outputs/edgar_chunks_2026-10-31/chunks.jsonl` | table `edgar_chunks` (embedding NULL) | ~35 s | 0 |
| 5 | Embed | see below | `outputs/edgar_embed_<date>/` logs; `edgar_chunks.embedding` | ~70 min (1,000-text probe 80 s serial; then 4 shards ~60 min) | USD 0.61 (61.0M tokens at USD 0.01 / 1M) |
| 6 | Index, statistics, checks | `.venv/Scripts/python -m src.phase_f_edgar.index_and_check --chunks outputs/edgar_chunks_2026-10-31/chunks.jsonl --out-dir outputs/edgar_index_<date> --allow-paid --budget-usd 0.01` | `checks.json`, `spot_check_chunks.md` | ~5 min (HNSW build 230 s) | < USD 0.001 |
| 7 | VecAdvisor analyze + dump | `.venv/Scripts/python -m src.phase_f_edgar.vecadvisor_and_dump --out-dir outputs/edgar_vecadvisor_<date> --dump-dir outputs/db_dumps_edgar_<date>` | `analyze_edgar_chunks.json`, `version.txt`; `edgar_chunks.dump` (git-ignored) | ~3.5 min (dump 0.79 GB) | 0 |
| 8 | Draft questions | `.venv/Scripts/python -m src.phase_f_edgar.draft_questions --allow-paid --budget-usd 0.5 --out-dir outputs/edgar_questions_draft_<date>` | `candidates.csv` (LF), `responses.jsonl`, `prompt.json`, `run_meta.json` | ~9 min | ~USD 0.05 |

Every step refuses to overwrite: output folders must not exist, and `load_table` stops if `edgar_chunks` exists.

### 1. Download

Source: EDGAR-CORPUS (Loukas et al., ECONLP 2021), Hugging Face dataset `eloukas/edgar-corpus` at revision `7e90f0f342569b35213445f809cfaf3b91f9964f`, years 2018-2020 (9 JSON-lines files, 5.55 GB). Licence: the Hugging Face card says Apache-2.0; the Zenodo record 5528490 of the same corpus says CC BY 4.0. The files are untrusted data: they go only into `data/raw/edgar_corpus/`, and nothing there is executed.

```bash
REV=7e90f0f342569b35213445f809cfaf3b91f9964f
for y in 2018 2019 2020; do for s in train validate test; do mkdir -p data/raw/edgar_corpus/$y; curl -sL --fail -o data/raw/edgar_corpus/$y/$s.jsonl "https://huggingface.co/datasets/eloukas/edgar-corpus/resolve/$REV/$y/$s.jsonl"; done; done
```

```bash
R=1d8ad4ca9b3dd8059ad90a75d4983776a23d44af; mkdir -p data/raw/edgar_corpus/qwen3_tokenizer; for f in tokenizer.json tokenizer_config.json; do curl -sL --fail -o data/raw/edgar_corpus/qwen3_tokenizer/$f https://huggingface.co/Qwen/Qwen3-Embedding-8B/resolve/$R/$f; done
```

Step 2 verifies every file against the pinned sha256 values in `src/phase_f_edgar/common.py` and stops on a mismatch.

### 5. Embed (resumable)

Qwen3-Embedding-8B via OpenRouter, same settings as `finqa_evidence_qwen3`: model `qwen/qwen3-embedding-8b`, documents with no prefix, `dimensions=1024`, `encoding_format=float`, 100 texts per call. One embedding per distinct `text_hash`.

```bash
.venv/Scripts/python -m src.phase_f_edgar.embed --allow-paid --budget-usd 2.0 --out-dir outputs/edgar_embed_2026-10-31 --limit 1000
```

```bash
for k in 0 1 2 3; do .venv/Scripts/python -m src.phase_f_edgar.embed --allow-paid --budget-usd 2.0 --out-dir outputs/edgar_embed_2026-10-31 --shard $k --of 4 & done; wait
```

- The first command embeds the first 1,000 distinct texts (the timing/cost probe); the second runs 4 shards in parallel (one shard per process; omit `--shard/--of` for a single process).
- **Resume after an interruption:** run the same command again with the same `--out-dir`. The database is the checkpoint: a batch is written in one transaction (`UPDATE ... WHERE embedding IS NULL`), so a restart embeds only the texts whose rows still have no embedding, never re-embeds or duplicates rows. `checkpoint*.json` mirrors the progress; `batches*.jsonl` logs every batch (texts, rows, tokens, cost, seconds) and every failed attempt; `api_calls*.jsonl` logs every HTTP call.
- The budget is cumulative over every run into the same `--out-dir`; with `--of n` each process may spend at most (budget - spent so far) / n.
- A failed or invalid batch (HTTP or network error, wrong count, wrong dimension, NaN or zero vector) is retried 5 times with backoff (5, 10, 20, 40 s); nothing invalid is ever written; after the last attempt the process stops.
- Progress: `docker exec vector_db psql -U postgres -d vector_db -c "SELECT count(*) FILTER (WHERE embedding IS NULL) FROM edgar_chunks"`.

### 6. Index, statistics, checks

`index_and_check` stops before indexing if any row has no embedding or any embedding's norm differs from 1 by more than 1e-3. It then sets `embedding NOT NULL`; creates the HNSW index `edgar_chunks_embedding_idx` on the plain `embedding` column with `vector_l2_ops`, `m = 16`, `ef_construction = 64` (as `finqa_evidence_qwen3`; `maintenance_work_mem = 512MB` for the build); B-tree indexes on `cik`, `fiscal_year`, `section`; `CREATE STATISTICS (dependencies, mcv)` on `(fiscal_year, section)` and `(cik, fiscal_year)`; `ANALYZE`. It checks that `pg_stats` has rows for `cik`, `fiscal_year` and `section` (the router's estimate path needs them), row count, zero vectors, dimensions, duplicate keys, `text_hash` against the text, and 5 self-retrievals (re-embeds 5 seeded chunks; the exact top-1 must have the same `text_hash`), and writes 10 seeded chunks to `spot_check_chunks.md`.

### 8. Draft questions

60 candidates (15 per filter breadth: cik+year+section, cik+year, year+section, section), Gemini 3.8 Flash on Vertex, temperature 0, thinking LOW. `candidates.csv` is written with LF line endings; the `outputs/edgar_*` folders are marked `-text` in `.gitattributes` so git never converts them. No retrieval or answer evaluation is run with these questions; the columns `keep`, `corrected_answer`, `corrected_type`, `note` are for the author.

## Verify checksums

Every output file (including the git-ignored `chunks.jsonl` and `edgar_chunks.dump`) has an entry in `outputs/data_checksums.json` with `sha256`, `bytes` and, for Phase F files, `line_endings`:

```bash
.venv/Scripts/python -c "import json,hashlib,pathlib; d=json.load(open('outputs/data_checksums.json'))['files']; [print('OK ' if hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()==v['sha256'] else 'BAD', k) for k,v in d.items() if '/edgar_' in k and pathlib.Path(k).exists()]"
```

New entries are added with `python -m src.phase_f_edgar.checksums --label <name> <paths>` (existing entries are never changed).

## Reset only the 10-K table

This drops `edgar_chunks` and its indexes and extended statistics; it does not touch the H&M tables (`hm_clothes_*`) or the FinQA tables (`finqa_evidence*`):

```bash
docker exec vector_db psql -U postgres -d vector_db -c "DROP TABLE IF EXISTS edgar_chunks"
```

Then rerun from step 4 (load), or restore the dump instead of steps 4-6:

```bash
MSYS_NO_PATHCONV=1 docker cp outputs/db_dumps_edgar_2026-10-31/edgar_chunks.dump vector_db:/tmp/edgar_chunks.dump
```

```bash
MSYS_NO_PATHCONV=1 docker exec vector_db pg_restore -U postgres -d vector_db /tmp/edgar_chunks.dump
```

```bash
docker exec vector_db psql -U postgres -d vector_db -c "ANALYZE edgar_chunks"
```

The dump holds the table, its indexes and its extended statistics but not planner statistics, so run `ANALYZE` after the restore (the router's estimate path needs `pg_stats`). `MSYS_NO_PATHCONV=1` stops Git Bash rewriting `/tmp/...` into a Windows path. Check the dump first against its `data_checksums.json` entry (`sha256` 2113f5f0...).

Before a rerun of step 5 into a fresh table, use a new `--out-dir` (the budget is counted per folder).

## Known properties of the 31 Oct 2026 build

- 433 companies (CIKs) x 2018-2020 = 1,299 reports; 158,308 chunks, 154,824 distinct texts; 5 reports have none of the five sections (1,294 cik+year filters, not 1,299).
- `fiscal_year` is the corpus `year` field. A check on "year ended <date>" phrases agrees with it for 16,256 of the 16,766 reports where a year could be detected (97 %); 329 are one year earlier, 122 one year later.
- Section 8 is often a pointer ("financial statements ... appended ...") rather than the statements; source text contains U+FFFD replacement characters where the original had curly quotes. Text is stored as in the source.
- `company_name` is set for 165 of 433 companies (rule in `build_chunks.py`), null for the rest; it can name a subsidiary bank rather than the registrant.
- Embeddings are unit-normalised (norms 0.99999988-1.00000013), so L2 and cosine rank identically.
- After `ANALYZE`, `pg_class.reltuples` was 158,555 (true count 158,308: the embedding UPDATEs left dead tuples); `cik` n_distinct is estimated at 430 (true 433) with 100 most-common values; the `(fiscal_year, section)` statistics hold an MCV list but no functional dependency (none found).
