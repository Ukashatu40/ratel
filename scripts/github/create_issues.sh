#!/usr/bin/env bash
# Create GitHub issues from docs/issues-week2/*.md.
# Each file: first line "# Title", second non-empty line "Labels: a, b, c", the rest is the body.
# The assignee is the login in "**Owner:** @login" (none while the owner is TODO). Run once.
# Re-running creates duplicates.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"

for f in docs/issues-week2/W2-*.md; do
  title="$(sed -n '1s/^# //p' "$f")"
  labels="$(grep -m1 '^Labels:' "$f" | sed 's/^Labels: *//; s/ *, */,/g')"
  assignee="$(grep -m1 -o '\*\*Owner:\*\* @[A-Za-z0-9-]*' "$f" | sed 's/.*@//' || true)"
  body="$(mktemp)"
  grep -v '^# ' "$f" | grep -v '^Labels:' > "$body"
  args=(--repo "$REPO" --title "$title" --label "$labels" --body-file "$body")
  if [ -n "$assignee" ]; then
    args+=(--assignee "$assignee")
  fi
  gh issue create "${args[@]}"
  rm -f "$body"
done
