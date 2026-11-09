#!/usr/bin/env bash
# Publishes the demo repo to GitHub: service/ as main, then one branch and PR per prs/*/,
# each PR's body taken from its PR.md (so "Implements: D-014" reaches the webhook).
#   usage: publish.sh [owner/name]   (default yyadav1120/payments-service, created private)
# GitHub numbers the PRs itself (#1, #2, …), not #284 / #291; see docs/demo.md.
set -euo pipefail
repo="${1:-yyadav1120/payments-service}"
gh="${GH:-gh}"
command -v "$gh" >/dev/null || gh="/mnt/c/Program Files/GitHub CLI/gh.exe"
here="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git_() {
  git -c user.name="${GIT_AUTHOR_NAME:-Tenet demo}" -c user.email="${GIT_AUTHOR_EMAIL:-demo@example.test}" \
    -c credential.helper= -c "credential.helper=!'$gh' auth git-credential" "$@"
}
front() { sed -n "s/^$1: //p" "$2"; }
body() { awk 'f>=2; /^---$/ {f++}' "$1"; }

"$gh" repo view "$repo" >/dev/null 2>&1 || "$gh" repo create "$repo" --private \
  --description "Demo payments service checked by Tenet against @payments-redesign"

cp -r "$here/service" "$work/repo"
cd "$work/repo"
git init -q -b main
git add -A
git_ commit -qm "Payments service: failed payments go to manual recovery"
git_ push -q --force "https://github.com/$repo.git" main

for pr in "$here"/prs/*/; do
  branch="$(front branch "$pr/PR.md")"
  title="$(front title "$pr/PR.md")"
  git checkout -q main
  git checkout -q -B "$branch"
  rsync -a --exclude PR.md "$pr" ./
  git add -A
  git_ commit -qm "$title"
  git_ push -q --force "https://github.com/$repo.git" "$branch"
  if [ -z "$("$gh" pr list -R "$repo" --head "$branch" --json number -q '.[].number')" ]; then
    body "$pr/PR.md" > "$work/body.md"
    file="$work/body.md"
    [[ "$gh" == *.exe ]] && file="$(wslpath -w "$file")"  # Windows gh needs a Windows path
    "$gh" pr create -R "$repo" --base main --head "$branch" --title "$title" --body-file "$file"
  fi
done
"$gh" pr list -R "$repo"
