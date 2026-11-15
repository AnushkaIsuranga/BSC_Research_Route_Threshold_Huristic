# Straddle-T Manifest Report (Amendment 12)

- **Parameters:** `SEED = 20261115`, `SMOKE_SEED = 20261116`, `FINQA_N = 100`, `k = 15`
- **Thresholds:** `T_edgar = 0.3786921696945195`, `T_hm = 0.07119177617441379`
- **Read-only DB check:** `SHOW transaction_read_only` -> `on` (`1043` unique SQL gold checks executed inside `BEGIN READ ONLY` + `ROLLBACK`)
- **FinQA 4-band eligible count:** `605` (sampled `100`)

## SQL used for gold containment checks
- **EDGAR:** `SELECT EXISTS (SELECT 1 FROM edgar_chunks WHERE ({wc}) AND cik = %s AND fiscal_year = %s AND section = %s AND text_hash = %s)`
- **FinQA:** `SELECT EXISTS (SELECT 1 FROM finqa_evidence WHERE ({wc}) AND metadata->>'ticker' = %s AND (metadata->>'year')::int = %s)`

## Pool SHA-256 verification (`POOL_CHECKSUMS.txt`)
- `band_population.csv`: `1bef0a60aa57b16e668abccc23082ffeca500c20fb0881e35a9511de6af8103b` (MATCH)
- `build_pool.py`: `23cbfb523b2446e6add6f4cae98d8e53ee6385af034caf490f48053886411e38` (MATCH)
- `coverage_summary.csv`: `3e0aabaabd75c8f930eb2293e6d804492eef7de3aeee5a9194fb69163ce57e9e` (MATCH)
- `dedupe_summary.csv`: `af3013d57ace61a404af1b85004fa1e3b636b6375a9a97ab919deb641967af66` (MATCH)
- `edgar_pool.csv`: `c11ddee7cdc6e81f685957708e57ca10b6d09d9b844d346cfb8965644b6172c7` (MATCH)
- `eligible_questions.csv`: `a2e16dc31951e395b7d2463b64e96ebabb0f90559da0c1665c2e9e6187e1064f` (MATCH)
- `finqa_pool.csv`: `4c0e656d9b60a8da4619bc68e70a7cea93c39b046f43d196a3e2a17d33b61b4d` (MATCH)
- `pool_s_gaps.csv`: `3b059c93668435b0aa6deed6728340cd8e331cd6c1fa1958e16f85afb65443c1` (MATCH)

## Counts per manifest and band

| Manifest | Band | Drawn | Eligible | Ineligible | Status |
| --- | --- | ---: | ---: | ---: | --- |
| `edgar_pairs_primary_T_edgar` | `far_below` | 40 | 40 | 0 | ok |
| `edgar_pairs_primary_T_edgar` | `near_below` | 40 | 40 | 0 | ok |
| `edgar_pairs_primary_T_edgar` | `near_above` | 40 | 40 | 0 | ok |
| `edgar_pairs_primary_T_edgar` | `far_above` | 30 | 30 | 10 | ok |
| `edgar_pairs_secondary_T_hm` | `far_below` | 40 | 40 | 0 | ok |
| `edgar_pairs_secondary_T_hm` | `near_below` | 0 | 10 | 30 | not_testable |
| `edgar_pairs_secondary_T_hm` | `near_above` | 40 | 40 | 0 | ok |
| `edgar_pairs_secondary_T_hm` | `far_above` | 40 | 40 | 0 | ok |
| `finqa_pairs_primary_T_hm` | `far_below` | 100 | 100 | 0 | ok |
| `finqa_pairs_primary_T_hm` | `near_below` | 100 | 100 | 0 | ok |
| `finqa_pairs_primary_T_hm` | `near_above` | 100 | 100 | 0 | ok |
| `finqa_pairs_primary_T_hm` | `far_above` | 100 | 100 | 0 | ok |
| `finqa_pairs_secondary_random` | `far_below` | 48 | 48 | 52 | ok |
| `finqa_pairs_secondary_random` | `near_below` | 100 | 100 | 0 | ok |
| `finqa_pairs_secondary_random` | `near_above` | 99 | 99 | 1 | ok |
| `finqa_pairs_secondary_random` | `far_above` | 50 | 50 | 50 | ok |
| `natural_only_edgar_T_edgar` | `far_below` | 40 | 40 | 0 | ok |
| `natural_only_edgar_T_edgar` | `near_below` | 40 | 40 | 0 | ok |
| `natural_only_edgar_T_edgar` | `near_above` | 0 | 0 | 40 | empty |
| `natural_only_edgar_T_edgar` | `far_above` | 0 | 0 | 40 | empty |
| `natural_only_edgar_T_hm` | `far_below` | 40 | 40 | 0 | ok |
| `natural_only_edgar_T_hm` | `near_below` | 0 | 8 | 32 | empty |
| `natural_only_edgar_T_hm` | `near_above` | 30 | 30 | 10 | ok |
| `natural_only_edgar_T_hm` | `far_above` | 40 | 40 | 0 | ok |
| `natural_only_finqa_T_hm` | `far_below` | 100 | 100 | 0 | ok |
| `natural_only_finqa_T_hm` | `near_below` | 80 | 80 | 20 | ok |
| `natural_only_finqa_T_hm` | `near_above` | 18 | 18 | 82 | ok |
| `natural_only_finqa_T_hm` | `far_above` | 0 | 0 | 100 | empty |

- **Smoke test (`smoke_test_pairs.csv`):** 14 pairs (10 EDGAR: 2 `far_below`, 3 `near_below`, 3 `near_above`, 2 `far_above`; 4 FinQA).
