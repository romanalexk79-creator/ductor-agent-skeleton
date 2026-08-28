# Example Daily Report

> This is a worked EXAMPLE scaffold shipped with the skeleton. Copy this folder,
> rename it, and adapt it to your real task. Register it with
> `tools/cron_tools/cron_add.py`.

## Goal

Once a day, gather some numbers and send the user a short, well-formatted
summary. Stay silent on failure only if the task says so (this example always
reports).

## Context

- Helper script lives in `scripts/report_data.py`. In the skeleton it returns
  **demo data** — replace its body with a real call into your
  `tools/integrations/` connector.
- Delivery goes through `tools/user_tools/notify.py`, which fans out to all
  allowed chat ids by default.

## Assignment

1. Read `example-daily-report_MEMORY.md` for prior context.
2. Run `python3 scripts/report_data.py` to collect the figures.
3. Format a concise summary (use the messenger's markdown).
4. Send it via `python3 ../../tools/user_tools/notify.py "<your message>"`.
5. Update `example-daily-report_MEMORY.md` with timestamp + what you sent.

## Output

A short daily summary delivered to the user. The task is complete once the
message is sent and memory is updated.
