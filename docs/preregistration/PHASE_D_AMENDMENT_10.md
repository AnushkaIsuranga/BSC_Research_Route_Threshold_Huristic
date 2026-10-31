# Phase D, Amendment 10: always_hnsw answer arm on the frozen 50 FinQA questions

**Status:** written 2026-10-31, committed and tagged `phase-d-amendment-10-2026-10-31` **before any model call** of this amendment. It adds one arm and a drift reference; it changes no earlier result, file or tag. Budget cap for everything below: **USD 1.50** (`--allow-paid --budget-usd`).

## Why

PostgreSQL's planner chose exact (`Limit/Sort/Seq Scan`) for all 50 frozen questions (Amendment 7 Step 1, A6 planner_iterative: exact 50, 0 differences from policy_v2), so "planner default" is identical to policy_v2 and needs no run. The arm not yet measured is the **no-routing index path**: always use the HNSW index with the filter. Amendment 7 Step 1 showed forced HNSW returning 0-13 distinct passages on 49/50 questions (median 5; Amendment 1's sweep: mean 5.3), but no answers were generated from it.

## Arm and settings (as the frozen Gemini run, `outputs/phase_d_gemini_full_2026-10-12/`, commit `8ac3033`)

- **always_hnsw:** every question uses `router.retrieve(route="post-filter", distinct=True)`, the route naive_llm used when it chose post-filter in the frozen run: `enable_indexscan = on`, `enable_seqscan = off`, `hnsw.iterative_scan = off`; table `finqa_evidence_qwen3` (35,862 rows, Qwen3 1024-d, HNSW m 16 / ef_construction 64, **L2** `<->`); `hnsw.ef_search = 40`; filter `metadata->>'ticker' = ... AND metadata->>'year' = ...`; **k = 15 distinct passages** (Amendment 1: dedupe by md5(content), over-fetch max(40, 10k) = 150 rows, (distance, id) tie-break in Python). Query vectors from `outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json` (SHA-256 checked). No guard, no fallback: whatever the index returns, including 0 rows, goes to the prompt.
- **Answer model:** Gemini 3.8 Flash, `ANSWER_SYSTEM` prompt and user message unchanged, max output 2,048 tokens, thinking_level LOW, temperature 0 (`config/generation.json`, unchanged since `8ac3033`), price table `config/prices.json` (content unchanged since `8ac3033`). **5 passes.**
- **Drift reference:** in the same session, **1 pass of policy_v2** (exact, as stored) on the same 50 questions.
- **Order:** the 300 items (always_hnsw 5 x 50, policy_v2 1 x 50) are shuffled together with `random.Random(20261031)` (arm and question order). Single attempt per call, no pacing (as the frozen run); an error stops the run, which is resumed manually and logged.
- Runner `src/phase_d_validation/always_hnsw_runner.py` (new); it reuses the frozen runner's record builder and scoring. Code changed since `8ac3033` and disclosed: Amendment 4 strict-label rule (strict undefined when the gold answer carries a scale word) and Amendment 4 Addendum 1 run control (explicit single-attempt Gemini client, optional pacer, unused here). Primary scoring code is unchanged.

## Pilot

5 questions drawn with `random.Random("20261031-pilot")` from the frozen 50 (sorted ids), always_hnsw only, 1 pass, separate folder; rows retrieved, answers and cost reported; **excluded from analysis**.

## Scoring and analysis

- Primary: Amendment 2 scale-word rule; strict reported alongside (questions with a strict-undefined gold excluded from strict comparisons only).
- Amendment 5 classes (`correct`, `abstain_or_parse_fail`, `wrong_ungrounded`, `wrong_grounded`; grounding field `retrieval_hit_passage`) per arm, as a **proxy**. Known overstatement (Addendum 1/2 label check): of 20 sampled `wrong_ungrounded` rows only 6 were unsupported by the retrieved text (14 calculable from it), so `wrong_ungrounded` is not a fabrication count.
- **Comparisons (all descriptive, secondary, no margin, no multiplicity correction):** always_hnsw vs stored policy_v2 (primary reference, all 5 stored passes) and vs stored naive_llm, paired by question: pass 1 exact McNemar (always_hnsw pass 1 vs stored pass 1) with Newcombe 95% CI; pooled over 5 passes, paired bootstrap of per-question mean correctness (10,000 resamples, seed 20261012, as Amendment 3).
- **Drift rule:** agreement of the new policy_v2 pass with stored policy_v2 pass 1 (same correctness label; same raw answer) is reported. **If more than 5 of 50 correctness labels differ,** this is reported and always_hnsw is compared against the drift-reference pass instead of the stored policy_v2, stated as such.
- Also: rows retrieved distribution, `retrieval_hit_passage` rate, 0-row questions (counted, answers listed), cost, latency (`total_ms`, descriptive only; the machine is in use by the author, CPU recorded at start and end, no quiet rule).

## Predictions (stated before any call)

always_hnsw returns fewer than 15 distinct passages on most questions; its gold-passage hit rate is lower than policy_v2's; its accuracy is lower than policy_v2's; it has more wrong answers whose gold passage was not retrieved (`wrong_ungrounded`). Questions with 0 rows are counted and their answers listed.
