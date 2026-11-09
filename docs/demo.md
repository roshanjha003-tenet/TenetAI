# Demo runbook

The demo slice from `CLAUDE.md`, run against the real app. `backend/tests/test_demo_rehearsal.py`
runs the same steps with recorded model responses; run it first, since a green result means the
moving parts line up.

```bash
cd backend && uv run pytest -q tests/test_demo_rehearsal.py
```

## Two ways to run it

- **Offline (no credentials).** Seed through v4 and load the recorded PR checks:
  `uv run python -m app.seed --reset --through 4 && uv run python scripts/load_demo_prs.py`.
  Screens 05–07 then show PR #284 passing and #291 drifting. Steps 2–5 need `ANTHROPIC_API_KEY`
  for the private AI and Capture.
- **Live.** A real GitHub repo, the GitHub App, Slack and the model, set up as described below.

## One-time setup for the live run

1. **Demo repo.** `bash demo-repo/scripts/publish.sh yyadav1120/payments-service` creates the repo
   (private) with `service/` as `main` and opens one PR per `demo-repo/prs/*`. The script is
   idempotent. GitHub numbers the PRs itself (#1, #2), so they won't be #284 and #291. The check
   keys on the `Implements: D-014` line, not the number.
   - Open the PRs only after D-014 is approved (step 6), or re-run the check by pushing an empty
     commit to the branch; until D-014 is agreed the link is *not linked* → neutral.
   - To start over: close the PRs, delete the branches, and run the script again.
2. **Tunnel.** `cloudflared tunnel --url http://localhost:8000`, then set `PUBLIC_URL` in `.env` to
   the printed `https://…trycloudflare.com` URL.
3. **GitHub App** (Settings → Developer settings → GitHub Apps → New):
   - Webhook URL `{PUBLIC_URL}/webhooks/github`, with a random secret → `GITHUB_WEBHOOK_SECRET`.
   - Repository permissions: Checks *read & write*, Pull requests *read*, Issues *read & write*
     (PR comments), Contents *read*, Metadata *read*.
   - Subscribe to events: *Pull request*, *Issue comment*.
   - Generate a private key → path in `GITHUB_PRIVATE_KEY`; App ID → `GITHUB_APP_ID`.
   - Install the app on the demo repo only. The installation id is learned from the first webhook.
4. **Slack** (optional): a bot with `chat:write`, invited to `#payments` → `SLACK_BOT_TOKEN`.
5. **Model**: `ANTHROPIC_API_KEY`.
6. **Seed to v3**, pointing the space at the live repo:

   ```bash
   cd backend
   export TENET_DEMO_REPO=yyadav1120/payments-service   # read from the shell, not .env
   uv run python -m app.seed --reset                     # @payments-redesign at v3
   cd .. && bash scripts/dev-api.sh & bash scripts/dev-web.sh
   ```

Sign in at http://localhost:3000 with a dev token: `dev-yashwant`, `dev-maya`, `dev-arjun` or
`dev-priya`. Use a separate browser profile per person to switch quickly.

## The run-through

| # | Who | Do | Expect |
|---|-----|----|--------|
| 1 | Yashwant | Spaces → `@payments-redesign` (seeded with PAY-142, "Payment retry policy v2" and #payments linked) | State v3; D-012, D-013 |
| 2 | Yashwant | New private session; ask how to retry safely given PAY-142 | Your AI answers; the space's activity doesn't change |
| 3 | Yashwant | Send the message that contains `@payments-redesign proposing: bounded automatic retries…` | Only the tagged text is shown as shared; the rest stays private |
| 4 | Maya | Review queue | D-014 pending review, with 4 constraints and parent D-013; Slack posts *proposal created* and *your turn* to Maya |
| 5 | Maya, then Arjun | Approve the product-scope stage, then the technical-safety stage | Arjun can't approve first; state stays v3 after Maya |
| 6 | anyone | State | v4 with D-014, approved by Maya Chen and Arjun Rao; Slack posts *state updated* |
| 7 | Arjun | Open the bounded-retries PR on GitHub; comment `@tenet where are we?`, `@tenet why?`, `@tenet what changed?` | Tenet check **success**; replies signed as `@payments-redesign/pr-N` with sources |
| 8 | Coding agent | Open the retry-transient-failures PR | Tests pass; Tenet check **failure** naming D-014's idempotency-key constraint, Maya + Arjun, and `payments/retry.py` lines |
| 9 | anyone | History → Rewind v2 → v4 | D-012, D-013 and D-014 step by step; nothing is written |

## If something goes wrong

- **Check is neutral**: by design (fail open). The check summary says why: not linked, stale, model
  error, or unsure. Check `ANTHROPIC_API_KEY`, and that D-014 was agreed before the PR event arrived.
- **No check at all**: the webhook didn't arrive or didn't match. In the App's *Advanced* tab, check
  recent deliveries. A 401 means the secret is wrong. If the repo isn't in the space, `TENET_DEMO_REPO`
  wasn't set when seeding.
- **Reset**: `uv run python -m app.seed --reset` returns to v3.
