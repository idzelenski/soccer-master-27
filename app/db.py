from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=0,
            max_size=4,
            timeout=10,
            kwargs={"row_factory": dict_row, "connect_timeout": 10},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Generator[psycopg.Connection, None, None]:
    with pool().connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def migrate(conn: psycopg.Connection) -> None:
    migration_dir = Path(__file__).resolve().parent.parent / "sql"
    for migration in sorted(migration_dir.glob("*.sql")):
        sql = migration.read_text(encoding="utf-8")
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
    conn.commit()


def check_database() -> dict:
    with connection() as conn:
        row = conn.execute(
            "SELECT current_database() AS database, current_setting('server_version') AS version, now() AS server_time"
        ).fetchone()
        return dict(row)
