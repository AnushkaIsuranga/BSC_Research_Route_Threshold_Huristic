# Table A.4 EXPLORATORY: answers whose result changes under scale-aware matching (74 answers)

| answer_span      | gold_number      | class                | class_scale      |   answers | pairs                                                                |
|:-----------------|:-----------------|:---------------------|:-----------------|----------:|:---------------------------------------------------------------------|
| $13,060 thousand | $13,060          | correct              | wrong_in_context |        53 | edgar_q015|cik+year; edgar_q015|cik+year+section; edgar_q015|section |
| $42.9 million    | $42,915 thousand | wrong_in_context     | correct          |        19 | edgar_q028|cik+year                                                  |
| 34,500,000       | 34.5 million     | wrong_not_in_context | correct          |         2 | edgar_q037|cik+year; edgar_q037|cik+year+section                     |

Source: `outputs/edgar_analysis_exploratory_2026-11-01/scale_changes.csv`
