#!/usr/bin/env bash
# Install a RatelLink release on core-cp. Run as root:
#
#   ./install-release.sh <ratel-link-RELEASE.tar.gz> [python-executable]
#
# Each release gets its own folder and its own virtualenv under /opt/ratel-link/releases/, and
# /opt/ratel-link/current points at the active one. So an upgrade is "install, then restart" and a
# rollback is "point current at the previous release, then restart" (deploy/core-cp/README.md).
# This script never restarts the service and never deletes an old release.
#
# The tarball is built from a reviewed commit on a developer machine:
#   git archive --format=tar.gz --prefix=ratel-link-$(git rev-parse --short HEAD)/ \
#     -o ratel-link-$(git rev-parse --short HEAD).tar.gz HEAD services/ratel_link services/common requirements
set -euo pipefail

BASE="${RATEL_LINK_BASE:-/opt/ratel-link}"
CONFIG_DIR="${RATEL_LINK_CONFIG_DIR:-/etc/ratel-link}"
SERVICE_USER="${RATEL_LINK_USER:-ratellink}"

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
  echo "RatelLink needs Python 3.12 or newer. Pass the executable as the second argument." >&2
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
# The settings and the key file live here, readable by the service user only.
install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_USER" "$CONFIG_DIR"

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
for required in services/ratel_link/main.py services/common requirements/link.txt requirements/constraints.txt; do
  if [ ! -e "$release/$required" ]; then
    echo "The tarball does not look like a RatelLink release (missing $required)." >&2
    exit 1
  fi
done

"$python" -m venv "$release/venv"
"$release/venv/bin/pip" install --quiet --no-cache-dir --disable-pip-version-check \
  -c "$release/requirements/constraints.txt" -r "$release/requirements/link.txt"

# Code is owned by root and cannot be written by the service.
chown -R root:root "$release"
chmod -R go-w "$release"

# The service user must be able to import it. Nothing is started.
runuser -u "$SERVICE_USER" -- env PYTHONPATH="$release/services" \
  "$release/venv/bin/python" -c 'import ratel_link.main' >/dev/null
installed=1
trap - EXIT

previous="$(readlink "$BASE/current" 2>/dev/null || true)"
ln -sfn "$release" "$BASE/current.new"
mv -Tf "$BASE/current.new" "$BASE/current"

echo "Installed $name. current -> $release"
if [ -n "$previous" ]; then
  echo "Previous release (for rollback): $previous"
fi
echo "Not restarted. Next: sudo systemctl restart ratel-link   (deploy/core-cp/README.md)"
