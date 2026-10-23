# Amendment 5 addendum 2: note counts (post hoc), 2026-10-23

Governed by `docs/preregistration/PHASE_D_AMENDMENT_5_ADDENDUM_2.md` (tag `phase-d-amendment-5-addendum-2-2026-10-23`), **written after the Addendum 1 results (commit `3c167ba`) were computed; it changes none of them.** Labels are **model-drafted labels verified by the author**: drafted by a language model from a different model family than the answer model (Gemini 3.8 Flash), blind to the key file, with the calculation written per row, then checked row by row by the author. The note counts below are **post hoc and descriptive only**; the scoring rule is unchanged. No model call, no database access.

## Input and checks

- Labelled copy with notes: `outputs/hallucination_labels_addendum2_2026-10-23/labelling_sheet_check_with_notes.csv` (SHA-256 `6abe9b266c03dd9ef740de0c0065d24e8da9b2d2918317cc20c1b74b6bc85d1a`), joined to the committed sheet (`5327010`) by `sample_id` only; its other columns are ignored.
- `check` and `gold_derivable` identical to the labels used in `3c167ba`: **40/40 rows**.
- Rows with a note: 36 of 40 (15 of 17 distinct questions).
- Topic rule (fixed in Addendum 1 section 3, case-insensitive): rounding = `round`; scale = `scale`/`million`/`thousand`; suspected gold error = `gold` with `error`/`wrong`/`incorrect`; count vs percentage = `count` with `percent`/`%`/`percentage`. A row can match more than one topic.

## Note counts (per row, 40; per distinct question, 17)

| topic | rows | of which wrong_ungrounded / wrong_grounded | S/C/N of those rows | distinct questions | of which wrong_ungrounded / wrong_grounded | sample_ids |
|---|---|---|---|---|---|---|
| rounding | 6 | 6 / 0 | C 6 | 2 | 2 / 0 | S007, S023, S031, S032, S037, S040 |
| scale | 3 | 0 / 3 | C 3 | 1 | 0 / 1 | S001, S010, S033 |
| suspected gold error | 4 | 4 / 0 | C 4 | 2 | 2 / 0 | S004, S013, S014, S015 |
| count vs percentage | 3 | 0 / 3 | C 3 | 1 | 0 / 1 | S009, S025, S027 |
| any of the four | 16 | 10 / 6 | C 16 | 6 | 4 / 2 | S001, S004, S007, S009, S010, S013, S014, S015, S023, S025, S027, S031, S032, S033, S037, S040 |
| other note only | 20 | 8 / 12 | C 9, N 6, S 5 | 9 | 4 / 5 | S003, S005, S006, S008, S011, S012, S016, S017, S018, S019, S020, S021, S028, S029, S030, S034, S035, S036, S038, S039 |
| no note | 4 | 2 / 2 | C 2, S 2 | 2 | 1 / 1 | S002, S022, S024, S026 |

Per-question counting as in Addendum 1: a question counts once in every row of the table in which one of its rows falls. "other note only" = a note that matches none of the four topics (e.g. ambiguous question wording, interpretation difference, gold not reproducible, unsupported number).

## Addendum 1 confusion tables (copied unchanged from `reports/hallucination_labels_2026-10-23.md`, commit `3c167ba`, for reference)

Where that report says "human labels", read "model-drafted labels verified by the author".

### Per row, 40 rows (model-drafted labels verified by the author)

**Table 1: proxy class vs S/C/N** (S: the answer number appears in the retrieved text; C: calculable from numbers in it; N: not supported by it)

| proxy class | rows | S | C | N (unsupported) | S or C (supported) |
|---|---|---|---|---|---|
| wrong_ungrounded | 20 | 0/20 (0%; CI 0-16%) | 14/20 (70%; CI 48-85%) | 6/20 (30%; CI 15-52%) | 14/20 (70%; CI 48-85%) |
| wrong_grounded | 20 | 7/20 (35%; CI 18-57%) | 13/20 (65%; CI 43-82%) | 0/20 (0%; CI 0-16%) | 20/20 (100%; CI 84-100%) |

**Table 2: proxy class vs `gold_derivable`** (Y: the gold answer can be obtained from the retrieved passages, directly or by calculation)

| proxy class | rows | gold derivable Y | gold derivable N |
|---|---|---|---|
| wrong_ungrounded | 20 | 12/20 (60%; CI 39-78%) | 8/20 (40%; CI 22-61%) |
| wrong_grounded | 20 | 18/20 (90%; CI 70-97%) | 2/20 (10%; CI 3-30%) |

### Per distinct question (model-drafted labels verified by the author) (17 questions; a question counts once in every cell in which one of its rows falls)

**Table 1: proxy class vs S/C/N** (S: the answer number appears in the retrieved text; C: calculable from numbers in it; N: not supported by it)

| proxy class | distinct questions | S | C | N (unsupported) | S or C (supported) |
|---|---|---|---|---|---|
| wrong_ungrounded | 9 | 0/9 (0%; CI 0-30%) | 6/9 (67%; CI 35-88%) | 3/9 (33%; CI 12-65%) | 6/9 (67%; CI 35-88%) |
| wrong_grounded | 8 | 3/8 (38%; CI 14-69%) | 5/8 (62%; CI 31-86%) | 0/8 (0%; CI 0-32%) | 8/8 (100%; CI 68-100%) |

**Table 2: proxy class vs `gold_derivable`** (Y: the gold answer can be obtained from the retrieved passages, directly or by calculation)

| proxy class | distinct questions | gold derivable Y | gold derivable N |
|---|---|---|---|
| wrong_ungrounded | 9 | 5/9 (56%; CI 27-81%) | 4/9 (44%; CI 19-73%) |
| wrong_grounded | 8 | 7/8 (88%; CI 53-98%) | 1/8 (12%; CI 2-47%) |

