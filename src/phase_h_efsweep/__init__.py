"""Phase H (Amendment 13): ef_search sweep manifest, runner, and EXPLAIN pass.

No LLM or external network/API clients are imported or used in this package.
Reuses src/phase_e_router/retriever.py and src/phase_f_edgar/session_tools.py
without modifying any tagged file.
"""

from __future__ import annotations

SEED = 20261117
EF_VALUES = (40, 100, 200, 400)
ARMS = ("always_exact", "default_hnsw", "always_iterative")
TIMED_REPS = 5
EARLY_STOP_MS = 1500.0
AMENDMENT_TAG = "phase-h-amendment-13"
