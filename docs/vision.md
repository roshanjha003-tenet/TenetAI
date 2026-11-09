# Tenet — Product Vision & Philosophy

Oct 21, 2026 · @yashwant

*This doc describes the long-term direction. The [PRD](https://claude.ai/artifact/EYbsUMb1ugBNvTH9HKQXqn) and [HLD](https://claude.ai/artifact/BSiwBUpJX4TyX6DquGVrFy) cover the MVP, which is built to grow into it.*

## Why this exists

Teams lose the why behind their work. Decisions are made in Slack threads, meetings and design reviews, written down in docs that go stale, and then built by people and increasingly by AI agents.

By the time a PR or feature lands, the reasoning behind it, the pushbacks, the reversed calls and the pivots are scattered or gone. Nobody holds the current agreed state or how the group got there.

Personal AI makes this worse. Much of the real thinking now happens in private AI sessions that nobody else ever sees. Tenet gives each project one place where that thinking, once shared, becomes the agreed record that everyone and every agent works from.

## Philosophy

Six beliefs shape every product decision. If a feature breaks one, it does not ship.

- **Think privately, share deliberately.** Everyone works with their own AI, in silo. Only what a person chooses to tag to the project's @id reaches the master agent.
- **Owners decide what becomes agreed.** A shared update is a proposal until the owner of that area approves it.
- **The journey matters, not only the outcome.** Pushbacks, callbacks, pivots and rejected options stay in the record, because they explain why the final answer is right.
- **Answers, not transcripts.** People ask the master agent where things stand and why, instead of reading docs and threads.
- **Nothing fades.** An approved decision stands until it is explicitly replaced, and every earlier state can be revisited.
- **Work is checked against what was decided.** PRs and features, including AI-made ones, are compared with the decisions above them.

## The decision tree

Decisions start at a root, such as the founder's direction, and branch down through product and design decisions to leaves: the PRs and features that implement them. Anyone can follow a leaf back up to see which decisions it rests on and who approved each one.

&#91;embedded content: decision tree · root to leaves\]

The tree records how each decision changed, not only where it ended up:

- **Pushback:** someone challenges a proposal; the objection and how it was resolved stay attached to the decision.
- **Callback:** an approved decision is reopened; the earlier version stays in history, and work below it can be rechecked.
- **Pivot:** the group abandons a direction; that branch is kept with the reason it lost.

Because every leaf hangs from approved decisions, a PR or feature that no longer matches them can be caught automatically.

## The master agents

Tribal knowledge lives in the master agents instead of in people's heads. Each product has a master agent, and each area below it has a child master agent of its own, mirroring the decision tree. Together they hold everything the group shared on the way to every PR and feature: design discussions, pushbacks, callbacks, pivots and approvals.

Anyone picking up work talks to the master agent for that product or area and gets up to speed quickly, instead of tracking down the people who were there.

It replaces the Google Doc as the place people go for context. Instead of reading a stale spec, people ask it directly:

- "Where are we on this?"
- "Why did we choose this approach over the alternative?"
- "What was proposed and rejected, and who pushed back?"
- "I'm new to this project; what do I need to know?"

Two limits keep it trustworthy. It only learns what people deliberately share, so its context stays clean. And it does not decide anything; owners do. It keeps the record and answers from it.

## Use cases

Tenet applies anywhere a group decides something that others later build on, not only code.

| Situation | Today | With Tenet |
| --- | --- | --- |
| Engineering design discussion | Options debated in a meeting or thread; the doc records only the winner | The chosen design, the rejected options and the pushbacks are all in the tree |
| Product decision | Decided in Slack, written up later, if at all | The decision is approved by its owner and becomes the state everyone builds on |
| Founder discussion | Direction lives in the founder's head or a slide deck | Direction becomes a root decision the rest of the work hangs from |
| AI-made PR | Reviewer can't tell whether it matches what was agreed | The PR is checked against the decisions above it, and drift is flagged |
| New person joins a project | Reads old docs, asks around, gets partial answers | Asks the master agent how the project got here |

## What it is not

These boundaries keep Tenet from drifting into products that already exist.

- **Not a shared chat room.** People think privately with their own AI; what is shared is the decision record, not the conversation.
- **Not automatic memory capture.** Nothing enters the record unless someone shares it on purpose and an owner approves it.
- **Not a log of what agents did.** Tools such as [Entire](https://techcrunch.com/2026/02/10/former-github-ceo-raises-record-60m-dev-tool-seed-round-at-300m-valuation/) record agent sessions alongside commits. Tenet records what the humans decided and how they got there.
- **Not an approval-workflow tool.** Getting an idea across to the team is instant: tag the @id and everyone on the project sees it and can respond. Approval never slows sharing; it only marks which ideas become the agreed record, and it is one tap by the owner, not a process.
- **Not only for code.** PRs are one kind of leaf; product calls and founder direction belong in the tree too.

## Open questions

- [ ] Strict tree or not? Decided: not strict. One PR often implements several decisions, and one decision shapes several features, so the record allows multiple parents while still being shown as a tree.
- [ ] How effortless can sharing be? Parked for later. Every decision log dies when people stop updating it; tagging the @id has to feel lighter than writing a doc.
- [ ] When is a change a callback versus a new decision? Reopening an approved decision and replacing it need clear, different rules.
- [ ] Which teams first? Pick the group where a missed decision is most costly and test the tree with them.
- [ ] What is the name? "Tenet AI" and TenetX already exist in AI decision auditing.
