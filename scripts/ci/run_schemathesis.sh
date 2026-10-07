#!/usr/bin/env bash
# Run Schemathesis against each service, only for operations that are implemented
# (i.e. NOT listed in contracts/not_implemented.txt). Fails if the service disagrees with
# contracts/openapi.yaml. Skips cleanly while nothing is implemented.
#
# Env:
#   BIN                 venv bin dir (default .venv/bin when unset; set BIN= to use PATH)
#   RATEL_TEST_API_KEY  synthetic API key the services accept in test (never a real key)
#   SCHEMATHESIS_EXTRA  extra flags, e.g. "--max-examples 50"
set -euo pipefail
cd "$(dirname "$0")/../.."

BIN="${BIN-.venv/bin}"
PY="${BIN:+$BIN/}python"
ST="${BIN:+$BIN/}schemathesis"
KEY="${RATEL_TEST_API_KEY:-test-only-not-a-real-key}"

# tag | uvicorn module | port
SERVICES=(
  "RatelLink|ratel_link.main:create_app|18081"
  "RatelMeter|app.main:create_app|18082"
)

status=0
pids=()
# shellcheck disable=SC2317,SC2329  # runs from the trap; older and newer shellcheck name this differently
cleanup() {
  local p
  for p in "${pids[@]:-}"; do
    if [ -n "$p" ]; then
      kill "$p" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

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
    -H "Authorization: $KEY" --checks all ${SCHEMATHESIS_EXTRA:-} || status=1
done
exit "$status"
