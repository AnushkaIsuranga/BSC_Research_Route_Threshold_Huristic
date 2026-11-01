# Table A.6 EXPLORATORY: wrong-source and wrong-year rows in the EDGAR label sample

| sample_id   | label   | mode         | wrong_source   | wrong_year   | author_note                                                                                                                                                                      |
|:------------|:--------|:-------------|:---------------|:-------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| L04         | S       | default_hnsw | True           | False        | Agree S. Number copied from another company's passage (wrong source).                                                                                                            |
| L13         | N       | default_hnsw | True           | False        | Changed S -> N. The only $0 in the passages is another company's unbilled revenue: a coincidental match, not support. Consistent with L32.                                       |
| L21         | S       | router       | False          | True         | Agree S, but wrong report year: the passage is from the 2019 10-K ("As of December 31, 2019"), while the question asks about the 2018 report. Gold ($25.3m) is correct for 2018. |
| L33         | S       | default_hnsw | True           | False        | Agree S. Number copied from another company's passage (wrong source).                                                                                                            |

Source: `outputs/edgar_analysis_exploratory_2026-11-01/label_error_sources.json`

Note: S rows: 8; wrong source ['L04', 'L33']; wrong year ['L21'].
