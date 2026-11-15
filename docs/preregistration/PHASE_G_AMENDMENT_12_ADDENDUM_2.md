# PHASE G — AMENDMENT 12, ADDENDUM 2

Date: 2026-11-15. Written before any straddle-T timing measurement. Amendment 12 and Addendum 1 are unchanged.

## 1. FinQA table
The candidate pool and the manifest were built on finqa_evidence (768-d nomic-embed-text), which has the same rows, ids and metadata as finqa_evidence_qwen3 (1024-d Qwen3-Embedding-8B): row-count and sorted-id fingerprint 35862 rows, sha256 ef9c68f103307fff9e48ea406acba865525083b67e4537c4084fe8ebf70f391b; fingerprint of (id, evidence_key, metadata) 191e9210e2bb95481baaff68fe20740e8314d6e4c71ff60c5f2c4d69af460113. Filter selectivity and gold containment depend only on ids and metadata and therefore carry over. All FinQA retrieval in Amendment 12 runs on finqa_evidence_qwen3 with the cached Qwen3 query vectors of Amendment 1, because the query vectors are 1024-d.

## 2. Smoke test
Section 11 of Amendment 12 says 10 pairs. The smoke set is smoke_test_pairs.csv: 14 pairs (10 EDGAR, 4 FinQA), seed 20261116, excluded from analysis.

## 3. Measurement units
Fixed arms (always_exact, default_hnsw, always_iterative, vecadvisor) are measured once per (qid, pool_id) and reused wherever that pair appears in several manifests; their results do not depend on T. The router arm is measured per (qid, pool_id, T_name). The measurement of a pair that appears in the smoke set is taken from the main run, not from the smoke run.

## 4. FinQA filter execution
The where_clause strings in the manifests are descriptive. The runner builds the SQL from the parsed filter: metadata->>'ticker' = or IN (...), and metadata->>'year' IN (...) with the years of any range written out as text values, without changing src/phase_e_router/retriever.py. Before any timed session the runner checks, for every distinct FinQA and EDGAR filter in the manifests, that the executed SQL returns exactly the manifest n_rows; any mismatch stops the run. Operators differ (BETWEEN versus IN) but the selected rows are identical.

## 5. Query vectors
Two questions in the FinQA draw (DG/2007/page_67.pdf-2 and HOLX/2009/page_127.pdf-4) had no cached Qwen3 vector. Their vectors were computed on 2026-11-15 with the same model and procedure as the cached vectors, after an already-cached question was re-embedded and reproduced with cosine 0.99992053. The file is outputs/straddle_t_vectors_2026-11-15/query_embeddings_qwen3_missing2.json (SHA-256 a17ae419606b209e407b07cc3323311ff6ce5bbb4a112331cd09d31bb8e70b3e). No question was replaced.

## 6. Interpretation of clustered intervals
The primary intervals are clustered by question; filter-clustered intervals are computed for every band as well. Where the two disagree about whether an interval crosses a pass threshold, the result for that band is reported as inconclusive. This is because several bands rest on few distinct filters (primary manifests: EDGAR near_above 20, EDGAR far_above 1, FinQA near_below 19, FinQA near_above 18).

## 7. Correction
retrieve() is defined in src/phase_e_router/policy_v3_1.py (line 157) and delegates the non-band modes to src/phase_e_router/retriever.py; the arms and settings of Addendum 1 are unchanged.