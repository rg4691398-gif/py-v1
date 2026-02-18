from flask import request, abort
from db import DB
from security import now

class RateLimit:
    def __init__(self, db: DB, max_fails: int = 6, lock_seconds: int = 300):
        self.db = db
        self.max_fails = max_fails
        self.lock_seconds = lock_seconds

    def _ip(self) -> str:
        return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip() or "unknown"

    def check_login_allowed(self):
        ip = self._ip()
        row = self.db.one("SELECT fails, locked_until FROM login_attempts WHERE ip=?", [ip])
        t = now()
        if row and int(row.get("locked_until", 0)) > t:
            abort(429, "Too many attempts. Try later.")

    def record_fail(self):
        ip = self._ip()
        t = now()
        row = self.db.one("SELECT fails FROM login_attempts WHERE ip=?", [ip])
        fails = int(row["fails"]) + 1 if row else 1
        locked_until = t + self.lock_seconds if fails >= self.max_fails else 0
        if row:
            self.db.exec("UPDATE login_attempts SET fails=?, last_at=?, locked_until=? WHERE ip=?", [fails, t, locked_until, ip])
        else:
            self.db.exec("INSERT INTO login_attempts(ip, fails, last_at, locked_until) VALUES(?,?,?,?)", [ip, fails, t, locked_until])

    def record_success(self):
        ip = self._ip()
        self.db.exec("DELETE FROM login_attempts WHERE ip=?", [ip])
