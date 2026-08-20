"""Shared project paths and constants for the research pipeline."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXTERNAL_DATA_DIR = DATA_DIR / "external"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LOGS_DIR = OUTPUTS_DIR / "logs"
PLOTS_DIR = OUTPUTS_DIR / "plots"
PHASE2_OUTPUT_DIR = OUTPUTS_DIR / "phase2_selection_output"

NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
SQL_DIR = PROJECT_ROOT / "sql"

BENCHMARK_DATA_DIR = PROJECT_ROOT / "ann-filtering-benchmark-datasets" / "data"
HM_DATASET_URL = "https://storage.googleapis.com/ann-filtered-benchmark/datasets/hnm.tgz"

CORRELATION_TIERS = (100, 75, 50, 25, 0)
HM_TABLES = tuple(f"hm_clothes_{tier}" for tier in CORRELATION_TIERS)

DEFAULT_DB_SETTINGS = {
    "dbname": "vector_db",
    "user": "postgres",
    "password": "mysecretpassword",
    "host": "127.0.0.1",
    "port": "5433",
}


def load_env_file(path: Path = PROJECT_ROOT / ".env") -> None:
    """Load simple KEY=VALUE entries without adding a runtime dependency."""
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def db_settings() -> dict[str, str]:
    load_env_file()
    return {
        "dbname": os.getenv("POSTGRES_DB", DEFAULT_DB_SETTINGS["dbname"]),
        "user": os.getenv("POSTGRES_USER", DEFAULT_DB_SETTINGS["user"]),
        "password": os.getenv("POSTGRES_PASSWORD", DEFAULT_DB_SETTINGS["password"]),
        "host": os.getenv("POSTGRES_HOST", DEFAULT_DB_SETTINGS["host"]),
        "port": os.getenv("POSTGRES_HOST_PORT", DEFAULT_DB_SETTINGS["port"]),
    }


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
