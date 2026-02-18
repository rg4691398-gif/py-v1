import os
from config import get_config
from db import DB
from werkzeug.security import generate_password_hash
from security import now

SCHEMA = [
"""CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  pass_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('super','operator')),
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL
);""",
"""CREATE TABLE IF NOT EXISTS routers (
  router_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  owner_user_id INTEGER NOT NULL,
  secret TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE
);""",
"""CREATE TABLE IF NOT EXISTS profiles (
  name TEXT PRIMARY KEY,
  seconds INTEGER NOT NULL CHECK(seconds > 0),
  up_bytes INTEGER NOT NULL CHECK(up_bytes >= 0),
  down_bytes INTEGER NOT NULL CHECK(down_bytes >= 0),
  price INTEGER NOT NULL DEFAULT 0 CHECK(price >= 0),
  expiry_days INTEGER NOT NULL DEFAULT 7 CHECK(expiry_days >= 0),
  created_at INTEGER NOT NULL
);""",
"""CREATE TABLE IF NOT EXISTS vouchers (
  code TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL,
  router_id TEXT NOT NULL,
  profile TEXT NOT NULL,
  seconds INTEGER NOT NULL,
  up_bytes INTEGER NOT NULL,
  down_bytes INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('unused','used','revoked')),
  used_at INTEGER,
  used_by_mac TEXT,
  used_by_router TEXT,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE RESTRICT
);""",
"""CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  router_id TEXT NOT NULL,
  mac TEXT NOT NULL,
  voucher TEXT NOT NULL,
  start_at INTEGER NOT NULL,
  end_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);""",
"""CREATE TABLE IF NOT EXISTS nonces (
  router_id TEXT NOT NULL,
  nonce TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY(router_id, nonce)
);""",
"""CREATE TABLE IF NOT EXISTS login_attempts (
  ip TEXT PRIMARY KEY,
  fails INTEGER NOT NULL DEFAULT 0,
  last_at INTEGER NOT NULL DEFAULT 0,
  locked_until INTEGER NOT NULL DEFAULT 0
);""",
"""CREATE INDEX IF NOT EXISTS idx_routers_owner ON routers(owner_user_id);""",
"""CREATE INDEX IF NOT EXISTS idx_vouchers_owner_status ON vouchers(owner_user_id, status);""",
"""CREATE INDEX IF NOT EXISTS idx_vouchers_router ON vouchers(router_id);""",
"""CREATE INDEX IF NOT EXISTS idx_vouchers_expires ON vouchers(expires_at);""",
"""CREATE INDEX IF NOT EXISTS idx_sessions_router_end ON sessions(router_id, end_at);""",
"""CREATE INDEX IF NOT EXISTS idx_sessions_voucher ON sessions(voucher);""",
"""CREATE INDEX IF NOT EXISTS idx_nonces_created ON nonces(created_at);""",
]

def main():
    cfg = get_config()
    db = DB(cfg["DB_PATH"], cfg["DB_BUSY_TIMEOUT_MS"])
    conn = db.connect()
    try:
        for stmt in SCHEMA:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()

    # bootstrap super admin
    admin_user = cfg["BOOTSTRAP_ADMIN_USER"]
    admin_pass = cfg["BOOTSTRAP_ADMIN_PASS"]
    row = db.one("SELECT id FROM users WHERE username=?", [admin_user])
    if not row:
        db.exec(
            "INSERT INTO users(username, pass_hash, role, enabled, created_at) VALUES(?,?,?,?,?)",
            [admin_user, generate_password_hash(admin_pass), "super", 1, now()]
        )
        print(f"✅ Created bootstrap super admin: {admin_user} / {admin_pass}")
    else:
        print("ℹ️ Bootstrap admin already exists.")

    print(f"✅ Migration complete. DB: {cfg['DB_PATH']}")

if __name__ == "__main__":
    main()
