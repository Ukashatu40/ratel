#!/usr/bin/env bash
# Build the patched Open5GS HSS (open5gs-hssd) for core-cp.
#
# Runs on the ops VM: Ubuntu 22.04 like core-cp, and it has internet. core-cp has none and should
# not get a compiler. Builds from the exact source package that is installed on core-cp, so the
# binary matches the shared libraries already there, then applies our patch and builds the HSS
# only. Nothing on this host is changed except build dependencies and a work folder.
#
# Usage:  ./build-hssd.sh [version]          default version: 2.8.0~jammy5 (what core-cp runs)
# Output: ./out/open5gs-hssd-ratel and its SHA-256, to copy to core-cp with deploy-hssd.sh
set -euo pipefail

PKG_VERSION=${1:-2.8.0~jammy5}
HERE=$(cd "$(dirname "$0")" && pwd)
PATCH=$HERE/0001-hss-move-msisdn-identities-to-registering-impi.patch
PPA=https://ppa.launchpadcontent.net/open5gs/latest/ubuntu
WORK=$HERE/work
OUT=$HERE/out

[ -f "$PATCH" ] || { echo "patch not found: $PATCH" >&2; exit 1; }
# Read the release in a subshell: /etc/os-release also sets VERSION and would overwrite ours.
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
[ "$CODENAME" = jammy ] || { echo "build on Ubuntu 22.04 (jammy), this is $CODENAME" >&2; exit 1; }

echo "== build dependencies"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq dpkg-dev patchelf meson ninja-build \
	build-essential flex bison cmake pkg-config libsctp-dev libgnutls28-dev libgcrypt-dev \
	libssl-dev libmongoc-dev libbson-dev libyaml-dev libnghttp2-dev libmicrohttpd-dev \
	libcurl4-gnutls-dev libtins-dev libtalloc-dev libidn11-dev >/dev/null

echo "== source package open5gs $PKG_VERSION from the Open5GS PPA"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"
cd "$WORK"
curl -4 -fsSL "$PPA/dists/jammy/main/source/Sources.gz" | gunzip >Sources
# The stanza for exactly this version, and the files and checksums it lists.
STANZA='BEGIN{RS=""; FS="\n"}
{p=0; ok=0; for (i = 1; i <= NF; i++) { if ($i == "Package: open5gs") p=1; if ($i == "Version: " v) ok=1 }}'
awk -v v="$PKG_VERSION" "$STANZA"' p && ok {print; exit}' Sources >stanza
if [ ! -s stanza ]; then
	echo "version $PKG_VERSION is no longer in the PPA. Versions it has:" >&2
	awk -v v="" "$STANZA"' p {print}' Sources | grep '^Version:' >&2
	exit 1
fi
DIR=$(sed -n 's/^Directory: //p' stanza)
awk '/^Checksums-Sha256:/{f=1;next} /^[A-Za-z-]+:/{f=0} f{print $1, $3}' stanza >sums
while read -r sum name; do
	curl -4 -fsSL -o "$name" "$PPA/$DIR/$name"
	echo "$sum  $name" | sha256sum -c - >&2
done <sums
DSC=$(awk '$2 ~ /\.dsc$/{print $2}' sums)
dpkg-source -x "$DSC" src >/dev/null

echo "== patch"
cd src
patch -p1 --forward <"$PATCH"

echo "== build the HSS only"
meson setup build --buildtype=release >/dev/null
ninja -C build src/hss/open5gs-hssd >/dev/null
BIN=$OUT/open5gs-hssd-ratel
cp build/src/hss/open5gs-hssd "$BIN"
# The build points the binary at the build folder's libraries. On core-cp it must use the
# installed ones, which come from this same source version.
patchelf --remove-rpath "$BIN"
strip "$BIN"
sha256sum "$BIN" | tee "$BIN.sha256"
echo
echo "Built from open5gs $PKG_VERSION with $(basename "$PATCH")."
echo "Copy $BIN and its .sha256 to core-cp next to deploy-hssd.sh."
