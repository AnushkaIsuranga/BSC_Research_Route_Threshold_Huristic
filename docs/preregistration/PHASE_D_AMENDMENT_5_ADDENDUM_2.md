# Phase D, Amendment 5, Addendum 2

**Status:** written 2026-10-23, committed and tagged `phase-d-amendment-5-addendum-2-2026-10-23`. **This addendum was written AFTER the results of Addendum 1 were computed** (commit `3c167ba`, `reports/hallucination_labels_2026-10-23.md`). **It changes none of those results**: no label, table, count or share of Addendum 1 is altered. It is a disclosure and a post-hoc descriptive addition, not a pre-registration. It amends nothing in `PHASE_D_AMENDMENT_5.md` (tag `phase-d-amendment-5-2026-10-23`) or `PHASE_D_AMENDMENT_5_ADDENDUM_1.md` (tag `phase-d-amendment-5-addendum-1-2026-10-23`); neither file is edited and no tag is moved. No model call, no API call, no database access.

## a) Labelling method (omitted from Addendum 1)

The S/C/N and `gold_derivable` labels were **drafted by a language model from a different model family than the answer model** (the answer model is Gemini 3.8 Flash), **blind to the key file** (`labelling_key.csv`: proxy class, arm, scoring), with the calculation written out per row, and **then checked row by row by the author**. They are reported as **"model-drafted labels verified by the author"**, not as independent human labels. This was not stated in Addendum 1 or in its report; the omission is logged in `DEVIATION_LOG.md`.

## b) Note column (added afterwards; post hoc)

After the Addendum 1 results, the author supplied a labelled copy with a third column `note` (filled in 36 of 40 rows). It is kept as a new file, `outputs/hallucination_labels_addendum2_2026-10-23/labelling_sheet_check_with_notes.csv`; the registered `labelling_sheet_check.csv` is unchanged. It is joined to the committed `labelling_sheet.csv` (commit `5327010`) **by `sample_id` only**; its other columns are ignored. Before use, its `check` and `gold_derivable` values must be identical, row by row, to those used in `3c167ba` (`label_analysis/labelled_rows_joined.csv`); if any differ, the analysis stops. (Checked while writing this: 40/40 identical.)

Its `gold_answer` / `model_answer` cells differ from the committed sheet only by spreadsheet formatting, ignored here (17 cells): gold_answer S002 `9.2%`->`9.20%`, S011/S029/S030/S034 `10.2%`->`10.20%`, S024 `9.2%`->`9.20%`; model_answer S003/S016 `$39`->`$39 `, S005/S039 `$ -61.1`->`($61.10)`, S017 `$200900.81`->`$200,900.81 `, S018 `$202,081.20`->`$202,081.20 `, S023/S031/S037 `18.2%`->`18.20%`, S036 `46.4%`->`46.40%`, S040 `19.5%`->`19.50%`.

Counted: rows whose note mentions **rounding, scale, a suspected gold error, or a count-versus-percentage mismatch**, using the keyword rule already written in Addendum 1 section 3 (case-insensitive: `round`; `scale`/`million`/`thousand`; `gold` with `error`/`wrong`/`incorrect`; `count` with `percent`/`%`/`percentage`), per row (40) and per distinct question (17), with the split by proxy class. These counts are **post hoc and descriptive only**. The notes were written after the labels and by the same verification process; **no change to the scoring rule** and no re-scoring follows from them.

## c) History of Addendum 1 (disclosure)

- The tag `phase-d-amendment-5-addendum-1-2026-10-23` was **moved once**: first set on `2dbfc72` (2026-10-23 11:03:10 +05:30, first version: empty `gold_derivable` column in a new sheet), then moved to `21d84de` (2026-10-23 11:23:23 +05:30, second version). No label had been used at either commit; the results followed in `1338264` and `3c167ba` (11:27:49 +05:30).
- `outputs/hallucination_classification_2026-10-23/labelling_sheet_v2.csv` (from `2dbfc72`) **exists and is withdrawn**: never used, left in place and in `data_checksums.json`.

## Outputs

`outputs/hallucination_labels_addendum2_2026-10-23/` (note counts, JSON) and `reports/hallucination_labels_addendum2_2026-10-23.md`, which copies the Addendum 1 confusion tables unchanged for reference, labelled "model-drafted labels verified by the author". `reports/hallucination_labels_2026-10-23.md` is not edited.
