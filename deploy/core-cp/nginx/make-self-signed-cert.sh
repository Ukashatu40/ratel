#!/usr/bin/env bash
# Make the self-signed certificate for the TLS proxy in front of RatelLink (ratel-link.conf.example).
#
#   sudo ./make-self-signed-cert.sh <ip-address-or-dns-name> [directory]
#
# The address or name is what the callers type in RATEL_LINK_BASE_URL (for example the address of
# core-cp as core-up and bss-app see it). It goes into the certificate, so a caller that uses a
# different one will refuse it: that is the point. Type it on the host. It is never in the
# repository (the repository is public).
#
# Writes privkey.pem (root only) and fullchain.pem into the directory (default /etc/ssl/ratel-link),
# the two paths the proxy template names. It refuses to overwrite either: to renew, move the old
# pair aside first. The certificate lasts 825 days, which is the callers' deadline for replacing it.
# It prints the certificate's SHA-256 fingerprint: read it out to whoever installs the certificate
# on a caller and have them compare it with what they see there.
#
# Only fullchain.pem (the public half) is ever copied to a caller, as the file its SSL_CERT_FILE
# points at (deploy/core-up/ratel-meter.env.example, deploy/bss-app/ratel-app.env.example). The
# folder is root-only (the umask below), so copy the file with sudo first; deploy/core-cp/README.md says how.
set -euo pipefail

usage() {
  echo "usage: sudo $0 <ip-address-or-dns-name> [directory]" >&2
  exit 2
}

host="${1:-}"
dir="${2:-/etc/ssl/ratel-link}"
[ -n "$host" ] || usage
[ "$#" -le 2 ] || usage

octet='(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])'
if [[ "$host" =~ ^$octet\.$octet\.$octet\.$octet$ ]]; then
  san="IP:$host"
elif [[ "$host" =~ ^[0-9.]+$ ]]; then
  echo "refused: '$host' looks like an IPv4 address but is not a valid one" >&2
  exit 2
elif [[ "$host" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$ ]]; then
  san="DNS:$host"
else
  echo "refused: '$host' is neither an IPv4 address nor a DNS name with a dot in it" >&2
  exit 2
fi

key="$dir/privkey.pem"
cert="$dir/fullchain.pem"
if [ -e "$key" ] || [ -e "$cert" ]; then
  echo "refused: $key or $cert already exists. Move the old pair aside to renew." >&2
  exit 1
fi

umask 077
mkdir -p "$dir"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout "$key" -out "$cert" -days 825 -subj "/CN=$host" \
  -addext "subjectAltName=$san" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature" \
  -addext "extendedKeyUsage=serverAuth" 2>/dev/null
chmod 0644 "$cert"
chmod 0600 "$key"

echo "Wrote $cert (public) and $key (private, root only)."
echo "Valid for $host, 825 days. Its fingerprint:"
openssl x509 -in "$cert" -noout -fingerprint -sha256
echo "Copy ONLY $cert to each caller. Never the key."
