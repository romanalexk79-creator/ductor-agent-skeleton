#!/usr/bin/env python3
"""Fail cron jobs over to codex when auth_watchdog says Claude's login is
down, and fail them back to Claude once it recovers.

Why this exists (base-4-2, second half): auth_watchdog.py only detects the
problem. This is the part that acts on it — flipping the `provider` field on
cron jobs via the existing tools/cron_tools/ scripts (never hand-editing
cron_jobs.json) and telling the user in Telegram every time it does, because
a silent provider switch silently changes model/quality/cost.

CRITICAL DESIGN CONSTRAINT: this script must never depend on Claude being
healthy. A normal Ductor cron job runs by having the *host* ductor_bot
process `docker exec` a Claude CLI call, which is exactly what breaks during
a Claude auth outage — the same failure mode this script exists to route
around. So this script:
  - is pure stdlib Python, no LLM call of any kind to decide what to do,
  - must be invoked by a scheduler that does not go through a Claude-backed
    cron job (see README_auth_watchdog.md for why no in-container scheduler
    is currently wired up, and what a durable fix requires).

State lives in state/provider_failover.json next to this script and records
exactly which jobs THIS script switched and what their provider was before,
so recovery only ever touches jobs it touched itself — never a job the user
pinned to some other provider by hand — and so a repeated run in the same
condition (still down / still healthy) is a no-op, not a duplicate alert.

Usage:
    python3 tools/user_tools/provider_failover.py             # act for real
    python3 tools/user_tools/provider_failover.py --dry-run   # plan only, no writes/alerts
    python3 tools/user_tools/provider_failover.py --selftest  # synthetic flip/flip-back checks

Exit code: 0 no action or action succeeded, 1 partial failure (some jobs
could not be switched/restored), 2 auth_watchdog itself could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auth_watchdog  # noqa: E402

_HOME = Path(os.environ.get("DUCTOR_HOME", "/ductor"))
_JOBS_PATH = _HOME / "cron_jobs.json"
_CRON_EDIT = Path(__file__).resolve().parent.parent / "cron_tools" / "cron_edit.py"
_NOTIFY = Path(__file__).resolve().parent / "notify.py"
_STATE_PATH = Path(__file__).resolve().parent / "state" / "provider_failover.json"

FALLBACK_PROVIDER = "codex"


def _load_state() -> dict:
    if not _STATE_PATH.is_file():
        return {"switched": {}}
    try:
        state = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"switched": {}}
    state.setdefault("switched", {})
    return state


def _save_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_jobs() -> list[dict]:
    """Read-only. All writes go through cron_edit.py, never direct JSON surgery
    (cron_list.py's own self-description forbids hand-editing cron_jobs.json;
    tools/CLAUDE.md's global rule is the same: prefer the tool scripts)."""
    if not _JOBS_PATH.is_file():
        return []
    raw = json.loads(_JOBS_PATH.read_text(encoding="utf-8"))
    return raw.get("jobs", raw if isinstance(raw, list) else [])


def plan_actions(verdict: dict, jobs: list[dict], switched_state: dict) -> dict:
    """Pure decision function — no I/O, no subprocess calls. Takes an
    auth_watchdog verdict, the current cron job list, and the switched-jobs
    part of state; returns which job ids to switch to the fallback provider
    and which to restore. Kept separate from main() so --selftest can drive
    it with synthetic verdicts without touching real cron_jobs.json or
    sending real Telegram messages.
    """
    status = verdict.get("status")
    fallback = verdict.get("fallback_provider")

    to_switch: list[str] = []
    if status == auth_watchdog.FAIL and fallback:
        for job in jobs:
            jid = job.get("id")
            if not jid or not job.get("enabled", True):
                continue
            if jid in switched_state:
                continue  # already switched by us — idempotent, not a re-switch
            if job.get("provider") not in (None, "claude"):
                continue  # user pinned this job to something else — never touch it
            to_switch.append(jid)

    to_restore: list[str] = []
    if status == auth_watchdog.OK:
        to_restore = sorted(switched_state.keys())

    return {"switch": to_switch, "restore": to_restore}


def _run_cron_edit(job_id: str, *flags: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(_CRON_EDIT), job_id, *flags],
        capture_output=True, text=True, timeout=30, check=False,
    )
    ok = proc.returncode == 0
    return ok, (proc.stdout if ok else (proc.stderr or proc.stdout)).strip()[:500]


def _notify(text: str) -> None:
    subprocess.run([sys.executable, str(_NOTIFY), text],
                    capture_output=True, text=True, timeout=20, check=False)


def _act(plan: dict, verdict: dict, state: dict, dry_run: bool) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    switched_ok, switched_failed = [], []
    restored_ok, restored_failed = [], []

    for jid in plan["switch"]:
        if dry_run:
            switched_ok.append(jid)
            continue
        ok, msg = _run_cron_edit(jid, "--provider", FALLBACK_PROVIDER)
        if ok:
            state["switched"][jid] = {
                "original_provider": None,  # only jobs with provider in (None, "claude") are ever switched
                "switched_at": now,
                "reason": {k: verdict.get(k) for k in ("detail", "window", "affected_jobs", "max_streak")},
            }
            switched_ok.append(jid)
        else:
            switched_failed.append((jid, msg))

    for jid in plan["restore"]:
        if dry_run:
            restored_ok.append(jid)
            continue
        original = state["switched"].get(jid, {}).get("original_provider")
        flags = ("--provider", original) if original else ("--clear-provider",)
        ok, msg = _run_cron_edit(jid, *flags)
        if ok:
            state["switched"].pop(jid, None)
            restored_ok.append(jid)
        else:
            restored_failed.append((jid, msg))

    if not dry_run:
        _save_state(state)

    alerted = False
    if switched_ok or switched_failed:
        lines = [f"⚠️ Вход Claude похоже сломан ({verdict.get('detail', '')})."]
        if switched_ok:
            lines.append(f"Переключил на резервный провайдер (codex/ChatGPT): {', '.join(switched_ok)}.")
        if switched_failed:
            lines.append("НЕ удалось переключить: " + ", ".join(
                f"{jid} ({msg})" for jid, msg in switched_failed))
        lines.append("Модель/качество/стоимость ответов у этих задач изменятся, пока вход Claude не восстановится.")
        if not dry_run:
            _notify("\n".join(lines))
        alerted = True
    if restored_ok or restored_failed:
        lines = ["✅ Вход Claude снова здоров."]
        if restored_ok:
            lines.append(f"Вернул провайдера по умолчанию (Claude): {', '.join(restored_ok)}.")
        if restored_failed:
            lines.append("НЕ удалось вернуть: " + ", ".join(
                f"{jid} ({msg})" for jid, msg in restored_failed))
        if not dry_run:
            _notify("\n".join(lines))
        alerted = True

    return {
        "switched_ok": switched_ok, "switched_failed": switched_failed,
        "restored_ok": restored_ok, "restored_failed": restored_failed,
        "alerted": alerted,
    }


def _selftest() -> list[str]:
    """Synthetic flip / flip-back / idempotency checks on plan_actions() —
    no subprocess calls, no real cron_jobs.json, no real Telegram message."""
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    jobs = [
        {"id": "job-a", "enabled": True, "provider": None},
        {"id": "job-b", "enabled": True, "provider": None},
        {"id": "job-c", "enabled": True, "provider": "gemini"},  # user-pinned, must never be touched
        {"id": "job-d", "enabled": False, "provider": None},     # disabled, must never be touched
    ]

    fail_verdict = {"status": auth_watchdog.FAIL, "fallback_provider": "codex", "detail": "test fail"}
    ok_verdict = {"status": auth_watchdog.OK, "detail": "test ok"}
    warn_verdict = {"status": auth_watchdog.WARN, "detail": "test warn"}
    fail_no_fallback = {"status": auth_watchdog.FAIL, "detail": "test fail, no key"}

    # 1. Flip: FAIL + fallback -> switch eligible jobs only (a, b), never c or d.
    plan1 = plan_actions(fail_verdict, jobs, {})
    check("flip switches job-a", "job-a" in plan1["switch"])
    check("flip switches job-b", "job-b" in plan1["switch"])
    check("flip never touches user-pinned job-c", "job-c" not in plan1["switch"])
    check("flip never touches disabled job-d", "job-d" not in plan1["switch"])
    check("flip does not restore anything", plan1["restore"] == [])

    # 2. Idempotency: already-switched jobs are not re-switched on a second FAIL.
    switched_state = {"job-a": {}, "job-b": {}}
    plan2 = plan_actions(fail_verdict, jobs, switched_state)
    check("idempotent: no re-switch of already-switched jobs", plan2["switch"] == [])

    # 3. FAIL without a fallback key configured -> no action at all (never
    #    silently do nothing AND claim a fallback that doesn't exist).
    plan3 = plan_actions(fail_no_fallback, jobs, {})
    check("no fallback key -> no switch attempted", plan3["switch"] == [])

    # 4. WARN -> no action either direction (not confirmed enough to act on).
    plan4 = plan_actions(warn_verdict, jobs, {})
    check("warn triggers no switch", plan4["switch"] == [])
    check("warn triggers no restore", plan4["restore"] == [])

    # 5. Flip-back: OK with jobs previously switched -> restore exactly those.
    plan5 = plan_actions(ok_verdict, jobs, switched_state)
    check("flip-back restores exactly the switched jobs",
          sorted(plan5["restore"]) == ["job-a", "job-b"])
    check("flip-back does not switch anything", plan5["switch"] == [])

    # 6. Idempotency the other way: OK with nothing switched -> no-op, not an
    #    empty-but-still-firing restore action.
    plan6 = plan_actions(ok_verdict, jobs, {})
    check("idempotent: OK with nothing switched restores nothing", plan6["restore"] == [])

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="plan actions and print them, but never call cron_edit.py or notify.py")
    parser.add_argument("--selftest", action="store_true",
                        help="run synthetic flip/flip-back checks and exit")
    args = parser.parse_args()

    if args.selftest:
        failures = _selftest()
        if failures:
            print(json.dumps({"selftest": "fail", "failures": failures}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps({"selftest": "ok", "checks_passed": 10}, ensure_ascii=False, indent=2))
        return 0

    verdict = auth_watchdog.analyze()
    jobs = _load_jobs()
    state = _load_state()
    plan = plan_actions(verdict, jobs, state["switched"])
    outcome = _act(plan, verdict, state, args.dry_run)

    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "watchdog_status": verdict["status"],
        "fallback_provider": verdict.get("fallback_provider"),
        "plan": plan,
        "outcome": outcome,
        "currently_switched": sorted(state["switched"].keys()),
    }, ensure_ascii=False, indent=2))

    if outcome["switched_failed"] or outcome["restored_failed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
