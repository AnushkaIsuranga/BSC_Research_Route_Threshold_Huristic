"""PostgreSQL/pgvector connection helpers."""

from __future__ import annotations

import psycopg2
from pgvector.psycopg2 import register_vector

from src import db_settings


def connect_pgvector():
    """Open a PostgreSQL connection and register pgvector adapters."""
    conn = psycopg2.connect(**db_settings())
    register_vector(conn)
    return conn
