# Mechanism check: policy_v2 vs naive_llm, pass 1

Source: `outputs/phase_d_gemini_full_2026-10-12/results.jsonl` (read-only). Primary scoring labels (`correct`).

## Discordant queries (4: b = 4 policy_v2 only correct, c = 0 naive_llm only correct)

| query | correct by | naive_llm route | rows returned policy_v2 / naive_llm | passage gold hit policy_v2 / naive_llm | policy_v2 raw answer | naive_llm raw answer | gold |
|---|---|---|---|---|---|---|---|
| ALXN/2016/page_153.pdf-2 | policy_v2 | post-filter | 15 / 3 | 0 / 0 | `113.6%` | `100%` | 114% |
| CDW/2015/page_70.pdf-1 | policy_v2 | post-filter | 15 / 2 | 1 / 1 | `-84` | `$ -61.1` | -84 |
| ECL/2017/page_79.pdf-1 | policy_v2 | post-filter | 15 / 7 | 0 / 0 | `70.5%` | `73.5%` | 70.5% |
| MRO/2004/page_125.pdf-1 | policy_v2 | post-filter | 15 / 0 | 1 / 0 | `$5970.33` | `$721.5` | 5970 |

## naive_llm accuracy over all 50 queries, split by its route and by passage-level gold hit

| group | n | correct | accuracy | mean rows returned |
|---|---|---|---|---|
| route = post-filter | 21 | 12 | 0.57 | 4.8 |
| route = pre-filter | 29 | 20 | 0.69 | 14.7 |
| gold hit = 1 | 30 | 23 | 0.77 | 10.2 |
| gold hit = 0 | 20 | 9 | 0.45 | 11.1 |
| route = post-filter, gold hit = 1 | 14 | 10 | 0.71 | 5.3 |
| route = post-filter, gold hit = 0 | 7 | 2 | 0.29 | 3.9 |
| route = pre-filter, gold hit = 1 | 16 | 13 | 0.81 | 14.4 |
| route = pre-filter, gold hit = 0 | 13 | 7 | 0.54 | 15.0 |

For comparison, policy_v2 on the same queries split by naive_llm's route:

| group (naive_llm route) | n | policy_v2 correct | naive_llm correct |
|---|---|---|---|
| post-filter | 21 | 16 | 12 |
| pre-filter | 29 | 20 | 20 |
