# Project Skeleton

A brand-neutral skeleton extracted from a production multi-agent Telegram
assistant. **All business identity has been removed** — no brand book, no POS
(Poster) integration, no reviews (2GIS) integration, no server/deploy
credentials. What remains is the reusable framework you drop your next project
onto.

## What's inside

```
project-skeleton/
├─ CLAUDE.md              # home-level agent prompt (generic)
├─ SHAREDMEMORY.md        # cross-agent shared knowledge (empty template)
├─ agents.json.template   # multi-agent registry (fill tokens per agent)
├─ config/
│  ├─ config.json         # runtime config TEMPLATE (put your bot token + ids)
│  └─ CLAUDE.md           # config-change rules
└─ workspace/             # the agent working area
   ├─ CLAUDE.md           # main behaviour + messenger rules (generic)
   ├─ README.md
   ├─ SECURITY.md
   ├─ .env.example        # integration secrets template (placeholders only)
   ├─ memory_system/      # long-term memory (empty template)
   ├─ docs/               # architecture / operations docs (generic)
   ├─ skills/             # skill-creator (generic)
   ├─ tools/
   │  ├─ agent_tools/     # multi-agent messaging (ask/list/create/remove)
   │  ├─ cron_tools/      # cron lifecycle
   │  ├─ webhook_tools/   # webhook lifecycle
   │  ├─ task_tools/      # background task delegation
   │  ├─ media_tools/     # file/audio/video/document helpers
   │  ├─ user_tools/      # generic utilities (notify, failover, calendar, weather)
   │  ├─ integrations/    # ← PUT YOUR CONNECTORS HERE (empty stub + guide)
   │  └─ deploy_tools/    # generic SFTP publish/rollback pattern
   ├─ cron_tasks/
   │  ├─ CLAUDE.md
   │  └─ example-daily-report/   # one worked example scaffold
   └─ dashboard_site/     # generic Telegram Mini-App PWA shell (re-skin it)
```

## What was intentionally REMOVED

- Brand book / colors / mascot / logos
- Poster POS client and everything that read sales/stock from it
- 2GIS reviews client and auto-reply pipeline
- iiko, WhatsApp, Yelumio Studio, Instagram/Apify connectors
- Finance / sales-analytics / stock / invoice / forecast business logic
- All server credentials (SSH key, host IP, Caddy webroots, DNS)
- Every `croissant-*` / `shift-*` cron task and branded dashboard
- Integration-bound health/smoke monitors

## Turning this into a new project

1. Copy `config/config.json` → `~/.ductor/config/config.json`, put your
   Telegram bot token and `allowed_user_ids`.
2. Copy `agents.json.template` → `~/.ductor/agents.json` if you want sub-agents.
3. Copy `workspace/.env.example` → `~/.ductor/.env`, add your integration keys.
4. Write your connectors under `workspace/tools/integrations/`.
5. Re-skin `workspace/dashboard_site/` with your brand.
6. Replace placeholders (`{{PROJECT_NAME}}`, `YOUR_SERVER_IP`, …) — search:
   `grep -rn "{{" . && grep -rn "YOUR_" .`
