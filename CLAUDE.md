# Tenet

For every AI-made change: why it was made, who approved it, and whether it still matches what was decided.
People think privately with their own AI, share deliberately by tagging the space's @id, owners approve what
becomes the agreed state, and every PR (including AI-made ones) is checked against the decisions it implements.

Read before planning any milestone:
- `docs/hld.md` — the design. Source of truth for entities, API, deep dives, PR check and the demo slice.
- `docs/prd.md` — product requirements and principles.
- `docs/vision.md` — long-term direction; don't build beyond the HLD's MVP cut.

## Core rules (never break these)

1. **Models propose, deterministic code checks, people approve.** No model output ever writes agreed state.
   Every model output is parsed into a strict schema and validated (references exist, decisions exist,
   area is the proposer's to touch) before use. Nothing is approved automatically.
2. **Only the State steward writes agreed state.** One ordered lane per space; commit only if the proposal's
   `base_version` equals HEAD (compare-and-swap). If HEAD moved: re-check; no conflict → apply, conflict →
   back to the owner.
3. **Event sourcing.** Append-only `events` table (no UPDATE/DELETE, enforced in the DB). A StateVersion is a
   snapshot plus a parent pointer. Rewind = read an older version. Event envelope: id, space_id, type, actor,
   at, target (kind, id, revision), payload, caused_by, idempotency_key.
4. **Privacy enforced by the database.** Private sessions live in separate tables with row-level security
   tied to the owner; the agents' DB role cannot read them. Only text containing the @id leaves a session.
5. **Bounded context.** Every model call gets a fixed budget: compact current state + spine (decisions above,
   statements and constraints only, ~15% of budget) + top retrieved evidence + the question. Never full history.
6. **PR check is against linked decisions, not HEAD.** A PR names decisions (`Implements: D-014`), each link
   pinned to the revision at link time. Two checks in order:
   - *Still current* (plain code): revised since → stale; reopened → under review; abandoned → orphaned.
   - *Still matches* (model, evaluator-optimizer): findings must cite a real constraint and real diff lines;
     code drops invalid ones; an evaluator re-reads and keeps only confirmed findings.
   Results: matches → success; drift → failure naming decision, constraint, approver(s), lines;
   stale / under review / orphaned / not linked / unsure / error → **neutral (fail open)**.
7. **Identity comes from the auth token,** never the request body. Webhooks are verified and idempotent.

## Stack

FastAPI (Python 3.12) · Postgres 16 + pgvector (Docker) · Postgres-backed queue partitioned by space ·
plain code + Anthropic SDK behind a small LLM gateway (cheap model for routing, strong model for conflict
and PR analysis) · Next.js + React for the web app · GitHub App (Checks API) · Slack app (notifications).
Secrets come from `.env` (never commit it; keep `.env.example` current).

## Demo slice (what must work end to end)

Seeded: org Acme Pay; Yashwant (founder), Maya Chen (product scope owner), Arjun Rao (technical safety
owner, payments engineering), one more engineer. Space `@payments-redesign` at agreed state **v3**:
- v1: space created
- v2: D-012 — failed payments stay on a manual recovery path (Oct 17 15:30)
- v3: D-013 — checkout ships behind a rollout flag, keep the Oct 23 target (Oct 18 16:10)
Items (stored as text with seeded excerpts): Jira PAY-142, Notion "Payment retry policy v2", Slack #payments.

D-014 "Enable bounded automatic retries for transient payment failures", parent D-013, constraints:
- at most 3 automatic attempts within 24 hours
- one idempotency key per payment, reused on every attempt
- hard declines are never retried; they stay on the manual recovery path
- retries stay behind the checkout rollout flag

| # | Step | Screen |
|---|------|--------|
| 1 | Yashwant creates the space and links the three items | 01 |
| 2 | Private work with own AI; nothing appears in the space | 02 |
| 3 | Only the tagged text leaves: "@payments-redesign proposing: bounded automatic retries…" | 02 |
| 4 | D-014 shows as review pending with constraints and parent; Slack notified | 03 |
| 5 | Fixed two-stage review: product scope (Maya) then technical safety (Arjun); state stays v3 until both approve | 04 |
| 6 | v4 is the agreed state | 05 |
| 7 | Arjun's PR #284 `Implements: D-014` → check passes; @tenet answers "where are we / why / what changed" in PR comments | 06 |
| 8 | Coding agent's PR #291 `Implements: D-014` creates a new idempotency key per retry; tests pass; check **fails** naming D-014's constraint, Maya + Arjun, and the lines | 06b |
| 9 | Read-only rewind of the payment retry policy v2 → v4, step by step | 07 |

Stubbed for the demo: onboarding/domain verification (users seeded), item fetching, approving from Slack,
email, metering. Later (do not build): configurable/parallel stages, tree view, branches, child agents,
suggested PR links, callbacks and rechecks.

Figma file key `QZQSFRbIYZqE7hOGMsugqj`. Frame node IDs: 01 `16-5787`, 02 `16-5944`, 03 `16-5624`,
04 `16-6076`, 05 `16-6223`, 06 `5-153`, 06b `35-333`, 07 `16-6379`, Components `1-2`.

## Build order

One milestone per session. Start in plan mode; get the plan approved before writing code.
Commit when the milestone's tests pass.

1. **Scaffold** — repo layout (`backend/`, `web/`, `demo-repo/`), FastAPI app with `/health`, Docker Compose
   for Postgres + pgvector, migrations (Alembic), pytest against a real test database, `.env.example`.
2. **Schema + event log + seed** — all HLD entities; append-only events enforced by trigger; State steward
   commit with compare-and-swap; seed script to v3, with an option to seed through v4 (D-014 approved)
   for PR-check tests.
3. **GitHub App + PR check** — webhook (verified, idempotent) → parse `Implements:` → pin revisions → still
   current → still matches (analyzer + code validation + evaluator) → Checks API result; fail open.
   Test with recorded fixtures for PR #284 (passes) and PR #291 (drift).
4. **Proposals + two-stage review** — create, approve/reject per stage, pushbacks; steward commits on final
   approval; events for every step.
5. **Private sessions + tag extraction + Capture** — RLS-protected session tables; only tagged text becomes
   an event; Capture drafts statement, constraints and parents; conflict check against the spine.
6. **Ask + rewind** — "where are we / why / what changed" with sources under a fixed budget; read any
   StateVersion; decision history timeline.
7. **Slack notifications** — proposal created, your-turn-to-review, state updated.
8. **Web UI** — screens 01–07 from Figma.
9. **Demo repo + run-through** — `acme-pay/payments-service` with a payments module whose retry function
   reuses one idempotency key; scripted PRs #284 and #291; full demo rehearsal.

## Conventions

- Tests for every milestone; the steward's CAS, the append-only rule, privacy and the PR check outcomes
  must each have direct tests.
- Model calls go through the gateway only, with strict schemas; tests use recorded fixtures, never live calls.
- Decision keys look like `D-014`; revisions are integers starting at 1; state versions are per-space integers.
