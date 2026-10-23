#!/usr/bin/env bash
# Build a RatelMeter agent release for core-up that carries its own dependencies, so installing it
# needs no internet on core-up (deploy/core-up/README.md, step 2).
#
#   scripts/release/build-meter-release.sh [commit] [output-folder]
#
# The code comes from `git archive` of a commit that is already on the reviewed branch, never from a
# working tree. The dependencies are downloaded here, on the developer machine, as prebuilt Linux
# wheels for Python 3.12 on x86_64 and pinned by requirements/constraints.txt. The result is one
# tarball, named after the commit, and its SHA-256 for the person copying it to check.
#
# Settings (for tests and for another target):
#   RATEL_PIP             the pip to download with (default: pip)
#   RATEL_RELEASE_BRANCH  the branch a release must come from (default: origin/main)
set -euo pipefail

ref="${1:-HEAD}"
out_dir="${2:-.}"
pip="${RATEL_PIP:-pip}"
reviewed_branch="${RATEL_RELEASE_BRANCH:-origin/main}"

root="$(git rev-parse --show-toplevel)"
commit="$(git -C "$root" rev-parse --short "$ref")"
name="ratel-meter-$commit"

if ! git -C "$root" merge-base --is-ancestor "$ref" "$reviewed_branch"; then
  echo "$ref is not on $reviewed_branch. Release only reviewed code (git fetch, then use a commit on main)." >&2
  exit 1
fi

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git -C "$root" archive --format=tar --prefix="$name/" "$ref" \
  services/meter_agent services/common requirements | tar -x -C "$work"

# Prebuilt wheels only: nothing is compiled on core-up, and nothing is fetched there.
mkdir "$work/$name/wheels"
"$pip" download --quiet --disable-pip-version-check --dest "$work/$name/wheels" \
  --only-binary=:all: --python-version 3.12 --implementation cp --abi cp312 \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
  -c "$work/$name/requirements/constraints.txt" -r "$work/$name/requirements/agent.txt"
(cd "$work/$name/wheels" && sha256 -- *.whl >../wheels.sha256)

mkdir -p "$out_dir"
# COPYFILE_DISABLE stops macOS adding ._ metadata files to the archive.
COPYFILE_DISABLE=1 tar -czf "$out_dir/$name.tar.gz" -C "$work" "$name"

echo "Built $out_dir/$name.tar.gz ($(wc -l <"$work/$name/wheels.sha256" | tr -d ' ') wheels)"
(cd "$out_dir" && sha256 "$name.tar.gz")
