# Security Policy

Baseline security posture for this skeleton. Adapt as you add integrations.

## Secrets

- All secrets live in `~/.ductor/.env`, `~/.ductor/config/config.json`, and
  `~/.ductor/agents.json` — all gitignored. Only `*.example` / `*.template`
  files are committed.
- `.gitignore` blocks `*token*`, `*secret*`, `*credential*`, `.env*`, `*.pem`,
  `*.key`, `id_rsa*`, and `**/config.json`.
- Never paste real tokens into chat. Any key that appears in a chat log must be
  rotated by its owner.

## Integrations

- Build connectors under `tools/integrations/`. **Read-only by default.**
- Any write path (posting, mutating external state) must be a separate,
  explicitly named function, gated behind human confirmation
  (dry-run → show diff → confirm). Never fold writes into a read client.
- If a provider only issues full-access (read+write) tokens, enforce read-only
  at the tool level and document the residual risk here.

## Agent boundaries

- Ask for confirmation before destructive actions.
- Ask before actions that publish or send data to external systems.
- Prefer reversible operations.
- Sub-agents get only the `allowed_user_ids` they need in `agents.json`.

## Runtime isolation

- When running in the `ductor-sandbox` Docker container, the filesystem is
  isolated to the `/ductor` mount; the host outside it is not reachable.
