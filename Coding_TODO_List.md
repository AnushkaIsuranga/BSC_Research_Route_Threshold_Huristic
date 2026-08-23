# Coding TODO List — Benchmarking Filtered Vector Selectivity
**As of:** 17 Aug 2026 (Week 6 of 17)
**Already done:** pgvector + Docker setup ✅ | 5 correlation-level datasets (25/50/75/100% scrambled + baseline) ✅ | Initial low-level ef_search vs. latency/recall plot ✅

This list is sequenced by **dependency**, not just calendar week — build things in this order so later scripts have what they need. Each item is tagged with its source (Proposal = core methodology, Tier 1/2 = from the evaluation doc) and rough effort.

---

## Phase A — Sweep Infrastructure (build this first — everything downstream depends on it)

- [ ] **1. SQL filter generator** — Python script that programmatically generates metadata filters (`WHERE` clauses) at *controlled, known selectivity ratios* against your H&M dataset. *(Proposal — core)*
  - Needs to work across all 5 correlation tables you've already built.
  - **Tier 1 #3:** bias the generator so it produces a higher density of filters in the **0.01%–5% selectivity range**, not evenly spread 10/20/30%. Set this now — retrofitting after the sweep runs means re-running it.

- [ ] **2. EXPLAIN ANALYZE wrapper** — function that runs a query with `EXPLAIN (ANALYZE, FORMAT JSON)`, executes it, and parses the plan. *(Proposal — core)*
  - Extract **Actual Execution Time**, not the planner's Estimated Cost (this is the "bypass cost-model bias" point from Mandarapu & Kunkunuru — already your design, just implement it this way).
  - **Tier 1 #2:** split the parsed latency into two numbers — **Filter Execution Time** vs. **Graph Traversal Time** (look for the filter node vs. the index-scan node in the JSON plan tree).
  - **Tier 1 #4:** also extract and log which **scan strategy** PostgreSQL actually chose (`Index Scan` / `Bitmap Heap Scan` / `Seq Scan`) so you can tell a genuine HNSW fragmentation apart from the optimizer just picking a bad plan.

- [ ] **3. Recall Score calculator** — compare the ANN-retrieved top-k against a ground-truth exact-kNN result set (brute-force) for the same filtered query, output Recall@k. *(Proposal — core)*
  - You need exact ground truth once per query; cache it, don't recompute every repeat.

- [ ] **4. Logging schema** — decide the row structure now, before you run anything at scale. Suggested columns: `correlation_level, selectivity_ratio, filter_time_ms, graph_time_ms, total_latency_ms, recall_score, scan_strategy, run_number`.
  - CSV is fine and free — no need for a separate DB.

- [ ] **5. Selectivity Sweep Loop orchestrator** — ties 1–4 together: for each correlation table × each generated filter, run the query **5 times**, take the median, write a row. *(Proposal — core, this is your Week 7–9 deliverable)*
  - Include a re-run/retry path for anomalous results (proposal already calls for this).

---

## Phase B — Agentic Router (can be built in parallel with Phase A — different codebase)

- [x] **6. LangGraph skeleton** — basic graph with a routing node and two execution branches (pre-filter path, post-filter path), wired to GPT-4o-mini for the eventual PoC. *(Proposal — core, this is your current Week 5–6 task)*

- [x] **7. Decision Matrix lookup function** — once Phase A gives you thresholds (recall<90%, latency>500ms boundaries per correlation level), this becomes the actual routing rule the graph calls. You can stub this now with placeholder thresholds and swap in real numbers after Phase C.

- [x] **8. Hysteresis buffer** — *(Tier 1 #1)* — when a query's estimated selectivity lands within a small margin of a threshold boundary, force the router to the safer strategy instead of re-evaluating fresh each time. This is a small addition to item 7 — build it into the same function, don't bolt it on separately later.

- [x] **9. Naïve Router baseline** — a second, simpler router variant with no Decision Matrix — just lets the LLM decide the execution path itself. This is your Phase 2 comparison baseline. *(Proposal — core)*

- [x] **10. Multi-query orchestration logging** — *(Tier 2 #6, optional)* — instrument the Naïve Router to detect/count when it splits a multi-evidence question into multiple sub-queries, and log the extra API round-trips. Cheap to add once #9 exists — skip if #9 alone is taking full effort.

---

## Phase C — Statistical Analysis (after Phase A produces data, ~Week 10–12)

- [x] **11. Threshold-detection script** — scans your Phase A output to find, per correlation level, exactly where recall crosses below 90% and where pre-filter latency crosses above 500ms.

- [ ] **12. Extend your existing scatter plot** — you already have a low-level ef_search vs. latency/recall plot; extend/replicate it as the dual-axis (latency + recall vs. selectivity) plot per correlation level called for in your proposal's Data Analysis section.

- [ ] **13. Decision Matrix builder** — turn the thresholds from #11 into the actual lookup table/function that #7 in Phase B will use for real (replacing the placeholder).

---

## Phase D — Validation / Baseline Comparison (~Week 12–14)

- [ ] **14. FinQA subset loader** — pull the 50-query stratified sample (single/dual/multi-evidence) using the dataset's own gold evidence annotations, as specified in your proposal.

- [ ] **15. End-to-end comparison runner** — run the same 50 queries through both routers (Decision Matrix vs. Naïve), capture End-to-End Latency, API Token Cost, and Numeric-Answer Error Rate.

- [ ] **16. Confidence interval calculator** — 95% CI on latency reduction and error-rate reduction, per your proposal's stated stats plan.

---

## Optional / only if time allows

- [ ] **Negative-correlation dataset variant** — *(Tier 2 #5)* a 6th scrambled table where metadata is deliberately anti-correlated with vector clusters, not just randomly shuffled. Build alongside your existing correlation tables if you revisit that script — don't reopen it just for this.
- [ ] **Expand the ef_search sweep** — you've already got a low-level version; widening it to more parameter combinations is a nice-to-have, not required. Treat as a "future work" line if time runs short.

## Explicitly skip / don't build into core sweep
- **Multi-attribute disjunction filter generation** (flagged in the evaluation doc as scope-risk) — don't add this to item 1's generator. If you want to gesture at it, do one small standalone script later as a labeled side-test, not part of the main sweep.

---

### Suggested build order this week
Given you're at the start of Week 6 with the router only started: I'd sequence it **2 → 1 → 3 → 4 → 5**, then **6 → 7 → 8 → 9**, since Phase A's output (real thresholds) is what makes the Decision Matrix in Phase B meaningful rather than a stub. If the router needs to visibly exist earlier for demo purposes, build 6 now with hardcoded placeholder thresholds and wire in real ones once Phase C finishes.
