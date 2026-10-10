#!/usr/bin/env bash
# Run Schemathesis against each service, only for operations that are implemented
# (i.e. NOT listed in contracts/not_implemented.txt). Fails if the service disagrees with
# contracts/openapi.yaml. Skips cleanly while nothing is implemented.
#
# RatelLink rejects every /v1 call without a valid API key (ADR 0007) and keeps its data in
# MongoDB, so for RatelLink this script prepares, throwaway and on its own:
#   - a database with a random name (dropped at the end) in the MongoDB at RATEL_TEST_MONGO_URI,
#   - an encryption key file in a temporary folder (deleted at the end),
#   - a test API key created with the admin CLI. It is never printed, and on GitHub Actions it is
#     also masked in the log.
# Nothing in the service is relaxed to make this work.
#
# Env:
#   BIN                  venv bin dir (default .venv/bin when unset; set BIN= to use PATH)
#   RATEL_TEST_MONGO_URI MongoDB to use for RatelLink, for example the one from `make up`:
#                        mongodb://<user>:<password>@127.0.0.1:27017/?authSource=admin
#                        In CI (CI=true) it is required. Locally, when it is not set, RatelLink is
#                        skipped with a warning.
#   RATEL_TEST_API_KEY   synthetic API key for services other than RatelLink (never a real key)
#   SCHEMATHESIS_EXTRA   extra flags, e.g. "--max-examples 50"
set -euo pipefail
cd "$(dirname "$0")/../.."

BIN="${BIN-.venv/bin}"
PY="${BIN:+$BIN/}python"
ST="${BIN:+$BIN/}schemathesis"
DEFAULT_KEY="${RATEL_TEST_API_KEY:-test-only-not-a-real-key}"

# tag | uvicorn module | port
SERVICES=(
  "RatelLink|ratel_link.main:create_app|18081"
  "RatelMeter|app.main:create_app|18082"
)

status=0
pids=()
workdir=""
test_db=""

# shellcheck disable=SC2317,SC2329  # runs from the trap; older and newer shellcheck name this differently
cleanup() {
  local p
  for p in "${pids[@]:-}"; do
    if [ -n "$p" ]; then
      kill "$p" 2>/dev/null || true
    fi
  done
  if [ -n "$test_db" ]; then
    DROP_DB="$test_db" "$PY" - <<'PY' 2>/dev/null || true
import os
from pymongo import MongoClient
MongoClient(os.environ["RATEL_TEST_MONGO_URI"], serverSelectionTimeoutMS=3000).drop_database(os.environ["DROP_DB"])
PY
  fi
  if [ -n "$workdir" ]; then
    rm -rf "$workdir"
  fi
}
trap cleanup EXIT

# Creates the database, key file and test API key for RatelLink. Sets KEY. Returns 1 to skip.
prepare_ratellink() {
  if [ -z "${RATEL_TEST_MONGO_URI:-}" ]; then
    if [ -n "${CI:-}" ]; then
      echo "[RatelLink] RATEL_TEST_MONGO_URI is not set in CI: it must point at the MongoDB service." >&2
      exit 1
    fi
    echo "[RatelLink] SKIPPED locally: set RATEL_TEST_MONGO_URI (make up) to fuzz its operations."
    return 1
  fi
  workdir="$(mktemp -d)"
  test_db="ratel_link_schemathesis_$$"
  export MONGO_URI="$RATEL_TEST_MONGO_URI" RATEL_LINK_DB_NAME="$test_db" RATEL_ENV=test
  export RATEL_LINK_KEY_FILE="$workdir/ratel_link.key"

  local up=""
  for _ in $(seq 1 40); do
    if "$PY" -c 'import os; from pymongo import MongoClient; MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=1500).admin.command("ping")' 2>/dev/null; then
      up=yes
      break
    fi
    sleep 1
  done
  if [ -z "$up" ]; then
    echo "[RatelLink] MongoDB did not answer at RATEL_TEST_MONGO_URI" >&2
    exit 1
  fi

  local cli=("$PY" -m ratel_link.admin_cli)
  PYTHONPATH=services "${cli[@]}" key generate --out "$RATEL_LINK_KEY_FILE" 2>/dev/null
  PYTHONPATH=services "${cli[@]}" init-db >/dev/null 2>"$workdir/err" || { cat "$workdir/err" >&2; exit 1; }
  if ! KEY="$(PYTHONPATH=services "${cli[@]}" api-key create --id schemathesis --name "Schemathesis (test)" 2>"$workdir/err")"; then
    cat "$workdir/err" >&2
    exit 1
  fi
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    echo "::add-mask::$KEY"
  fi
}

for entry in "${SERVICES[@]}"; do
  IFS='|' read -r tag module port <<<"$entry"
  # Assigned first so a failing helper stops the script (set -e) instead of looking like "none".
  implemented=$(PYTHONPATH=services:. "$PY" -m tests.contract.helpers implemented "$tag")
  # Not `mapfile`: macOS ships bash 3.2, which does not have it.
  ids=()
  while IFS= read -r op_id; do
    if [ -n "$op_id" ]; then
      ids+=("$op_id")
    fi
  done <<<"$implemented"
  if [ "${#ids[@]}" -eq 0 ]; then
    echo "[$tag] no implemented operations yet, skipping Schemathesis"
    continue
  fi

  KEY="$DEFAULT_KEY"
  if [ "$tag" = "RatelLink" ]; then
    prepare_ratellink || continue
  fi

  echo "[$tag] fuzzing ${#ids[@]} operation(s): ${ids[*]}"
  PYTHONPATH=services "$PY" -m uvicorn --factory "$module" --host 127.0.0.1 --port "$port" \
    --log-level warning &
  pids+=("$!")
  for _ in $(seq 1 30); do
    curl -fs "http://127.0.0.1:$port/healthz" >/dev/null && break
    sleep 0.5
  done
  curl -fs "http://127.0.0.1:$port/healthz" >/dev/null || { echo "[$tag] service did not start"; exit 1; }

  include=()
  for i in "${ids[@]}"; do include+=(--include-operation-id "$i"); done
  # shellcheck disable=SC2086
  "$ST" run contracts/openapi.yaml --url "http://127.0.0.1:$port" "${include[@]}" \
    -H "Authorization: Bearer $KEY" --checks all ${SCHEMATHESIS_EXTRA:-} || status=1
done
exit "$status"
