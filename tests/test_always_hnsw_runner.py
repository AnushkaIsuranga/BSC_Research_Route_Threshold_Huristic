import unittest.mock

import pytest

from src.phase_b_router import router as router_mod
from src.phase_d_validation import always_hnsw_runner as AH
from tests.test_router_graphs import deps, state


IDS = [f"T{i}/2020/page_1.pdf-1" for i in range(50)]


def test_full_schedule_counts_and_seed():
    items = AH.schedule(IDS)
    assert len(items) == 300 and len(set(items)) == 300
    assert sum(1 for _, _, a in items if a == AH.ARM_HNSW) == 250
    assert {p for p, _, a in items if a == AH.ARM_V2} == {1}
    assert {p for p, _, a in items if a == AH.ARM_HNSW} == {1, 2, 3, 4, 5}
    assert items == AH.schedule(list(reversed(IDS)))          # deterministic, independent of input order
    assert items[:5] != sorted(items)[:5]                       # shuffled


def test_pilot_schedule():
    items = AH.schedule(IDS, pilot=True)
    assert len(items) == 5 and all(p == 1 and a == AH.ARM_HNSW for p, _, a in items)
    assert items == AH.schedule(IDS, pilot=True)


@pytest.fixture
def recorded_retrieve():
    calls = []

    def fake(conn, route, t, y, v, k, tbl="finqa_evidence", distinct=False):
        calls.append((route, k, distinct))
        return {"rows": [], "rows_fetched": 0, "tie_truncated": True}
    with unittest.mock.patch.object(router_mod, "retrieve", side_effect=fake):
        yield calls


@pytest.mark.parametrize("sel", [0.0005, 0.5])
def test_always_hnsw_uses_post_filter_whatever_the_selectivity(recorded_retrieve, sel):
    out = AH.build_always_hnsw_graph(deps()).invoke(state(sel))
    assert out["chosen_route"] == "post-filter"
    assert recorded_retrieve == [("post-filter", 6, False)]
    assert out["rows_returned"] == 0                            # 0 rows still go to the answer model, no fallback
