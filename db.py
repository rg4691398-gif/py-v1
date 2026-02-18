# db.py
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional


def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class DB:
    def __init__(self, path: str, busy_timeout_ms: int = 5000):
        self.path = (path or "vouchers.db").strip()
        self.busy_timeout_ms = int(busy_timeout_ms or 5000)

        # ✅ Fix: only mkdir if parent directory exists
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        # isolation_level=None => autocommit mode; we manage BEGIN/COMMIT ourselves
        conn = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1000.0,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = dict_factory

        # Pragmas (safe defaults)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms};")
        return conn

    @contextmanager
    def transaction(self, immediate: bool = False):
        conn = self.connect()
        try:
            if immediate:
                conn.execute("BEGIN IMMEDIATE;")
            else:
                conn.execute("BEGIN;")
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def one(self, sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        try:
            cur = conn.execute(sql, tuple(params))
            return cur.fetchone()
        finally:
            conn.close()

    def all(self, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        conn = self.connect()
        try:
            cur = conn.execute(sql, tuple(params))
            return cur.fetchall()
        finally:
            conn.close()

    def val(self, sql: str, params: Iterable[Any] = ()) -> Any:
        row = self.one(sql, params)
        if not row:
            return None
        return next(iter(row.values()))

    def exec(self, sql: str, params: Iterable[Any] = ()) -> None:
        conn = self.connect()
        try:
            conn.execute(sql, tuple(params))
        finally:
            conn.close()
