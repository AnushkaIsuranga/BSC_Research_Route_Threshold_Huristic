"""policy_v2: route = "exact" if estimated_selectivity < T else "iterative-relaxed".

T is read from the frozen config file config/policy_v2.json. The policy never returns
forced-hnsw. Invalid selectivity (None, NaN, non-numeric, outside [0, 1]) raises; there is no
fall-through route.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "policy_v2.json"
EXACT = "exact"
ITERATIVE_RELAXED = "iterative-relaxed"


class PolicyV2InputError(ValueError):
    pass


@lru_cache(maxsize=None)
def load_threshold(path: Path = CONFIG_PATH) -> float:
    t = json.loads(Path(path).read_text(encoding="utf-8"))["T"]
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not 0.0 < t < 1.0:
        raise PolicyV2InputError(f"invalid T in {path}: {t!r}")
    return float(t)


def get_routing_decision_v2(estimated_selectivity: float, threshold: float | None = None) -> str:
    s = estimated_selectivity
    if s is None:
        raise PolicyV2InputError("estimated_selectivity is None")
    if isinstance(s, bool) or not isinstance(s, (int, float)):
        raise PolicyV2InputError(f"estimated_selectivity must be a number, got {type(s).__name__}: {s!r}")
    if math.isnan(s):
        raise PolicyV2InputError("estimated_selectivity is NaN")
    if not 0.0 <= s <= 1.0:
        raise PolicyV2InputError(f"estimated_selectivity {s!r} outside [0, 1]")
    t = load_threshold() if threshold is None else threshold
    return EXACT if s < t else ITERATIVE_RELAXED
