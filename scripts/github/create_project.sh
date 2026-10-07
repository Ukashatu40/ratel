#!/usr/bin/env bash
# Create the "RatelPlus Subscriber Platform" GitHub Project and its custom fields.
#
# Needs the `project` token scope:  gh auth refresh -s project
# Usage: create_project.sh <owner>      (user or organization login)
#
# Limits of the gh CLI that this script does NOT work around (do these in the web UI, see
# docs/GITHUB_SETUP.md):
#   - Edit the built-in Status field options to Backlog, Ready, In Progress, Review,
#     QA / Integration, Blocked, Done.
#   - Create the four views (Delivery Board, Roadmap, Team Workload, Risks / Blockers).
set -euo pipefail
OWNER="${1:?usage: create_project.sh <owner>}"
TITLE="RatelPlus Subscriber Platform"

NUMBER="$(gh project create --owner "$OWNER" --title "$TITLE" --format json --jq .number)"
echo "Created project #$NUMBER"

field() { # name type [options]
  if [ "$2" = "SINGLE_SELECT" ]; then
    gh project field-create "$NUMBER" --owner "$OWNER" --name "$1" --data-type SINGLE_SELECT \
      --single-select-options "$3" >/dev/null
  else
    gh project field-create "$NUMBER" --owner "$OWNER" --name "$1" --data-type "$2" >/dev/null
  fi
  echo "  field: $1"
}

field "Priority" SINGLE_SELECT "P0,P1,P2,P3"
field "Risk" SINGLE_SELECT "Critical,High,Medium,Low"
field "Workstream" SINGLE_SELECT "Contracts,RatelLink,RatelMeter,BSS Lines,BSS Money,RatelDesk,RatelPay,Cross-cutting"
field "Week" SINGLE_SELECT "Week 1,Week 2,Week 3,Week 4,Week 5,Week 6,Week 7,Week 8,Demo"
field "Type" SINGLE_SELECT "Feature,Bug,Refactor,Security,Database,Infrastructure,Documentation,Investigation"
field "Target Date" DATE
# Assignee and Reviewers are built-in project fields. Status exists already (edit its options by hand).
echo "Done. Now finish Status options and views in the web UI (docs/GITHUB_SETUP.md)."
