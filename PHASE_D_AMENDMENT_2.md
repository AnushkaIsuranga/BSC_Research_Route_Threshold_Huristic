# Phase D, Amendment 2

**Status:** written 2026-10-12, tagged before any run under it. Amends `PHASE_D_AMENDMENT_1.md` (tags `phase-d-amendment-1-2026-10-12`, `-filled-2026-10-12`, `-filled-v2-2026-10-12`; none edited) and, through it, `PHASE_D_LLM_PROTOCOL.md`. Everything not mentioned here stays as in Amendment 1, including MARGIN = 0.10, P-a = 10%, k = 15 distinct, the Qwen3 table and cached query embeddings, the tie-break, seeded arm order, 2048 max output tokens, `thinking_level=LOW`, pass 1 primary / pass 2 robustness.

**Origin of items 1a and 1b.** Both were prompted by the 5-query Gemini 3.8 Flash pilot (`outputs/phase_d_gemini_pilot_2026-10-12`, `reports/gemini_pilot_2026-10-12.md`). **The pilot rows are excluded from every analysis.** What the pilot showed: (a) Gemini appended units to answers (`$18.75 million`), which the Amendment 1 rule scores as unparseable; (b) the frozen naive router prompt gave `post-filter` on 4 of 5 queries, with reasons of the form "no ticker or fiscal year was specified in the query". These two decisions are therefore made after seeing 5 pilot rows, and are labelled as such here; neither was tuned on accuracy.

## 1a. Scoring: primary and strict rules

- **Primary rule (reported as the main accuracy):** the Amendment 1 rule (section 6: `|p − g| ≤ max(0.01·max(|p|,|g|), 1e-9)`, percent sign stripped and compared on the percent scale, `$` / commas / accounting negatives / ratios as before, boolean gold matches yes/no/true/false) **plus**: a trailing scale word **million, billion, thousand, mn, bn, m or k**, case-insensitive with an optional final period, is stripped **without rescaling**. Currency symbols and signs behave as before: `$18.75 million` → 18.75; `-$0.5 million` → -0.5; `(5.2) million` → -5.2. A value is never multiplied: `$18.75 million` does not match a gold of `18750000`.
- **Strict rule (secondary, reported alongside):** exactly the Amendment 1 rule; text such as `$18.75 million` is unparseable, scored wrong and flagged `parse_failure`.
- Both labels (`correct`, `correct_strict`) and both parse-failure flags are stored in every result row; `paired_stats.py --rule primary|strict` selects which is analysed. Unit tests: `tests/test_scoring.py` (scale words, signs, no rescaling, garbage still rejected, strict rejects scale words).
- The primary rule is more lenient than strict only for answers that carry a scale word; for every other answer the two rules agree.

## 1b. New arm `naive_informed` (secondary)

- Same router model, same JSON schema (`{"route": "pre-filter"|"post-filter", "reason": str}`), same no-retry / no-default / scored-wrong-on-schema-failure rule as `naive_llm`, same answer model and settings. **Only the router prompt differs:** the user message also states the metadata filter that will be applied (the ticker and year that the pipeline derives from the query id), **without selectivity and without row counts.**
- `naive_llm` keeps the frozen prompt (`NAIVE_ROUTER_SYSTEM` is unchanged) and **remains the pre-registered primary comparison**. `naive_informed` is secondary.
- **Exact prompt text** (`src/phase_b_router/router.py`):

  *`naive_llm` system message (frozen), user message `Question: {question}`:*
  ```
  You are the router of a vector database. Decide how to apply a metadata filter (company ticker and fiscal year) to the vector search for the user's question. 'pre-filter' applies the filter first and searches only the matching rows; 'post-filter' searches the whole index first and applies the filter afterwards. Reply with JSON only, exactly: {"route": "pre-filter" or "post-filter", "reason": "<one short sentence>"}
  ```
  *`naive_informed` system message (the frozen text plus one sentence):*
  ```
  You are the router of a vector database. Decide how to apply a metadata filter (company ticker and fiscal year) to the vector search for the user's question. 'pre-filter' applies the filter first and searches only the matching rows; 'post-filter' searches the whole index first and applies the filter afterwards. Reply with JSON only, exactly: {"route": "pre-filter" or "post-filter", "reason": "<one short sentence>"} The metadata filter that will be applied is stated before the question.
  ```
  *`naive_informed` user message (example for query `ADI/2011/page_61.pdf-1`):*
  ```
  Metadata filter to be applied: ticker = ADI, year = 2011
  Question: <the question text>
  ```
- Reporting for the secondary arm: accuracy and McNemar (b, c, p) for policy_v2 vs naive_informed with the **same non-inferiority check (MARGIN 0.10)** (lower bound of the 95% Newcombe CI of accuracy(policy_v2) − accuracy(naive_informed) above −0.10), its latency CI, its post-filter share, and the same fields for decision_matrix vs naive_informed. No claim is made from the secondary comparison that overrides the primary one. The runner's default arm set is now four arms (`decision_matrix`, `policy_v2`, `naive_llm`, `naive_informed`), shuffled per (pass, query) with the same seed rule.

## 1c. P-a

**P-a stays at 10%** (5 of 50 queries routed to `post-filter` by the Gemini naive router with the frozen prompt), range 0-25%, as pre-registered. Recorded: the 5-query pilot showed `post-filter` on 4 of 5 queries with the frozen prompt. P-a is not changed. The post-filter share of `naive_informed` is reported separately and has no pre-registered value.

## 2. Reporting added for the Gemini run

For the full Gemini run (50 queries × 4 arms × 2 passes; budget cap USD 5): primary = policy_v2 vs naive_llm, pass 1, primary scoring rule, `--margin 0.10`; secondary = policy_v2 vs naive_informed, strict-rule results for every pair, decision_matrix vs naive_llm, latency by arm position, cached tokens, post-filter shares against P-a, truncations (finish reason MAX_TOKENS), thinking-token statistics, total cost.

## 3. Derived re-scoring of earlier outputs

Every earlier Phase D output (30 Sept, 12 Oct, local v3, Gemini pilot) is re-scored under both rules into new derived files (`outputs/rescored_2026-10-12/`); raw files are not altered. Original labels in the old files were produced under the Amendment 1 / earlier scorer and are unchanged.

## 4. Limitations added

- The primary scoring rule was chosen after seeing 5 pilot answers; the strict rule is reported alongside for that reason.
- The informed router sees the same question text plus the ticker and year; it is a stronger baseline than the frozen router, not a replacement for it.
- Gemini thinking length varies from 0 to about 500 tokens per call at `thinking_level=LOW` and is not deterministic at temperature 0 (pilot), so cost and latency have a wide spread.
