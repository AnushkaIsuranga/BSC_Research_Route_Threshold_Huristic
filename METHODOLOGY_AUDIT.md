# Methodology and local-LLM audit

## Assessment

The overall research design is reasonable: measure filtered ANN recall and
latency across correlation levels, derive danger zones, route FinQA queries
through a deterministic decision matrix, and compare it with a naive router.
The implementation was not yet suitable for a defensible API-vs-local
comparison without the fixes below.

Important limitations to record in the thesis:

1. The Phase-A threshold file is derived from the H&M benchmark tables. It is
   not automatically a FinQA-specific threshold model. The FinQA run currently
   uses `hm_clothes_0` as its correlation tier, so this is a transfer test, not
   evidence that all FinQA metadata has those H&M correlations.
2. `pre-filter` is implemented as exact vector ranking over the metadata subset
   (`enable_indexscan=off`); `post-filter` is the HNSW/index path. Keep this
   operational definition fixed and state it explicitly.
3. Retrieval quality and answer quality must be reported separately. A correct
   answer can occur with incomplete evidence, and an incorrect answer can be
   caused by the local model rather than retrieval or routing.
4. Random embeddings are invalid for this experiment. The loader now refuses
   to continue unless OpenRouter embeddings or a configured Ollama embedding
   model is used. The DB must be rebuilt if it was created with random vectors.
5. The selected 50-query file is a stratified validation sample, not a training
   set. Do not tune thresholds or prompts on these rows and then report the
   same rows as an unbiased final result.
6. The local Ollama run is supplementary: the proposal's primary comparison
   uses its specified API/router model. Local model size, tokenizer, model
   digest, and hardware can change routing and answer behavior. FinQA's
   embedding dimension and geometry also differ from H&M, so H&M thresholds
   remain a transfer condition rather than FinQA validation.

## Local Ollama procedure

1. Start PostgreSQL/pgvector and Ollama.
2. Choose one local chat model for routing and answer generation. If fully
   local retrieval is required, choose an Ollama embedding model too.
3. Rebuild the evidence DB with the same embedding model used at query time:

```powershell
$env:EMBEDDING_BACKEND = "ollama"
$env:OLLAMA_EMBEDDING_MODEL = "<installed-embedding-model>"
.venv\Scripts\python.exe -m src.phase_d_validation.finqa_db_setup
```

4. List models and run a smoke test before the full sample:

```powershell
.venv\Scripts\python.exe -m src.phase_d_validation.local_ollama_runner --list-models
.venv\Scripts\python.exe -m src.phase_d_validation.local_ollama_runner `
  --answer-model <chat-model> --router-model <chat-model> `
  --embedding-mode ollama --embedding-model <embedding-model> --limit 5
```

5. Run all 50 rows, then use the generated CSV for accuracy, route counts,
   retrieval counts, and latency. Only after that should the API runner be used
   with the same prompts, k, subset, and embedding space.

If the DB was built with OpenRouter embeddings, use
`--embedding-mode openrouter`; this still tests local answer/routing models but
is not a fully local experiment.

## Exploratory Post-Hoc Analysis on Frozen Data

An exploratory post-hoc check was performed on the frozen validation sample to evaluate local selectivity's impact on retrieval yield. 

The original run's "post-filter" branch executed a metadata-filtered HNSW index scan with `ef_search=40` and iterative scan disabled. (Commit hash `b59c004`.) By replaying competing hypotheses against the results, we determined the exact mechanism at play:
1. **Elements vs. Rows**: In pgvector, without iterative scan, an index scan returns up to `ef_search` graph elements, which is 40. However, pgvector groups rows with identical vectors into a single graph element (up to `HNSW_HEAPTIDS = 10` rows per element). 
2. **Duplicate Embeddings Expand the Pool**: Because the dataset contains 35,862 rows but only ~10,843 unique embeddings (duplicate content across examples), the 40 graph elements returned by the index scan expand to up to about 400 underlying heap tuples.
3. **Local selectivity reproduces the variance**: Replaying this exact filtered, non-iterative index scan perfectly reproduced the `naive_retrieved` counts (45 out of 45 queries) from the frozen run. The Naive router's failure to retrieve sufficient evidence is reproduced by this bounded pool constraint: the post-filter effectively searches a pool of up to about 400 rows (not just 40), and when local selectivity is low, even this expanded pool contains fewer than `k=6` matching items.

*Note on distinct evidence*: Since rows aren't necessarily distinct evidence (due to duplicate passages), future analysis should also report distinct-content counts for the post-filter results.

**Optional design idea for discussion:** A potential enhancement to the router could involve a cheap pre-flight probe: run the same filtered index scan, and if it returns fewer than `k` candidates, immediately fall back to the exact-search pre-filter path. This explicitly uses local selectivity to adjust the path on-the-fly and guarantees sufficient evidence retrieval.
