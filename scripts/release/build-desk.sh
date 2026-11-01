#!/usr/bin/env bash
# Build RatelDesk's files for bss-app: the static site nginx serves to the office network and the VPN.
#
#   scripts/release/build-desk.sh [commit] [output-folder]
#
# The result is one tarball, ratel-desk-<commit>.tar.gz, holding only the built files (index.html and its
# assets), and its SHA-256 for the person copying it to check. Nothing runs on bss-app: it is unpacked into a folder
# and nginx serves it (deploy/bss-app/README.md, "RatelDesk").
#
# The code comes from `git archive` of a commit that is already on the reviewed branch, never from a working tree,
# so a developer's .env.local (which can switch the Desk to mock data) is never in the build. The build is made for
# the real API: VITE_USE_MOCK is forced off and the API address is left empty, so the Desk calls the host it is
# served from. Needs Node and npm on this machine (the version in .github/workflows/ci.yml).
#
# Settings (for tests and for another target):
#   RATEL_NPM             the npm to build with (default: npm)
#   RATEL_RELEASE_BRANCH  the branch a release must come from (default: origin/main)
set -euo pipefail

ref="${1:-HEAD}"
out_dir="${2:-.}"
npm="${RATEL_NPM:-npm}"
reviewed_branch="${RATEL_RELEASE_BRANCH:-origin/main}"

root="$(git rev-parse --show-toplevel)"
commit="$(git -C "$root" rev-parse --short "$ref")"
name="ratel-desk-$commit"

if ! git -C "$root" merge-base --is-ancestor "$ref" "$reviewed_branch"; then
  echo "$ref is not on $reviewed_branch. Release only reviewed code (git fetch, then use a commit on main)." >&2
  exit 1
fi

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git -C "$root" archive --format=tar "$ref" web/desk | tar -x -C "$work"
desk="$work/web/desk"

# Locked packages only, no install scripts; then the production build, for the real API.
(
  cd "$desk"
  "$npm" ci --ignore-scripts --no-audit --no-fund
  env -u VITE_API_BASE_URL VITE_USE_MOCK=false "$npm" run build
)

if [ ! -f "$desk/dist/index.html" ]; then
  echo "The build made no dist/index.html." >&2
  exit 1
fi

mkdir "$work/$name"
cp -R "$desk/dist/." "$work/$name/"
# The sample import files belong to the stock screen, which the real build does not offer (src/lib/features.ts).
rm -rf "$work/$name/samples"

mkdir -p "$out_dir"
# COPYFILE_DISABLE stops macOS adding ._ metadata files to the archive.
COPYFILE_DISABLE=1 tar -czf "$out_dir/$name.tar.gz" -C "$work" "$name"

echo "Built $out_dir/$name.tar.gz ($(find "$work/$name" -type f | wc -l | tr -d ' ') files)"
(cd "$out_dir" && sha256 "$name.tar.gz")
