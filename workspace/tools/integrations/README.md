# Integrations

**This folder is intentionally empty in the skeleton.** It is where your
project's external connectors go — the equivalent of the POS / reviews / sheets
clients that were removed when this skeleton was extracted.

## Pattern to follow

Each integration is a small, self-contained Python module that:

1. Reads its secrets from environment variables (see `../../.env.example`),
   never hardcoded.
2. Exposes a thin, testable client — one class or a few functions.
3. Is **read-only by default**. Any write path must be a separate, explicitly
   named function that requires human confirmation (dry-run → show → confirm).
4. Is invoked by cron tasks / user tools / sub-agents by absolute path.

## Example layout

```
integrations/
  my_pos/
    client.py        # read sales/stock
    CLAUDE.md         # how the agent should use it
  my_reviews/
    client.py        # fetch reviews
    publish.py        # write path — human-confirmed only
  my_sheets/
    sync.py
```

## Security reminders

- Store keys in `~/.ductor/.env`, add them to `.env.example` as placeholders.
- Never commit real tokens. `.gitignore` already blocks `*token*`, `*secret*`,
  `*credential*`, `.env*`.
- Rotate any key that ends up in a chat log.
