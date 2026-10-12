"""Run holdout_analysis.py unchanged on outputs/phase_a_holdout_rerun (module paths redirected)."""
import sys
from pathlib import Path

from src.phase_c_analysis import holdout_analysis as A

A.HO = Path("outputs/phase_a_holdout_rerun")
A.OUT = A.HO / "analysis"
sys.argv = [sys.argv[0], "--date", "2026-10-12-rerun"]
A.main()
