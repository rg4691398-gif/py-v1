import hmac
import hashlib
import secrets
import time
from flask import session, request, abort

def now() -> int:
    return int(time.time())

def rand_code(n: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))

def hmac_hex(secret: str, msg: str) -> str:
    return hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

def hmac_verify(secret: str, msg: str, sig_hex: str) -> bool:
    try:
        expected = hmac_hex(secret, msg).lower()
        return hmac.compare_digest(expected, (sig_hex or "").lower())
    except Exception:
        return False

def csrf_token() -> str:
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
    return tok

def csrf_validate(token: str | None) -> None:
    tok = session.get("_csrf")
    if not tok or not token or not hmac.compare_digest(tok, token):
        abort(400, "CSRF validation failed")
