"""Run holdout_analysis.py unchanged on outputs/phase_a_holdout_rerun (module paths redirected).

holdout_analysis.py hardcodes the string 'outputs/phase_a_holdout' in its report text; the data it
reads comes from A.HO (redirected here), so only the labels are rewritten to the rerun folder.
"""
import sys
from pathlib import Path

from src.phase_c_analysis import holdout_analysis as A

ORIG, RERUN = "outputs/phase_a_holdout", "outputs/phase_a_holdout_rerun"
A.HO = Path(RERUN)
A.OUT = A.HO / "analysis"
_build = A.build_report
A.build_report = lambda *a, **k: _build(*a, **k).replace(ORIG + "/", RERUN + "/")
sys.argv = [sys.argv[0], "--date", "2026-10-12-rerun"]
A.main()
