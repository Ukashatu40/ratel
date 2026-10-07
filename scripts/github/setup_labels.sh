#!/usr/bin/env bash
# Create or update labels from .github/labels.yml. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"

python3 - <<'PY' | while IFS=$'\t' read -r name color desc; do
import yaml
for l in yaml.safe_load(open(".github/labels.yml")):
    print(f"{l['name']}\t{l['color']}\t{l['description']}")
PY
  gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" --force
done
echo "Labels applied to $REPO"
