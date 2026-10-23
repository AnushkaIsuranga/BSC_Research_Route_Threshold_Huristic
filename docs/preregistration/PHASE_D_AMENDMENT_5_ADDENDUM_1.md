# Phase D, Amendment 5, Addendum 1 (second version)

**Status:** written 2026-10-23, committed and tagged `phase-d-amendment-5-addendum-1-2026-10-23` **before any label was used** (no confusion table, count or share has been computed from the labels). It amends `docs/preregistration/PHASE_D_AMENDMENT_5.md` (tag `phase-d-amendment-5-2026-10-23`, not edited). It **supersedes the first version of this addendum** (commit `2dbfc72`, same day, never used): that version added an empty column to a new sheet `labelling_sheet_v2.csv`; the user decided it is not needed. `labelling_sheet_v2.csv` is withdrawn and not used; it is left in place and in the history because nothing is deleted before the final cleanup. The tag was moved from `2dbfc72` to the commit of this version. Everything else of Amendment 5 stands (grounding field, classes, the 40-row sample from the Gemini full run, pass 1, seed 20261023, naming rule for "hallucination"). No model call, no API call, no database write.

## 1. Source of the labels and its verification

The labels are in `outputs/hallucination_classification_2026-10-23/labelling_sheet_check.csv` (the user's labelled copy; columns `check` = S / C / N and `gold_derivable` = Y / N). Before use it is verified against the committed `labelling_sheet.csv` (commit `5327010`, SHA-256 `84b841fc5e5dd11388a3fc8ada7cc10efe915731b645806097d94001b70694ed`): same 40 rows in the same order; `sample_id`, `question` and `retrieved_passages` identical in 40/40 rows. `gold_answer` (6 rows) and `model_answer` (11 rows) differ **only in number formatting introduced by the spreadsheet application** (e.g. `9.2%` -> `9.20%`, `$ -61.1` -> `($61.10)`, thousands separators, a trailing space); all 17 differing cells are numerically equivalent. The committed sheet remains the reference for the texts; the two label columns are joined to `labelling_key.csv` by `sample_id`. Accepted values: `check` in {S, C, N}, `gold_derivable` in {Y, N}; any other or empty value stops the analysis.

## 2. The added column and the two confusion tables

`gold_derivable`: **Y** = the gold answer can be obtained from the retrieved passages of that row, directly or by calculation; **N** = it cannot. Two tables, each with the two proxy classes (`wrong_ungrounded`, `wrong_grounded`) as rows: **(1)** proxy class vs S/C/N as pre-registered (N = "unsupported"; S and C = "supported"), **(2)** proxy class vs `gold_derivable`. Reason: S/C/N records where the model's number came from, not whether the correct answer was available. Counts with row shares and Wilson 95% CIs, descriptive, no test, no validation threshold.

## 3. Rows with notes

Rows whose note mentions rounding, scale, a suspected gold error, or a count-versus-percentage mismatch are counted separately (case-insensitive keyword match on the note text: `round`; `scale`, `million`, `thousand`; `gold` together with `error`, `wrong` or `incorrect`; `count` together with `percent`, `%` or `percentage`). Descriptive only; no change to the scoring rule. The attached file contains no note text (its `check` column holds one letter per row), so unless a note column is supplied this count is reported as not available.

## 4. Counts per row and per distinct question

Every table is given per row (40 rows) and per distinct question (17 questions, one `query_id` each). Per-question rule, fixed here: a question is counted once in each (proxy class, label) cell in which at least one of its rows falls, so a question can appear in more than one cell and cell totals can exceed 17; the number of distinct questions per proxy class is reported next to the table.

## 5. Not in this addendum

No new sample, no change to classes or scoring, no cross-tabulation of S/C/N against `gold_derivable`, no conclusion about the word "hallucination" (stated with the results, after reading them).
