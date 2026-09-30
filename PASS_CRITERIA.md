# Phase D Pass Criteria (Sanity Gates)

These are pipeline-validity gates, not performance thresholds. They must be
committed before the retrieval pilot and must not be changed after inspecting
pilot results. The local Ollama run is supplementary to the primary API
comparison.

## Definitions

Gold evidence is identified by `(query_id, evidence_key)`. For retrieved set
`R` and gold set `G`:

- Unit recall = `|G ∩ R| / |G|`
- Full hit = all gold units are retrieved
- Any hit = at least one gold unit is retrieved
- Distinct-content count = unique retrieved contents among top-k

## Gates

- Infrastructure: PostgreSQL, pgvector, Ollama, required models, and one test
  embedding must all work; vector dimensions must match.
- Database: independent raw-entry count, unique-content count, key resolution,
  nonzero vectors, and vector dimension must all match.
- Retrieval pilot: 5 queries; 100% key resolution, self-retrieval passes,
  zero infrastructure errors, any-hit on at least 4/5, and mean unit recall at
  least 0.5.
- LLM pilot: 5–10 queries; zero infrastructure errors, at most 20% parse
  failures, no mock/default answers, explicit `num_ctx`, and one JSONL row per
  query. Answer accuracy is not a pilot gate.
- Full run: exactly 50 JSONL rows, including failures; the summary CSV must be
  reproducible from JSONL alone.

Failures count as incorrect in the primary result and are excluded only in a
reported sensitivity result. A genuine infrastructure bug may be fixed and
rerun once only if recorded in `DEVIATION_LOG.md`; tuning is not an exception.

Record model names and digests, Ollama version, prompt, k, ef_search, seed,
temperature, thresholds/subset hashes, and the occurrence-based selectivity
denominator. H&M-derived thresholds are reported as a transfer condition for
FinQA, not as FinQA-validated thresholds.
