# EDGAR 10-K evaluation questions: drafting, verification and selection

Written 2026-11-01. Covers the candidate questions over table `edgar_chunks` (runbook: `docs/RUNBOOK_EDGAR.md`).
Not a pre-registration; the selection below has **not** been applied yet.

## 1. Drafting (`src/phase_f_edgar/draft_questions.py`, `outputs/edgar_questions_draft_2026-10-31/`)

Questions are built **backwards from a gold chunk**:

1. Pool: chunks of companies with an extracted `company_name` that contain at least 3 financial numbers (23,307 chunks).
2. Seeded shuffle (seed `"20261031-questions"`); walk the list and take **one chunk per company** until 60 are drawn.
3. 15 chunks each are assigned the filter breadths cik+year+section, cik+year, year+section and section, in that order.
   The filter is built **from the gold chunk's own metadata**, so the gold chunk always passes it.
4. Gemini 3.8 Flash (Vertex, temperature 0, thinking LOW, JSON mode, 2,048 output tokens) receives the chunk text, company,
   CIK, fiscal year and section name and returns `{question, answer, type, basis}`. The prompt (in `prompt.json`) requires a
   single-number answer, paraphrasing, and naming the company and fiscal year. `type` is lookup or calculation.
5. Gold chunk ids = every row with the same text as the gold chunk that passes the filter.

## 2. Automatic checks (`src/phase_f_edgar/verify_questions.py`, `outputs/edgar_questions_verify_2026-11-01/checks.csv`)

| Check | Definition |
|---|---|
| A number_in_chunk (lookup only) | The drafted answer's number, normalised ($, commas, %/percent, parentheses = negative, thousand/million/billion), appears in the gold chunk, either as written or after scaling. A percent answer only matches a percent. |
| B independent_answer | gpt-oss-120b on Vertex (Amendment 8 endpoint, temperature 0) answers from the gold chunk alone, with a single number and units or "not answerable". It is compared with the drafted answer by the Amendment 2 primary scorer, after cutting the number span from both. "not answerable" = N. |
| C company_match | The question names `company_name`, or the name appears in the gold chunk or in section 1 of the same report. **Subsidiary flag** recorded separately: the name is described as a subsidiary there. |
| D retrievable | The question is embedded with the Amendment 1 query recipe (Qwen3-Embedding-8B, 1024-d, instruct prefix). Exact search (forced, plan checked), k = 15, under all four filters built from the gold chunk's metadata. Gold rank and exact selectivity are recorded. |
| E generic_fact | Y if the drafted number also appears in at least 5 other chunks under the drafted filter. |
| F alt_source | Number of other chunks of the same CIK (any year or section) containing the drafted number. Report only. |

**auto_pass** = (A = Y or B = Y) and C = Y and D = Y at cik+year+section and no subsidiary flag and E = N. Every other row is
**needs_review**, with its failing checks listed. D at the broader breadths is recorded but not used for the status. The question
embeddings and the four filters with their selectivities are saved, checksummed, for reuse in the evaluation.

## 3. Author review (`review_sheet.csv`)

The review sheet holds every needs_review row plus **10 auto_pass rows drawn with seed 20261101**. Rows whose drafted number is not
in the chunk come first, then q057, q033 and q055 if flagged; the rest follow in seeded random order. The author fills in
decision (keep / fix / drop), corrected_answer, corrected_type and note.

## 4. Final selection rule (to be applied after the review)

- Eligible questions are those that are auto_pass, or that the author marks keep or fix (a fix uses the corrected answer and type).
- Every eligible calculation question is kept. Lookup questions are then drawn with seed 20261101 until there are **40 in total**.
- If fewer than 40 qualify, all are used and the shortfall is reported.
- Each selected question is evaluated under **all four filter breadths** of its gold chunk (cik+year+section, cik+year,
  year+section, section), not only its drafted breadth.

## 5. Known limitations

- Only companies with an extracted name are covered: 165 of 433 sampled companies.
- Questions always name the company and fiscal year, even under broad filters. Under a broad filter, the vector search must pick the
  company from the question text (the coarse-filter case).
- Only chunks with text identical to the gold chunk count as gold. Other chunks may also hold the answer, for example the next
  year's comparative figures; check F counts these for the same company.
- The drafting model (Gemini 3.8 Flash) is from the same family as the evaluation answer model.
- Check C is close to automatic: the drafting model was given `company_name`, so every question names it. The stricter results
  are recorded separately (name in the gold chunk: 12 of 60; name in section 1: 59 of 60). The subsidiary flag is a text heuristic.
- Check B uses the deterministic scorer only on the number span cut from each answer, because drafted answers carry unit words
  ("$59.65 per Bbl") that the scorer cannot parse as gold. One gpt-oss-120b call (q020) timed out and counts as N.
- Check E counts any recurrence of the number under the drafted filter. Under year+section and section filters, round numbers
  ("$15 million", "4.0%") recur often, so E flags commonness of the number as well as truly generic facts.

## 6. Disclosure text

> Questions and gold answers were drafted by Gemini 3.8 Flash from the corpus. They were automatically cross-checked for: the number
> being present in the source, an independent re-answer by gpt-oss-120b, a company match, retrievability under exact search, and a
> generic-fact flag. The author reviewed them where a check failed, plus a random sample of 10 that passed.
