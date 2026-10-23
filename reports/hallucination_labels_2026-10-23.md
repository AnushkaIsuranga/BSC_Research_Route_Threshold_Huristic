# Human labels vs the proxy classes (Amendment 5 + addendum 1), 2026-10-23

Pre-registered in `docs/preregistration/PHASE_D_AMENDMENT_5.md` and `PHASE_D_AMENDMENT_5_ADDENDUM_1.md` (tag `phase-d-amendment-5-addendum-1-2026-10-23`, second version, written before any label was used). 40 sampled rows (Gemini full run, pass 1, seed 20261023; 20 `wrong_ungrounded` and 20 `wrong_grounded` by design, so the shares below are within-class shares, not prevalences) from 17 distinct questions. Descriptive only: counts, shares with Wilson 95% CIs, no test, no validation threshold. No model call, no database access.

## Verification of the labelled file

`outputs/hallucination_classification_2026-10-23/labelling_sheet_check.csv` (SHA-256 `ffc001b798207fc21d083eb9bbeaef40ffa4de59efa37da07ff5cd31235d0959`) against the committed original sheet (commit `5327010`, registered SHA-256 `84b841fc...`): same 40 rows in the same order; identical in sample_id 40/40, question 40/40, gold_answer 34/40, model_answer 29/40, retrieved_passages 40/40. The 17 differing cells (gold_answer 6, model_answer 11) are number formatting introduced by the spreadsheet application and are all numerically equivalent (e.g. S002 '9.2%' -> '9.20%'; S011 '10.2%' -> '10.20%'; S024 '9.2%' -> '9.20%'). Labels were joined to the proxy classes by `sample_id` through `labelling_key.csv`; all `check` values are in {S, C, N} and all `gold_derivable` values in {Y, N}.

## Per row (40 rows)

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

## Per distinct question (17 questions; a question counts once in every cell in which one of its rows falls)

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

Within a proxy class, questions with rows carrying different S/C/N labels: 0; different `gold_derivable` labels: 0 (over 17 question-class pairs), so the per-row and per-question tables differ only in how often repeated rows are counted.

## Rows with notes (rounding, scale, suspected gold error, count-vs-percentage mismatch)

**Not available:** the labelled file has no note column (its check column holds one letter per row). The count cannot be made from this file and none was estimated. If the notes exist elsewhere, supplying them as a column named `note` lets this script count them (keyword rules fixed in the addendum).

## What the labels show (descriptive; 20 + 20 rows from 9 + 8 questions)

- **Most ungrounded wrong answers are not unsupported.** Of the 20 `wrong_ungrounded` rows, 6/20 (30%; CI 15-52%) were labelled N; 14/20 (70%; CI 48-85%) were C and 0/20 (0%; CI 0-16%) were S. So most 'ungrounded wrong answers' used numbers present in, or calculable from, the retrieved passages. The proxy is not a measure of fabrication.
- **All N rows are in the ungrounded class.** 0 of 20 `wrong_grounded` rows are N; all 20 are supported (S 7, C 13). In this sample the proxy missed no unsupported answer, but most rows it flagged were supported.
- **Gold answer availability.** Gold derivable (Y): 12/20 (60%; CI 39-78%) of `wrong_ungrounded` and 18/20 (90%; CI 70-97%) of `wrong_grounded`. So in most wrong answers of both classes the correct answer could be obtained from the prompt. 8 `wrong_ungrounded` and 2 `wrong_grounded` rows had a gold answer not derivable from the passages; the grounded-N rows are the ones to inspect for a gold error or an ambiguous question (the file has no notes to say).
- **Limit of this evidence.** The data do not support calling `wrong_ungrounded` answers hallucinations in general; only the N-labelled subset is unsupported by the retrieved text. The sample is drawn 20 + 20 by design and covers 17 questions, so these are not prevalence estimates for the full run and the intervals are wide.

