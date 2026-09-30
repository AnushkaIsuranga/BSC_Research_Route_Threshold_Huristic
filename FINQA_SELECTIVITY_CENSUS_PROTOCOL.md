# FinQA Selectivity Census and Supplementary-Sample Protocol

**Status:** frozen before census execution.

## Advance prediction

The 1,147 FinQA queries are expected to remain well below the Decision Matrix
switching region near 0.329 selectivity. Reaching that region would require a
single ticker/year filter to match approximately 11,800 of the 35,862 evidence
rows. The existing 50-query sample reached only 0.00056–0.01944 selectivity.

## Selectivity definition

For query `(ticker, year)`, selectivity is:

```text
count(finqa_evidence rows matching ticker and year)
---------------------------------------------------
count(all finqa_evidence rows)
```

The denominator is occurrence-based and is the same calculation used by the
local evaluation runner.

## Fixed bands and quotas

Bands are fixed before inspecting the census:

| Band | Selectivity interval | Quota | Adequacy minimum |
|---|---:|---:|---:|
| B1 | `< 0.02` | 10 | 10 |
| B2 | `>= 0.02 and < 0.10` | 10 | 10 |
| B3 | `>= 0.10 and < 0.329` | 10 | 10 |
| B4 | `>= 0.329` | 10 | 10 |

Within each band, draw at most 10 queries using random seed `20260930`, without
replacing queries from the locked primary 50-query sample. Preserve the
existing single/dual/multi-evidence breadth strata using the query's gold
evidence-unit count: single = 1, dual = 2, multi = 3 or more. Selection uses
only selectivity, overlap exclusion, and this pre-existing evidence-breadth
label; it never uses model outputs, retrieval, or answer correctness.

If a band has fewer than 10 eligible queries, report the shortage and do not
top up from another band. The supplementary sample is exploratory and does not
replace or alter the locked primary 50-query result.

## Execution order

1. Commit this file before running the census.
2. Run a read-only census over all 1,147 raw FinQA queries.
3. Validate that the census reproduces the primary sample's recorded
   selectivities.
4. Save the full per-query census and distribution summary.
5. Apply the fixed bands and quotas only after the census is complete.
