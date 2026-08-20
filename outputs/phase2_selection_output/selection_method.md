# FinQA Phase 2 candidate-selection method

Primary signal: `qa.gold_inds` count (dataset-provided gold evidence units).

Candidate buckets: 1 unit = narrow; 2 units = boundary; 3+ units = broad. These are candidate buckets only; final labels require documented manual review.

For broad candidates, table-plus-text (`hybrid`) evidence is surfaced before single-modality examples after evidence-unit count. Temporal span, entity/category span, aggregation scope, and program operation count are recorded supporting/balance signals, not tier determinants.

Seed: `42`.

Candidate counts: {'boundary_candidate': 454, 'broad_candidate': 125, 'narrow_candidate': 568}.

Modality counts: {'hybrid': 158, 'table': 706, 'text': 283}.
