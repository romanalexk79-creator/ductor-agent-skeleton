# Workspace

Agent working area for {{PROJECT_NAME}}. This is a brand-neutral skeleton — see
the top-level `../README.md` for what was removed and how to build on it.

## Layout

- `CLAUDE.md` — main behavior + messenger rules (read first)
- `memory_system/` — long-term memory
- `tools/` — the framework toolbelt (see `tools/CLAUDE.md`)
  - `agent_tools/ cron_tools/ webhook_tools/ task_tools/ media_tools/` — infra
  - `user_tools/` — generic utilities (notify, failover, calendar, weather)
  - `integrations/` — **your connectors go here** (empty in skeleton)
  - `deploy_tools/` — generic SFTP publish/rollback pattern
- `cron_tasks/` — scheduled task folders (one worked example included)
- `dashboard_site/` — generic Telegram Mini-App PWA shell to re-skin
- `skills/` — custom skills
- `docs/` — architecture & operations docs
- `output_to_user/` — generated deliverables to send to the user (create as needed)

## First run

1. Fill `../config/config.json` (bot token + allowed ids).
2. Copy `.env.example` → `~/.ductor/.env` for integration keys.
3. Read `CLAUDE.md`, then start building under `tools/integrations/`.
