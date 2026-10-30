"""policy_v3 (Amendment 9): pure functions only, no database access.

- estimate_selectivity(): planner "Plan Rows" / reltuples, error on missing statistics (no fallback).
- decide_band(): s_est < T/2 -> exact; s_est > 2T -> iterative; otherwise (edges included) "count".
- count_cap() / decide_count(): capped count, count == cap -> iterative, else exact.
- local_probe_route() / combine_with_probe(): p < k -> exact.
- cell_passes(): PHASE_A_ARMS_PROTOCOL.md Amendment 1, A3.
- calibrate(): safe interval and T, per table and pooled.
"""

from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence

EXACT = "exact"
ITERATIVE = "iterative"
COUNT = "count"


class PolicyInputError(ValueError):
    """Missing or invalid input to a decision rule; never replaced by a default."""


def _check_T(T) -> float:
    if T is None or isinstance(T, bool) or not isinstance(T, (int, float)) or not math.isfinite(T) or not 0 < T < 1:
        raise PolicyInputError(f"T must be a number in (0, 1), got {T!r}")
    return float(T)


def estimate_selectivity(plan_rows, reltuples) -> float:
    """s_est = Plan Rows / N. reltuples -1 (never analysed) or <= 0, or a missing Plan Rows, is an error."""
    if reltuples is None or isinstance(reltuples, bool) or not isinstance(reltuples, (int, float)):
        raise PolicyInputError(f"reltuples missing: {reltuples!r}")
    if reltuples == -1:
        raise PolicyInputError("reltuples = -1: table has no statistics (ANALYZE has not run)")
    if reltuples <= 0:
        raise PolicyInputError(f"reltuples = {reltuples}: cannot estimate selectivity")
    if plan_rows is None or isinstance(plan_rows, bool) or not isinstance(plan_rows, (int, float)) or plan_rows < 0:
        raise PolicyInputError(f"Plan Rows missing or invalid: {plan_rows!r}")
    return float(plan_rows) / float(reltuples)


def decide_band(s_est, T) -> str:
    T = _check_T(T)
    if s_est is None or isinstance(s_est, bool) or not isinstance(s_est, (int, float)) or not math.isfinite(s_est) or s_est < 0:
        raise PolicyInputError(f"s_est missing or invalid: {s_est!r}")
    if s_est < T / 2:
        return EXACT
    if s_est > 2 * T:
        return ITERATIVE
    return COUNT


def count_cap(T, n_rows) -> int:
    """LIMIT of the capped count: floor(T * N) + 1."""
    T = _check_T(T)
    if n_rows is None or isinstance(n_rows, bool) or not isinstance(n_rows, (int, float)) or n_rows <= 0:
        raise PolicyInputError(f"N missing or invalid: {n_rows!r}")
    return math.floor(T * n_rows) + 1


def decide_count(count, cap) -> str:
    if count is None or cap is None or count < 0 or cap < 1 or count > cap:
        raise PolicyInputError(f"invalid capped count {count!r} / cap {cap!r}")
    return ITERATIVE if count == cap else EXACT


def decide_from_full_count(full_count, T, n_rows) -> str:
    """Reference decision from an uncapped count (used to check the capped count)."""
    return ITERATIVE if full_count >= count_cap(T, n_rows) else EXACT


def local_probe_route(p, k) -> str:
    if p is None or k is None or p < 0 or k < 1:
        raise PolicyInputError(f"invalid probe count p={p!r}, k={k!r}")
    return EXACT if p < k else ITERATIVE


def combine_with_probe(router_route: str, p, k) -> str:
    """router_plus_probe: keep the router's route, except iterative with p < k -> exact."""
    if router_route not in (EXACT, ITERATIVE):
        raise PolicyInputError(f"router route must be exact/iterative, got {router_route!r}")
    if router_route == ITERATIVE and local_probe_route(p, k) == EXACT:
        return EXACT
    return router_route


def cell_passes(recalls: Sequence, latencies_ms: Sequence, *, n_expected: int = 20, recall_target: float = 0.9,
                latency_limit_ms: float = 500.0) -> dict:
    """Pass rule A3: all n_expected vectors valid, mean recall >= target, median of per-vector medians <= limit.
    An invalid vector is None in either list."""
    if len(recalls) != n_expected or len(latencies_ms) != n_expected:
        return {"passed": False, "valid": False, "reason": f"expected {n_expected} vectors, got {len(recalls)}/{len(latencies_ms)}",
                "mean_recall": None, "median_latency_ms": None}
    if any(r is None for r in recalls) or any(t is None for t in latencies_ms):
        n_bad = sum(1 for r, t in zip(recalls, latencies_ms) if r is None or t is None)
        return {"passed": False, "valid": False, "reason": f"{n_bad} invalid vectors", "mean_recall": None,
                "median_latency_ms": None}
    mean_recall = statistics.fmean(recalls)
    med = statistics.median(latencies_ms)
    reasons = []
    if mean_recall < recall_target:
        reasons.append("recall")
    if med > latency_limit_ms:
        reasons.append("latency")
    return {"passed": not reasons, "valid": True, "reason": "+".join(reasons) or None, "mean_recall": mean_recall,
            "median_latency_ms": med}


def safe_interval(grid: Sequence[float], exact_pass: dict, iter_pass: dict) -> dict:
    """One table (or the pooled pass map). grid: sorted distinct selectivities; *_pass: {s: bool} for every s."""
    grid = sorted(grid)
    if len(set(grid)) != len(grid) or not grid:
        raise PolicyInputError("grid must be non-empty and distinct")
    for name, m in (("exact", exact_pass), ("iterative", iter_pass)):
        missing = [s for s in grid if s not in m or m[s] is None]
        if missing:
            raise PolicyInputError(f"{name} pass status missing at {missing}")
    passing_exact = [s for s in grid if exact_pass[s]]
    s_exact_max = max(passing_exact) if passing_exact else None
    s_iter_min = None
    for i, s in enumerate(grid):
        if all(iter_pass[x] for x in grid[i:]):
            s_iter_min = s
            break
    lower = None
    if s_iter_min is not None:
        i = grid.index(s_iter_min)
        lower = grid[i - 1] if i > 0 else grid[0]
    empty = s_exact_max is None or s_iter_min is None or lower >= s_exact_max
    out = {"s_exact_max": s_exact_max, "s_iter_min": s_iter_min, "lower": lower, "upper": s_exact_max,
           "lower_is_smallest_grid_point": s_iter_min is not None and s_iter_min == grid[0], "empty": empty}
    if not empty:
        out["T"] = math.sqrt(lower * s_exact_max)
        out["T_rule"] = "geometric mean of interval endpoints"
    else:
        fails = {T: _threshold_failures(grid, [exact_pass], [iter_pass], T) for T in grid}
        best = min(grid, key=lambda T: (fails[T], T))
        out["T"] = best
        out["T_rule"] = "empty interval: grid point with fewest failing cells (ties -> smaller)"
        out["failures_by_T"] = {str(T): n for T, n in fails.items()}
    return out


def _threshold_failures(grid, exact_maps, iter_maps, T) -> int:
    n = 0
    for e, it in zip(exact_maps, iter_maps):
        for s in grid:
            n += 0 if (e[s] if s < T else it[s]) else 1
    return n


def calibrate(cells: Iterable[dict]) -> dict:
    """cells: one record per (table, s) with keys table, s, exact_pass, iter_pass (bools).
    Returns per-table intervals and the pooled interval (a grid point passes only if it passes on every table).
    In the empty pooled case, failures are counted over all tables' cells."""
    by_table: dict[str, dict] = {}
    for c in cells:
        for key in ("table", "s", "exact_pass", "iter_pass"):
            if c.get(key) is None:
                raise PolicyInputError(f"cell missing {key}: {c}")
        t = by_table.setdefault(c["table"], {"exact": {}, "iter": {}})
        if c["s"] in t["exact"]:
            raise PolicyInputError(f"duplicate cell {c['table']} s={c['s']}")
        t["exact"][c["s"]], t["iter"][c["s"]] = bool(c["exact_pass"]), bool(c["iter_pass"])
    if not by_table:
        raise PolicyInputError("no cells")
    grids = {tuple(sorted(v["exact"])) for v in by_table.values()}
    if len(grids) != 1:
        raise PolicyInputError("tables have different grids")
    grid = list(next(iter(grids)))
    per_table = {t: safe_interval(grid, v["exact"], v["iter"]) for t, v in sorted(by_table.items())}
    pooled_exact = {s: all(v["exact"][s] for v in by_table.values()) for s in grid}
    pooled_iter = {s: all(v["iter"][s] for v in by_table.values()) for s in grid}
    pooled = safe_interval(grid, pooled_exact, pooled_iter)
    if pooled["empty"]:
        maps = list(by_table.values())
        fails = {T: _threshold_failures(grid, [m["exact"] for m in maps], [m["iter"] for m in maps], T) for T in grid}
        pooled["T"] = min(grid, key=lambda T: (fails[T], T))
        pooled["T_rule"] = "empty pooled interval: grid point with fewest failing cells over all tables (ties -> smaller)"
        pooled["failures_by_T"] = {str(T): n for T, n in fails.items()}
    return {"grid": grid, "per_table": per_table, "pooled": pooled, "T": pooled["T"]}
