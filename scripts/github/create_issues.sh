#!/usr/bin/env bash
# Create GitHub issues from docs/issues-week2/*.md.
# Each file: first line "# Title", second non-empty line "Labels: a, b, c", the rest is the body.
# Owners are never assigned here. Run once. Re-running creates duplicates.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"

for f in docs/issues-week2/W2-*.md; do
  title="$(sed -n '1s/^# //p' "$f")"
  labels="$(grep -m1 '^Labels:' "$f" | sed 's/^Labels: *//; s/ *, */,/g')"
  body="$(mktemp)"
  grep -v '^# ' "$f" | grep -v '^Labels:' > "$body"
  gh issue create --repo "$REPO" --title "$title" --label "$labels" --body-file "$body"
  rm -f "$body"
done
