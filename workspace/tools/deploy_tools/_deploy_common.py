#!/usr/bin/env python3
"""Shared config + helpers for the mindmap deploy chain (Your Project).

The whole "full edit access" for the published mindmap page is four links:

    source-of-truth (repo)  ->  server  ->  publish  ->  rollback

- source-of-truth : the HTML in THIS workspace (edited here, nowhere else)
- server          : Caddy webroot on the your host
- publish         : push source -> server, backup the old copy, reload Caddy, verify
- rollback        : restore any previous backup, reload, verify

Both mindmap_publish.py and mindmap_rollback.py import from here so the server
coordinates live in exactly one place.
"""
from __future__ import annotations
import os, sys, urllib.request

# Make the toolkit self-sufficient: vendored libs (paramiko) live here and must
# be importable no matter how this is invoked (agent, cron, arbitrary cwd).
for _p in ("/ductor/opt/pylibs", "/ductor/workspace/tools/_compat"):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# --- the four links, all configurable via env for portability ---------------
HOST         = os.environ.get("DEPLOY_HOST", "YOUR_SERVER_IP")
SSH_USER     = os.environ.get("DEPLOY_USER", "root")
SSH_KEY      = os.environ.get("DEPLOY_SSH_KEY", "/path/to/your/ssh_key")

# 1) SOURCE OF TRUTH — edited in the workspace, this file IS the truth.
SRC          = os.environ.get(
    "DEPLOY_SRC",
    "/path/to/your/page.html")

# 2) SERVER — where Caddy serves the page from.
REMOTE_DIR   = os.environ.get("DEPLOY_REMOTE_DIR",
    "/var/www/your-domain/page")
REMOTE_INDEX = REMOTE_DIR + "/index.html"
BACKUP_DIR   = REMOTE_DIR + "/backups"
REMOTE_OWNER = os.environ.get("DEPLOY_OWNER", "caddy:caddy")

# public URL used to verify a deploy actually took.
URL          = os.environ.get("DEPLOY_URL", "https://your-domain/page/")
KEEP_BACKUPS = int(os.environ.get("DEPLOY_KEEP", "10"))


def connect():
    """Return (ssh_client, sftp_client). Requires paramiko."""
    try:
        import paramiko
    except ImportError:
        sys.exit("paramiko not installed (pip install paramiko)")
    key = paramiko.RSAKey.from_private_key_file(SSH_KEY)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=SSH_USER, pkey=key, timeout=25)
    return c, c.open_sftp()


def run(ssh, cmd):
    """Run a remote command, return (rc, stdout+stderr)."""
    _in, out, err = ssh.exec_command(cmd)
    o = out.read().decode() + err.read().decode()
    rc = out.channel.recv_exit_status()
    return rc, o.strip()


def reload_caddy(ssh):
    rc, o = run(ssh, "systemctl reload caddy && echo RELOADED")
    if rc != 0 or "RELOADED" not in o:
        raise RuntimeError("caddy reload failed: " + o)


def verify(expect_snippet="Your Project"):
    """Fetch the live URL, return (ok, http_code, note)."""
    try:
        req = urllib.request.Request(URL, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            ok = (r.status == 200) and (expect_snippet in body)
            return ok, r.status, ("content OK" if expect_snippet in body else
                                  "200 but expected snippet missing")
    except Exception as e:
        return False, None, f"fetch error: {e}"


def ts(ssh):
    """Timestamp from the SERVER clock, so backup names sort correctly."""
    _rc, o = run(ssh, "date +%Y%m%d-%H%M%S")
    return o.strip()


def list_backups(sftp):
    """Return sorted list of backup filenames (newest last)."""
    try:
        files = [f for f in sftp.listdir(BACKUP_DIR)
                 if f.startswith("index.") and f.endswith(".html")]
    except IOError:
        return []
    return sorted(files)
