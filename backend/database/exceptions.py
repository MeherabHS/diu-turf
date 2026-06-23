"""Shared database exceptions — used by PostgreSQL and SQLite adapters."""


class UniqueViolationError(Exception):
    """Raised when a unique constraint is violated (mirrors asyncpg.UniqueViolationError)."""

    def __init__(self, message: str = "", constraint_name: str = "") -> None:
        super().__init__(message)
        self.constraint_name = constraint_name
