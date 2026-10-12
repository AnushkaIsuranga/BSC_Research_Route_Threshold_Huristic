import math

import pytest

from src.phase_b_router.policy_v2 import (EXACT, ITERATIVE_RELAXED, PolicyV2InputError, get_routing_decision_v2,
                                          load_threshold)

T = load_threshold()


def test_T_is_frozen_value():
    assert T == 0.1


def test_just_below_T():
    assert get_routing_decision_v2(math.nextafter(T, 0)) == EXACT


def test_exactly_T_is_iterative():
    assert get_routing_decision_v2(T) == ITERATIVE_RELAXED


def test_above_T():
    assert get_routing_decision_v2(0.1000001) == ITERATIVE_RELAXED


def test_zero():
    assert get_routing_decision_v2(0) == EXACT
    assert get_routing_decision_v2(0.0) == EXACT


def test_one():
    assert get_routing_decision_v2(1) == ITERATIVE_RELAXED


@pytest.mark.parametrize("bad", [float("nan"), None, -0.001, 1.0001, 5, "0.05", True, float("inf"), float("-inf")])
def test_invalid_raises(bad):
    with pytest.raises(PolicyV2InputError):
        get_routing_decision_v2(bad)


def test_never_forced_hnsw():
    outs = {get_routing_decision_v2(i / 1000) for i in range(1001)}
    assert outs == {EXACT, ITERATIVE_RELAXED}
