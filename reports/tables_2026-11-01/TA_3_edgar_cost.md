# Table A.3 EDGAR session cost per step and pass projection

| step                                              |   calls |   cost_usd |
|:--------------------------------------------------|--------:|-----------:|
| llm_router decision                               |     160 |  0.0447435 |
| answer pilot (excluded)                           |       5 |  0.0221715 |
| answer main pass 1                                |     355 |  1.39634   |
| session total                                     |     520 |  1.46325   |
| projection, 5 pass(es) (pilot mean x 355 prompts) |       - |  7.87088   |
| projection, 3 pass(es) (pilot mean x 355 prompts) |       - |  4.72253   |
| projection, 1 pass(es) (pilot mean x 355 prompts) |       - |  1.57418   |

Source: `outputs/edgar_cost_log_2026-11-01/cost_log.jsonl`, `outputs/edgar_answers_2026-11-01/pass_decision.json`

Note: Rule: largest of 5, 3, 1 passes whose projection <= USD 4.50 and keeps the session under USD 6.00; chosen passes = 1.
