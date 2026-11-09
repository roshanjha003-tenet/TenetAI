# Tenet AI — Product Requirements Document

Oct 17, 2026 · @yashwant · Status: Draft v1

## Pitch

**Git for team decisions:** branch, decide, merge, and rewind to see how your team got here, across Slack, Jira, Docs and GitHub.

## Problem

Teams work across Slack, Jira, Docs, Notion and GitHub, each person with their own AI. Decisions are made in one tool, written down in another and implemented in a third, so nobody holds the current agreed state or how the team reached it.

## How it works

1. **Pull in:** Create a shared space for a piece of work, with an ID, and pull in what matters: the Jira ticket, the PRs, the Notion or Google doc, the Slack thread.
2. **Add people:** Invite whoever is involved: PMs, engineers, founder's office.
3. **Work privately:** Each person works with their own AI in their own space. Nothing is shared until they tag the project's @id, so the master agent only receives what people intentionally share.
4. **Propose and review:** With a tagged update, the person picks one action: update the status, propose a decision, or send a PR or proposal doc for review. It goes to the owner of that area for a one-tap approval, the master agent tracks it, and once approved it updates the shared state everyone works from.
5. **Ask and rewind:** Anyone can ask "where are we?" and get the current state, or rewind to see how a decision came about, step by step.

A master agent and subagents track the work behind the scenes; users just ask and get an answer.

## Design principles

Two principles decide every design choice. If a feature makes either one worse, it does not ship.

**1. Easy to consume.** Most people only need to know where things stand, so the product must hand them answers, not transcripts.

- **One glance first:** anyone sees the current state in a few lines; detail and history open only when they ask.
- **It comes to them:** approvals, updates and status arrive in Slack, email and the PR, so most people rarely open the app.
- **Only what changed for you:** each person sees what changed since they last looked, and only owners get asked to act.
- **Every claim links to its source:** the ticket, PR, doc or thread behind it is one click away.

**2. State that persists across conversations.** Every AI conversation starts from what the team has already agreed, not from an empty chat or an old transcript.

- **Shared memory:** each person's AI and the master agent read the same state, so everyone's AI knows what the team decided.
- **Nothing fades:** approved decisions stay in place until explicitly replaced; they are never lost as chats grow or scroll away.
- **Governed and versioned:** Notion and memory-layer startups are building shared AI memory too; ours differs because owners approve what enters it and every version can be rewound.

## The decision tree

| Idea | In the decision tree |
| --- | --- |
| Shared ID for a piece of work | The repository |
| Items pulled from Jira, GitHub, Docs, Notion, Slack | The evidence each commit points to |
| People working privately | Branches |
| Exploring directions before pivoting | Parallel branches; the team merges the one it agrees on |
| A decision approved by the owner of its area | A reviewed merge |
| The current state | HEAD |
| Backtracking to how you got here | Walking back through the log to any earlier commit |

Rejected branches are kept, so the team can always see what was considered and why it was not chosen.

## MVP

- A small web or desktop app for the shared space: pull items in by link, add people by work email, private AI sessions, decisions, status and rewind.
- Approvals and status updates go through Slack and email, so people never have to open the app for a quick approve or "what changed".
- Approval rule: the owner of an area approves, then everyone the decision affects is notified.
- A GitHub check flags PRs linked to a decision that has since changed.

**Later:** multi-step approval chains (engineer, then tech lead, then PM) and deeper two-way integrations.

## What makes it different

Notion can already link Jira tickets and PRs into a page. It cannot:

- keep a versioned record of what was agreed
- route decisions to the right owners
- let you rewind how you got here
- check the code against what was decided

**Positioning.** Shared agent memory where people choose what to share, owners review the direction, and everyone sees a clean current state, without bloating anyone's context.

**Why deliberate sharing matters.** Notion's open-source Lore captures agent memory automatically. In one internal Notion team's vault, 15–20% of memories were likely duplicates, 8–12% were information agents could infer on their own, and about 13% had no value; Notion's conclusion was that memory quality matters. Deliberate tagging and owner review keep the shared state clean by design.

## Moat

The differentiation above can be copied; what builds up over time cannot.

- **Approved history:** every month of use adds to a record of what was decided, by whom and why, which a team loses if it leaves.
- **In the merge path:** once the PR check is a required step before merging, removing it means giving up a safety check.
- **Neutral across tools:** Notion sees Notion and Slack sees Slack; connecting all of them is structurally hard for any one of them.
- **Focus:** Lore was a 20% project at Notion; this is the whole company, so it can move fast and pivot quickly as demand grows.
