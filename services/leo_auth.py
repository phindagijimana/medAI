"""Optional login and audit log for a locally hosted LEO.

Login is OFF until a user exists (``bin/leo user add NAME``) or ``MEDAI_LEO_REQUIRE_LOGIN=1`` is set.  With
``MEDAI_LEO_REQUIRE_LOGIN=1`` and no users, nobody can log in (fails closed).

When on, every page and API route except ``/health`` and the login page needs either a login session (cookie) or
HTTP Basic credentials (for scripts).  Passwords are stored only as salted hashes (werkzeug scrypt) in
``data/leo_users.json`` (owner-only file).  Failed logins are throttled per user and address.

The audit log (``data/leo_audit.jsonl``, owner-only, append only) records who did what and when.  It never holds
note text, file contents or passwords; it holds user, address, event, job id, file *name* and counts.

This is a small shared-secret scheme for one site, not single sign-on.  Passwords travel in clear text unless the
app is served over HTTPS (put a TLS proxy in front, or use an SSH tunnel).
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from flask import Response, g, jsonify, redirect, request, session
from werkzeug.security import check_password_hash, generate_password_hash

MIN_PASSWORD = 10
MAX_FAILS, FAIL_WINDOW_S = 5, 600
SESSION_HOURS = float(os.environ.get("MEDAI_LEO_SESSION_HOURS", "8"))
EXEMPT = ("/health", "/leo/login", "/leo/logout")
ANON = "(no login)"

_LOCK = threading.Lock()
_FAILS: dict[tuple[str, str], list[float]] = {}
_DUMMY = generate_password_hash("not-a-real-password")      # so unknown users cost the same time as known ones


def _data_dir() -> Path:
    d = Path(os.environ.get("APP_HOME", os.getcwd())) / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def users_path() -> Path:
    return Path(os.environ.get("MEDAI_LEO_USERS") or _data_dir() / "leo_users.json")


def audit_path() -> Path:
    return Path(os.environ.get("MEDAI_LEO_AUDIT") or _data_dir() / "leo_audit.jsonl")


def _secure(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


# ─── users ───────────────────────────────────────────────────────────────

def load_users() -> dict[str, dict]:
    p = users_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()).get("users", {})
    except (OSError, ValueError):
        return {}


def _save_users(users: dict[str, dict]) -> None:
    p = users_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"users": users}, indent=2))
    _secure(tmp)
    tmp.replace(p)


def valid_name(name: str) -> bool:
    return bool(name) and len(name) <= 40 and all(c.isalnum() or c in "._-" for c in name)


def add_user(name: str, password: str) -> None:
    if not valid_name(name):
        raise ValueError("user name: letters, digits, . _ - only (max 40)")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    with _LOCK:
        users = load_users()
        users[name] = {"hash": generate_password_hash(password), "changed": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        _save_users(users)


def remove_user(name: str) -> bool:
    with _LOCK:
        users = load_users()
        if name not in users:
            return False
        del users[name]
        _save_users(users)
        return True


def enabled() -> bool:
    return os.environ.get("MEDAI_LEO_REQUIRE_LOGIN", "") in ("1", "true", "yes") or bool(load_users())


def current_user() -> str:
    """Logged-in user name, or ``(no login)`` when login is off."""
    return getattr(g, "leo_user", None) or ANON


# ─── audit ───────────────────────────────────────────────────────────────

def audit(event: str, **fields: Any) -> None:
    """Append one line.  Callers must not pass note text; long values are cut."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "user": current_user(),
           "ip": request.remote_addr or "", "event": event}
    rec.update({k: (v[:200] if isinstance(v, str) else v) for k, v in fields.items()})
    try:
        p = audit_path()
        with _LOCK:
            new = not p.exists()
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if new:
                _secure(p)
    except OSError:                                         # never break a request because the log is unwritable
        pass


# ─── throttle ────────────────────────────────────────────────────────────

def _throttled(user: str, ip: str) -> bool:
    now = time.time()
    with _LOCK:
        hits = [t for t in _FAILS.get((user, ip), []) if now - t < FAIL_WINDOW_S]
        _FAILS[(user, ip)] = hits
        return len(hits) >= MAX_FAILS


def _fail(user: str, ip: str) -> None:
    with _LOCK:
        _FAILS.setdefault((user, ip), []).append(time.time())


def verify(user: str, password: str, ip: str = "") -> Optional[str]:
    """User name if the password is right, else None.  Counts failures; refuses while throttled."""
    if _throttled(user, ip):
        return None
    rec = load_users().get(user)
    ok = check_password_hash(rec["hash"] if rec else _DUMMY, password or "")
    if rec and ok:
        with _LOCK:
            _FAILS.pop((user, ip), None)
        return user
    _fail(user, ip)
    return None


# ─── request guard ───────────────────────────────────────────────────────

_LOGIN_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LEO · Sign in</title><style>
body{margin:0;font:15px/1.5 system-ui,sans-serif;color:#0a2342;background:#fff}
header{background:#0a2342;color:#fff;padding:14px 20px;font-weight:700;font-size:20px}
main{max-width:360px;margin:40px auto;padding:0 20px}
label{display:block;margin:12px 0 4px}input{width:100%;font:inherit;padding:8px;border:1px solid #0a2342;border-radius:4px;box-sizing:border-box}
button{margin-top:18px;font:inherit;font-weight:600;padding:9px 20px;border-radius:4px;border:1px solid #0a2342;background:#0a2342;color:#fff;cursor:pointer}
.err{margin-top:12px;font-weight:600}.small{font-size:13px;margin-top:18px}
</style></head><body><header>LEO</header><main><h1 style="font-size:18px">Sign in</h1>
<form method="post" action="/leo/login"><input type="hidden" name="next" value="__NEXT__">
<label for="u">User</label><input id="u" name="username" autocomplete="username" autofocus required>
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button></form>__ERR__
<div class="small">Research use only. Your sign-ins and actions are logged (no note text).</div></main></body></html>"""


def _safe_next(n: str) -> str:
    """Only same-site paths: no scheme, no host, no protocol-relative URLs."""
    p = urlparse(n or "")
    return n if n.startswith("/") and not n.startswith("//") and not p.scheme and not p.netloc else "/leo/ui"


def _page(err: str = "", nxt: str = "/leo/ui", status: int = 200) -> Response:
    import html
    body = _LOGIN_HTML.replace("__NEXT__", html.escape(nxt, quote=True)).replace(
        "__ERR__", f'<div class="err" role="alert">{html.escape(err)}</div>' if err else "")
    r = Response(body, status=status, mimetype="text/html")
    r.headers["Cache-Control"] = "no-store"
    return r


def _same_origin() -> bool:
    o = request.headers.get("Origin")
    return not o or urlparse(o).netloc == request.host


def _guard():
    if not enabled():
        return None
    if request.path in EXEMPT:
        return None
    user = None
    via = ""
    s = session.get("leo_user")
    if s and time.time() - session.get("leo_t", 0) < SESSION_HOURS * 3600 and s in load_users():
        user, via = s, "session"
    elif request.authorization and request.authorization.type == "basic":
        user, via = verify(request.authorization.username or "", request.authorization.password or "",
                           request.remote_addr or ""), "basic"
    if not user:
        wants_page = request.method == "GET" and "text/html" in request.headers.get("Accept", "")
        if wants_page:
            return redirect("/leo/login?next=" + request.full_path.rstrip("?"))
        r = jsonify({"error": "login required"})
        r.status_code = 401
        r.headers["WWW-Authenticate"] = 'Basic realm="LEO"'
        return r
    if via == "session" and request.method in ("POST", "PUT", "DELETE", "PATCH") and not _same_origin():
        return jsonify({"error": "cross-site request refused"}), 403
    g.leo_user = user
    return None


def init_app(app) -> None:
    """Install the guard, login routes and cookie settings.  Safe to call when login is off."""
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    if os.environ.get("MEDAI_LEO_COOKIE_SECURE", "") in ("1", "true", "yes"):
        app.config["SESSION_COOKIE_SECURE"] = True
    app.before_request(_guard)

    @app.route("/leo/login", methods=["GET", "POST"])
    def leo_login():
        if not enabled():
            return redirect("/leo/ui")
        if request.method == "GET":
            return _page(nxt=_safe_next(request.args.get("next", "")))
        name = (request.form.get("username") or "").strip()
        nxt = _safe_next(request.form.get("next", ""))
        ip = request.remote_addr or ""
        if _throttled(name, ip):
            audit("login_blocked", target=name)
            return _page("Too many attempts. Wait ten minutes.", nxt, 429)
        if verify(name, request.form.get("password", ""), ip):
            session.clear()
            session["leo_user"], session["leo_t"] = name, time.time()
            g.leo_user = name
            audit("login")
            return redirect(nxt)
        audit("login_failed", target=name)
        return _page("Wrong user or password.", nxt, 401)

    @app.route("/leo/logout", methods=["POST"])
    def leo_logout():
        if session.get("leo_user"):
            g.leo_user = session["leo_user"]
            audit("logout")
        session.clear()
        return redirect("/leo/login") if enabled() else redirect("/leo/ui")
