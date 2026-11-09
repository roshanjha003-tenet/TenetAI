---
number: 291
branch: agent/retry-transient-failures
author: Coding agent (on behalf of Priya Nair)
title: Retry transient payment failures automatically
---
Adds automatic retries for transient payment failures, capped at 3 attempts within 24 hours.
Hard declines still go to the manual recovery queue. Retries only run with the
`checkout_rollout` flag on. All tests pass.

Implements: D-014
