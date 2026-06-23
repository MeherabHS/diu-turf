"""services/db.py — DEPRECATED.

MongoDB has been fully removed. This file is kept only so that any missed
import does not cause an immediate ImportError.

All database access uses database.connection.get_conn (asyncpg).
"""
# Re-export get_conn under the old name as a safety net.
from database.connection import get_conn as get_db  # noqa: F401

__all__ = ["get_db"]
