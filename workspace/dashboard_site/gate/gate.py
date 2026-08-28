#!/usr/bin/env python3
"""
Telegram Mini App gate — serves dashboard data ONLY to verified bot users.

Verifies the Telegram Mini App initData signature (HMAC-SHA256 per Telegram's
algorithm), checks the user id against allowed_user_ids from config, and only
then returns data.json. Listens on localhost:8944; put a reverse proxy (Caddy /
nginx) in front for /api/*. Serve /data/* with 403 directly so the data is only
reachable through this gate.

This is generic skeleton code — set DATA_PATH to wherever your build writes the
dashboard JSON, and expose it in the app via fetch("./api/data").
"""
import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl

CONFIG_PATH = os.path.expanduser(
    os.environ.get("GATE_CONFIG_PATH", "~/.ductor/config/config.json"))
DATA_PATH = os.environ.get(
    "GATE_DATA_PATH", "/var/www/your-domain/data/data.json")
HOST, PORT = "127.0.0.1", 8944
MAX_AGE = 86400  # reject initData older than 24h (replay protection)


def load_cfg():
    c = json.load(open(CONFIG_PATH))
    return c.get("telegram_token") or "", set(c.get("allowed_user_ids") or [])


def verify(init_data, token, allowed):
    """Return (user_dict, None) on success or (None, reason) on rejection."""
    if not init_data:
        return None, "no_init_data"
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    recv_hash = pairs.pop("hash", None)
    if not recv_hash:
        return None, "no_hash"
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, recv_hash):
        return None, "bad_signature"
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if MAX_AGE and (time.time() - auth_date) > MAX_AGE:
        return None, "expired"
    try:
        user = json.loads(pairs.get("user", "{}"))
    except Exception:
        user = {}
    if allowed and user.get("id") not in allowed:
        return None, "not_allowed"
    return user, None


class Handler(BaseHTTPRequestHandler):
    server_version = "miniapp-gate"

    def _send(self, code, obj, raw=None):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _gate(self):
        init_data = self.headers.get("X-Telegram-Init-Data", "")
        try:
            token, allowed = load_cfg()
        except Exception:
            return None, "server_error"
        if not token:
            return None, "server_error"
        return verify(init_data, token, allowed)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            return self._send(200, {"ok": True})
        if path in ("/api/data", "/api/verify"):
            user, reason = self._gate()
            if reason:
                code = 500 if reason == "server_error" else 403
                return self._send(code, {"ok": False, "error": reason})
            if path == "/api/verify":
                return self._send(200, {"ok": True, "user_id": user.get("id")})
            try:
                with open(DATA_PATH, "rb") as f:
                    data = f.read()
            except Exception:
                return self._send(500, {"ok": False, "error": "no_data"})
            return self._send(200, None, raw=data)
        return self._send(404, {"ok": False, "error": "not_found"})

    def log_message(self, *a):
        pass  # quiet; journald handles logs


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
