# db.py
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


class DB:
    """
    SQLite helper with:
      - single DB file path
      - per-thread connections (SQLite best practice)
      - WAL mode + busy_timeout (helps with concurrent access on Render)
      - foreign keys ON
      - Row dict-like access
    """

    def __init__(
        self,
        path: Optional[str] = None,
        busy_timeout_ms: int = 5000,
        wal: bool = True,
    ) -> None:
        self.path = path or os.environ.get("DB_PATH", "vouchers.db")
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.wal = bool(wal)
        self._local = threading.local()

        # Ensure DB directory exists (if path contains directories)
        db_dir = os.path.dirname(self.path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        # Initialize DB pragmas once
        with self.connect() as conn:
            self._apply_pragmas(conn)

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        # Important: these must execute on an open connection
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms};")
        if self.wal:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.path,
                timeout=max(1, self.busy_timeout_ms // 1000),
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            self._apply_pragmas(conn)
            self._local.conn = conn
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """
        Context-managed connection.
        NOTE: returns a per-thread connection; does not close each time.
        """
        conn = self._get_conn()
        try:
            yield conn
        finally:
            # Do not close here; keep per-thread connection cached.
            # (Closing per request can be OK too, but caching is faster.)
            pass

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Context-managed transaction (commit/rollback).
        """
        with self.connect() as conn:
            try:
                conn.execute("BEGIN;")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.transaction() as conn:
            conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def close_thread(self) -> None:
        """
        Optional: close per-thread connection (e.g. at process shutdown).
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.conn = None
