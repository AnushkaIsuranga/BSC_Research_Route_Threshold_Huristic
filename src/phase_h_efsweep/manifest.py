"""Build the deterministic Amendment 13 manifest (timed rows + untimed EXPLAIN pass)."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from src import PROJECT_ROOT
from src.phase_e_router import cells as C
from src.phase_h_efsweep import ARMS, EF_VALUES, SEED

HM_TABLES = ("hm_clothes_0", "hm_clothes_25", "hm_clothes_50", "hm_clothes_75", "hm_clothes_100")
HM_FILTERS_PATH = "outputs/phase_a_arms/filters.json"
EDGAR_CAL_FILTERS_PATH = "outputs/edgar_calibration_2026-11-01/grid_filters.json"
EDGAR_CAL_QUERIES_PATH = "outputs/edgar_eval_set_2026-11-01/calibration_queries.csv"
EDGAR_EVAL_PAIRS_PATH = "outputs/edgar_eval_set_2026-11-01/pairs.csv"

# Deterministic smoke-test subset (Stage D):
# - H&M: hm_clothes_0 and hm_clothes_100, 3 cells each spanning selectivity
#   (lo3 < T_hm, lo5 just above T_hm, idx2 high), 3 vectors (0, 1, 2)
# - EDGAR calibration: g02, g07, g11 x first 3 calibration queries
# - EDGAR eval pairs: first 4 pairs (one question's 4 breadths)
SMOKE_HM_TABLES = ("hm_clothes_0", "hm_clothes_100")
SMOKE_HM_FILTERS = ("lo3", "lo5", "idx2")
SMOKE_HM_VECTORS = (0, 1, 2)
SMOKE_EDGAR_CAL_FILTERS = ("g02", "g07", "g11")
SMOKE_N_EDGAR_CAL_VECTORS = 3
SMOKE_N_EDGAR_EVAL_PAIRS = 4


def cell_rng(cell_id: str, seed: int = SEED) -> random.Random:
    """Derive a per-cell sub-RNG deterministically from (seed, cell_id), independent of other cells."""
    digest = hashlib.sha256(f"{seed}|{cell_id}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _load_hm_units(smoke: bool = False) -> list[dict[str, Any]]:
    filters = json.loads((PROJECT_ROOT / HM_FILTERS_PATH).read_text(encoding="utf-8"))
    if smoke:
        filters = [f for f in filters if f["filter_id"] in SMOKE_HM_FILTERS]
        tables = SMOKE_HM_TABLES
        vec_ids = list(SMOKE_HM_VECTORS)
    else:
        tables = HM_TABLES
        vec_ids = C.vector_indices("in_sample")

    units: list[dict[str, Any]] = []
    for table in tables:
        for f in filters:
            fid = f["filter_id"]
            unit_id = f"hm|{table}|{fid}"
            units.append({
                "unit_id": unit_id,
                "dataset": "hm",
                "role": "primary",
                "table": table,
                "cell_id": fid,
                "selectivity": float(f["selectivity"]),
                "conditions": f["conditions"],
                "k": 10,
                "vector_keys": [str(v) for v in vec_ids],
                "breadth": None,
            })
    return units


def _load_edgar_cal_units(smoke: bool = False) -> list[dict[str, Any]]:
    filters = json.loads((PROJECT_ROOT / EDGAR_CAL_FILTERS_PATH).read_text(encoding="utf-8"))
    with (PROJECT_ROOT / EDGAR_CAL_QUERIES_PATH).open("r", encoding="utf-8", newline="") as fh:
        qids = [r["qid"] for r in csv.DictReader(fh)]
    if smoke:
        filters = [f for f in filters if f["filter_id"] in SMOKE_EDGAR_CAL_FILTERS]
        qids = qids[:SMOKE_N_EDGAR_CAL_VECTORS]

    units: list[dict[str, Any]] = []
    for f in filters:
        fid = f["filter_id"]
        unit_id = f"edgar_cal|edgar_chunks|{fid}"
        units.append({
            "unit_id": unit_id,
            "dataset": "edgar_cal",
            "role": "primary",
            "table": "edgar_chunks",
            "cell_id": fid,
            "selectivity": float(f["selectivity"]),
            "conditions": f["conditions"],
            "k": 15,
            "vector_keys": list(qids),
            "breadth": None,
        })
    return units


def _load_edgar_eval_units(smoke: bool = False) -> list[dict[str, Any]]:
    with (PROJECT_ROOT / EDGAR_EVAL_PAIRS_PATH).open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if smoke:
        rows = rows[:SMOKE_N_EDGAR_EVAL_PAIRS]

    units: list[dict[str, Any]] = []
    for r in rows:
        pid = r["pair_id"]
        unit_id = f"edgar_eval|edgar_chunks|{pid}"
        units.append({
            "unit_id": unit_id,
            "dataset": "edgar_eval",
            "role": "secondary",
            "table": "edgar_chunks",
            "cell_id": pid,
            "selectivity": float(r["selectivity"]),
            "conditions": json.loads(r["filter"]),
            "k": 15,
            "vector_keys": [r["qid"]],
            "breadth": r["breadth"],
        })
    return units


def build_units(smoke: bool = False) -> list[dict[str, Any]]:
    """Build all measurement units (65 H&M + 13 EDGAR cal + 160 EDGAR eval for full)."""
    return _load_hm_units(smoke=smoke) + _load_edgar_cal_units(smoke=smoke) + _load_edgar_eval_units(smoke=smoke)


def build_manifest(smoke: bool = False, seed: int = SEED) -> dict[str, Any]:
    """Build deterministic shuffled timed rows and untimed EXPLAIN items."""
    units = build_units(smoke=smoke)
    unit_order = list(units)
    random.Random(seed).shuffle(unit_order)

    timed_rows: list[dict[str, Any]] = []
    explain_items: list[dict[str, Any]] = []

    for unit in unit_order:
        uid = unit["unit_id"]
        rng = cell_rng(uid, seed=seed)
        first_vkey = unit["vector_keys"][0]

        for vkey in unit["vector_keys"]:
            arms = list(ARMS)
            rng.shuffle(arms)
            for arm in arms:
                if arm == "always_exact":
                    ef_list: list[int | None] = [None]
                else:
                    ef_list = list(EF_VALUES)
                    rng.shuffle(ef_list)
                for ef in ef_list:
                    ef_tok = "none" if ef is None else str(ef)
                    row_key = f"{uid}|{vkey}|{arm}|{ef_tok}"
                    timed_rows.append({
                        "row_key": row_key,
                        "unit_id": uid,
                        "dataset": unit["dataset"],
                        "role": unit["role"],
                        "table": unit["table"],
                        "cell_id": unit["cell_id"],
                        "vector_key": vkey,
                        "arm": arm,
                        "ef_search": ef,
                        "selectivity": unit["selectivity"],
                        "conditions": unit["conditions"],
                        "k": unit["k"],
                        "breadth": unit["breadth"],
                    })
                    if vkey == first_vkey:
                        explain_items.append({
                            "explain_key": row_key,
                            "unit_id": uid,
                            "dataset": unit["dataset"],
                            "role": unit["role"],
                            "table": unit["table"],
                            "cell_id": unit["cell_id"],
                            "vector_key": vkey,
                            "arm": arm,
                            "ef_search": ef,
                            "selectivity": unit["selectivity"],
                            "conditions": unit["conditions"],
                            "k": unit["k"],
                        })

    return {
        "seed": seed,
        "smoke": smoke,
        "n_units": len(unit_order),
        "n_timed_rows": len(timed_rows),
        "n_explain_items": len(explain_items),
        "timed_rows": timed_rows,
        "explain_items": explain_items,
    }


def write_manifest(out_dir: Path, smoke: bool = False, seed: int = SEED) -> tuple[Path, str]:
    """Write manifest.json and manifest_meta.json (with SHA-256) to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(smoke=smoke, seed=seed)
    mpath = out_dir / "manifest.json"
    mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8", newline="\n")
    sha = hashlib.sha256(mpath.read_bytes()).hexdigest()
    meta = {
        "seed": seed,
        "smoke": smoke,
        "n_units": manifest["n_units"],
        "n_timed_rows": manifest["n_timed_rows"],
        "n_explain_items": manifest["n_explain_items"],
        "manifest_sha256": sha,
    }
    (out_dir / "manifest_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8", newline="\n")
    return mpath, sha
