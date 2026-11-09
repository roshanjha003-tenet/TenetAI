---
number: 284
branch: arjun/bounded-retries
author: Arjun Rao
title: Bounded automatic retries for transient payment failures
---
Retries transient processor failures automatically: at most 3 attempts within 24 hours, each
reusing the payment's idempotency key. Hard declines stay on the manual recovery queue, and the
whole path stays behind the `checkout_rollout` flag.

Implements: D-014
