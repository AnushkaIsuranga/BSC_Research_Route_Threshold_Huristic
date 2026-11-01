# Table 4.2 Calibrated threshold T and safe interval

| dataset   | scope                   | iterative variant   |   lower |   upper (s_exact_max) |   s_iter_min | empty interval   |      T | rule                                                                   |
|:----------|:------------------------|:--------------------|--------:|----------------------:|-------------:|:-----------------|-------:|:-----------------------------------------------------------------------|
| H&M       | hm_clothes_0            | default iterative   |  0.0008 |                0.1061 |       0.0105 | False            | 0.0095 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_25           | default iterative   |  0.0001 |                0.1061 |       0.0001 | False            | 0.0036 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_50           | default iterative   |  0.0008 |                0.1061 |       0.0105 | False            | 0.0095 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_75           | default iterative   |  0.0008 |                0.1061 |       0.0105 | False            | 0.0095 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_100          | default iterative   |  0.0478 |                0.1061 |       0.1061 | False            | 0.0712 | geometric mean of interval endpoints                                   |
| H&M       | pooled                  | default iterative   |  0.0478 |                0.1061 |       0.1061 | False            | 0.0712 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_0            | tuned iterative     |  0.0001 |                0.1061 |       0.0008 | False            | 0.0036 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_25           | tuned iterative     |  0.0001 |                0.1061 |       0.0008 | False            | 0.0036 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_50           | tuned iterative     |  0.0001 |                0.1061 |       0.0008 | False            | 0.0036 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_75           | tuned iterative     |  0.0001 |                0.1061 |       0.0008 | False            | 0.0036 | geometric mean of interval endpoints                                   |
| H&M       | hm_clothes_100          | tuned iterative     |  0.0478 |                0.1061 |       0.1061 | False            | 0.0712 | geometric mean of interval endpoints                                   |
| H&M       | pooled                  | tuned iterative     |  0.0478 |                0.1061 |       0.1061 | False            | 0.0712 | geometric mean of interval endpoints                                   |
| EDGAR     | edgar_chunks (= pooled) | default iterative   |  -      |                0.4709 |       -      | True             | 0.3787 | empty interval: grid point with fewest failing cells (ties -> smaller) |
| EDGAR     | edgar_chunks (= pooled) | tuned iterative     |  -      |                0.4709 |       -      | True             | 0.3787 | empty interval: grid point with fewest failing cells (ties -> smaller) |

Source: `config/policy_v3_hm.json`, `outputs/edgar_calibration_2026-11-01/calibration.json`

Note: The deployed T is the pooled value (H&M 0.0712, EDGAR 0.3787). Empty cells: no s_iter_min / lower endpoint exists.
