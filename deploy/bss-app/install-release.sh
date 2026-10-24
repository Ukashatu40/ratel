#!/usr/bin/env bash
# Install an app release (RatelBSS and the RatelMeter API) on bss-app. Run as root:
#
#   ./install-release.sh <ratel-app-RELEASE.tar.gz> [python-executable]
#
# Each release gets its own folder and its own virtualenv under /opt/ratel-app/releases/, and
# /opt/ratel-app/current points at the active one (ratel-app.service runs from there). So an
# upgrade is "install, then restart" and a rollback is "point current at the previous release, then
# restart" (deploy/bss-app/README.md). This script never restarts the service, never runs a database
# migration and never deletes an
# old release.
#
# The tarball is built from a reviewed commit on a developer machine, with its dependencies inside
# (scripts/release/build-release.sh app). A tarball without a wheels/ folder still works: pip then
# downloads the dependencies, which needs this host to resolve names.
set -euo pipefail

BASE="${RATEL_APP_BASE:-/opt/ratel-app}"
CONFIG_DIR="${RATEL_APP_CONFIG_DIR:-/etc/ratel-app}"
SERVICE_USER="${RATEL_APP_USER:-ratelbss}"

tarball="${1:?usage: install-release.sh <release.tar.gz> [python-executable]}"
python="${2:-python3.12}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: it creates the service user and owns the code." >&2
  exit 1
fi
if [ ! -f "$tarball" ]; then
  echo "No such file: $tarball" >&2
  exit 1
fi
if ! "$python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "The app needs Python 3.12 or newer. Pass the executable as the second argument." >&2
  exit 1
fi

name="$(basename "$tarball" .tar.gz)"
case "$name" in
  *[!A-Za-z0-9._-]* | "")
    echo "The release name '$name' may only contain letters, digits, dot, dash and underscore." >&2
    exit 1
    ;;
esac
release="$BASE/releases/$name"
if [ -e "$release" ]; then
  echo "Release $name is already installed at $release. Nothing was changed." >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$BASE" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  echo "created user $SERVICE_USER"
fi
install -d -m 0755 -o root -g root "$BASE" "$BASE/releases"
# Settings: root can read them (systemd does), the service group can
# list the folder, nobody else. The env file inside is created by hand and is mode 0600.
install -d -m 0750 -o root -g "$SERVICE_USER" "$CONFIG_DIR"

mkdir "$release"
installed=0
cleanup_on_failure() {
  # Runs on every exit. A release that did not finish installing is removed, whether a command
  # failed or this script stopped on purpose, so a retry never meets a half-made folder.
  if [ "$installed" -ne 1 ]; then
    rm -rf "$release"
    echo "Install failed: $release was removed. The active release is unchanged." >&2
  fi
}
trap cleanup_on_failure EXIT

tar -xzf "$tarball" --no-same-owner --strip-components=1 -C "$release"
for required in services/app/main.py services/app/alembic.ini services/common requirements/app.txt requirements/constraints.txt; do
  if [ ! -e "$release/$required" ]; then
    echo "The tarball does not look like an app release (missing $required)." >&2
    exit 1
  fi
done

"$python" -m venv "$release/venv"
pip_args=(--quiet --no-cache-dir --disable-pip-version-check
  -c "$release/requirements/constraints.txt" -r "$release/requirements/app.txt")
if [ -d "$release/wheels" ]; then
  # A release built by scripts/release/build-release.sh app carries its dependencies: no network.
  echo "Installing dependencies from the release's own wheels (no network used)."
  "$release/venv/bin/pip" install "${pip_args[@]}" --no-index --find-links "$release/wheels"
else
  "$release/venv/bin/pip" install "${pip_args[@]}"
fi

# Code is owned by root and cannot be written by the service.
chown -R root:root "$release"
chmod -R go-w "$release"

# The service user must be able to import it. Nothing is started.
runuser -u "$SERVICE_USER" -- env PYTHONPATH="$release/services" \
  "$release/venv/bin/python" -c 'import app.main' >/dev/null
installed=1
trap - EXIT

previous="$(readlink "$BASE/current" 2>/dev/null || true)"
ln -sfn "$release" "$BASE/current.new"
mv -Tf "$BASE/current.new" "$BASE/current"

echo "Installed $name. current -> $release"
if [ -n "$previous" ]; then
  echo "Previous release (for rollback): $previous"
fi
echo "Not restarted, no migration run. Next: the database migration, then restart the service (deploy/bss-app/README.md)"
