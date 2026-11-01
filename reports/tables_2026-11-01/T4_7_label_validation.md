# Table 4.7 Label validation: automatic class vs checked S/C/N(/X) labels

| dataset                       | automatic class      | S   | C   | N   | X                  |
|:------------------------------|:---------------------|:----|:----|:----|:-------------------|
| FinQA (Amendment 5, 40 rows)  | wrong_grounded       | 7   | 13  | 0   | -                  |
| FinQA (Amendment 5, 40 rows)  | wrong_ungrounded     | 0   | 14  | 6   | -                  |
| EDGAR (Amendment 11, 40 rows) | wrong_in_context     | 8   | 0   | 2   | 16                 |
| EDGAR (Amendment 11, 40 rows) | wrong_not_in_context | 0   | 0   | 12  | 2                  |
| EDGAR agreement (S/C/N rows)  | 20/22 = 0.909        | -   | -   | -   | 18 X rows excluded |

Source: `outputs/hallucination_classification_2026-10-23/label_analysis/label_confusion.json`, `outputs/edgar_analysis_exploratory_2026-11-01/agreement.json`

Note: S = number in the retrieved text; C = calculable from it; N = not supported; X (EDGAR only, added by the author, DEVIATION_LOG.md 2026-11-01) = refusal. FinQA proxy: wrong_ungrounded; EDGAR proxy: wrong_not_in_context. Labels drafted by the AI assistant and checked by the author.
