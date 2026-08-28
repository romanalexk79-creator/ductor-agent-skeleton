# Architecture

A multi-agent messenger assistant built on the Ductor runtime.

## Components

- **Main agent** — the coordinator the user talks to. Configured in
  `config/config.json`. Prompt: `workspace/CLAUDE.md`.
- **Sub-agents (optional)** — separate bots, each with its own chat, workspace,
  and memory. Registered in `agents.json`. The main agent delegates to them via
  `tools/agent_tools/`.
- **Tools** — the framework toolbelt under `workspace/tools/`:
  - `agent_tools` inter-agent messaging
  - `cron_tools` / `webhook_tools` scheduled + event-driven triggers
  - `task_tools` background task delegation (autonomous worker processes)
  - `media_tools` audio/video/document handling
  - `user_tools` generic utilities
  - `integrations` your external connectors (empty in the skeleton)
  - `deploy_tools` static-site publish/rollback
- **Memory** — `memory_system/MAINMEMORY.md` (per-agent) and `SHAREDMEMORY.md`
  (cross-agent, synced by the Supervisor).
- **Cron tasks** — isolated folders under `cron_tasks/`, each run as a fresh
  headless agent session.
- **Dashboard** — optional Telegram Mini-App PWA under `dashboard_site/`.

## Data flow (typical)

```
user ──▶ main agent ──▶ tools/integrations/<connector> ──▶ external service
                   └──▶ sub-agent (domain worker) ──▶ tools/integrations/...
cron ──▶ headless agent ──▶ tools ──▶ notify.py ──▶ user
```

## Extending

1. Add a connector under `tools/integrations/`.
2. Add domain logic as a `user_tools` script or a sub-agent.
3. Schedule recurring work as a `cron_tasks/` folder.
4. Surface results in the messenger and/or the dashboard.
