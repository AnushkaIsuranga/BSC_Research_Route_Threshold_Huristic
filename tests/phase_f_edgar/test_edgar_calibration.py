"""Phase F Task 3 helpers: grid cik sets, quiet-rule stop condition, guard derivation (no database)."""

import pytest

from src.phase_e_router import retriever as R
from src.phase_f_edgar import calibrate_edgar as CE
from src.phase_f_edgar import session_tools as S


def test_grid_filters_close_and_reproducible():
    rows = {f"{i:07d}": (i * 37) % 900 + 8 for i in range(433)}
    n = sum(rows.values())
    grid = [0.000124, 0.0105, 0.106, 0.47]
    a, b = CE.build_grid_filters(rows, grid, n), CE.build_grid_filters(rows, grid, n)
    assert a == b
    for f, s in zip(a, grid):
        assert f["matched_rows"] == sum(rows[c] for c in f["conditions"][0][1])
        assert abs(f["matched_rows"] - s * n) <= 908            # within one CIK's rows of the target
    assert CE.build_grid_filters(rows, grid, n, seed=1) != a


def test_quiet_start_stops_after_three_refusals(tmp_path):
    calls = []
    check = lambda: {"quiet": False, "cpu_mean": 40.0, "blocking_processes": []}
    with pytest.raises(SystemExit, match="3 times"):
        S.quiet_start(tmp_path, check=check, sleep=calls.append)
    assert calls == [300, 300]
    seq = iter([{"quiet": False, "cpu_mean": 30.0, "blocking_processes": []}, {"quiet": True, "cpu_mean": 10.0, "blocking_processes": []}])
    assert S.quiet_start(tmp_path, check=lambda: next(seq), sleep=lambda s: None)["passed"]["attempt"] == 2


def test_guard_derivation_k15():
    by = {("g", "q", R.R_EXACT): {"recall15": 1.0, "recall10": 1.0, "latency_ms": 10.0, "rows_returned": 15},
          ("g", "q", R.R_ITER): {"recall15": 0.4, "recall10": 0.5, "latency_ms": 3.0, "rows_returned": 6},
          ("g", "q", R.R_ITER_TUNED): {"recall15": 0.9, "recall10": 0.9, "latency_ms": 30.0, "rows_returned": 15}}
    assert CE.per_vector(by, "g", "q", "iter") == (0.4, 3.0, 6, False, 0.5)
    assert CE.per_vector(by, "g", "q", "iter_guard") == (1.0, 13.0, 15, True, 1.0)
    assert CE.per_vector(by, "g", "q", "tuned_guard") == (0.9, 30.0, 15, False, 0.9)


def test_recall_at():
    assert S.recall_at([1, 2, 3], [1, 2, 4], 15) == 2 / 3
    assert S.recall_at(list(range(15)), list(range(14, -1, -1)), 10) == 0.5
    assert S.recall_at([], [], 15) is None
