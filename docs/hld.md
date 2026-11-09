# Tenet — High-Level Design

Oct 20, 2026 · @yashwant · Status: Draft v2 · Scope: MVP

## Overview

This document designs the MVP of Tenet: *for every AI-made change, why it was made, who approved it, and whether it still matches what was decided.* It follows a standard system design order (requirements, core entities, API, high-level design, deep dives) and builds the AI part from a few well-known agent patterns instead of one autonomous agent.

**The principle behind every choice:** language models propose, deterministic code checks what is valid, and people approve. No model ever writes the agreed state directly.

## Requirements

**Functional: users should be able to**

1. Create a space with a shared ID, add people, and pull in items by link: a Jira ticket, a PR, a doc, a Slack thread.
2. Work privately with an AI, sharing only what they tag with the space's @id.
3. Send a tagged update for review (a status update, a decision or a PR); the right owner approves it, creating a new version of the state.
4. Ask "where are we?" or "why?", and rewind to see how the state got here.
5. See every linked PR checked against the agreed state.

Out of scope for the MVP: configurable approval chains (the demo runs one fixed two-stage review), two-way sync with other tools, and agents that act without a person approving.

**Non-functional: the system should**

| Requirement | Target | Why it matters here |
| --- | --- | --- |
| Correct shared state | No lost or conflicting updates; every change traceable | The product is the record; one wrong state destroys trust |
| Privacy | Private sessions unreadable by other people and by agents | People only share honestly if private stays private |
| Auditability | Append-only history; any past version can be rebuilt | Rewind and "who approved this" depend on it |
| Bounded context | Every model call stays within a fixed token budget, however long the history | Cost and answer quality stay flat as spaces grow |
| Latency | Answers start within about 3 seconds; PR checks post within 60 seconds | Fast enough to use in the middle of a review |
| Scale | Modest at first (estimate below) | Avoids over-engineering early |

**Rough scale.** 1,000 teams × 10 people × about 50 tagged events a day is about 500,000 events a day, or roughly 6 writes a second on average. Write volume is tiny. The hard problems are keeping shared state correct and keeping model calls cheap and reliable, not throughput, which is why the deep dives focus on consistency, context and validation rather than sharding.

## Core entities

These are what the API exchanges and the database stores. The Git column is the mental model the whole design follows.

| Entity | What it holds | Git analogy |
| --- | --- | --- |
| Space | Shared ID, goal, members, owners per area | Repository |
| Area | A part of the product with one owner: the subtree of decisions under it, and the scope of a child master agent | A directory with a CODEOWNERS entry |
| Member | Person, role (admin, owner, member, viewer), areas they own | Collaborator |
| Item | A pulled-in link with a snapshot excerpt and a content hash | A file a commit points to |
| Session | One person's private AI conversation | Local working copy |
| Event | Append-only, typed record of anything that happened in a space, including pushbacks, callbacks and pivots | Reflog |
| Proposal | A tagged update awaiting review: type, content, evidence, base version | Pull request |
| Decision | An approved choice: statement, constraints (short must and must-not lines that work can be checked against), area, revision, status (active, under review, abandoned), proposer, approver, evidence, and parents (the decisions it builds on) | The change inside a commit |
| StateVersion | A snapshot of the agreed state, with a pointer to its parent | Commit |
| Branch | A line of exploration from a base version, later merged or abandoned | Branch |
| PRLink | A code PR, the decisions it implements (each pinned to the revision it was written against), and its check result | A linked commit in another repository |

PR-to-decision links are used from day one: the PR check depends on them. Decision parents are recorded in the MVP and used by conflict checks, but the tree view in the [vision doc](https://claude.ai/artifact/NFN18wu7HmhnbHzudq7cXj) comes later, without migrating anyone's history.

## API

REST over HTTPS for the apps, plus webhooks from GitHub and Slack. The caller's identity always comes from the auth token, never from the request body, so nobody can approve as someone else.

```
POST /spaces                       {name, goal}                 → Space
POST /spaces/{id}/members          {email, role, areas}
POST /spaces/{id}/items            {url}                        → Item

POST /sessions                     {spaceId}                    → Session
POST /sessions/{id}/messages       {text}                       → reply
     a message containing @space creates a Proposal; nothing else leaves the session

POST /spaces/{id}/proposals        {type, content, evidence[], baseVersion}
     type: status | decision | callback | revision | pivot
POST /proposals/{id}/approve       {note?}
POST /proposals/{id}/reject        {reason}
POST /proposals/{id}/pushbacks     {reason, evidence[]}         → Pushback
POST /pushbacks/{id}/resolve       {outcome, note}
POST /decisions/{id}/reaffirm      {note?}

GET  /spaces/{id}/state?version=   → StateVersion (default: HEAD)
GET  /spaces/{id}/history          → versions, branches, decisions, events
GET  /decisions/{id}?rev=          → Decision at a revision, with its events
POST /spaces/{id}/ask              {question, area?}            → answer + sources

POST /prs/{id}/links               {decisionIds[]}              → PRLink
POST /webhooks/github
POST /webhooks/slack
```

Every proposal carries the `baseVersion` it was written against, which lets the State steward catch a proposal written against stale state. PRs do not use it: a PR is pinned to the revisions of the decisions it implements, so it is checked only against what it claims to implement (see PR check below).

## High-level design

&#91;embedded content: Tenet architecture · 5 layers, 20 components\]

People use the web app, Slack, email and GitHub; services handle requests; agents interpret and check; only the State steward writes the agreed state, and private sessions stay in their own walled-off tables.

**How each requirement flows through it**

1. **Pull in and invite.** The web app calls the Spaces service. Connectors fetch each link, store a snapshot excerpt and hash as an Item, and index it for retrieval.
2. **Work privately.** Messages go to the Sessions service and its private tables. Only a message containing the @id leaves, as a tagged event.
3. **Propose and approve.** The master agent classifies the tagged input; Capture turns it into a structured proposal with its constraints and suggested parents; Conflict check compares it with the area's decisions and the decisions above it. The owner gets it in Slack or email. On approval, the Space queue passes it to the State steward, which commits a new version, and the Notifier tells the people affected.
4. **Ask and rewind.** The master agent retrieves the current state plus the most relevant events and evidence, and answers with sources. Rewind reads any earlier StateVersion.
5. **PR check.** A GitHub webhook reaches Connectors; the PR analyzer reads the decisions the PR says it implements, at the revisions it was written against, plus the constraints above them, and posts the intent card and check result (see PR check below).

**Agent design.** Instead of one autonomous agent, the agent layer combines three well-known patterns, each used only where it earns its cost.

| Pattern | Where it is used | Why this pattern |
| --- | --- | --- |
| Routing | The master agent classifies each tagged input as a status update, decision, callback, pivot, question or PR | Each type gets a simpler, specialized prompt, and a cheaper model can do the classifying |
| Orchestrator-workers | For "where are we?" and PR checks, the master agent picks which subagents and sources to consult, then combines their results | The steps depend on the question, so they cannot be fixed in advance |
| Evaluator-optimizer | Conflict check and the PR analyzer review drafts before anything reaches a person | There is a clear standard to check against, the agreed state, so a second pass cuts false alarms |

Subagents never write state. They return structured proposals and findings; the State steward and the owner decide what becomes true.

## Deep dives

Each deep dive answers one non-functional requirement.

**1. Versioned state as event sourcing (the Git model).** Every change is an event in an append-only log. A StateVersion is a commit: a snapshot plus a pointer to its parent. Branches start from a base version; merging an approved proposal creates the next version on main. Rewind means reading an older version, and a snapshot every N events keeps that fast. *Why:* the audit trail and rewind come for free. Updating rows in place would be simpler, but it would throw away the history that is the product.

**2. One writer per space.** All approved changes for a space pass through one ordered lane of the queue, partitioned by space ID, to the State steward. The steward commits only if the proposal's base version still matches HEAD, a compare-and-swap. If HEAD has moved, it re-checks the proposal: no conflict means it is applied; a conflict sends it back to the owner. *Why:* write volume per space is tiny, so serializing it costs nothing and removes race conditions without distributed locks.

**3. Bounded context, no bloat.** Each model call gets a fixed budget: the compact current state (decisions and constraints), the top retrieved events and evidence from the vector index filtered to that space, and the question. Never the full history. Older discussion is compacted into summaries; decisions are pinned and never summarized away. *Why:* cost and accuracy stay flat however large a space grows.

**4. Privacy enforced by the database.** Private sessions live in separate tables with row-level security tied to the session's owner, and the agents' database role has no access to them. The Sessions service extracts only the tagged text and emits it as an event. *Why:* privacy becomes a guarantee the system enforces, not a promise in a policy.

**5. Trustworthy model output.** Every model output must match a strict schema and pass deterministic checks (references exist, decisions exist, the area is the proposer's to touch) before it is used. Evaluators review drafts, owners approve, and nothing is ever approved automatically. Webhooks carry idempotency keys, and failed jobs retry from the queue. *Why:* models will sometimes be wrong; the design makes sure a wrong output is caught or held, never silently committed.

**6. PR checks fail open.** If the check service is down or unsure, the GitHub check reports neutral rather than failing. *Why:* a tool that randomly blocks merges gets uninstalled.

**7. Scaling later.** Services are stateless and scale out. One Postgres instance with pgvector is enough for the MVP; partition by space ID when needed. The LLM gateway sends simple tasks such as classification to cheaper models and hard ones such as conflict and PR analysis to stronger models.

## PR check: against the decisions a PR implements

The check asks one question: does this PR still match the decisions it says it implements? It no longer compares the PR's base version with HEAD. Most changes to HEAD have nothing to do with a given PR, so flagging every PR whenever any decision moves would teach people to ignore the check.

**Constraints make decisions checkable.** When a decision is captured, Capture drafts its constraints as short must and must-not lines ("retries go through the retry queue", "never call the payment provider directly on retry"), and the owner approves them together with the decision. A decision with no constraints can still be linked, but the check can then only report whether it is still current.

**Linking a PR to decisions.** A PR names its decisions in its description, for example `Implements: D-7, D-12`. A coding agent started from a private session gets these IDs from the session's context and writes them in for the author. If a PR names none, the analyzer suggests up to three likely decisions and the author confirms with one click (later; the MVP needs the IDs written in). Each link is pinned to the decision's revision at the moment of linking.

**What the check reads.** For each linked decision: its statement and constraints at the pinned revision, its current revision and status, and the constraints of every decision above it (the spine, described under Master agents). Plus the PR's diff and description. Never the full history, so the token budget stays fixed.

**Two checks, in order.**

1. **Still current** (plain code, no model). Compare each link's pinned revision and status with the decision as it is now. Revised since: stale. Reopened: under review. Abandoned in a pivot: orphaned.
2. **Still matches** (model, evaluator-optimizer). The analyzer drafts findings, each naming a decision, a constraint, the lines in the diff and a one-line explanation. Plain code drops any finding that cites a constraint that does not exist or lines that are not in the diff. An evaluator then re-reads each remaining finding against the diff and keeps only those it confirms.

| Result | When | GitHub check |
| --- | --- | --- |
| Matches | Linked decisions are current and no finding is confirmed | Success |
| Drift | A confirmed finding contradicts a constraint | Failure, naming the decision, the constraint, its approver and the lines |
| Stale | A linked decision was revised after the PR linked it | Neutral, showing what changed |
| Under review or orphaned | A linked decision is reopened or abandoned | Neutral, naming the owner to ask |
| Not linked | The PR names no decisions | Neutral, asking for links |
| Unsure or down | Low confidence, timeout or error | Neutral (fails open) |

Drift fails the check, but it only blocks merging if the team makes the check required in branch protection.

**Rechecks.** When a linked decision is revised, reopened or abandoned, every open PR linked to it is rechecked and its result updated. Following links finds the affected work directly, which is what makes callbacks cheap.

*Why:* every flag points to one decision, one constraint and one approver, so a reviewer can act on it or argue with it. A check against HEAD could only say that something, somewhere, had changed.

## Decision lifecycle: pushback, callback, pivot

Every change to a decision is an event, and every change to the agreed state still goes through a proposal, the area owner's approval and the State steward. Pushbacks are the one exception: they attach to an open proposal and change nothing until the owner acts.

**One event envelope.** Every event carries `id`, `spaceId`, `type`, `actor`, `at`, `target` (kind, id, revision), `payload`, `causedBy` (the event that led to it) and an idempotency key. `causedBy` is what lets rewind tell the story in order: a pivot points to the callback that opened the question, which points to the pushback that started it.

```
proposal.created     proposal.approved     proposal.rejected
pushback.raised      pushback.resolved     {accepted | overruled | withdrawn, note}
decision.created     decision.reopened     decision.reaffirmed
decision.revised     {fromRev, toRev}
decision.abandoned   {reason, replacedBy[]}
decision.flagged     {conflictsWith[]}
pr.linked            pr.checked
```

| Event | Who starts it | Who resolves it | Effect on the decision | Effect on work below |
| --- | --- | --- | --- | --- |
| Pushback | Anyone in the space, on an open proposal | The area owner: accepted (proposer revises), overruled (one-line reason) or withdrawn | None until approval; then the pushback and its outcome stay attached to the decision | None |
| Callback | Anyone, as a callback proposal on an approved decision; the owner's approval reopens it | The owner: reaffirm (same revision) or approve a revision (next revision) | Status becomes under review, but it still stands until replaced | Linked PRs show under review; on revision, child decisions and linked PRs are rechecked |
| Pivot | Anyone, as a pivot proposal naming the decisions to abandon and what replaces them | The owner of the highest decision being abandoned | Abandoned decisions keep their content, the reason they lost and a pointer to what replaced them | Child decisions are flagged to their owners; linked PRs become orphaned |

**Callback or new decision?** This answers the open question in the vision doc. A callback keeps the decision's ID and answers the same question again, so the new answer is its next revision and everything linked to it is rechecked. A new decision answers a different question, even if it builds on the old one, so it gets a new ID with the old one as a parent. A pivot replaces decisions whose question no longer matters: they are abandoned, not revised. The owner's rule of thumb: same question, new answer → revise; new question → new decision; old question no longer matters → pivot.

**Pushback stays light.** A pushback can only target an open proposal; challenging something already approved is a callback. Approving with open pushbacks is still one tap plus one line: the open pushbacks are recorded as overruled with that line.

*Why:* the journey is the product. Keeping these as events rather than fields on a decision means rewind can replay the argument in order, and no outcome overwrites how it was reached.

## Master agents and child agents

A master agent is not a long-running process. It is a scope, a prompt and a retrieval filter over the same event log and state. The product's master agent covers the whole space; a child master agent covers one area, a subtree of the decision tree with one owner. Children can have children of their own, mirroring the tree.

**What a child draws on.** A child sees its own area in detail, everything above it as constraints, and nothing sideways.

| Context | Included | How much |
| --- | --- | --- |
| Its own area: active decisions, open proposals, recent events, evidence | Always | Most of the budget, ranked by relevance to the question |
| The spine: every decision above the area, back to the root | Always, pinned | Statements and constraints only, no discussion, capped at a fixed share of the budget (about 15%) |
| Sibling areas | Only for questions that cross areas | Through the parent, never directly |
| The parent's discussion history | Never directly | The child asks the parent |
| Private sessions | Never | Enforced by the database |

With multiple parents, the spine is the union of every path to the root, deduplicated. If it outgrows its share, the root and the nearest parents are always kept and the rest are ranked by relevance. A question that crosses areas goes to the lowest agent that covers both, which consults the children (orchestrator-workers) and combines their answers.

**When a child's context conflicts with a decision above it.** A decision above wins until it is explicitly changed. The child agent never resolves a conflict; it surfaces both sources and routes the conflict to people.

1. **A new proposal in the area contradicts the spine.** Conflict check runs against the spine as well as the area. The proposal is held as blocked by that decision, and the proposer chooses: revise the proposal to fit, or turn it into a callback on the decision above, which goes to that decision's owner. If the decision above is revised, the held proposal is checked again; if it is reaffirmed, the proposal goes back to the proposer.
2. **A decision above changes, and an approved child decision now conflicts.** The revision or pivot triggers a recheck of the decisions below it. Each conflicting child decision gets a `decision.flagged` event and its owner is notified. The child decision stays active, because nothing fades, but the agent answers from the decision above and points out the conflict until the child owner revises it or calls back the parent.
3. **Two parents of one decision conflict with each other.** The child cannot choose. The conflict goes to both parents' owners, and to the owner of their nearest shared ancestor if they disagree.

When answering, an agent says which level each claim comes from ("payments decided X; this follows from the product decision Y, approved by the product owner"), so a reader can see when an area and the level above it disagree.

**MVP cut.** The MVP runs one master agent per space. Areas exist as owners and as the filter that builds each call's context, so the spine and the conflict rules above work from day one. Separate child agents, with their own prompts and escalation between them, come later; adding them changes how context is routed, not what is stored.

## Demo slice and MVP cut

The demo follows one decision, D-014, from a private thought through a two-stage review to two PRs: one that matches it and one AI-made PR that breaks it. Each step matches a frame in the Figma mocks (01–07, plus 06b for drift). Everything shown runs for real; anything not shown is out of scope for this week.

**Setup (seeded).** Acme Pay with four members: Yashwant (founder), Maya Chen (product scope owner), Arjun Rao (technical safety owner, payments engineering) and one more engineer. The space `@payments-redesign` is at agreed state v3: D-012 (failed payments stay on a manual recovery path, v2) and D-013 (checkout ships behind a rollout flag, Oct 23 target, v3). Linked items, stored as text: Jira PAY-142, Notion Payment retry policy v2, Slack #payments. The GitHub test repo `acme-pay/payments-service` has a payments module with a retry function.

| # | Step | What the viewer sees | Components | Screen |
| --- | --- | --- | --- | --- |
| 1 | Create the space | Yashwant creates `@payments-redesign` and links the Jira ticket, the Notion policy and the Slack channel | Web app, Spaces service | 01 |
| 2 | Private work | Yashwant works through automatic retries with their own AI; nothing appears in the space | Web app, Sessions service | 02 |
| 3 | Tag the @id | Only the tagged text leaves: "@payments-redesign proposing: bounded automatic retries for transient payment failures" | Sessions service emits the tagged text | 02 |
| 4 | Proposal | D-014 shows as review pending: up to 3 attempts in 24 hours, one idempotency key per payment, hard declines stay manual, parent D-013; Slack is notified | Master agent (routing), Capture, Conflict check against the spine, Notifier | 03 |
| 5 | Ordered review | Stage 1, product scope: Maya approves. Stage 2, technical safety: Arjun approves. State stays v3 until both have approved | Two-stage review, Space queue, State steward | 04 |
| 6 | Shared agreement | v4 is the agreed state, with D-014's constraints and who approved each stage | State steward, Notifier | 05 |
| 7 | Matching PR | Arjun's PR #284 says Implements: D-014; the check passes, and @tenet answers "where are we?", "why 3 retries?" and "what changed?" in PR comments with sources | GitHub App webhook, PRLink, PR analyzer, Ask | 06 |
| 8 | Drift flagged | A coding agent opens PR #291, also Implements: D-014. It makes a new idempotency key on every retry; the code is clean and tests pass. Within a minute the check fails, naming D-014's constraint, its approvers and the lines | PR analyzer, evaluator, Checks API | 06b |
| 9 | Rewind | Read-only history of the payment retry policy, v2 to v4, step by step, with what was agreed at each moment | Event log, StateVersion reads | 07 |
| 10 | Callback and recheck | Arjun reopens D-014, revises it, and open PRs are rechecked | Callback, revision, recheck | After the demo |

**Build cut.**

- Built for the demo: space creation, private sessions, tag extraction, Capture with constraints and parents, a fixed two-stage review (product scope, then technical safety) approved in the web app, Slack notifications, the event log and State steward, the GitHub App with the Checks API, both PR checks (still current, still matches), @tenet answers in PR comments, and a read-only rewind of one decision's history.
- MVP, stubbed for the demo: onboarding and domain verification (users are seeded), item fetching (links stored as text with seeded excerpts), approving from Slack, email notifications, metering and spending caps.
- Later: configurable and parallel stages, the tree view, branches, separate child agents, suggested PR links, callbacks and rechecks, deeper two-way integrations.

**What makes it land.** PR #284 and PR #291 look alike at a glance: same decision linked, clean code, passing tests. Only the decision record knows that #291 breaks D-014, because a new idempotency key on each retry can charge a customer twice. That is the line against Entire: Entire can show what the agent did; Tenet shows that what it did breaks what the team agreed, and who agreed it.

## Onboarding and access (AAA)

The demo targets about 100 users, roughly 10 startups of 10 people, on company accounts only. Individuals join a waitlist until the team product is proven.

**Onboarding flow**

1. Choose company or individual; individuals join the waitlist for now.
2. The first company admin verifies the domain with a DNS record or a Google Workspace or Microsoft admin sign-in.
3. The admin invites colleagues from verified domains; each confirms their own inbox with a magic link or one-time code.
4. Optionally, the admin invites guests from other domains (outside counsel, agencies, contractors), limited to specific spaces and marked as external.
5. Only verified members and approved guests can start private AI chats or join spaces.

**Authentication (who you are).** Work-account sign-in (Google or Microsoft) through a managed provider, which brings multi-factor login. Free email providers are blocked for company accounts, and a company can register several domains. Slack and GitHub identities link to the same account by work email; incoming webhooks are verified with Slack's signing secret and GitHub App tokens.

**Authorization (what you can do).** Roles per space (admin, owner, member, viewer, guest) plus ownership per area. Every row carries an organization ID enforced by row-level security; private sessions are readable only by their owner; agents run under a limited role; connectors act with each person's own permissions. Access ends when an admin removes someone, and later automatically through the company's login system.

**Accounting (what happened, what it cost).** The event log records every approval, rejection, permission change and sign-in. Model tokens and PR checks are metered per organization, with a spending cap per company.

**Later, for individual plans:** solo use starts immediately with a short trial or limited free tier; referral discounts apply only after the referred person verifies their email and becomes active.

## Technology choices and trade-offs

The stack favours one database and plain code over specialized infrastructure, because the MVP's risk is correctness and speed of building, not load.

| Component | Choice | Why |
| --- | --- | --- |
| Web app | React and Next.js | Fast to build; widely known |
| Backend | FastAPI | Python suits the agent and model code |
| Database | Postgres with pgvector | One store for events, state, permissions and retrieval; row-level security for privacy |
| Queue | Postgres-backed or managed queue, partitioned by space | Ordering per space without new infrastructure |
| Agents | Plain code with a model SDK, behind an LLM gateway | Simple patterns need no heavy framework; providers can be switched |
| Auth | Managed auth with work email | Membership maps to the same email across tools |

| Choice | Gained | Given up |
| --- | --- | --- |
| Event sourcing over updating rows | Full history, rewind, audit | More complex reads; needs snapshots |
| One writer per space | Simple, correct ordering | Throughput per space is limited, which is fine at expected volume |
| Fixed patterns over a fully autonomous agent | Predictable, testable, cheaper | Less flexible on unusual requests |
| People approve every decision | Trust and accountability | Slower than automatic updates |
| Fail-open PR checks | Never blocks merges by mistake | A stale PR can slip through during an outage |
| PRs checked against their linked decisions, not HEAD | Few false alarms; every flag names one decision, one constraint and its approver | An unlinked PR gets no conformance check, so linking has to be nearly effortless |

## Planned extension: staged handoffs

A space can optionally pass work through ordered stages, for example founder's office, then product and legal, then engineering leads, with each stage clearing the work before the next begins. The default stays simple: the owner of an area approves. The demo runs one fixed version of this, product scope then technical safety; the rest of this section stays planned.

- **Stages on one @id.** A space holds an ordered list of stages, each with its people, approvers and approval rule (any or all). Stages can run in parallel, such as product and legal together.
- **Cleared versions move forward.** When a stage approves, that version is marked cleared and the next stage starts from it, with every decision and its reasons attached. In Git terms, it is a release promoted through environments, each with its own reviewers.
- **Changes flow back to their owner.** A later stage that needs to change an earlier decision sends a proposal back to the stage that owns it, rather than changing it in place.
- **Small design change.** A stage field on Proposal and StateVersion, an approval rule per stage checked by the State steward, and the Notifier telling the next stage when it is their turn.

*Why it matters:* each handoff today is a meeting or a slide deck, and the reasons get lost. Here, context travels with the work. It fits larger and regulated startups best; smaller teams that iterate in parallel can leave it off.
