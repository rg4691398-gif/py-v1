# db.py
import os
import sqlite3
import threading
from contextlib import contextmanager


class DB:
    """
    SQLite helper for Flask apps.

    Key points:
    - Safely creates parent directory if DB_PATH includes a directory.
      (If DB_PATH is 'vouchers.db', dirname == '' -> no mkdir, avoids Render crash)
    - Provides connect() and a contextmanager for transactions.
    - Uses a thread-local connection to reduce overhead.
    """

    def __init__(self, path: str):
        self.path = (path or "vouchers.db").strip()
        parent = os.path.dirname(self.path)
        if parent:  # ✅ only create dir if dirname exists
            os.makedirs(parent, exist_ok=True)

        self._local = threading.local()

    def connect(self) -> sqlite3.Connection:
        """Get/create a thread-local connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            # Pragmas: reasonable defaults for web usage
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self._local.conn = conn
        return conn

    def close(self):
        """Close thread-local connection (call at teardown if you want)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.conn = None

    @contextmanager
    def tx(self):
        """
        Transaction context:
          with db.tx() as conn:
              conn.execute(...)
        Commits on success, rolls back on error.
        """
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ---------- convenience helpers ----------

    def execute(self, sql: str, params: tuple = ()):
        with self.tx() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount

    def executemany(self, sql: str, seq_of_params):
        with self.tx() as conn:
            cur = conn.executemany(sql, seq_of_params)
            return cur.rowcount

    def fetchone(self, sql: str, params: tuple = ()):
        conn = self.connect()
        cur = conn.execute(sql, params)
        return cur.fetchone()

    def fetchall(self, sql: str, params: tuple = ()):
        conn = self.connect()
        cur = conn.execute(sql, params)
        return cur.fetchall()

    def scalar(self, sql: str, params: tuple = (), default=None):
        row = self.fetchone(sql, params)
        if row is None:
            return default
        # sqlite3.Row supports indexing by position
        return row[0]
