# Phase D Deviation Log

## 2026-09-30 — latency instrumentation correction

The first completed local run recorded retrieval-plus-answer latency because
the timer started after the naive router call and embedding generation. This
was an instrumentation bug, not model/prompt/threshold tuning. The runner was
updated to preserve the original retrieval-plus-answer fields and additionally
record end-to-end latency including route selection, embedding, retrieval, and
answer generation. The frozen configuration remains unchanged; the full run is
repeated with the corrected measurement.

Record any full-run infrastructure repair here before repeating a query or run:
date, failure, exact change, why it is a bug rather than tuning, affected
queries, and rerun result.
