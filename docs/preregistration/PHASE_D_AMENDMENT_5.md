# Phase D, Amendment 5: hallucination-oriented breakdown of wrong answers (existing outputs only)

**Status:** written 2026-10-23, committed and tagged `phase-d-amendment-5-2026-10-23` **before any classification was computed.** It adds an analysis of existing outputs; it does not change, re-analyse or supersede any result of Amendments 1-3 or any earlier protocol (those files are unchanged). **No model call, no API call (cost USD 0), no database write.** The only database access is read-only `SELECT`s of evidence text for the manual validation sheet.

**Why.** The supervisor asked that hallucination be measured, not only accuracy. The logged fields allow a proxy: a wrong answer given although the gold evidence was not (fully) in the prompt, versus a wrong answer given with the gold evidence present. This amendment pre-registers the classes, the comparisons and a blind manual validation before any of them is computed.

## 1. Field used for "gold evidence retrieved" (decision of the user, 2026-10-23)

- **Runs with `retrieval_hit_passage`** (everything from the Amendment 1 retrieval onward: Gemini full run, local v3, v4, v5): `retrieval_hit_passage` (every gold row's text is among the retrieved passage texts) is the grounding field. It is the primary retrieval metric under Amendment 1. Reason: with distinct retrieval the kept copy of a repeated passage can carry another page's id, so the strict page-id field `retrieval_hit` is 0 in many rows whose gold passage text was in the prompt (read-only count before this decision: `retrieval_hit` = 0 with `retrieval_hit_passage` = 1 in 423 of 1,000 Gemini rows, 430 of 1,000 local v5 rows, 172 of 400 local v4 rows; the reverse never occurs).
- **The 12 Oct local baseline** (`outputs/phase_d_local_2026-10-12`, nomic embeddings, k = 6, non-distinct): its rows contain only the strict `retrieval_hit`, so **`retrieval_hit` is used for that run.** Its retrieval was non-distinct, but copies of a passage under other page ids still count as misses there, so its ungrounded rates are not comparable with the other runs'.
- `retrieval_hit` stays in every classified file as a reported sensitivity column. **Sensitivity table (once per run):** the same class counts computed with the strict `retrieval_hit`, labelled "strict page-id test, shown for transparency only".
- **Stop-on-null rule:** if the grounding field is missing or null in any row, the script stops and reports the row; it does not guess or fill.

## 2. Row classes

Assigned in this order, per arm × question × pass, from logged fields only (`correct` = the primary scoring rule of Amendment 2):

1. `correct`: `correct == 1`.
2. `abstain_or_parse_fail`: `correct == 0` and `parse_failure == 1` (no number parsed; includes "the evidence does not contain…").
3. `wrong_ungrounded`: `correct == 0`, `parse_failure == 0`, grounding field `== 0`.
4. `wrong_grounded`: `correct == 0`, `parse_failure == 0`, grounding field `== 1`.

Also reported: `correct_ungrounded` (`correct == 1` and grounding field `== 0`), a sub-count of `correct`, not a fifth class.

**Naming.** `wrong_ungrounded` is a **proxy** for hallucination, not proof of fabrication (the number may be derivable from other retrieved passages, or from gold evidence that was retrieved under a different text). Reports call it "ungrounded wrong answer (hallucination proxy)". The word "hallucination" is used for it only after the blind manual validation of section 4 supports it.

## 3. Analyses (each model separately, never pooled across models)

Runs analysed, each on its own: Gemini 3.8 Flash full run (`outputs/phase_d_gemini_full_2026-10-12`, 4 arms × 50 questions × 5 passes), local qwen2.5:7b v5 (5 passes), v4 (2 passes), v3 (3 arms, 2 passes) and the 12 Oct baseline (3 arms, 2 passes). The pilot and smoke runs are not analysed.

1. **Counts and rates** per arm and per pass, with Wilson 95% CIs; pooled over the available passes.
2. **Paired comparison policy_v2 vs naive_llm per question** of the rate of `wrong_ungrounded`, of `wrong_grounded` and of `abstain_or_parse_fail`: pass 1 with the exact McNemar test and the discordant counts; pooled over passes with a paired bootstrap over questions (10,000 resamples, seed 20261012) of the per-question mean class indicator. Descriptive, **pre-specified, secondary**; no margin and no non-inferiority claim; no multiplicity correction.
3. For `naive_llm` and `naive_informed`: the same breakdown split by the chosen route (pre-filter vs post-filter), with the mean number of rows returned (pass 1 and pooled).
4. `rows_returned` of the `wrong_ungrounded` rows (how many are 0-row cases; distribution; by arm).

## 4. Blind manual validation sample

- **Source:** Gemini full run, pass 1, all arms. Seed **20261023**. Random draw (rows sorted by question id and arm, then `random.Random(20261023)`) of up to 20 `wrong_ungrounded` and up to 20 `wrong_grounded` rows (all of them if fewer), classes as defined in sections 1-2.
- **Labelling sheet** (`labelling_sheet.csv`): `sample_id`, `question`, `gold_answer`, `model_answer` (the raw output), and the full text of every retrieved passage (read-only `SELECT` by `retrieved_ids` from `finqa_evidence_qwen3`, in prompt order). It does **not** contain the proxy class, the arm or the route. Rows are shuffled.
- **Key file** (`labelling_key.csv`, separate): `sample_id` → `query_id`, `arm`, `pass`, proxy class.
- **Human label** (entered by the user): **S** = the answer number appears in the retrieved text; **C** = the answer can be calculated from numbers in the retrieved text; **N** = the answer is not supported by the retrieved text.
- **After the user returns the labels:** a confusion table of proxy class vs human label (N = "unsupported"; S and C = "supported"). It is **not** computed before the labels arrive.

## 5. Not in this amendment

No scale-up (1,075 question) data, no new model runs, no LLM judge, no change to prompts, scoring or retrieval. Amendment 4 (scale-up) is unaffected and has not been run beyond the aborted smoke test.

## 6. Implementation and outputs

`src/phase_d_validation/hallucination_classify.py` (generic: takes a `results.jsonl` and an explicit grounding field; usable unchanged on a later scale-up output) and `tests/test_hallucination_classify.py`. Outputs go to `outputs/hallucination_classification_2026-10-23/` (classified rows per run as CSV, summary tables as CSV/JSON, labelling sheet and key) and `reports/hallucination_classification_2026-10-23.md`; all new outputs are added as new entries to `outputs/data_checksums.json`.

## 7. Limitations (stated before the analysis)

- The classes are a proxy built from logged fields; "ungrounded" depends on the retrieval-hit definition, and a model can answer correctly or wrongly from partial evidence.
- Passage-level hit compares the gold row text with the retrieved texts; near-duplicates with different text count as misses.
- The abstain/parse-failure class contains every answer without a parsed number, including answers cut off by a token limit.
- One hosted model and one local model; 50 questions; the comparisons are secondary, with no multiplicity control; five passes of identical inputs measure generation noise, not new data.
- The 12 Oct baseline uses a different retrieval setup and the strict field; it is shown for continuity only.
