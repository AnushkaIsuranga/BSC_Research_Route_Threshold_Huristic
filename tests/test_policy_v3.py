import math

import pytest

from src.phase_e_router.policy_v3 import (COUNT, EXACT, ITERATIVE, PolicyInputError, calibrate, cell_passes,
                                          combine_with_probe, count_cap, decide_band, decide_count,
                                          decide_from_full_count, estimate_selectivity, local_probe_route,
                                          safe_interval)

T = 0.08


# ---- band rule edges
def test_band_just_below_half_T_is_exact():
    assert decide_band(math.nextafter(T / 2, 0), T) == EXACT


def test_band_at_half_T_counts():
    assert decide_band(T / 2, T) == COUNT


def test_band_at_T_counts():
    assert decide_band(T, T) == COUNT


def test_band_at_two_T_counts():
    assert decide_band(2 * T, T) == COUNT


def test_band_just_above_two_T_is_iterative():
    assert decide_band(math.nextafter(2 * T, 1), T) == ITERATIVE


def test_band_zero_is_exact():
    assert decide_band(0.0, T) == EXACT


@pytest.mark.parametrize("bad", [None, float("nan"), -0.1, "0.1", True])
def test_band_missing_estimate_errors(bad):
    with pytest.raises(PolicyInputError):
        decide_band(bad, T)


@pytest.mark.parametrize("bad_T", [None, 0, 1, -0.1, float("inf")])
def test_band_missing_T_errors(bad_T):
    with pytest.raises(PolicyInputError):
        decide_band(0.05, bad_T)


# ---- estimate
def test_estimate_ratio():
    assert estimate_selectivity(1149, 105100.0) == pytest.approx(1149 / 105100)


@pytest.mark.parametrize("reltuples", [-1, -1.0, 0, None])
def test_estimate_missing_statistics_errors(reltuples):
    with pytest.raises(PolicyInputError):
        estimate_selectivity(10, reltuples)


@pytest.mark.parametrize("plan_rows", [None, -1, "10"])
def test_estimate_missing_plan_rows_errors(plan_rows):
    with pytest.raises(PolicyInputError):
        estimate_selectivity(plan_rows, 105100)


# ---- capped count
def test_count_cap_value():
    assert count_cap(0.1, 105100) == 10511


def test_count_equal_cap_is_iterative():
    assert decide_count(10511, 10511) == ITERATIVE


def test_count_below_cap_is_exact():
    assert decide_count(10510, 10511) == EXACT


def test_count_above_cap_is_invalid():
    with pytest.raises(PolicyInputError):
        decide_count(10512, 10511)


@pytest.mark.parametrize("full", [0, 9, 10510, 10511, 10512, 50000])
def test_capped_matches_full_count(full):
    cap = count_cap(0.1, 105100)
    assert decide_count(min(full, cap), cap) == decide_from_full_count(full, 0.1, 105100)


# ---- local probe
def test_probe_k_minus_one_is_exact():
    assert local_probe_route(9, 10) == EXACT


def test_probe_k_is_iterative():
    assert local_probe_route(10, 10) == ITERATIVE


def test_probe_invalid_errors():
    with pytest.raises(PolicyInputError):
        local_probe_route(None, 10)


def test_combine_probe_overrides_iterative_only():
    assert combine_with_probe(ITERATIVE, 9, 10) == EXACT
    assert combine_with_probe(ITERATIVE, 10, 10) == ITERATIVE
    assert combine_with_probe(EXACT, 100, 10) == EXACT


# ---- pass rule
def test_pass_rule_pass_and_fail_reasons():
    assert cell_passes([1.0] * 20, [10.0] * 20)["passed"]
    r = cell_passes([0.85] * 20, [600.0] * 20)
    assert not r["passed"] and r["reason"] == "recall+latency"
    assert cell_passes([0.9] * 20, [500.0] * 20)["passed"]       # boundaries inclusive


def test_pass_rule_invalid_vector_fails():
    r = cell_passes([1.0] * 19 + [None], [1.0] * 20)
    assert not r["passed"] and not r["valid"]
    assert not cell_passes([1.0] * 19, [1.0] * 19)["passed"]


# ---- calibration
GRID = [0.0001, 0.001, 0.01, 0.05, 0.1, 0.2, 0.3]


def _maps(exact_upto, iter_from):
    return ({s: s <= exact_upto for s in GRID}, {s: s >= iter_from for s in GRID})


def test_interval_and_geometric_mean():
    e, it = _maps(0.2, 0.05)
    r = safe_interval(GRID, e, it)
    assert (r["lower"], r["upper"], r["empty"]) == (0.01, 0.2, False)
    assert r["T"] == pytest.approx(math.sqrt(0.01 * 0.2))


def test_iter_min_requires_all_higher_points():
    e, it = _maps(0.2, 0.0001)
    it[0.01] = False                       # a failure in the middle pushes s_iter_min above it
    r = safe_interval(GRID, e, it)
    assert r["s_iter_min"] == 0.05 and r["lower"] == 0.01


def test_iter_min_at_smallest_point_uses_that_point():
    e, it = _maps(0.1, 0.0001)
    r = safe_interval(GRID, e, it)
    assert r["lower_is_smallest_grid_point"] and r["lower"] == 0.0001 and not r["empty"]


def test_empty_interval_picks_fewest_failures():
    e, it = _maps(0.01, 0.2)               # exact passes up to 0.01, iterative only from 0.2: gap at 0.05, 0.1
    r = safe_interval(GRID, e, it)
    assert r["empty"]
    # T=0.05: 0.05 and 0.1 go iterative and fail -> 2; T=0.1: 0.05 exact fails, 0.1 iter fails -> 2; T=0.2: 2. Ties -> smallest.
    assert r["T"] == 0.05 and r["failures_by_T"]["0.05"] == 2


def test_no_iterative_pass_is_empty():
    e, it = _maps(0.2, 1.0)
    assert safe_interval(GRID, e, it)["empty"]


def test_missing_pass_status_errors():
    e, it = _maps(0.2, 0.05)
    del it[0.3]
    with pytest.raises(PolicyInputError):
        safe_interval(GRID, e, it)


def test_calibrate_pooled_is_intersection():
    cells = []
    for t, (eu, itf) in {"a": (0.2, 0.01), "b": (0.1, 0.05)}.items():
        e, it = _maps(eu, itf)
        cells += [{"table": t, "s": s, "exact_pass": e[s], "iter_pass": it[s]} for s in GRID]
    r = calibrate(cells)
    assert r["per_table"]["a"]["T"] == pytest.approx(math.sqrt(0.001 * 0.2))
    assert (r["pooled"]["lower"], r["pooled"]["upper"]) == (0.01, 0.1)
    assert r["T"] == pytest.approx(math.sqrt(0.01 * 0.1))


def test_calibrate_rejects_missing_and_duplicate():
    with pytest.raises(PolicyInputError):
        calibrate([{"table": "a", "s": 0.1, "exact_pass": True, "iter_pass": None}])
    c = {"table": "a", "s": 0.1, "exact_pass": True, "iter_pass": True}
    with pytest.raises(PolicyInputError):
        calibrate([c, dict(c)])
