# Table 4.3 H&M pass counts per mode

| mode / rule                                     | session                      |   in-sample /65 |   held-out 1 /25 |   held-out 2 /25 |   held-out /50 |   held-out 1 quiet re-run /25 |
|:------------------------------------------------|:-----------------------------|----------------:|-----------------:|-----------------:|---------------:|------------------------------:|
| Always exact [always_exact]                     | Phase E (Amendment 9)        |              25 |               15 |                0 |             15 |                             - |
| Always iterative [always_iterative]             | Phase E (Amendment 9)        |              54 |               24 |               25 |             49 |                             - |
| Filtered HNSW (pgvector default) [default_hnsw] | Phase E (Amendment 9)        |              11 |                0 |                7 |              7 |                             - |
| Fixed T = 0.1 [fixed_t_0_1]                     | Phase E (Amendment 9)        |              65 |               25 |               25 |             50 |                             - |
| Iterative, tuned [iterative_tuned]              | Phase E (Amendment 9)        |              59 |               25 |               25 |             50 |                             - |
| LLM router [llm_router]                         | Phase E (Amendment 9)        |               - |               15 |                3 |             18 |                             - |
| Local probe [local_probe]                       | Phase E (Amendment 9)        |              64 |               23 |               23 |             46 |                             - |
| Oracle (per cell) [oracle]                      | Phase E (Amendment 9)        |              65 |               25 |               25 |             50 |                             - |
| Planner + iterative [planner_iterative]         | Phase E (Amendment 9)        |              45 |               15 |               15 |             30 |                             - |
| HNSW, retry exact [retry_exact]                 | Phase E (Amendment 9)        |              45 |               15 |               15 |             30 |                             - |
| Router (policy_v3.1) [router]                   | Phase E (Amendment 9)        |              65 |               25 |               25 |             50 |                             - |
| Router, always count [router_always_count]      | Phase E (Amendment 9)        |              65 |               25 |               25 |             50 |                             - |
| Router, no guard [router_no_guard]              | Phase E (Amendment 9)        |              65 |               25 |               25 |             50 |                             - |
| Router + local probe [router_plus_probe]        | Phase E (Amendment 9)        |              64 |               23 |               23 |             46 |                             - |
| Router, tuned iterative [router_tuned]          | Phase E (Amendment 9)        |              65 |               25 |               25 |             50 |                             - |
| v1 decision matrix [P1]                         | Phase A policy evaluation    |              29 |               21 |               10 |             31 |                             - |
| policy_v2                                       | Phase A (Amendment 6 Part B) |              65 |               24 |               25 |             49 |                            25 |
| B1 VBASE (s < 0.18)                             | Phase A (Amendment 6 Part B) |              65 |               23 |               25 |             48 |                            25 |
| B2 Milvus via NaviX (s <= 0.05)                 | Phase A (Amendment 6 Part B) |              65 |               25 |               25 |             50 |                            25 |
| B3 Qdrant (rows < 1,250)                        | Phase A (Amendment 6 Part B) |              64 |               24 |               25 |             49 |                            24 |
| B4 Gan & Wang (recall/latency labels)           | Phase A (Amendment 6 Part B) |              63 |               24 |               25 |             49 |                            24 |
| B4b Gan & Wang (SLA labels)                     | Phase A (Amendment 6 Part B) |              64 |               25 |               25 |             50 |                            25 |

Source: `outputs/phase_e_comparison_hm_2026-10-31/summary.json`, `outputs/phase_a_amendment6_2026-10-23/partb_summary.json`, `outputs/phase_a_arms/analysis/policy_evaluation_cells.csv`, `outputs/phase_a_holdout/analysis/policy_cells.csv`, `outputs/phase_a_holdout2/analysis/policy_cells.csv`

Note: Pass = mean recall@10 >= 0.90 and median latency <= 500 ms, all 20 vectors valid. Phase E and Phase A rows come from different measurement sessions. The LLM router was run on the held-out sets only.
