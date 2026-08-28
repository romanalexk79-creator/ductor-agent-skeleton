#!/usr/bin/env python3
"""Detect provider auth degradation (e.g. an expired Claude OAuth token).

Two independent signals, scanned from /ductor/logs/agent.log:

  (a) explicit auth-failure text — "401", "Invalid authentication",
      "OAuth token expired", "Please run /login", etc. — but ONLY from a
      real ERROR/WARNING log line emitted by the provider/CLI code itself,
      never from lines that just echo user input (a Telegram message or a
      CLI command's argv can legitimately contain the string "401" without
      any auth failure happening). See the "false positive" note below —
      in the 2026-07-23/24 incident this signal turned out to be entirely
      useless in practice, not merely "less reliable".

  (b) a run of consecutive cron completions for the same job that are both
      `status=error:*` AND abnormally fast (duration_ms below a threshold).
      A real auth failure makes the CLI die almost immediately (~4-10s in
      the incident), while a normal run takes tens of seconds. This signal
      is weighted more heavily: it caught the 2026-07-24 03:00-06:30 UTC
      outage even though the log has no genuine 401 text anywhere in this
      incident — checked directly: every line in this log that ever matches
      the auth regex is [INFO]-level and is either a `Message received
      text=` line or a `CLI stream cmd:` line quoting the *user's* pasted
      complaint ("...Failed to authenticate. API Error: 401 Invalid
      authenticati...") back into the log as command argv. Neither is a
      real provider/CLI error. Signal (a) is not "a backup that mostly
      doesn't fire" here — it is currently dead weight; signal (b) is the
      only thing that actually detected this incident.

  False positive fixed 2026-07-24: an earlier version of this script
  counted those two echoed-user-text lines as auth errors (auth_log_hits=2),
  which made the report claim "explicit auth errors in log AND ..." when in
  fact only signal (b) had fired. Fixed by requiring the auth regex to hit a
  line that is (1) not an echo of user input (no "CLI stream cmd:", "CLI
  cmd:", or "Message received text=" marker) and (2) logged at ERROR or
  WARNING level by the provider/CLI logger — never INFO.

Reads `Cron job completed job=<name> status=<status> duration_ms=<n>` lines
written by ductor_bot.cron.observer — no dependency on cron_jobs.json, which
only stores the single latest run per job and cannot show a streak.

No external dependencies.

Usage:
    python3 tools/user_tools/auth_watchdog.py                # JSON report
    python3 tools/user_tools/auth_watchdog.py --lookback-hours 48

Exit code: 0 ok, 1 warn, 2 fail (matches health_check.py's convention).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HOME = Path(os.environ.get("DUCTOR_HOME", "/ductor"))
_LOG = _HOME / "logs" / "agent.log"
_ENV = _HOME / ".env"

OK, WARN, FAIL = "ok", "warn", "fail"

# How far back to look by default. The incident window was ~3.5h; 24h gives
# enough margin to also catch the earlier 07-23 14:30-16:30 episode without
# scanning the whole file on a long-lived log.
_DEFAULT_LOOKBACK_HOURS = 24
# Cap on how much of the log to read from the tail, to stay bounded on a log
# that has grown large. Generous: cron lines are short and infrequent.
_SCAN_BYTES = 20_000_000

# A "fast" cron failure: real work takes 15-60s in this deployment; an auth
# failure dies in single-digit seconds. 10s leaves comfortable margin.
_FAST_FAIL_SECONDS = 10.0
# Consecutive fast failures (trailing, i.e. ending at the most recent run
# for that job) needed before signal (b) is considered triggered at all.
_STREAK_WARN = 2
# Max gap between two fast-fail runs of the same job to still count as one
# unbroken streak. Cron jobs here run every 30 min; quiet hours or a missed
# tick can create legitimate multi-hour gaps that must NOT be read as one
# continuous outage spanning both — 90 min covers jitter, not quiet hours.
_MAX_STREAK_GAP = timedelta(minutes=90)
# Trailing streak, OR total fast-fail events across jobs in the lookback
# window, needed to escalate to fail. The real incident produced a streak
# of 8 for one job — comfortably past this.
_STREAK_FAIL = 3
_TOTAL_FAIL = 3

_TS_RE = r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
_CRON_RE = re.compile(
    _TS_RE + r".*Cron job completed job=(?P<job>.+?) status=(?P<status>\S+) "
             r"duration_ms=(?P<dur>\d+)")
# Same intent as check_auth() in health_check.py, plus the exact incident
# phrasing ("Failed to authenticate. API Error: 401 Invalid authentication").
# Deliberately avoids bare "401" (also matches "foo.py:401" style refs).
_AUTH_RE = re.compile(
    r"(HTTP\s*401|status[ =:]+401|\b401 Unauthorized\b|401 Invalid authentication|"
    r"Invalid API key|authentication[_ ]failed|Failed to authenticate|"
    r"OAuth token (expired|invalid)|Please run /login)",
    re.IGNORECASE)
# Standard log line: "<ts> [LEVEL] logger.name:file.py:line: message".
_LEVEL_RE = re.compile(r"^\S+ \S+ \[(?P<level>\w+)\]")
_REAL_ERROR_LEVELS = {"ERROR", "WARNING"}
# Lines that carry raw user/CLI-argv text can legitimately contain "401" or
# "authentication" without any auth failure happening — a Telegram message
# forwarded verbatim, or a command's argv echoing what the user typed. These
# markers identify such lines so they never count as evidence, regardless
# of what regex they happen to match.
_USER_ECHO_MARKERS = ("CLI stream cmd:", "CLI cmd:", "Message received text=")


def _is_real_auth_line(line: str) -> bool:
    """True only for a genuine provider/CLI error line, never an echo of
    user input. A match inside a line quoting user text (chat message,
    command argv) is a false positive, not evidence of an auth failure."""
    if any(marker in line for marker in _USER_ECHO_MARKERS):
        return False
    level_m = _LEVEL_RE.match(line)
    return bool(level_m and level_m.group("level") in _REAL_ERROR_LEVELS)


def _read_tail(path: Path, max_bytes: int) -> str:
    with path.open("rb") as fh:
        fh.seek(max(0, path.stat().st_size - max_bytes))
        return fh.read().decode("utf-8", errors="replace")


def _parse_ts(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _scan(text: str, cutoff: datetime) -> tuple[list[dict], list[str]]:
    """Return (cron completion events within cutoff, auth-error lines within cutoff)."""
    cron_events: list[dict] = []
    auth_lines: list[str] = []
    for line in text.splitlines():
        m = _CRON_RE.search(line)
        if m:
            try:
                ts = _parse_ts(m.group("ts"))
            except ValueError:
                continue
            if ts >= cutoff:
                cron_events.append({
                    "ts": ts, "job": m.group("job"),
                    "status": m.group("status"), "duration_ms": int(m.group("dur")),
                })
            continue
        if _AUTH_RE.search(line) and _is_real_auth_line(line):
            ts_m = re.match(_TS_RE, line)
            if ts_m:
                try:
                    ts = _parse_ts(ts_m.group("ts"))
                except ValueError:
                    ts = None
                if ts is not None and ts < cutoff:
                    continue
            auth_lines.append(line.strip()[:200])
    return cron_events, auth_lines


def _is_fast_fail(ev: dict) -> bool:
    return ev["status"].startswith("error") and ev["duration_ms"] < _FAST_FAIL_SECONDS * 1000


def _longest_fast_fail_segment(events: list[dict]) -> dict | None:
    """Longest run of *consecutive* fast-fail completions anywhere in the
    (chronological) event list — not just a currently-ongoing one. An
    incident that has already recovered by the time this runs must still
    be found retrospectively, so we scan the whole window rather than only
    the trailing edge."""
    best: dict | None = None
    run: list[dict] = []
    for ev in events + [None]:  # sentinel flushes the last run
        breaks_gap = run and ev is not None and (ev["ts"] - run[-1]["ts"]) > _MAX_STREAK_GAP
        if ev is not None and _is_fast_fail(ev) and not breaks_gap:
            run.append(ev)
            continue
        if run and len(run) >= (best["length"] if best else 0):
            best = {"length": len(run), "start": run[0]["ts"], "end": run[-1]["ts"]}
        run = [ev] if (breaks_gap and ev is not None and _is_fast_fail(ev)) else []
    return best


def analyze(lookback_hours: float = _DEFAULT_LOOKBACK_HOURS) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)

    if not _LOG.is_file():
        return {"status": WARN, "detail": "no log file to scan",
                "signal_a": False, "signal_b": False}

    text = _read_tail(_LOG, _SCAN_BYTES)
    cron_events, auth_lines = _scan(text, cutoff)

    # Group cron events per job, preserving chronological order.
    by_job: dict[str, list[dict]] = {}
    for ev in cron_events:
        by_job.setdefault(ev["job"], []).append(ev)

    segments = {job: _longest_fast_fail_segment(evs) for job, evs in by_job.items()}
    segments = {job: seg for job, seg in segments.items() if seg is not None}

    # A successful cron run proves the login works again, so any streak that
    # ended before it is history, not an active outage. Without this gate the
    # watchdog keeps crying FAIL until the incident scrolls out of the lookback
    # window — which is exactly the false-alarm loop the dedup work fixed.
    last_success = max((ev["ts"] for ev in cron_events
                        if ev["status"] == "success"), default=None)
    resolved = {job: seg for job, seg in segments.items()
                if last_success is not None and seg["end"] < last_success}
    segments = {job: seg for job, seg in segments.items() if job not in resolved}
    max_streak = max((seg["length"] for seg in segments.values()), default=0)
    total_fast_fails = sum(1 for ev in cron_events if _is_fast_fail(ev))
    affected_jobs = sorted(job for job, seg in segments.items() if seg["length"] >= _STREAK_WARN)

    signal_b = max_streak >= _STREAK_WARN
    # Same recency rule for the log signal: auth errors predating the last
    # successful run describe an outage that is already over.
    fresh_auth = [ln for ln in auth_lines
                  if last_success is None or _parse_ts(ln[:19]) > last_success]
    signal_a = bool(fresh_auth)

    window = None
    if segments:
        # The window of the single worst (longest) streak — not the union of
        # every fast-fail event, which could span two unrelated episodes.
        worst_job, worst_seg = max(segments.items(), key=lambda kv: kv[1]["length"])
        window = {
            "start": worst_seg["start"].isoformat(timespec="seconds"),
            "end": worst_seg["end"].isoformat(timespec="seconds"),
            "job": worst_job,
        }

    b_is_fail = max_streak >= _STREAK_FAIL or total_fast_fails >= _TOTAL_FAIL

    if signal_a and signal_b:
        status = FAIL
        detail = (f"explicit auth errors in log AND a {max_streak}-run fast-failure "
                  f"streak on {', '.join(affected_jobs)} — provider login almost certainly expired")
    elif signal_b and b_is_fail:
        status = FAIL
        detail = (f"{max_streak}-run streak of fast cron failures on "
                  f"{', '.join(affected_jobs)} ({total_fast_fails} fast fails total in log), "
                  f"no explicit 401 text logged — pattern matches an auth outage")
    elif signal_b:
        status = WARN
        detail = (f"{max_streak}-run streak of fast cron failures on "
                  f"{', '.join(affected_jobs)} — below fail threshold ({_STREAK_FAIL}), watching")
    elif signal_a:
        status = WARN
        detail = f"{len(auth_lines)} explicit auth-error line(s) in log, no fast-fail cron streak (yet)"
    else:
        status = OK
        detail = "no auth-failure text and no fast-fail cron streak in lookback window"

    result = {
        "status": status,
        "detail": detail,
        "signal_a": signal_a,
        "signal_b": signal_b,
        "lookback_hours": lookback_hours,
        "window": window,
        "affected_jobs": affected_jobs,
        "max_streak": max_streak,
        "total_fast_fails": total_fast_fails,
        "auth_log_hits": len(fresh_auth),
        "last_auth_hit": fresh_auth[-1] if fresh_auth else None,
        "cron_events_scanned": len(cron_events),
        "last_success": last_success.isoformat(timespec="seconds") if last_success else None,
        # Kept for post-mortems: recovered incidents stay visible without alerting.
        "resolved_incidents": [
            {"job": job, "start": seg["start"].isoformat(timespec="seconds"),
             "end": seg["end"].isoformat(timespec="seconds"), "length": seg["length"]}
            for job, seg in sorted(resolved.items())
        ],
    }
    # Only ever included when a real key is present — never claim a fallback
    # exists when it does not (see suggest_fallback_provider()).
    fallback = suggest_fallback_provider()
    if fallback:
        result["fallback_provider"] = fallback
    return result


def _selftest() -> list[str]:
    """Sanity checks for signal (a) filtering. Returns a list of failure
    messages (empty = all passed). Run with --selftest."""
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    # 1. The exact real-world false positive: user's complaint echoed back
    #    into the log as a Telegram message, at INFO level. Must NOT count.
    user_echo_1 = ("2026-07-23 15:31:16 [INFO] ductor_bot.orchestrator.core:core.py:362: "
                   "[main:msg:965835789] Message received text=теперь мне присылает "
                   "failed to authenticate. api error: 401 invalid authenticati")
    check("user Message-received text with 401 must not count",
          _AUTH_RE.search(user_echo_1) is not None  # regex does match the text...
          and not _is_real_auth_line(user_echo_1))   # ...but the line filter rejects it

    # 2. Same complaint, echoed a second time as CLI argv (stream cmd), INFO level.
    user_echo_2 = ("2026-07-23 15:31:16 [INFO] ductor_bot.cli.claude_provider:claude_provider.py:240: "
                   "[main:msg:965835789:405c9573] CLI stream cmd: docker exec -w /ductor/workspace "
                   "-- теперь мне присылает Failed to authenticate. API Error: 401 Invalid authenticati")
    check("user CLI-argv echo with 401 must not count",
          _AUTH_RE.search(user_echo_2) is not None
          and not _is_real_auth_line(user_echo_2))

    # 3. A genuine provider/CLI error at ERROR level — must count.
    real_error = ("2026-07-24 03:00:05 [ERROR] ductor_bot.cli.claude_provider:claude_provider.py:250: "
                  "API Error: 401 Invalid authentication")
    check("real ERROR-level provider auth failure must count",
          _AUTH_RE.search(real_error) is not None and _is_real_auth_line(real_error))

    # 4. Same, but WARNING level — must also count.
    real_warning = ("2026-07-24 03:00:05 [WARNING] ductor_bot.cli.service:service.py:400: "
                    "Please run /login to reauthenticate")
    check("real WARNING-level provider auth failure must count",
          _AUTH_RE.search(real_warning) is not None and _is_real_auth_line(real_warning))

    # 5. Unrelated INFO-level provider line without auth text — must not count
    #    (regex should not even match, guards against an overly broad pattern).
    unrelated = ("2026-07-24 03:00:05 [INFO] ductor_bot.cli.claude_provider:claude_provider.py:282: "
                "CLI done session=abc turns=1 cost=$0.01 tokens=5 duration_ms=2000")
    check("unrelated INFO line must not match auth regex at all",
          _AUTH_RE.search(unrelated) is None)

    return failures


def _has_openai_key() -> bool:
    """Presence check only — never returns or logs the key value itself.

    Env injection only happens per CLI subprocess run (see your_integration.py's
    _load_env for the same pattern), so a bare os.environ lookup is not
    reliable when this script runs standalone rather than as an already-
    wrapped CLI call. Read .env directly as a fallback.
    """
    if os.environ.get("OPENAI_API_KEY"):
        return True
    if not _ENV.is_file():
        return False
    for line in _ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip()
        if line.startswith("OPENAI_API_KEY=") and line.split("=", 1)[1].strip().strip("'\""):
            return True
    return False


def suggest_fallback_provider() -> str | None:
    """Provider name to fail over to, or None if no fallback key is configured.

    Only reports a provider whose key is actually present — see
    README_auth_watchdog.md for why this deliberately does NOT claim Gemini
    works (gemini_api_key is unset in this deployment) even though the
    cron framework supports it.
    """
    if _has_openai_key():
        return "codex"
    return None


def check_auth_watchdog(r) -> None:
    """health_check.py-style hook — call from _CHECKS."""
    result = analyze()
    extra = {k: v for k, v in result.items() if k not in ("status", "detail")}
    r.add("auth_watchdog", result["status"], result["detail"], **extra)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lookback-hours", type=float, default=_DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--selftest", action="store_true",
                        help="run built-in false-positive/true-positive checks and exit")
    args = parser.parse_args()

    if args.selftest:
        failures = _selftest()
        if failures:
            print(json.dumps({"selftest": "fail", "failures": failures}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps({"selftest": "ok", "checks_passed": 5}, ensure_ascii=False, indent=2))
        return 0

    result = analyze(args.lookback_hours)
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **result,
    }, ensure_ascii=False, indent=2))
    return {OK: 0, WARN: 1, FAIL: 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
