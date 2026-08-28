# {{PROJECT_NAME}} Home

This is the top-level `~/.ductor` directory for {{PROJECT_NAME}}.
The main assistant usually runs with cwd `workspace/`.

## Cold Start (No Context)

Read in this order:

1. `workspace/CLAUDE.md` (main behavior + messenger rules)
2. `workspace/tools/CLAUDE.md` (tool routing)
3. `workspace/memory_system/MAINMEMORY.md` (long-term context)
4. `config/CLAUDE.md` (only for config changes)

## Top-Level Layout

- `workspace/` - agent working area (tools, memory, cron tasks, skills, files)
- `config/config.json` - runtime configuration
- `sessions.json` - per-chat session state (runtime, gitignored)
- `cron_jobs.json` - cron registry (runtime, gitignored)
- `webhooks.json` - webhook registry (runtime, gitignored)
- `logs/` - runtime logs

## Multi-Agent System (optional)

This skeleton supports a Supervisor + sub-agent architecture. If you only need
a single assistant, ignore `agents.json` entirely.

- `agents.json` is the single source of truth for every sub-agent bot token,
  allowed users, and model settings. Copy `agents.json.template` to start.
- The Supervisor reads `agents.json` at startup and merges each agent's token
  into its runtime config. **A sub-agent's bot token comes from `agents.json`,
  not from `config/config.json`.**
- Never hardcode or copy bot tokens between agents.

### Inter-Agent Communication

Synchronous (blocks until response):
```bash
python3 workspace/tools/agent_tools/ask_agent.py TARGET_AGENT "Your message"
```
Asynchronous (returns immediately, response delivered via the messenger):
```bash
python3 workspace/tools/agent_tools/ask_agent_async.py TARGET_AGENT "Your message"
```

### Shared Knowledge

`SHAREDMEMORY.md` holds facts shared across all agents (infra, user
preferences). The Supervisor syncs changes into each agent's `MAINMEMORY.md`.

- Agent-specific knowledge → that agent's `memory_system/MAINMEMORY.md`.
- Cross-agent knowledge → `SHAREDMEMORY.md`
  (via `workspace/tools/agent_tools/edit_shared_knowledge.py`).

## Operating Rules

- Use tool scripts in `workspace/tools/` for cron/webhook lifecycle changes.
  Do not manually edit `cron_jobs.json` or `webhooks.json`.
- When config changes are requested, edit only the requested keys in
  `config/config.json`, then tell the user to run `/restart`.
- Save user-facing generated files in `workspace/output_to_user/` and send with
  `<file:/absolute/path/...>`.
- Update `workspace/memory_system/MAINMEMORY.md` silently when durable user
  facts or preferences are learned.
