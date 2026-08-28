# Deploy brief (generic SFTP publish/rollback)

A minimal pattern for publishing a static page / Mini-App to a server over SSH,
with rollback. All targets are parametrized via environment variables — nothing
is hardcoded to a specific host or domain in the skeleton.

## Configure (env, e.g. in ~/.ductor/.env)

- `DEPLOY_HOST`     — server IP / hostname (default placeholder: `YOUR_SERVER_IP`)
- `DEPLOY_SSH_KEY`  — path to your private key (`/path/to/your/ssh_key`)
- `DEPLOY_SRC`      — local file/dir to publish (`/path/to/your/page.html`)
- `DEPLOY_WEBROOT`  — remote webroot (`/var/www/your-domain/page`)
- `DEPLOY_URL`      — public URL for post-deploy verification

## Flow

1. **Publish** — upload `DEPLOY_SRC` to `DEPLOY_WEBROOT`, keeping a timestamped
   backup of the previous version on the server.
2. **Verify** — fetch `DEPLOY_URL` and assert an expected snippet is present.
3. **Rollback** — restore the most recent server-side backup if verification
   fails or on request.

See `_deploy_common.py` for the shared helpers. Write per-target
`publish.py` / `rollback.py` wrappers next to it as needed.
