#!/usr/bin/env bash
# The host's half of a deploy (scripts/deploy/deploy.sh runs it with sudo). Not meant to be run by hand.
#
#   deploy-remote.sh <app|desk|meter|calls> <tarball-name> <sha256> <python> <workdir>
#
# In the work folder, next to this script: the tarball, and (not for desk) install-release.sh.
# Order: check the checksum, remember the running release, install, restart, wait for the service to say it is
# up, and put the previous release back if it does not. A database migration is never undone here.
#
# Settings (environment; the defaults are right on the hosts, the tests change them):
#   RATEL_DEPLOY_APP_BASE (/opt/ratel-app)  RATEL_DEPLOY_METER_BASE (/opt/ratel-meter)  RATEL_DEPLOY_WWW (/var/www)
#   RATEL_DEPLOY_LOG (/var/log/ratel-deploy.log)  RATEL_DEPLOY_WAIT (seconds to wait for a service, 30)
#   RATEL_DEPLOY_KEEP=1 keeps the work folder
set -euo pipefail

target="${1:?usage: deploy-remote.sh <app|desk|meter|calls> <tarball> <sha256> <python> <workdir>}"
tarball_name="${2:?}"
expected="${3:?}"
python="${4:-}"
workdir="${5:-$(cd "$(dirname "$0")" && pwd)}"

app_base="${RATEL_DEPLOY_APP_BASE:-/opt/ratel-app}"
meter_base="${RATEL_DEPLOY_METER_BASE:-/opt/ratel-meter}"
www="${RATEL_DEPLOY_WWW:-/var/www}"
log_file="${RATEL_DEPLOY_LOG:-/var/log/ratel-deploy.log}"
wait_seconds="${RATEL_DEPLOY_WAIT:-30}"
systemctl="${RATEL_DEPLOY_SYSTEMCTL:-systemctl}"
journalctl="${RATEL_DEPLOY_JOURNALCTL:-journalctl}"
curl="${RATEL_DEPLOY_CURL:-curl}"
systemd_run="${RATEL_DEPLOY_SYSTEMD_RUN:-systemd-run}"
sha256="${RATEL_DEPLOY_SHA256:-sha256sum}"

say() { echo "deploy-remote: $*"; }
[ "${RATEL_DEPLOY_KEEP:-0}" = 1 ] || trap 'rm -rf "$workdir"' EXIT

record() {  # one line per deploy, for whoever asks later who changed what
  local line
  line="$(date -u +%FT%TZ) $target ${prev_name:-none} -> ${new_name:-none} $1 by ${SUDO_USER:-root}"
  echo "$line" >> "$log_file" 2>/dev/null || true
  logger -t ratel-deploy "$line" 2>/dev/null || true
}
die() { say "$*"; record "FAILED"; exit 1; }

[ -f "$workdir/$tarball_name" ] || die "the tarball is not in $workdir"
actual="$("$sha256" "$workdir/$tarball_name" | cut -d' ' -f1)"
[ "$actual" = "$expected" ] || die "the checksum on the host differs from the one built (copy damaged?): nothing was installed"
say "checksum ok"

name_of() { [ -n "$1" ] && basename "$1" || echo none; }

# Restart a systemd unit and wait until `check` passes, or the time is up.
wait_for() {  # wait_for <description> <command...>
  local what="$1" waited=0
  shift
  while ! "$@"; do
    waited=$((waited + 1))
    [ "$waited" -le "$wait_seconds" ] || { say "$what: not up after ${wait_seconds}s"; return 1; }
    sleep 1
  done
}

app_healthy() {
  "$curl" -fsS -o /dev/null http://127.0.0.1:8000/healthz &&
    [ "$("$curl" -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/readyz)" = "200" ]
}

agent_up() {  # agent_up <unit> <epoch the restart began>: it logged its start and nothing has failed since
  local out
  out="$("$journalctl" -u "$1" --since "@$2" --no-pager 2>/dev/null || true)"
  grep -q 'meter.agent.started' <<<"$out" &&
    ! grep -qE 'meter.agent.tick_error|meter.counters.nft_failed|Traceback|code=exited' <<<"$out"
}

switch_back() {  # switch_back <link> <previous release>
  if [ -n "$2" ]; then ln -sfn "$2" "$1" && say "put the previous release back: $(basename "$2")"; else say "there was no previous release to put back"; fi
}

case "$target" in
  app)
    link="$app_base/current"
    prev="$(readlink -f "$link" 2>/dev/null || true)"; prev_name="$(name_of "$prev")"
    bash "$workdir/install-release.sh" "$workdir/$tarball_name" "$python"
    new="$(readlink -f "$link")"; new_name="$(name_of "$new")"
    say "installed $new_name (was $prev_name); migrating"
    if ! "$systemd_run" --wait --pipe -p User=ratelbss -p EnvironmentFile=/etc/ratel-app/ratel-app-migrate.env \
        -p Environment=PYTHONPATH="$link/services" -p Environment=PYTHONDONTWRITEBYTECODE=1 \
        "$link/venv/bin/python" -m alembic -c "$link/services/app/alembic.ini" upgrade head; then
      switch_back "$link" "$prev"
      die "the migration failed; the service was not restarted and still runs $prev_name"
    fi
    "$systemctl" restart ratel-app.service
    if ! wait_for "ratel-app (healthz, readyz)" app_healthy; then
      switch_back "$link" "$prev"
      "$systemctl" restart ratel-app.service || true
      say "NOTE: the migration was applied and is not undone; check that the old release runs against the new schema"
      die "the new release did not come up: rolled back"
    fi
    ;;
  desk)
    link="$www/ratel-desk"
    prev="$(readlink "$link" 2>/dev/null || true)"; prev_name="$(name_of "$prev")"
    new_name="${tarball_name%.tar.gz}"
    dest="$www/desk-releases/$new_name"
    install -d -m 0755 "$www/desk-releases" "$dest"
    tar -xzf "$workdir/$tarball_name" --strip-components=1 -C "$dest"
    if [ "$(id -u)" -eq 0 ]; then chown -R root:root "$dest"; fi
    chmod -R go-w "$dest"
    ln -sfn "$dest" "$link"
    if [ ! -f "$link/index.html" ]; then
      switch_back "$link" "$prev"
      die "the unpacked Desk has no index.html: rolled back"
    fi
    ;;
  meter|calls)
    if [ "$target" = meter ]; then unit="ratel-meter.service"; else unit="ratel-meter-calls.service"; fi
    link="$meter_base/current"
    prev="$(readlink -f "$link" 2>/dev/null || true)"; prev_name="$(name_of "$prev")"
    bash "$workdir/install-release.sh" "$workdir/$tarball_name" "$python"
    new="$(readlink -f "$link")"; new_name="$(name_of "$new")"
    say "installed $new_name (was $prev_name); restarting $unit"
    began="$(date +%s)"
    "$systemctl" restart "$unit"
    if ! wait_for "$unit" agent_up "$unit" "$began"; then
      switch_back "$link" "$prev"
      "$systemctl" restart "$unit" || true
      die "the new agent did not come up cleanly: rolled back"
    fi
    say "a tick that fails shows at the next 5-minute boundary: read the journal then"
    ;;
  *) die "unknown target: $target" ;;
esac

record "ok"
say "done: $target now runs $new_name"
