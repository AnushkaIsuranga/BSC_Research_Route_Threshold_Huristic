"""The committed figure data, tables and PNGs pass every check of src/figures/check_figures.py (report anchors, 16 cm width)."""

from src.figures import check_figures as C


def test_all_figure_and_table_checks_pass():
    C.ROWS.clear()
    C.run()
    fails = [r for r in C.ROWS if r[-1] != "OK"]
    assert not fails, fails
    assert len(C.ROWS) >= 79
