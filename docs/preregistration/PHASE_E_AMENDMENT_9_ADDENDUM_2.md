# Phase E, Amendment 9, Addendum 2: CPU measure of the quiet-machine rule

**Status:** written 2026-10-30, committed and tagged `phase-e-amendment-9-addendum-2-2026-10-30` before the D2 calibration session and before Task 4. Amends `PHASE_E_AMENDMENT_9.md` (tag `phase-e-amendment-9-2026-10-30`) and Addendum 1 only where stated; everything else is unchanged.

## Why it was added

Amendment 9 requires "mean host CPU <= 25% over 30 s before start" without naming the measure. The implementation (`src/phase_e_router/cells.py`, `quiet_check`) used `Win32_Processor.LoadPercentage`. Two checks with no torrent client, Ollama or Jupyter running refused to start:

| check | Win32 LoadPercentage samples (%) | mean | `\Processor(_Total)\% Processor Time` | sum of per-process CPU |
|---|---|---|---|---|
| 1 | 52, 54, 42, 74, 74, 74 | 61.7 | 28.7-68.8 | about 18 % |
| 2 | 36, 49, 49, 40, 41, 72 | 47.8 | 11.7-20.6 (sampled just after) | about 15 % |

In check 2 the per-process counters (largest: svchost 4.3 %, Claude 3.5 %, dwm 1.7 %, System 1.6 %, Kaspersky 1.5 %) agree with the processor counter, not with LoadPercentage, which runs about 25-30 points higher and jumps (40 -> 72) without any process accounting for it. The rule was meant to exclude competing work, which LoadPercentage does not measure reliably on this host. The change was made at the author's decision after these two refusals and **before any timed-session data existed** (no row of `outputs/phase_e_calibration_hm_2026-10-30/results.jsonl` or `outputs/phase_e_comparison_hm_2026-10-31/` had been written).

## Rule (D2 session and Task 4)

- Measure: Windows performance counter `\Processor(_Total)\% Processor Time`, 6 consecutive samples at a 5 s interval (`Get-Counter -SampleInterval 5 -MaxSamples 6`, about 30 s); each sample is the average over its interval.
- The session starts only if no torrent client, Ollama or Jupyter process runs **and** the mean of the 6 samples is **<= 25 %**. The limit, the process list and "otherwise the session does not start" are unchanged.
- Disclosure: 6 `Win32_Processor.LoadPercentage` readings are taken right after and stored with the check, not used for the decision. The 5-minute host-load log during the session records both measures and the top-5 processes.
- No other quiet-rule measure is substituted later; a refusal is reported, not overridden.
