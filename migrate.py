# migrate.py
import os
import sqlite3
import time


DB_PATH = os.environ.get("DB_PATH", "vouchers.db")


def migrate() -> None:
    # Ensure parent directory exists (if DB_PATH includes folders)
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()

        # Core tables
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS routers (
              router_id TEXT PRIMARY KEY,
              secret TEXT NOT NULL,
              created_at INTEGER NOT NULL
            );
            """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS vouchers (
              code TEXT PRIMARY KEY,
              duration_seconds INTEGER NOT NULL,
              used INTEGER NOT NULL DEFAULT 0,
              used_by_mac TEXT,
              used_at INTEGER
            );
            """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              router_id TEXT NOT NULL,
              mac TEXT NOT NULL,
              end_at INTEGER NOT NULL,
              created_at INTEGER NOT NULL,
              UNIQUE(router_id, mac)
            );
            """
        )

        # Anti-replay nonces (optional but recommended)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS nonces (
              nonce TEXT PRIMARY KEY,
              created_at INTEGER NOT NULL
            );
            """
        )

        # Helpful indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_router_mac ON sessions(router_id, mac);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_end_at ON sessions(end_at);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_vouchers_used ON vouchers(used);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_nonces_created_at ON nonces(created_at);")

        conn.commit()
        print(f"✅ Migration OK: {DB_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
