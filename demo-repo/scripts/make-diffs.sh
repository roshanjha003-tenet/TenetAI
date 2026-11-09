#!/usr/bin/env bash
# Builds each scripted PR on top of service/ and writes its unified diff to
# backend/tests/fixtures/github/pr_<number>.diff, running the PR's tests on the way.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="$here/../backend/tests/fixtures/github"
mkdir -p "$out"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cp -r "$here/service" "$work/repo"
cd "$work/repo"
git init -q -b main
git add -A
git -c user.name=demo -c user.email=demo@example.test commit -qm "base"
echo "== base"; uv run --quiet pytest -q 2>&1 | tail -1

for pr in "$here"/prs/*/; do
  number="$(sed -n 's/^number: //p' "$pr/PR.md")"
  git checkout -q main
  git checkout -q -B "pr-$number"
  rsync -a --exclude PR.md "$pr" ./
  echo "== PR #$number"; uv run --quiet pytest -q 2>&1 | tail -1
  git add -A
  git diff --cached main > "$out/pr_$number.diff"
  git -c user.name=demo -c user.email=demo@example.test commit -qm "PR $number"
done
ls -l "$out"
