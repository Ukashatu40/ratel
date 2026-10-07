#!/usr/bin/env bash
# Create or update the main-branch ruleset from .github/rulesets/main-protection.json.
#
# BEFORE running: push the initial commit to main (a ruleset blocks direct pushes), and make sure
# the workflows have run once so the required status checks exist.
# Rulesets on private repositories need a paid GitHub plan. If this fails with a plan error, use
# docs/GITHUB_SETUP.md "Fallback: classic branch protection".
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
FILE=".github/rulesets/main-protection.json"
NAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$FILE")"

EXISTING="$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name==\"$NAME\") | .id" || true)"
if [ -n "$EXISTING" ]; then
  gh api -X PUT "repos/$REPO/rulesets/$EXISTING" --input "$FILE" >/dev/null
  echo "Updated ruleset $NAME ($EXISTING) on $REPO"
else
  gh api -X POST "repos/$REPO/rulesets" --input "$FILE" >/dev/null
  echo "Created ruleset $NAME on $REPO"
fi
