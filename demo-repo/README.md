# demo-repo

Source for the demo GitHub repo `acme-pay/payments-service`: a payments module whose retry function
reuses one idempotency key, plus scripted PRs #284 (matches D-014) and #291 (drifts).

- `scripts/make-diffs.sh` rebuilds the PR diffs used as test fixtures, running each PR's tests.
- `scripts/publish.sh [owner/name]` pushes it to a private GitHub repo and opens the PRs (see `docs/demo.md`).
