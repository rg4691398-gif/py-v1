from typing import Any, Dict, Optional
from functools import wraps
from flask import session, redirect, url_for, request, abort
from werkzeug.security import check_password_hash, generate_password_hash

from db import DB
from security import now

SESSION_KEY = "uid"

class Auth:
    def __init__(self, db: DB):
        self.db = db

    def user(self) -> Optional[Dict[str, Any]]:
        uid = session.get(SESSION_KEY)
        if not uid:
            return None
        return self.db.one("SELECT id, username, role, enabled, created_at FROM users WHERE id=?", [int(uid)])

    def is_super(self) -> bool:
        u = self.user()
        return bool(u and u.get("role") == "super")

    def login(self, username: str, password: str) -> bool:
        u = self.db.one("SELECT id, pass_hash, enabled FROM users WHERE username=?", [username])
        if not u or int(u.get("enabled", 0)) != 1:
            return False
        if not check_password_hash(u["pass_hash"], password):
            return False
        session[SESSION_KEY] = int(u["id"])
        session.permanent = True
        return True

    def logout(self) -> None:
        session.pop(SESSION_KEY, None)

    def create_user(self, username: str, password: str, role: str) -> None:
        self.db.exec(
            "INSERT INTO users(username, pass_hash, role, enabled, created_at) VALUES(?,?,?,?,?)",
            [username, generate_password_hash(password), role, 1, now()]
        )

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get(SESSION_KEY):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def super_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from flask import g
        if not g.user or g.user.get("role") != "super":
            abort(403)
        return view(*args, **kwargs)
    return wrapped
