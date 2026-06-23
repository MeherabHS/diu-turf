"""Helpers for running multi-statement SQL migrations with asyncpg."""
from __future__ import annotations

from alembic import op


def strip_sql_comments(sql: str) -> str:
    """Remove SQL line and inline comments before splitting statements."""
    lines: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if "--" in line:
            line = line.split("--", 1)[0]
        if line.strip():
            lines.append(line)
    return "\n".join(lines)


def split_sql_statements(sql: str) -> list[str]:
    """Split a multi-statement SQL script into individual executable statements."""
    statements: list[str] = []
    for chunk in strip_sql_comments(sql).split(";"):
        stmt = chunk.strip()
        if stmt:
            statements.append(stmt)
    return statements


def execute_sql_script(sql: str) -> None:
    """Execute each DDL statement separately (asyncpg rejects multi-command prepares)."""
    conn = op.get_bind()
    for stmt in split_sql_statements(sql):
        conn.exec_driver_sql(stmt)
