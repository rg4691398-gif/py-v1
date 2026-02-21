# migrate.py
import os
import sqlite3


def migrate():
    db_path = os.environ.get("DB_PATH", "vouchers.db").strip()
    busy_timeout_ms = int(os.environ.get("DB_BUSY_TIMEOUT_MS", "5000"))

    conn = sqlite3.connect(db_path, timeout=busy_timeout_ms / 1000.0)
    cur = conn.cursor()

    # -----------------------------
    # USERS
    # -----------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('super_admin','operator'))
    );
    """)

    # -----------------------------
    # VOUCHERS
    # -----------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        duration_minutes INTEGER NOT NULL DEFAULT 60,
        status TEXT NOT NULL DEFAULT 'unused' CHECK(status IN ('unused','used')),
        created_by INTEGER,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        used_at INTEGER,
        used_by_mac TEXT,
        FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
    );
    """)

    # -----------------------------
    # SESSIONS (active time tracking)
    # -----------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id INTEGER NOT NULL,
        mac TEXT NOT NULL,
        start_at INTEGER NOT NULL,
        end_at INTEGER NOT NULL,
        router_id TEXT,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        FOREIGN KEY(voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE
    );
    """)

    # -----------------------------
    # NONCES (anti-replay for /api/auth)
    # -----------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS nonces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nonce TEXT UNIQUE NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    );
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
