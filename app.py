from __future__ import annotations

import os
import re
import secrets
from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify, abort

from config import get_config
from db import DB
from auth import Auth, login_required
from rate_limit import RateLimit
from security import now, rand_code, csrf_token, csrf_validate, hmac_verify

MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")

def fmt_time(ts: int | None) -> str:
    if not ts:
        return "-"
    # render in local time of the server; keep simple (Render is UTC)
    import datetime
    return datetime.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S UTC")

def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "0B"
    n = int(n)
    units = ["B","KB","MB","GB","TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    if i == 0:
        return f"{int(f)}{units[i]}"
    return f"{f:.1f}{units[i]}"

def create_app() -> Flask:
    cfg = get_config()
    app = Flask(__name__)
    app.secret_key = cfg["SECRET_KEY"]
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = True  # Render uses HTTPS
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7  # 7 days

    db = DB(cfg["DB_PATH"], cfg["DB_BUSY_TIMEOUT_MS"])
    auth = Auth(db)
    rl = RateLimit(db)

    @app.before_request
    def load_user():
        g.cfg = cfg
        g.db = db
        g.auth = auth
        g.user = auth.user()

    @app.context_processor
    def inject_globals():
        return {
            "brand": cfg["PRINT_BRAND"],
            "csrf": csrf_token(),
            "fmt_time": fmt_time,
            "fmt_bytes": fmt_bytes,
            "flash_ok": session.pop("_flash_ok", None),
            "flash_err": session.pop("_flash_err", None),
        }

    def flash_ok(msg: str): session["_flash_ok"] = msg
    def flash_err(msg: str): session["_flash_err"] = msg

    # ----------------
    # Auth
    # ----------------
    @app.get("/")
    def root():
        if g.user:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET","POST"])
    def login():
        if g.user:
            return redirect(url_for("dashboard"))
        err = ""
        if request.method == "POST":
            rl.check_login_allowed()
            csrf_validate(request.form.get("csrf"))
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            if not username or not password:
                err = "Missing credentials"
            elif auth.login(username, password):
                rl.record_success()
                return redirect(url_for("dashboard"))
            else:
                rl.record_fail()
                err = "Invalid login"
        return render_template("login.html", err=err, csrf=csrf_token(), brand=cfg["PRINT_BRAND"])

    @app.get("/logout")
    def logout():
        auth.logout()
        return redirect(url_for("login"))

    # ----------------
    # Dashboard
    # ----------------
    @app.get("/dashboard")
    @login_required
    def dashboard():
        u = g.user
        t = now()
        if u["role"] == "super":
            routers = int(db.val("SELECT COUNT(*) FROM routers") or 0)
            unused = int(db.val("SELECT COUNT(*) FROM vouchers WHERE status='unused' AND expires_at>=?", [t]) or 0)
            used = int(db.val("SELECT COUNT(*) FROM vouchers WHERE status='used'") or 0)
            active = int(db.val("SELECT COUNT(*) FROM sessions WHERE end_at>?", [t]) or 0)
            recent = db.all(
                "SELECT router_id, mac, voucher, start_at, end_at FROM sessions WHERE end_at>? ORDER BY end_at ASC LIMIT 200",
                [t]
            )
        else:
            uid = int(u["id"])
            routers = int(db.val("SELECT COUNT(*) FROM routers WHERE owner_user_id=?", [uid]) or 0)
            unused = int(db.val("SELECT COUNT(*) FROM vouchers WHERE owner_user_id=? AND status='unused' AND expires_at>=?", [uid, t]) or 0)
            used = int(db.val("SELECT COUNT(*) FROM vouchers WHERE owner_user_id=? AND status='used'", [uid]) or 0)
            active = int(db.val(
                "SELECT COUNT(*) FROM sessions s JOIN routers r ON r.router_id=s.router_id WHERE r.owner_user_id=? AND s.end_at>?",
                [uid, t]
            ) or 0)
            recent = db.all(
                "SELECT s.router_id, s.mac, s.voucher, s.start_at, s.end_at "
                "FROM sessions s JOIN routers r ON r.router_id=s.router_id "
                "WHERE r.owner_user_id=? AND s.end_at>? ORDER BY s.end_at ASC LIMIT 200",
                [uid, t]
            )
        return render_template(
            "dashboard.html",
            title="Dashboard",
            active="dashboard",
            user=u,
            routersCount=routers,
            unusedCount=unused,
            usedVouchers=used,
            activeSessionsCount=active,
            recentSessions=recent,
            now_ts=t,
        )

    # ----------------
    # Operators (Super only)
    # ----------------
    @app.route("/operators", methods=["GET","POST"])
    @login_required
    def operators():
        u = g.user
        if u["role"] != "super":
            abort(403)
        err = ""
        if request.method == "POST":
            csrf_validate(request.form.get("csrf"))
            action = request.form.get("action","")
            if action == "create":
                username = (request.form.get("username") or "").strip()
                password = (request.form.get("password") or "").strip()
                if not username or not password:
                    err = "Missing username/password"
                else:
                    try:
                        auth.create_user(username, password, "operator")
                        flash_ok("Operator created")
                        return redirect(url_for("operators"))
                    except Exception:
                        err = "Username already exists"
            elif action == "delete":
                uid = int(request.form.get("user_id") or 0)
                if uid:
                    db.exec("DELETE FROM users WHERE id=? AND role='operator'", [uid])
                    flash_ok("Operator deleted")
                    return redirect(url_for("operators"))
        ops = db.all("SELECT id, username, enabled FROM users WHERE role='operator' ORDER BY created_at DESC")
        return render_template("operators.html", title="Operators", active="operators", user=u, isSuper=True, operators=ops, err=err)

    # ----------------
    # Profiles
    # ----------------
    @app.route("/profiles", methods=["GET","POST"])
    @login_required
    def profiles():
        u = g.user
        is_super = (u["role"] == "super")
        err = ""
        if request.method == "POST":
            csrf_validate(request.form.get("csrf"))
            action = request.form.get("action","")
            if action == "create":
                if not is_super:
                    abort(403)
                name = (request.form.get("name") or "").strip()
                seconds = int(request.form.get("seconds") or 0)
                up_mb = int(request.form.get("up_mb") or 0)
                down_mb = int(request.form.get("down_mb") or 0)
                price = int(request.form.get("price") or 0)
                expiry_days = int(request.form.get("expiry_days") or 7)
                if not name or seconds <= 0 or up_mb < 0 or down_mb < 0 or price < 0 or expiry_days < 0:
                    err = "Invalid fields"
                else:
                    try:
                        db.exec(
                            "INSERT INTO profiles(name, seconds, up_bytes, down_bytes, price, expiry_days, created_at) VALUES(?,?,?,?,?,?,?)",
                            [name, seconds, up_mb*1024*1024, down_mb*1024*1024, price, expiry_days, now()]
                        )
                        flash_ok("Profile created")
                        return redirect(url_for("profiles"))
                    except Exception:
                        err = "Profile name already exists"
            elif action == "delete":
                if not is_super:
                    abort(403)
                name = (request.form.get("name") or "").strip()
                if name:
                    db.exec("DELETE FROM profiles WHERE name=?", [name])
                    flash_ok("Profile deleted")
                    return redirect(url_for("profiles"))
        profs = db.all("SELECT name, seconds, up_bytes, down_bytes, price, expiry_days FROM profiles ORDER BY created_at DESC")
        return render_template("profiles.html", title="Profiles", active="profiles", user=u, isSuper=is_super, profiles=profs, err=err)

    # ----------------
    # Routers
    # ----------------
    @app.route("/routers", methods=["GET","POST"])
    @login_required
    def routers():
        u = g.user
        is_super = (u["role"] == "super")
        err = ""
        if request.method == "POST":
            csrf_validate(request.form.get("csrf"))
            action = request.form.get("action","")
            if action == "create":
                router_id = (request.form.get("router_id") or "").strip()
                name = (request.form.get("name") or "").strip()
                secret = (request.form.get("secret") or "").strip() or secrets.token_hex(16)
                if not router_id or not name:
                    err = "Missing router_id/name"
                else:
                    owner_user_id = int(u["id"])
                    if is_super:
                        owner_user_id = int(request.form.get("owner_user_id") or 0)
                        if owner_user_id <= 0:
                            err = "Select operator owner"
                    if not err:
                        try:
                            db.exec(
                                "INSERT INTO routers(router_id, name, owner_user_id, secret, enabled, created_at) VALUES(?,?,?,?,?,?)",
                                [router_id, name, owner_user_id, secret, 1, now()]
                            )
                            flash_ok("Router created")
                            return redirect(url_for("routers"))
                        except Exception:
                            err = "Router ID already exists"
            elif action == "delete":
                rid = (request.form.get("router_id") or "").strip()
                if rid:
                    if is_super:
                        db.exec("DELETE FROM routers WHERE router_id=?", [rid])
                    else:
                        db.exec("DELETE FROM routers WHERE router_id=? AND owner_user_id=?", [rid, int(u["id"])])
                    flash_ok("Router deleted")
                    return redirect(url_for("routers"))

        if is_super:
            rows = db.all(
                "SELECT r.router_id, r.name, r.enabled, u.username AS owner_username "
                "FROM routers r JOIN users u ON u.id=r.owner_user_id ORDER BY r.created_at DESC"
            )
            ops = db.all("SELECT id, username FROM users WHERE role='operator' AND enabled=1 ORDER BY created_at DESC")
        else:
            rows = db.all("SELECT router_id, name, enabled FROM routers WHERE owner_user_id=? ORDER BY created_at DESC", [int(u["id"])])
            for r in rows:
                r["owner_username"] = ""
            ops = []
        return render_template("routers.html", title="Routers", active="routers", user=u, isSuper=is_super, routers=rows, operators=ops, err=err)

    # ----------------
    # Vouchers
    # ----------------
    @app.route("/vouchers", methods=["GET","POST"])
    @login_required
    def vouchers():
        u = g.user
        is_super = (u["role"] == "super")
        err = ""

        status = (request.values.get("status") or "").strip()
        q = (request.values.get("q") or "").strip()

        if request.method == "POST":
            csrf_validate(request.form.get("csrf"))
            action = request.form.get("action","")
            if action == "generate":
                if is_super:
                    flash_err("Super Admin cannot generate vouchers. Create an Operator and generate from that account.")
                    return redirect(url_for("vouchers"))
                profile = (request.form.get("profile") or "").strip()
                scope = (request.form.get("router_scope") or "").strip() or "*"
                qty = int(request.form.get("qty") or 0)
                if not profile or qty < 1 or qty > 500:
                    err = "Invalid profile/qty (max 500 per batch)"
                else:
                    if scope != "*" and scope:
                        owned = db.one("SELECT router_id FROM routers WHERE router_id=? AND owner_user_id=? AND enabled=1", [scope, int(u["id"])])
                        if not owned:
                            err = "Invalid router scope"
                    if not err:
                        p = db.one("SELECT name, seconds, up_bytes, down_bytes, expiry_days FROM profiles WHERE name=?", [profile])
                        if not p:
                            err = "Profile not found"
                        else:
                            t = now()
                            expires_at = t + int(p["expiry_days"]) * 86400
                            try:
                                with db.transaction(immediate=True) as conn:
                                    for _ in range(qty):
                                        code = ""
                                        for __ in range(10):
                                            cand = rand_code(8)
                                            ex = conn.execute("SELECT code FROM vouchers WHERE code=?", [cand]).fetchone()
                                            if not ex:
                                                code = cand
                                                break
                                        if not code:
                                            raise RuntimeError("code")
                                        conn.execute(
                                            "INSERT INTO vouchers(code, owner_user_id, router_id, profile, seconds, up_bytes, down_bytes, expires_at, status, created_at) "
                                            "VALUES(?,?,?,?,?,?,?,?,?,?)",
                                            [code, int(u["id"]), scope, p["name"], int(p["seconds"]), int(p["up_bytes"]), int(p["down_bytes"]), expires_at, "unused", t]
                                        )
                                flash_ok("Vouchers generated")
                                return redirect(url_for("vouchers"))
                            except Exception:
                                err = "Generation failed"
            elif action == "delete":
                code = (request.form.get("code") or "").strip().upper()
                if code:
                    if is_super:
                        db.exec("DELETE FROM vouchers WHERE code=?", [code])
                    else:
                        db.exec("DELETE FROM vouchers WHERE code=? AND owner_user_id=?", [code, int(u["id"])])
                    flash_ok("Voucher deleted")
                    return redirect(url_for("vouchers"))

        profs = db.all("SELECT name, seconds, up_bytes, down_bytes, price FROM profiles ORDER BY created_at DESC")
        if is_super:
            rtrs = db.all("SELECT router_id, name FROM routers WHERE enabled=1 ORDER BY created_at DESC")
        else:
            rtrs = db.all("SELECT router_id, name FROM routers WHERE owner_user_id=? AND enabled=1 ORDER BY created_at DESC", [int(u["id"])])

        params = []
        where = []
        if not is_super:
            where.append("owner_user_id=?")
            params.append(int(u["id"]))
        if status:
            where.append("status=?")
            params.append(status)
        if q:
            where.append("code LIKE ?")
            params.append(f"%{q}%")
        sql = "SELECT code, router_id, profile, seconds, expires_at, status, used_at, used_by_mac, used_by_router, created_at FROM vouchers"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT 500"
        rows = db.all(sql, params)

        t = now()
        for v in rows:
            ui = v["status"]
            if v["status"] == "used":
                end_at = int(db.val("SELECT end_at FROM sessions WHERE voucher=? ORDER BY id DESC LIMIT 1", [v["code"]]) or 0)
                ui = "active" if end_at > t else "used"
            v["ui_status"] = ui

        return render_template(
            "vouchers.html",
            title="Vouchers",
            active="vouchers",
            user=u,
            isSuper=is_super,
            profiles=profs,
            routers=rtrs,
            vouchers=rows,
            err=err,
            status=status,
            q=q,
        )

    @app.get("/print")
    @login_required
    def print_page():
        u = g.user
        is_super = (u["role"] == "super")
        t = now()
        if is_super:
            rows = db.all("SELECT code, profile, seconds, expires_at FROM vouchers WHERE status='unused' AND expires_at>=? ORDER BY created_at DESC LIMIT 200", [t])
        else:
            rows = db.all("SELECT code, profile, seconds, expires_at FROM vouchers WHERE owner_user_id=? AND status='unused' AND expires_at>=? ORDER BY created_at DESC LIMIT 200", [int(u["id"]), t])
        return render_template("print.html", vouchers=rows, brand=cfg["PRINT_BRAND"])

    # ----------------
    # API: Router voucher auth
    # ----------------
    @app.post("/api/auth")
    def api_auth():
        data = request.get_json(silent=True) or {}
        router_id = (data.get("router_id") or "").strip()
        mac = (data.get("mac") or "").strip().lower()
        voucher = (data.get("voucher") or "").strip().upper()
        ts = int(data.get("ts") or 0)
        nonce = (data.get("nonce") or "").strip()
        sig = (data.get("sig") or "").strip().lower()

        if not router_id or not mac or not voucher or not nonce or not sig:
            return jsonify({"allow": 0, "reason": "missing"}), 400
        if not MAC_RE.match(mac):
            return jsonify({"allow": 0, "reason": "mac"}), 400

        t = now()
        if ts != 0:
            if abs(t - ts) > int(cfg["MAX_CLOCK_SKEW_SECONDS"]):
                return jsonify({"allow": 0, "reason": "skew"}), 403

        r = db.one("SELECT router_id, owner_user_id, secret, enabled FROM routers WHERE router_id=?", [router_id])
        if not r or int(r["enabled"]) != 1:
            return jsonify({"allow": 0, "reason": "router"}), 403

        msg = f"{router_id}|{mac}|{voucher}|{ts}|{nonce}"
        if not hmac_verify(r["secret"], msg, sig):
            return jsonify({"allow": 0, "reason": "sig"}), 403

        # Nonce replay protection
        ttl = int(cfg["NONCE_TTL_SECONDS"])
        db.exec("DELETE FROM nonces WHERE created_at < ?", [t - ttl])
        try:
            db.exec("INSERT INTO nonces(router_id, nonce, created_at) VALUES(?,?,?)", [router_id, nonce, t])
        except Exception:
            return jsonify({"allow": 0, "reason": "replay"}), 403

        # Atomic voucher consumption
        try:
            with db.transaction(immediate=True) as conn:
                v = conn.execute(
                    "SELECT code, owner_user_id, router_id, seconds, up_bytes, down_bytes, expires_at, status, used_by_mac "
                    "FROM vouchers WHERE code=?",
                    [voucher]
                ).fetchone()
                if not v:
                    return jsonify({"allow": 0, "reason": "voucher"}), 403
                if int(v["expires_at"]) < t:
                    return jsonify({"allow": 0, "reason": "expired"}), 403
                if v["status"] == "revoked":
                    return jsonify({"allow": 0, "reason": "revoked"}), 403
                if int(v["owner_user_id"]) != int(r["owner_user_id"]):
                    return jsonify({"allow": 0, "reason": "tenant"}), 403
                scope = v["router_id"]
                if scope != "*" and scope != router_id:
                    return jsonify({"allow": 0, "reason": "scope"}), 403

                if v["status"] == "unused":
                    seconds = int(v["seconds"])
                    if seconds <= 0:
                        return jsonify({"allow": 0, "reason": "bad_seconds"}), 403

                    conn.execute(
                        "UPDATE vouchers SET status='used', used_at=?, used_by_mac=?, used_by_router=? WHERE code=? AND status='unused'",
                        [t, mac, router_id, voucher]
                    )
                    chk = conn.execute("SELECT status, used_by_mac FROM vouchers WHERE code=?", [voucher]).fetchone()
                    if not chk or chk["status"] != "used" or (chk["used_by_mac"] or "").lower() != mac:
                        return jsonify({"allow": 0, "reason": "race"}), 403

                    end_at = t + seconds
                    conn.execute(
                        "INSERT INTO sessions(router_id, mac, voucher, start_at, end_at, created_at) VALUES(?,?,?,?,?,?)",
                        [router_id, mac, voucher, t, end_at, t]
                    )
                    return jsonify({"allow": 1, "remaining": seconds, "up": int(v["up_bytes"]), "down": int(v["down_bytes"])})

                # Already used: allow only same MAC + session remaining
                if (v.get("used_by_mac") or "").lower() != mac:
                    return jsonify({"allow": 0, "reason": "used_by_other"}), 403

                s = conn.execute(
                    "SELECT end_at FROM sessions WHERE voucher=? AND mac=? ORDER BY id DESC LIMIT 1",
                    [voucher, mac]
                ).fetchone()
                if not s:
                    return jsonify({"allow": 0, "reason": "no_session"}), 403
                remaining = int(s["end_at"]) - t
                if remaining <= 0:
                    return jsonify({"allow": 0, "reason": "session_expired"}), 403
                return jsonify({"allow": 1, "remaining": remaining, "up": int(v["up_bytes"]), "down": int(v["down_bytes"])})

        except Exception:
            return jsonify({"allow": 0, "reason": "server"}), 500

    return app

app = create_app()

if __name__ == "__main__":
    # local dev only
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
