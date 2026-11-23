#!/usr/bin/env bash
# Build the patched Open5GS HSS for core-cp, as a complete set installed under its own prefix.
#
# Why a complete set: core-cp does not run the packaged HSS. Since 11 Oct 2026 it runs a separate
# build in /opt/open5gs-hss (2.8.0 plus the upstream fix for issue #4633, through the drop-in
# fix4633.conf), with its own libraries. This build reproduces that (2.8.0 plus the same fix) and
# adds our patch, installed with its own libraries under /opt/open5gs-hss-ratel, so it never mixes
# with another build's libraries.
#
# Runs on any Ubuntu 22.04 host with internet (core-cp has none and should not get a compiler).
# Nothing on this host is changed except build dependencies and a work folder.
#
# Usage:  ./build-hssd.sh [package-version]     default 2.8.0~jammy5, the source core-cp's build used
# Output: ./out/open5gs-hss-ratel.tgz and its .sha256, to copy to core-cp with deploy-hssd.sh
set -euo pipefail

PKG_VERSION=${1:-2.8.0~jammy5}
PREFIX=/opt/open5gs-hss-ratel
HERE=$(cd "$(dirname "$0")" && pwd)
PATCHES=("$HERE/0000-upstream-100ee681-hss-cx-stop-imsi-extraction-at-realm.patch"
	"$HERE/0001-hss-move-msisdn-identities-to-registering-impi.patch")
PPA=https://ppa.launchpadcontent.net/open5gs/latest/ubuntu
WORK=$HERE/work
OUT=$HERE/out

for p in "${PATCHES[@]}"; do [ -f "$p" ] || { echo "patch not found: $p" >&2; exit 1; }; done
# Read the release in a subshell: /etc/os-release also sets VERSION.
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
[ "$CODENAME" = jammy ] || { echo "build on Ubuntu 22.04 (jammy), this is $CODENAME" >&2; exit 1; }

echo "== build dependencies"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq dpkg-dev meson ninja-build \
	build-essential flex bison cmake pkg-config libsctp-dev libgnutls28-dev libgcrypt-dev \
	libssl-dev libmongoc-dev libbson-dev libyaml-dev libnghttp2-dev libmicrohttpd-dev \
	libcurl4-gnutls-dev libtins-dev libtalloc-dev libidn11-dev >/dev/null

echo "== source package open5gs $PKG_VERSION from the Open5GS PPA"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"
cd "$WORK"
curl -4 -fsSL "$PPA/dists/jammy/main/source/Sources.gz" | gunzip >Sources
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
# The PPA index checksums are verified above. The signature check needs the maintainer's key,
# which this host may not have; dpkg-source then only warns.
dpkg-source -x "$DSC" src >/dev/null

echo "== patches"
cd src
for p in "${PATCHES[@]}"; do
	echo "-- $(basename "$p")"
	patch -p1 --forward <"$p"
done

echo "== build and install under $PREFIX (staged)"
meson setup build --prefix="$PREFIX" --buildtype=release >/dev/null
ninja -C build >/dev/null
DESTDIR=$WORK/stage meson install -C build --quiet >/dev/null

BIN=$WORK/stage$PREFIX/bin/open5gs-hssd
grep -q "Cx: move Public-Identity" <(strings "$BIN") || { echo "our patch is not in the binary" >&2; exit 1; }
echo "runpath: $(readelf -d "$BIN" | sed -n 's/.*RUNPATH.*\[\(.*\)\]/\1/p')"

TGZ=$OUT/open5gs-hss-ratel.tgz
tar -C "$WORK/stage" -czf "$TGZ" "${PREFIX#/}"
(cd "$OUT" && sha256sum "$(basename "$TGZ")" | tee "$(basename "$TGZ").sha256")
echo
echo "Built open5gs $PKG_VERSION + upstream 100ee681 (#4633) + our patch, prefix $PREFIX."
echo "Copy $TGZ, its .sha256 and deploy-hssd.sh to one folder on core-cp."
