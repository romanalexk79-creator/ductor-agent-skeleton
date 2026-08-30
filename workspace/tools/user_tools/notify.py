#!/usr/bin/env python3
"""Send a message to the user's Telegram chat directly via the Bot API.

Used by jobs that run with `silent_on_success` (their normal agent reply is
never delivered), so an alert has to be pushed explicitly.

Usage:
    python3 tools/user_tools/notify.py "text"
    echo "text" | python3 tools/user_tools/notify.py -
    python3 tools/user_tools/notify.py --md "**bold** text"  # render **..** as bold
    python3 tools/user_tools/notify.py --extra-only "text"   # skip primary chat
    python3 tools/user_tools/notify.py --to 111 --to 222 -   # only these chats

Sends to the primary chat plus EVERY id in config's `allowed_user_ids` and
`notify_extra_chat_ids` (e.g. the shared team account) -- the standing rule is
that every summary reaches every allowed id, EXCEPT ids listed in
`notify_exclude_ids` (users allowed to talk to the bot but opted out of
broadcasts; the exclusion is ignored when explicit --to ids are given).
With --extra-only the primary chat
is skipped (but the other allowed ids still receive it) -- use it when the
primary chat already got the message another way (e.g. as the agent's own
reply). With one or more --to <id>, the message goes ONLY to those explicit
chats (primary, allowed_user_ids and notify_extra_chat_ids are ignored) -- use
it to scope a single message to a specific audience.

With --md the text is treated as light Markdown: `**bold**` becomes bold and the
message is sent with Telegram parse_mode=HTML (all other characters are HTML-
escaped, so the raw text stays literal). Without --md the text is sent verbatim
with no parse_mode, exactly as before.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG = Path("/ductor/config/config.json")
# 0 = unset. Provide the primary chat via config.api.chat_id, config
# allowed_user_ids, or the DUCTOR_CHAT_ID env var. Never hardcode a real id here.
DEFAULT_CHAT_ID = int(os.environ.get("DUCTOR_CHAT_ID") or 0)
API = "https://api.telegram.org/bot{token}/sendMessage"
TG_LIMIT = 4096


def _chunks(text: str):
    while text:
        yield text[:TG_LIMIT]
        text = text[TG_LIMIT:]


def _md_to_html(text: str) -> str:
    """Escape HTML, then turn `**bold**` into <b>bold</b> for parse_mode=HTML."""
    escaped = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.DOTALL)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    args = sys.argv[1:]
    # Leading options (any order): --extra-only and/or repeated --to <id>.
    # --extra-only: skip the primary chat, deliver only to notify_extra_chat_ids.
    # --to <id>:    send ONLY to the given explicit chat id(s), ignoring primary
    #               and notify_extra_chat_ids (scopes one message to a specific
    #               audience without editing the global config).
    extra_only = False
    as_md = False
    explicit: list[int] = []
    while args and args[0] in ("--extra-only", "--to", "--md"):
        if args[0] == "--extra-only":
            extra_only = True
            args = args[1:]
        elif args[0] == "--md":
            as_md = True
            args = args[1:]
        else:  # --to <id>
            if len(args) < 2 or not args[1].lstrip("-").isdigit():
                print("--to requires a numeric chat id", file=sys.stderr)
                return 2
            explicit.append(int(args[1]))
            args = args[2:]
    if not args:
        print(__doc__)
        return 2

    text = sys.stdin.read() if args[0] == "-" else " ".join(args)
    text = text.strip()
    if not text:
        print("nothing to send", file=sys.stderr)
        return 2

    cfg = json.loads(CONFIG.read_text())
    token = cfg.get("telegram_token")
    if not token:
        print("no telegram_token in config.json", file=sys.stderr)
        return 1

    primary = cfg.get("api", {}).get("chat_id") or DEFAULT_CHAT_ID

    # Build recipient list. Explicit --to ids win outright; otherwise the
    # primary chat first, then any extra copies (e.g. the shared team account),
    # deduped while preserving order.
    if explicit:
        source = explicit
    else:
        # Rule (user, 2026-08-09): every summary reaches every allowed id.
        # Default recipients = union of the primary chat, all allowed_user_ids,
        # and any extra copies (e.g. a shared account not in allowed_user_ids).
        # --extra-only drops the primary chat -- used when it already got the
        # message another way (e.g. as the agent's own reply) -- but still fans
        # out to the other allowed ids.
        allowed = [int(u) for u in cfg.get("allowed_user_ids", []) if u]
        extra = [int(c) for c in cfg.get("notify_extra_chat_ids", []) if c]
        seed = [] if extra_only else [primary]
        source = [*seed, *allowed, *extra]
        if extra_only:
            source = [c for c in source if c != primary]
        # Opt-out list (user, 2026-08-12): ids that may USE the bot (they are in
        # allowed_user_ids) but must NOT receive broadcast summaries/digests.
        # Applies only to the default fan-out -- an explicit --to <id> still
        # reaches them, so a message can be scoped to them deliberately.
        exclude = {int(x) for x in cfg.get("notify_exclude_ids", []) if x}
        if exclude:
            source = [c for c in source if c not in exclude]
    recipients: list[int] = []
    for cid in source:
        if cid and cid not in recipients:
            recipients.append(cid)

    if not recipients:
        print("no recipients (extra-only with empty notify_extra_chat_ids)", file=sys.stderr)
        return 0

    failed = False
    for chat_id in recipients:
        for part in _chunks(text):
            fields = {
                "chat_id": chat_id,
                "text": _md_to_html(part) if as_md else part,
                "disable_web_page_preview": "true",
            }
            if as_md:
                fields["parse_mode"] = "HTML"
            payload = urllib.parse.urlencode(fields).encode()
            try:
                resp = urllib.request.urlopen(
                    API.format(token=token), data=payload, timeout=20
                )
                body = json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                print(f"telegram error {exc.code} for {chat_id}: {exc.read().decode()[:300]}", file=sys.stderr)
                failed = True
                break
            except Exception as exc:  # noqa: BLE001 - network layer
                print(f"send failed for {chat_id}: {exc}", file=sys.stderr)
                failed = True
                break
            if not body.get("ok"):
                print(f"telegram rejected for {chat_id}: {body}", file=sys.stderr)
                failed = True
                break

    if failed:
        # A failure to one recipient (e.g. shared account hasn't pressed Start)
        # must not swallow delivery to the others.
        return 1

    print(f"sent to {len(recipients)} recipient(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
