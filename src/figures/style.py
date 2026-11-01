"""Common style for the dissertation figures (2026-11-01): one fixed colour and marker per mode, fixed mode order, display
names, A4 sizing and the save helper. Colours are Okabe-Ito plus Paul Tol's muted set (colour-blind safe); modes that share
a hue differ by marker.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src import PROJECT_ROOT  # noqa: E402

FIG_DIR = PROJECT_ROOT / "reports/figures_2026-11-01"
TAB_DIR = PROJECT_ROOT / "reports/tables_2026-11-01"
CM = 1 / 2.54
FULL_W = 16 * CM                                          # A4 text width
FONT = 9

plt.rcParams.update({
    "font.size": FONT, "axes.labelsize": FONT, "xtick.labelsize": FONT, "ytick.labelsize": FONT, "legend.fontsize": FONT,
    "font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 300,
    "pdf.fonttype": 42, "ps.fonttype": 42, "axes.titlesize": FONT, "legend.frameon": False, "svg.hashsalt": "figures-2026-11-01",
    "path.simplify": False,
})

# code name -> (display name, colour, marker); this order is the order of legends and tables
MODES = {
    "router": ("Router (policy_v3.1)", "#0072B2", "o"),
    "router_tuned": ("Router, tuned iterative", "#56B4E9", "o"),
    "router_no_guard": ("Router, no guard", "#56B4E9", "v"),
    "router_always_count": ("Router, always count", "#56B4E9", "<"),
    "router_plus_probe": ("Router + local probe", "#56B4E9", ">"),
    "always_exact": ("Always exact", "#000000", "P"),
    "llm_router": ("LLM router", "#CC79A7", "D"),
    "fixed_t_0_1": ("Fixed T = 0.1", "#332288", "p"),
    "router_hmT": ("Router with H&M T", "#009E73", "*"),
    "local_probe": ("Local probe", "#44AA99", "h"),
    "planner_iterative": ("Planner + iterative", "#117733", "v"),
    "retry_exact": ("HNSW, retry exact", "#882255", "X"),
    "iterative_tuned": ("Iterative, tuned", "#DDCC77", "^"),
    "always_iterative": ("Always iterative", "#E69F00", "^"),
    "vecadvisor": ("VecAdvisor", "#999933", "d"),
    "vbase": ("VBASE rule (s < 0.18)", "#AA4499", "H"),
    "milvus": ("Milvus rule (s <= 0.05)", "#88CCEE", "8"),
    "qdrant": ("Qdrant rule (rows)", "#CC6677", "<"),
    "default_hnsw": ("Filtered HNSW (pgvector default)", "#D55E00", "s"),
    "oracle": ("Oracle (per cell)", "#777777", "*"),
    # FinQA arms and H&M prior rules
    "policy_v2": ("Router (policy_v2)", "#0072B2", "o"),
    "naive_llm": ("LLM router", "#CC79A7", "D"),
    "always_hnsw": ("Filtered HNSW (pgvector default)", "#D55E00", "s"),
    "decision_matrix": ("Decision matrix v1 (LLM-free)", "#BBBBBB", "o"),
    "naive_informed": ("LLM router, informed prompt", "#CC79A7", "d"),
    "v1": ("v1 decision matrix", "#BBBBBB", "o"),
    "B1": ("B1 VBASE (s < 0.18)", "#AA4499", "H"),
    "B2": ("B2 Milvus (s <= 0.05)", "#88CCEE", "8"),
    "B3": ("B3 Qdrant (rows < 1,250)", "#CC6677", "<"),
    "B4": ("B4 Gan & Wang (recall/latency labels)", "#661100", "v"),
    "B4b": ("B4b Gan & Wang (SLA labels)", "#AA6644", "v"),
}
EDGAR_MODES = ["router", "router_tuned", "router_no_guard", "router_always_count", "router_plus_probe", "always_exact", "llm_router",
               "fixed_t_0_1", "router_hmT", "local_probe", "planner_iterative", "retry_exact", "iterative_tuned", "always_iterative",
               "vecadvisor", "vbase", "milvus", "qdrant", "default_hnsw"]
ROUTER_GROUP_LABEL = "Router (= always-exact; 7 identical modes)"
BREADTH_LABEL = {"cik+year+section": "company + year + section", "cik+year": "company + year", "year+section": "year + section",
                 "section": "section", "all": "all breadths"}

# calibration routes (EDGAR Fig 4.4 / A.1)
ROUTES = {"exact": ("Exact", "#000000", "o"), "iter": ("Iterative (default)", "#E69F00", "^"),
          "iter_guard": ("Iterative + guard", "#0072B2", "s"), "tuned": ("Iterative, tuned", "#DDCC77", "v"),
          "tuned_guard": ("Iterative, tuned + guard", "#009E73", "D")}
# H&M three-arm run (Fig 4.2)
ARMS = {"planner-default": ("Planner default", "#777777", "o"), "forced-exact": ("Forced exact", "#000000", "P"),
        "forced-hnsw": ("Forced HNSW (= filtered HNSW)", "#D55E00", "s"), "iterative-relaxed": ("Iterative, relaxed order", "#E69F00", "^"),
        "iterative-strict": ("Iterative, strict order", "#009E73", "v")}
HM_TABLE_LABEL = {"hm_clothes_0": "hm_clothes_0 (least correlated)", "hm_clothes_25": "hm_clothes_25", "hm_clothes_50": "hm_clothes_50",
                  "hm_clothes_75": "hm_clothes_75", "hm_clothes_100": "hm_clothes_100 (most correlated)"}
T_HM_COLOUR, T_EDGAR_COLOUR = "#009E73", "#0072B2"


def name(mode: str) -> str:
    return MODES[mode][0]


def colour(mode: str) -> str:
    return MODES[mode][1]


def marker(mode: str) -> str:
    return MODES[mode][2]


def half_up(x: float, places: int = 3) -> str:
    """Report-style rounding (half away from zero on the decimal text of the value)."""
    return str(Decimal(repr(x)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def fig(h_cm: float, ncols: int = 1, nrows: int = 1, w_cm: float | None = None, **kw):
    return plt.subplots(nrows, ncols, figsize=((w_cm * CM) if w_cm else FULL_W, h_cm * CM), **kw)


def save(f, stem: str) -> list[Path]:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for ext in ("png", "pdf"):
        p = FIG_DIR / f"{stem}.{ext}"
        f.savefig(p, dpi=300, bbox_inches="tight", pad_inches=0.03, metadata={"CreationDate": None} if ext == "pdf" else {"Software": None})
        out.append(p)
    plt.close(f)
    return out
