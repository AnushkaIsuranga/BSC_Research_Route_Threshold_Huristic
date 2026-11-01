# Table A.5 EXPLORATORY: pairs whose prompt held 0 passages

| mode         | breadth          |   n_pairs |   zero_passage_pairs |   gave_number |   abstained_primary |   refusal |   correct |
|:-------------|:-----------------|----------:|---------------------:|--------------:|--------------------:|----------:|----------:|
| default_hnsw | all              |       160 |                    8 |             8 |                   0 |         0 |         0 |
| default_hnsw | cik+year+section |        40 |                    4 |             4 |                   0 |         0 |         0 |
| default_hnsw | cik+year         |        40 |                    2 |             2 |                   0 |         0 |         0 |
| default_hnsw | year+section     |        40 |                    1 |             1 |                   0 |         0 |         0 |
| default_hnsw | section          |        40 |                    1 |             1 |                   0 |         0 |         0 |

Source: `outputs/edgar_analysis_exploratory_2026-11-01/zero_passages.csv`

Note: All other mode x breadth rows have 0 such pairs.
