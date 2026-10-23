# Phase D, Amendment 5, Addendum 1: a second human column (`gold_derivable`) and a second confusion table

**Status:** written 2026-10-23 and tagged `phase-d-amendment-5-addendum-1-2026-10-23` **before any label has been used**: no human label (S/C/N or `gold_derivable`) has been returned or computed on. It amends `docs/preregistration/PHASE_D_AMENDMENT_5.md` (tag `phase-d-amendment-5-2026-10-23`, not edited). Everything not mentioned here is as there: the grounding field, the classes, the sample (Gemini full run, pass 1, seed 20261023, 40 rows: 20 `wrong_ungrounded` and 20 `wrong_grounded`), the rule that the confusion tables are not computed before the labels arrive, and the naming rule for "hallucination". No model call, no API call, no database write.

## 1. Why

The pre-registered label S / C / N records **where the model's number came from** (S: the answer number appears in the retrieved text; C: it can be calculated from numbers in the retrieved text; N: not supported by the retrieved text). It does not record **whether the correct answer was available** in the retrieved passages. Wrong answers with the evidence present (reading, extraction or reasoning errors) are therefore not distinguished from wrong answers that merely used another number from the passages (both can be S or C). A second human column separates them.

## 2. The new column

`gold_derivable`, entered by the user for every row of the labelling sheet:

- **Y** = the gold answer shown in the `gold_answer` column can be obtained from the retrieved passages of that row, directly or by calculation.
- **N** = it cannot be obtained from them (some needed number or fact is not in the retrieved passages).

The label is entered with the sheet as it is (question, gold answer, model answer, retrieved passages); the sheet contains no proxy class, arm or route. `gold_derivable` is judged independently of the S/C/N label and of whether the model's answer was right.

## 3. The sheet: `labelling_sheet_v2.csv`

`outputs/hallucination_classification_2026-10-23/labelling_sheet_v2.csv` is a new copy of the labelling sheet with the column `gold_derivable` (empty) appended as the last column. All other columns, all 40 rows and the row order are unchanged. It was built from the committed original (commit `5327010`; SHA-256 `84b841fc5e5dd11388a3fc8ada7cc10efe915731b645806097d94001b70694ed`, the value registered in `outputs/data_checksums.json`), **not** from the working-tree file `labelling_sheet.csv`, which was re-saved in a spreadsheet application on 2026-10-23 after the commit and no longer equals the registered original (spreadsheet reformatting of numeric-looking answers, for example `9.2%` to `9.20%` and `$ -61.1` to `($61.10)`). Verification (done by `src/phase_d_validation/make_labelling_sheet_v2.py` before the file is written, and repeated by its test): the original re-serialises to the registered SHA-256; v2 with its last column removed re-serialises to the same SHA-256 (byte-identical apart from the new column); every field of every row equals the original field; `sample_id`s are S001-S040 in the original order. `labelling_key.csv` is unchanged. The new sheet's SHA-256 is registered in `outputs/data_checksums.json`.

Practical note for the labeller: open the sheet so that answer columns keep their text (a spreadsheet application may rewrite values such as `$ -61.1`); the file as delivered is the reference.

## 4. The two confusion tables (computed only after the labels are returned)

For the 40 sampled rows, with the proxy classes from the key file (`wrong_ungrounded`, `wrong_grounded`):

1. **Table 1, as already pre-registered:** proxy class vs the S/C/N label (N = "unsupported"; S and C = "supported").
2. **Table 2, new:** proxy class vs `gold_derivable` (Y / N).

Each table is reported as counts per cell with the row shares and Wilson 95% confidence intervals, descriptively (n <= 40, no hypothesis test, no threshold for "validation" fixed in advance). How the word "hallucination" is used for `wrong_ungrounded` after the labels arrive is stated with the tables and not fixed here; the Amendment 5 naming rule stands until then. The S/C/N label is returned in a column named `label` (not part of the v2 file as delivered); the two columns are returned together keyed by `sample_id`.

## 5. Not in this addendum

No new analysis of the full runs, no new sample, no change to the classification, no cross-tabulation of S/C/N against `gold_derivable` (not pre-registered).
