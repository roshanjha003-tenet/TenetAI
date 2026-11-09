# Tenet

For every AI-made change: why it was made, who approved it, and whether it still matches what was decided.
Design: `docs/hld.md`. Working rules and build order: `CLAUDE.md`.

## Layout

- `backend/` FastAPI service, Alembic migrations, tests
- `web/` Next.js app
- `demo-repo/` source for the demo GitHub repo and its scripted PRs
- `docker-compose.yml` Postgres 16 + pgvector
- `scripts/` dev launchers

## Development (inside WSL)

Needs Docker, [uv](https://docs.astral.sh/uv/) (provides Python 3.12) and Node 20+.

```bash
cp .env.example .env
docker compose up -d --wait db
cd backend
uv sync
uv run alembic upgrade head
uv run pytest -q
uv run ruff check .
```

Run the app with demo data:

```bash
cd backend
uv run python -m app.seed --reset --through 4   # @payments-redesign at v4
uv run python scripts/load_demo_prs.py          # PR #284 passes, PR #291 drifts (recorded fixtures)
cd ..
bash scripts/dev-api.sh                         # http://localhost:8000
bash scripts/dev-web.sh                         # http://localhost:3000 (npm install in web/ first)
```

Sign in with a seeded user's dev token (`dev-yashwant`, `dev-maya`, `dev-arjun`, `dev-priya`); dev tokens
work only while `ENV=dev`. Yashwant is the org admin (Admin page: people, invites, domains, usage, audit).
The full demo, live against GitHub and Slack, is in [`docs/demo.md`](docs/demo.md).

Tests run against the `tenet_test` database, which the compose init script creates the first time the
volume is made. If you created the volume before that script existed: `docker compose down -v`.

## What needs credentials

Everything runs locally without secrets; these turn on the live integrations (`.env.example` lists them):

- `ANTHROPIC_API_KEY` — your private AI, routing, Capture, conflict check, PR analysis, Ask
- GitHub App (`GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`) — PR checks and `@tenet` comments
- Slack (`SLACK_BOT_TOKEN`) — notifications
- Google OAuth client (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) — Sign in with Google, and attach and sync
  Google Docs
- Microsoft Entra app (`MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`) — Sign in with Microsoft (work accounts)

## Sign-in and access

- **Who gets in:** an existing user, someone holding an invite for that exact email, or anyone whose email
  domain your org has verified with a DNS TXT record (Admin → Verified domains). Free-mail domains can never
  be verified. Invited people from other domains join as **external guests**: only the spaces they're
  invited to, no org directory, no new spaces.
- **Sessions:** an HttpOnly cookie holding a random token (only its hash is stored); 12 h idle, 7 days at
  most; sign out one session or all. State-changing requests need the `X-Tenet-CSRF` header from the web
  app's origin.
- **Isolation in the database:** the API connects as `tenet_api`, which owns nothing, so row-level security
  limits every query to the caller's org. Migrations and the seed use the owner (`MIGRATION_DATABASE_URL`).
- **Accounting:** an append-only audit log of sign-ins, sessions, invites, roles, domains and connections;
  every model call is metered per org, and a monthly cap (default $50) pauses model features when reached.

OAuth redirect URIs to register (with `PUBLIC_URL` = where the API is reachable):

- Google: `{PUBLIC_URL}/api/auth/google/callback` (sign-in) and `{PUBLIC_URL}/api/connect/google/callback`
  (Drive)
- Microsoft: `{PUBLIC_URL}/api/auth/microsoft/callback`; for Microsoft accounts to be trusted without a
  Tenet-verified domain, add the `xms_edov` optional claim to the ID token.

The session cookie is `SameSite=Lax`, so the web app and API must share a site, for example
`app.example.com` and `api.example.com` (or both on `localhost`).

### Before deploying beyond localhost

The API refuses to start with `ENV=prod` unless all of these hold:

- `SECRET_KEY` is a long random value (32+ characters).
- `PUBLIC_URL` and `WEB_URL` are https.
- Google or Microsoft sign-in is configured.
- `DATABASE_URL` uses the `tenet_api` role (not a superuser, not the table owner). Give it a real password
  with `ALTER ROLE tenet_api PASSWORD '…'`, or set `TENET_API_PASSWORD` before running migrations.

Optionally set `TOKEN_ENCRYPTION_KEY` (a Fernet key); otherwise Google tokens are encrypted with a key
derived from `SECRET_KEY`. Rate limits are per API process, so with several processes add limits at
the proxy too.
