#!/usr/bin/env bash
# Deploy a reviewed release to one host, from this machine: build it from origin/main, copy it, check the
# checksum on the host, install it, restart, check that it came up, and roll back if it did not.
#
#   scripts/deploy/deploy.sh <app|desk|meter|calls|link> [--commit REF] [--tarball FILE] [--dry-run] [--yes]
#
# app    RatelBSS, the RatelMeter API and the RatelPay page on bss-app: install, migrate, restart, health check
# desk   RatelDesk's files on bss-app: unpack and switch the link
# meter  the RatelMeter data agent on core-up
# calls  the RatelMeter call agent on the voice VM
# link   RatelLink on core-cp (restart, then healthz and readyz)
#
# The release comes from `git archive` of a commit that is already on origin/main (the build scripts refuse
# anything else), never from a working tree. The host is reached by its ssh alias; the sudo password is typed
# once per deploy, on the host (ssh -t). Nothing secret is in this file or on the command line, and nothing
# here edits an env file, nginx or a firewall: those stay manual (docs/runbooks/deploying.md).
#
# Settings (environment):
#   RATEL_RELEASE_DIR     where builds are kept          (default: ~/ratel-releases)
#   RATEL_HOST_APP        ssh alias of bss-app           (default: ratelplus-bss-app)
#   RATEL_HOST_CORE_UP    ssh alias of core-up           (default: ratelplus-core-up)
#   RATEL_HOST_VOICE      ssh alias of the voice VM      (default: ratelplus-voice)
#   RATEL_HOST_CORE_CP    ssh alias of core-cp           (default: ratelplus-core-cp)
#   RATEL_LINK_PYTHON     Python 3.12 on core-cp         (default: /opt/python-3.12/bin/python3.12)
#   RATEL_SSH, RATEL_SCP  the ssh and scp to use         (default: ssh, scp)
set -euo pipefail

usage() {
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}
fail() { echo "deploy: $*" >&2; exit 1; }

target="${1:-}"
[ -n "$target" ] || usage
shift
ref="origin/main"
tarball=""
dry=0
yes=0
while [ $# -gt 0 ]; do
  case "$1" in
    --commit) [ $# -ge 2 ] || usage; ref="$2"; shift 2 ;;
    --tarball) [ $# -ge 2 ] || usage; tarball="$2"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    --yes) yes=1; shift ;;
    *) usage ;;
  esac
done

root="$(git rev-parse --show-toplevel)"
release_dir="${RATEL_RELEASE_DIR:-$HOME/ratel-releases}"
ssh_bin="${RATEL_SSH:-ssh}"
scp_bin="${RATEL_SCP:-scp}"

case "$target" in
  app)   host="${RATEL_HOST_APP:-ratelplus-bss-app}";      prefix="ratel-app";   build="app";   installer="deploy/bss-app/install-release.sh"; python="python3.12" ;;
  desk)  host="${RATEL_HOST_APP:-ratelplus-bss-app}";      prefix="ratel-desk";  build="desk";  installer="";                                 python="" ;;
  meter) host="${RATEL_HOST_CORE_UP:-ratelplus-core-up}";  prefix="ratel-meter"; build="meter"; installer="deploy/core-up/install-release.sh"; python="/opt/python-3.12/bin/python3.12" ;;
  calls) host="${RATEL_HOST_VOICE:-ratelplus-voice}";      prefix="ratel-meter"; build="meter"; installer="deploy/core-up/install-release.sh"; python="/opt/python-3.12/bin/python3.12" ;;
  link)  host="${RATEL_HOST_CORE_CP:-ratelplus-core-cp}";  prefix="ratel-link";  build="link";  installer="deploy/core-cp/install-release.sh"; python="${RATEL_LINK_PYTHON:-/opt/python-3.12/bin/python3.12}" ;;
  *) usage ;;
esac

sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

if [ -z "$tarball" ]; then
  git -C "$root" fetch -q origin
  commit="$(git -C "$root" rev-parse --short "$ref")" || fail "unknown commit: $ref"
  subject="$(git -C "$root" log -1 --format=%s "$ref")"
  mkdir -p "$release_dir"
  tarball="$release_dir/$prefix-$commit.tar.gz"
  echo "Building $prefix-$commit: $subject"
  if [ "$dry" -eq 1 ]; then
    echo "(dry run: not built)"
  elif [ "$build" = "desk" ]; then
    "$root/scripts/release/build-desk.sh" "$commit" "$release_dir"
  else
    "$root/scripts/release/build-release.sh" "$build" "$commit" "$release_dir"
  fi
else
  commit="$(basename "$tarball" .tar.gz)"
  commit="${commit#"$prefix"-}"
  subject="(a tarball that was already built)"
fi

if [ "$dry" -eq 1 ] && [ ! -f "$tarball" ]; then
  sum="(not built)"
else
  [ -f "$tarball" ] || fail "no such file: $tarball"
  sum="$(sha256 "$tarball")"
fi

echo
echo "  target   $target on $host"
echo "  release  $(basename "$tarball")"
echo "  sha256   $sum"
echo "  change   $subject"
echo
if [ "$dry" -eq 1 ]; then
  echo "Dry run: nothing was copied or changed."
  exit 0
fi
if [ "$yes" -ne 1 ]; then
  read -r -p "Deploy this to $host? [y/N] " answer
  [ "$answer" = "y" ] || fail "not confirmed, nothing was done"
fi

ssh_opts=(-o ControlMaster=auto -o "ControlPath=$HOME/.ssh/ratel-cm-%C" -o ControlPersist=10m)
rdir="$("$ssh_bin" "${ssh_opts[@]}" "$host" 'mktemp -d /tmp/ratel-deploy.XXXXXX')" || fail "cannot reach $host"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
files=("$tarball" "$root/scripts/deploy/remote/deploy-remote.sh")
if [ -n "$installer" ]; then
  # The host runs it under a fixed name, next to the tarball.
  cp "$root/$installer" "$stage/install-release.sh"
  files+=("$stage/install-release.sh")
fi
"$scp_bin" -p "${ssh_opts[@]}" "${files[@]}" "$host:$rdir/" || fail "copy to $host failed"

status=0
"$ssh_bin" -t "${ssh_opts[@]}" "$host" \
  "sudo bash $rdir/deploy-remote.sh $target $(basename "$tarball") $sum '$python' $rdir" || status=$?

result="ok"
[ "$status" -eq 0 ] || result="FAILED($status)"
printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$target" "$host" "$commit" "$result" >> "$release_dir/deploy-log.tsv"
echo
if [ "$status" -eq 0 ]; then
  echo "Deployed $commit to $host ($target)."
else
  echo "The deploy of $commit to $host FAILED (exit $status). Read the output above: if it says it rolled back, the previous release is running." >&2
fi
exit "$status"
