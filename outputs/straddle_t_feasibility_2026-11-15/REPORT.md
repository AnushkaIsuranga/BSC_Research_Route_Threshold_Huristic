# Straddle-T Feasibility Enumeration Report (2026-11-15)

## Config & Thresholds
- `T_edgar` = `0.3786921696945195` (from `config/policy_v3_1_edgar.json`)
- `T_hm` = `0.07119177617441379` (from `config/policy_v3_1_hm.json`)
- Contiguous bands: `far_below`: $s \le T/2$; `near_below`: $T/2 < s \le T$; `near_above`: $T < s \le 2T$; `far_above`: $s > 2T$.

## Table Row Counts
- `edgar_chunks`: `158308` rows (years: [2018, 2019, 2020], sections: ['1', '1A', '7', '7A', '8'])
- `finqa_evidence`: `35862` rows (years: 1999..2019 across 20 distinct years; 100 distinct tickers)

## Step A: Existing EDGAR Manifest (`pairs.csv`)
| threshold | breadth | far_below | near_below | near_above | far_above | total |
|---|---|---:|---:|---:|---:|---:|
| T_edgar | cik+year+section | 40 | 0 | 0 | 0 | 40 |
| T_edgar | cik+year | 40 | 0 | 0 | 0 | 40 |
| T_edgar | year+section | 40 | 0 | 0 | 0 | 40 |
| T_edgar | section | 10 | 30 | 0 | 0 | 40 |
| T_hm | cik+year+section | 40 | 0 | 0 | 0 | 40 |
| T_hm | cik+year | 40 | 0 | 0 | 0 | 40 |
| T_hm | year+section | 2 | 8 | 30 | 0 | 40 |
| T_hm | section | 2 | 0 | 0 | 38 | 40 |

## Step D: Band Population Summary (usable filters, n_rows >= 15)
| table | threshold | band | usable_total | natural | constructed | min_s | max_s |
|---|---|---|---:|---:|---:|---:|---:|
| edgar_chunks | T_edgar | far_below | 6281 | 6222 | 59 | 0.000095 | 0.189232 |
| edgar_chunks | T_edgar | near_below | 60 | 6 | 54 | 0.190654 | 0.376304 |
| edgar_chunks | T_edgar | near_above | 42 | 0 | 42 | 0.388458 | 0.740613 |
| edgar_chunks | T_edgar | far_above | 3 | 0 | 3 | 0.807672 | 1.000000 |
| edgar_chunks | T_hm | far_below | 6212 | 6209 | 3 | 0.000095 | 0.017498 |
| edgar_chunks | T_hm | near_below | 6 | 3 | 3 | 0.057729 | 0.065322 |
| edgar_chunks | T_hm | near_above | 26 | 9 | 17 | 0.076958 | 0.142280 |
| edgar_chunks | T_hm | far_above | 142 | 7 | 135 | 0.142867 | 1.000000 |
| finqa_evidence | T_hm | far_below | 444 | 375 | 69 | 0.000446 | 0.035190 |
| finqa_evidence | T_hm | near_below | 95 | 12 | 83 | 0.036473 | 0.071134 |
| finqa_evidence | T_hm | near_above | 98 | 6 | 92 | 0.071245 | 0.139591 |
| finqa_evidence | T_hm | far_above | 171 | 0 | 171 | 0.143076 | 1.000000 |
| finqa_evidence | T_edgar_ref | far_below | 656 | 393 | 263 | 0.000446 | 0.187078 |
| finqa_evidence | T_edgar_ref | near_below | 51 | 0 | 51 | 0.189448 | 0.377726 |
| finqa_evidence | T_edgar_ref | near_above | 68 | 0 | 68 | 0.383135 | 0.755758 |
| finqa_evidence | T_edgar_ref | far_above | 33 | 0 | 33 | 0.759383 | 1.000000 |

## Step E: Gold-Containment Feasibility
- `selected.csv` (40 rows) columns: `['qid', 'question', 'type', 'answer', 'gold_number', 'selection_basis', 'drafted_breadth', 'company_name', 'cik', 'fiscal_year', 'section', 'gold_text_hash', 'gold_chunk_text']` (gold key: `cik`, `fiscal_year`, `section`, `gold_text_hash`)
- `calibration_queries.csv` (20 rows) columns: `['qid', 'question', 'status', 'review_decision', 'reason_not_selected']`
- Disjointness confirmed: `True`
- FinQA `finqa_test.json` (1147 questions): `(ticker, year)` present in `finqa_evidence` for `1147` / `1147` questions.

| dataset | threshold | band | n_questions | questions_with_ge_1_filter |
|---|---|---|---:|---:|
| edgar_chunks | T_edgar | far_below | 40 | 40 |
| edgar_chunks | T_edgar | near_below | 40 | 40 |
| edgar_chunks | T_edgar | near_above | 40 | 40 |
| edgar_chunks | T_edgar | far_above | 40 | 40 |
| edgar_chunks | T_hm | far_below | 40 | 40 |
| edgar_chunks | T_hm | near_below | 40 | 10 |
| edgar_chunks | T_hm | near_above | 40 | 40 |
| edgar_chunks | T_hm | far_above | 40 | 40 |
| finqa_evidence | T_hm | far_below | 1147 | 1147 |
| finqa_evidence | T_hm | near_below | 1147 | 1147 |
| finqa_evidence | T_hm | near_above | 1147 | 1147 |
| finqa_evidence | T_hm | far_above | 1147 | 1147 |

## Exact SQL Used
### EDGAR GROUPING SETS
```sql
SELECT cik, fiscal_year, section,
               GROUPING(cik) AS g_cik,
               GROUPING(fiscal_year) AS g_yr,
               GROUPING(section) AS g_sec,
               COUNT(*) AS n_rows
        FROM edgar_chunks
        GROUP BY GROUPING SETS (
            (cik, fiscal_year, section),
            (cik, fiscal_year),
            (fiscal_year, section),
            (cik, section),
            (cik),
            (fiscal_year),
            (section)
        )
        ORDER BY g_cik, g_yr, g_sec, cik NULLS LAST, fiscal_year NULLS LAST, section NULLS LAST
```

### FinQA GROUPING SETS
```sql
SELECT metadata->>'ticker' AS ticker,
               (metadata->>'year')::int AS year,
               GROUPING(metadata->>'ticker') AS g_ticker,
               GROUPING((metadata->>'year')::int) AS g_year,
               COUNT(*) AS n_rows
        FROM finqa_evidence
        GROUP BY GROUPING SETS (
            (metadata->>'ticker', (metadata->>'year')::int),
            (metadata->>'ticker'),
            ((metadata->>'year')::int)
        )
        ORDER BY g_ticker, g_year, ticker NULLS LAST, year NULLS LAST
```
