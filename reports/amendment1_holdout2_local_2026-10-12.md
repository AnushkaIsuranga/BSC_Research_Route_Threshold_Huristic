# Amendment 1, second held-out test and local rerun, 2026-10-12

Nothing here involved a chat-LLM paid call or an embedding API call (cached query embeddings and the already built tables were used). Values are computed from the files named. MARGIN and P-a are still **TO FILL BEFORE PAID RUN** in `PHASE_D_AMENDMENT_1.md`.

## Commits and tags

| Step | Hash | Tag |
|---|---|---|
| 1 distinct-passage retrieval + sweep + rule | `451d868` | |
| 2 Amendment 1, runner options, stats `--margin` | `4187977` | `phase-d-amendment-1-2026-10-12` |
| 3 provenance notes (.env comment, config note, finqa_utils comment) | `dfdabe6` | |
| 4 dumps + checksums | `3d3f78a` | |
| 5 second held-out protocol frozen (+ harness, analysis) | `c01f2da` | `phase-a-holdout2-frozen-2026-10-12` |
| 5 second held-out results | `a04adc3` | |
| runner: cache lookup by query_id | `74e299a` | |
| 6 v3 local run + this report | see final message | |

## Step 1: distinct-passage retrieval (finqa_evidence_qwen3, retrieval only)

`router.retrieve(distinct=True)`: rank by (distance, id), drop repeats by `md5(content)`, over-fetch on every route (exact: SQL `DISTINCT ON (md5(content))` over the whole filtered set; index routes: `max(40, 10k)` rows, repeats dropped in Python). Tests: 95 passed at that commit (96 now). A gold hit is defined on passage text (every gold row's text among the retrieved texts), because the kept copy of a repeated passage can carry another page's id. 50 queries, `outputs/phase_d_k_sweep_distinct_2026-10-12/`.

| route | k distinct | all-gold | any-gold | mean distinct rows returned | queries under-filled | est. prompt tokens (qwen2.5) |
|---|---|---|---|---|---|---|
| exact | 6 | 21/50 | 39/50 | 6.0 | 0 | 461 |
| exact | 10 | 27/50 | 43/50 | 10.0 | 0 | 664 |
| exact | 15 | 33/50 | 46/50 | 14.8 | 2 | 931 |
| exact | 20 | 35/50 | 47/50 | 19.5 | 3 | 1188 |
| post-filter | 6 | 19/50 | 36/50 | 4.2 | 27 | 353 |
| post-filter | 10 | 20/50 | 36/50 | 5.1 | 45 | 398 |
| post-filter | 15 | 21/50 | 37/50 | 5.3 | 49 | 409 |
| post-filter | 20 | 21/50 | 37/50 | 5.3 | 50 | 410 |

**Pre-stated rule applied:** chosen k = smallest k whose exact-route all-gold hit is within 2 queries of the k = 20 value. Exact all-gold hits {'6': 21, '10': 27, '15': 33, '20': 35}; k = 20 value 35; **chosen k = 15**. Post-filter under-fills heavily (at k = 15, 49 of 50 queries return fewer than 15 distinct rows; mean 5.3), because a non-iterative HNSW scan offers at most `ef_search` = 40 candidates, many of them copies of the same passage. Correction to my earlier report: the "7-10 of 50 queries with no gold evidence at k = 20" used strict page-id matching; at passage level 3 of 50 queries retrieve no gold evidence at k = 20 on the exact route (any-gold 47/50). Token estimates use the linear fit from the earlier report (approximation).

## Step 2: Amendment 1

`PHASE_D_AMENDMENT_1.md` (tag `phase-d-amendment-1-2026-10-12`; the frozen protocol file is unchanged). Contains the reframed question (non-inferiority primary; latency superiority and cost secondary; McNemar b, c, p as before), one hosted model (Gemini 3.8 Flash) plus the local model, pilot of 5 queries then 50 x 3 x 2 with a USD 10 cap, Qwen3-Embedding-8B 1024-d via the API `dimensions` parameter (table `finqa_evidence_qwen3`; query cache SHA-256 `930cadc0bdea177b0951a6891c227606cc47a3b4a1ce8c437563635f9be9ff23`), k = 15 distinct, the tie-break, seeded arm order, the scoring rule, naive-JSON-failure scored wrong with no retry, pass 1 primary / pass 2 robustness, limitations. `paired_stats.py` now requires `--margin` (refuses without it; tested) and outputs the non-inferiority and latency-superiority checks. **Before the tag is used for a paid run, MARGIN and P-a must be filled and the file re-tagged.** Two things I added that you did not list, flagged: an open risk that Gemini's `maxOutputTokens` includes thinking tokens (256 may truncate; check in the pilot) and the sentence that non-inferiority with 50 pairs can only be shown for margins larger than the interval half-width.

## Step 3: provenance notes

The misleading item was `EMBEDDING_MODEL=qwen/qwen3-embedding-8b` in `.env` (and defaults in `finqa_utils.py` / `finqa_db_setup.py`). Added: a comment line above it in `.env` (all other lines verified byte-identical; the file is git-ignored and untracked; the key was not touched), a comment in `src/utils/finqa_utils.py`, and a note field in `config/generation.json` (this also re-formatted the JSON; values unchanged apart from the note). `docs/CODE_MANUAL.docx` already says nomic built the frozen table, so it was not changed; `finqa_db_setup.py` (your untracked file) was not edited.

## Step 4: data freeze

| file | bytes | sha256 |
|---|---|---|
| `outputs/db_dumps_embeddings_2026-10-12/finqa_evidence_nomic_prefixed.dump` | 128,303,956 | `62aaaffef253e76d4232717c2f1f77b7f62f9331c4588e68fb9c4ceaae9a71d9` |
| `outputs/db_dumps_embeddings_2026-10-12/finqa_evidence_qwen3.dump` | 140,644,882 | `f68e819987280efea81ea924f8be8ae4e5f279ee4139ff685dcbcc5cfeb563c9` |
| `outputs/embedding_build_2026-10-12/query_embeddings_qwen3.json` | 1,154,534 | `930cadc0bdea177b0951a6891c227606cc47a3b4a1ce8c437563635f9be9ff23` |
| `outputs/embedding_build_2026-10-12/query_embeddings_nomic_prefixed.json` | 527,343 | `ed4f6de7f7ff90e4006cb295ffea65607b58dece73fabe25fac882e122f443e0` |
| `outputs/phase_d_k_sweep_2026-10-12/query_embeddings_nomic_asis.json` | 526,564 | `8fc8c6b21511e6f2937511b1c29f0c5cd050d4f531b7a19200fe8c8d1b54479e` |

Added as new entries to `outputs/data_checksums.json` (88 -> 93 entries; the 88 existing entries verified unchanged against the previous commit). Dumps are `pg_dump -Fc`, one table each (the qwen3 dump was listed with `pg_restore --list`: one TABLE DATA entry); git-ignored. The distinct-sweep and v3 outputs are not in the checksum file.

## Step 5: second held-out test

Protocol frozen before any query (`PHASE_A_HOLDOUT2_PROTOCOL.md`, tag `phase-a-holdout2-frozen-2026-10-12`). P1 routes were computed from `policy.py` and `phase_a_v1/thresholds.json` with no queries (table in the protocol). Run: seed 20261017, table order ['hm_clothes_100', 'hm_clothes_75', 'hm_clothes_25', 'hm_clothes_0', 'hm_clothes_50'], vectors 40-59, commit `c01f2da`, 1,500 rows, 0 errors, 0 plans not as intended, 10:51-11:41 UTC (about 50 min). Ollama stopped, no Jupyter or python process before the start; top-5 CPU consumers before the start were BackgroundDownload 4.4%, chrome 2.7%, 1.0%, 0.9%, claude 0.3%; total CPU 11-23%. Self-test (main-run filter, vectors 0-1) matched the main run: same recall, rows and plans; forced-exact 686 / 790 ms against 825 / 882 ms. Host load at the starts of the five tables (3 one-second samples, %): run_start 10:51:42Z [30, 15, 12]; table 10:51:50Z [39, 18, 21]; table 11:01:50Z [18, 28, 17]; table 11:12:12Z [65, 31, 27]; table 11:21:48Z [3, 5, 8]; table 11:31:41Z [12, 11, 8]; run_end 11:41:17Z [5, 6, 2]. The third table start read 65%, 31%, 27% (a transient, not explained); the host load afterwards was 3-12%.

**Hypotheses (as defined in the frozen protocol):**

- **H10 (primary), policy_v2 passes all 25 cells: HOLDS (25/25).**
- H11 h2a (exploratory): **FAILS**, P1 fails 0/5 cells. Failing: none.
- H11 h2b (exploratory): **HOLDS**, P1 fails 1/5 cells. Failing: hm_clothes_75 (forced-exact): latency 523 ms.
- H11 h2c: **HOLDS**, P1 fails 4/5 cells. Failing: hm_clothes_25 (forced-exact): latency 615 ms; hm_clothes_50 (forced-hnsw): recall 0.885; hm_clothes_75 (forced-hnsw): recall 0.775; hm_clothes_100 (forced-hnsw): recall 0.660.
- H11 h2d: **HOLDS**, P1 fails 5/5 cells. Failing: hm_clothes_0 (forced-exact): latency 698 ms; hm_clothes_25 (forced-exact): latency 686 ms; hm_clothes_50 (forced-exact): latency 698 ms; hm_clothes_75 (forced-exact): latency 785 ms; hm_clothes_100 (forced-hnsw): recall 0.630.
- H11 h2e: **HOLDS**, P1 fails 5/5 cells. Failing: hm_clothes_0 (forced-exact): latency 814 ms; hm_clothes_25 (forced-exact): latency 828 ms; hm_clothes_50 (forced-exact): latency 811 ms; hm_clothes_75 (forced-exact): latency 846 ms; hm_clothes_100 (forced-hnsw): recall 0.730.
- **H12, P4 fails latency in all 15 cells with s >= 0.30: HOLDS (15/15).** Exploratory cells (s < 0.30, no claim): P4 latency hm_clothes_0 x h2a 454.7 ms; hm_clothes_0 x h2b 490.7 ms; hm_clothes_25 x h2a 437.4 ms; hm_clothes_25 x h2b 478.4 ms; hm_clothes_50 x h2a 435.7 ms; hm_clothes_50 x h2b 485.8 ms; hm_clothes_75 x h2a 447.2 ms; hm_clothes_75 x h2b 523.4 ms (over 500); hm_clothes_100 x h2a 466.0 ms; hm_clothes_100 x h2b 483.9 ms (see the full table in `reports/holdout2_results_2026-10-12.md`).

| policy | passed of 25 | passed of the 15 confirmatory cells |
|---|---|---|
| P1 v1 matrix | 10/25 | 1/15 |
| P4 always forced-exact | 9/25 | 0/15 |
| P5 always forced-hnsw | 7/25 | 7/15 |
| P6 always iterative-relaxed | 25/25 | 15/15 |
| policy_v2 (T = 0.1) | 25/25 | 15/15 |

Notes: policy_v2 and P6 are the same policy on these filters (both choose iterative-relaxed everywhere, s >= 0.23), so their identical counts are one result, not two. H11 and H12 are about the failure of other policies; they do not test policy_v2. The latency prediction (about 1.95 ms per 0.001 selectivity from the quiet rerun) predicted forced-exact at about 450 / 500 / 635 / 735 / 870 ms for h2a-h2e; measured P4/P1 forced-exact medians were about 436-466 / 478-523 / 615 / 686-698 / 814-828 ms, i.e. the extrapolation was 3-7% high at h2c-h2e and in range at h2a-h2b. H11 for h2a failed as the protocol anticipated (exploratory): forced-exact stayed under 500 ms on all five tables. The one failing P1 cell on h2b (hm_clothes_75, 523 ms) is 23 ms over the SLA. Per-cell recall and latency for every arm are in `reports/holdout2_results_2026-10-12.md`.

## Step 6: local rerun with Amendment 1 settings (`outputs/phase_d_local_2026-10-12_v3/`)

qwen2.5:7b (digest `845dbda0ea48`, Ollama 0.40.2), table `finqa_evidence_qwen3`, cached Qwen3 query embeddings (sha256 `930cadc0bdea177b...`), k = 15, distinct = True, tie-break, seeded arm order, DM tier hm_clothes_0, 50 queries x 3 arms x 2 passes = 300 rows, 0 errors, commit `74e299a`, cost 0.

**Per arm, pass 1:**

| arm | correct/50 | retrieval hit, passage level (primary) | strict (query_id, key) hit | parse failures | route parse failures | routes | mean rows returned by route |
|---|---|---|---|---|---|---|---|
| naive_llm | 12 | 0.62 | 0.22 | 1 | 0 | {'post-filter': 10, 'pre-filter': 40} | post-filter: 4.7, pre-filter: 14.8 |
| decision_matrix | 12 | 0.66 | 0.22 | 2 | 0 | {'pre-filter': 50} | pre-filter: 14.8 |
| policy_v2 | 13 | 0.66 | 0.22 | 2 | 0 | {'exact': 50} | exact: 14.8 |

Naive-arm post-filter share: **10/50 = 20%** (12 Oct: 11/50; 1 query changed route). All 10 post-filter queries returned fewer than 15 rows (mean 4.7). DM and policy_v2 routes identical on 50/50 queries.

**Paired tests, pass 1** (X vs Y; b = X only correct, c = Y only correct):

| X vs Y | b | c | exact McNemar p | accuracy diff X-Y | 95% CI (Newcombe, paired) | total-latency diff X-Y, ms | 95% CI (paired bootstrap, 10,000, seed 20261012) |
|---|---|---|---|---|---|---|---|
| decision_matrix vs naive_llm | 0 | 0 | 1.000 | +0.000 | [-0.037, +0.037] | -507 | [-604, -407] |
| policy_v2 vs naive_llm | 1 | 0 | 1.000 | +0.020 | [-0.030, +0.073] | -600 | [-677, -518] |
| decision_matrix vs policy_v2 | 0 | 1 | 1.000 | -0.020 | [-0.073, +0.030] | +93 | [+18, +167] |

**Where the primary CI falls against example margins (information only; the real margin is yours):** policy_v2 - naive = +0.020, lower bound -0.030. Against 0.05: above -0.05; 0.10: above -0.10; 0.15: above -0.15. (The stats script was run with `--margin 0.10` only because the argument is required; the same lower bound applies to any margin.) With b + c = 1 the interval is narrow; this reflects how few queries differ between arms, not a precise accuracy for the arms. Latency superiority: the policy_v2 - naive CI excludes 0 (in favour of policy_v2); cost is 0 for the local model.

**Latency split, pass 1 (ms, median [IQR]) and tokens:**

| arm | DB | router | generation | total | mean input tokens |
|---|---|---|---|---|---|
| naive_llm | 14.0 [46.1] | 526.4 [101.0] | 164.5 [244.9] | 762.6 [349.7] | 818 |
| decision_matrix | 13.6 [10.5] | 0.0 [0.0] | 291.0 [344.7] | 310.0 [365.9] | 930 |
| policy_v2 | 13.3 [3.0] | 0.0 [0.0] | 135.4 [162.8] | 150.4 [161.0] | 930 |

Embedding time is 0 in every arm in this run because query vectors come from the cache (12 Oct: median about 17-19 ms of local nomic embedding), so total latencies are not directly comparable with 12 Oct.

**Order/caching effect in the latency data (new, not anticipated):** median generation time by arm position within a query is position 1: 462 ms, position 2: 132 ms, position 3: 137 ms. The arm that runs first for a query is about 3.5x slower than the arms that follow, whichever arm it is (e.g. DM first 463 ms, DM second 131 ms; policy_v2 first 454 ms, second 132 ms), consistent with Ollama reusing the already evaluated prompt when DM and policy_v2 (and naive on its pre-filter route) send an identical prompt; I did not test that explanation. Because randomised order balances positions only on average (DM ran before policy_v2 in 34 of 50 queries), the DM vs policy_v2 total-latency difference (+93 ms) and any per-arm generation-time comparison are confounded by position and should not be read as an arm effect. The policy_v2 vs naive latency difference is dominated by the naive router's own LLM call (median 526 ms) and is much larger than this effect.

**Pass 1 vs pass 2 agreement (same query, same arm; target for answers was 50/50):**

| arm | same answer | same route | same correctness | 12 Oct same answer |
|---|---|---|---|---|
| naive_llm | 49/50 | 50/50 | 50/50 | 50/50 |
| decision_matrix | 46/50 | 50/50 | 49/50 | 47/50 |
| policy_v2 | 48/50 | 50/50 | 49/50 | 49/50 |

The 50/50 answer target is **not met** (naive 49, policy_v2 48, DM 46). The tie-break did not remove the pass-to-pass differences, as expected from the earlier finding that the rows were already identical between passes.

## Comparison with the 12 Oct local run (pass 1)

| | 12 Oct | v3 |
|---|---|---|
| decision_matrix correct | 11/50 | 12/50 (gained 7 queries, lost 6) |
| policy_v2 correct | 11/50 | 13/50 (gained 8 queries, lost 6) |
| naive_llm correct | 11/50 | 12/50 (gained 8 queries, lost 7) |
| all-gold retrieval hit (DM) | 12/50 (strict pairs) | 33/50 passage level; 11/50 strict |
| mean input tokens (DM) | 475 | 930 |
| naive post-filter | 11/50 | 10/50 |
| policy_v2 - naive, accuracy | +0.000 [-0.067, +0.067] | +0.020 [-0.030, +0.073] |

What the data show, and what they do not:

- The evidence in the prompt changed a great deal: passage-level all-gold retrieval is 33/50 for DM and policy_v2 (the Step 1 sweep value at k = 15) against 12/50 on 12 Oct, and the prompt grew from about 475 to about 930 input tokens. Accuracy changed by +1, +2 and +1 queries net. Per arm, 6-8 queries became correct and 6-7 became wrong, so the answers changed on many queries (more than pass-to-pass noise, which flips 0-1 correctness labels per arm), but the changes cancel. For qwen2.5:7b, more and better evidence did not raise accuracy here. This run cannot say which of the amendment items (embedding, k, distinct, order) caused individual changes; they were changed together.
- Naive routing barely changed (10 vs 11 post-filter; 1 route differs): the router prompt and model were unchanged, and the router sees only the question.
- The two deterministic arms differ by one query (policy_v2 13, DM 12) although they send the same prompt; this is generation nondeterminism, consistent with the pass-agreement table.
- Parse failures of the answer: DM 2, policy_v2 2, naive 1 (12 Oct: 3, 3, 2); no naive-router JSON failures in either run.
- `distinct_dropped` is 0 for the exact route by construction (the SQL `DISTINCT ON` does not report what it dropped).

## Uncertain or unexpected

- Order effect on generation latency (above). Not previously visible because arm order was fixed or rotated; it affects any hosted-model latency comparison too if the provider caches prompts.
- policy_v2 passes 25/25 here (first held-out test: 24/25 in the original run, 25/25 in the quiet rerun), but on this test it is the same policy as always-iterative (P6); the test shows iterative-relaxed passes at s = 0.23-0.45, not that the threshold T = 0.1 is right beyond that.
- The run of the third table in held-out 2 started during a CPU spike (65% in one sample); its results do not look different from the others (no failing policy_v2 cell), but I did not test for an effect.
- Pass-to-pass answer differences of the local model remain unexplained.
- I did not touch the open DECISION items (router design), MARGIN or P-a.
