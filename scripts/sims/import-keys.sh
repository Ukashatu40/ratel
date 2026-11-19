#!/usr/bin/env bash
# Import the keys of chosen SIMs into RatelLink from the laptop, so that RatelDesk can sell them (RatelLink answers
# "Unknown line" at activation until a SIM's keys are in). The key file never leaves the laptop: the chosen rows are read
# here, and the keys travel only inside SSH, on standard input, to `POST /v1/sims` on core-cp. They are never on a command
# line, in a file on the server, on the screen or in this script's output.
#
#   scripts/sims/import-keys.sh 0455 [0456 ...]       the last four digits of each SIM's IMSI
#
# It asks for a caller key (hidden), made on core-cp for the session and disabled after it:
#   admin_cli api-key create --id lab-import-<n> --name "lab <n>"    ...    admin_cli api-key disable --id lab-import-<n>
# Every SIM is checked before anything is sent: exactly one row, a 15-digit IMSI, Ki and OPc of 32 hex characters.
# Sending the same keys again is harmless (200); different keys for an IMSI already stored are refused (409) and kept.
#
# Settings: RATEL_SIMS_FILE (default docs/source/sims.csv), RATEL_HOST_CORE_CP (ssh alias, default ratelplus-core-cp),
#           RATEL_LINK_URL (on core-cp, default http://127.0.0.1:8081)
set -euo pipefail

[ $# -ge 1 ] || { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
file="${RATEL_SIMS_FILE:-$root/docs/source/sims.csv}"
host="${RATEL_HOST_CORE_CP:-ratelplus-core-cp}"
url="${RATEL_LINK_URL:-http://127.0.0.1:8081}"
[ -r "$file" ] || { echo "import-keys: cannot read the key file ($file)" >&2; exit 2; }
case "$url" in http://127.0.0.1:*|http://localhost:*) ;; *) echo "import-keys: RATEL_LINK_URL must be local to core-cp" >&2; exit 2 ;; esac

bodies=()
for four in "$@"; do
  [[ "$four" =~ ^[0-9]{4}$ ]] || { echo "import-keys: '$four' is not four digits" >&2; exit 2; }
  rows="$(awk -F, -v f="$four" '{ sub(/\r$/, "") } NR > 1 && substr($2, length($2) - 3) == f' "$file")"
  count="$(printf '%s' "$rows" | grep -c . || true)"
  [ "$count" -eq 1 ] || { echo "import-keys: $four matches $count rows in the key file; nothing was sent" >&2; exit 1; }
  IFS=, read -r _ imsi _ _ _ ki opc _ <<<"$rows"
  [[ "$imsi" =~ ^[0-9]{15}$ ]] || { echo "import-keys: $four: the IMSI is not 15 digits; nothing was sent" >&2; exit 1; }
  [[ "$ki" =~ ^[0-9A-Fa-f]{32}$ && "$opc" =~ ^[0-9A-Fa-f]{32}$ ]] \
    || { echo "import-keys: $four: Ki or OPc is not 32 hex characters; nothing was sent" >&2; exit 1; }
  bodies+=("$(printf '{"imsi":"%s","ki":"%s","opc":"%s"}' "$imsi" "$ki" "$opc")")
done
unset rows imsi ki opc

token=""
printf 'caller key (hidden): ' >&2
IFS= read -rs token || true
echo >&2
[ -n "$token" ] || { echo "import-keys: no caller key; nothing was sent" >&2; exit 2; }

# On core-cp: the first line of standard input is the caller key, then one SIM per line. The header goes to curl through a
# process substitution, so the key is never on a command line there either. Prints one HTTP status per SIM.
remote="bash -c 'IFS= read -r t; while IFS= read -r b; do printf %s \"\$b\" | curl -sS -o /dev/null -w \"%{http_code}\\n\" -X POST $url/v1/sims --config <(printf \"header = \\\"Authorization: Bearer %s\\\"\\n\" \"\$t\") -H \"Content-Type: application/json\" --data-binary @- || echo 000; done'"
codes="$( { printf '%s\n' "$token"; printf '%s\n' "${bodies[@]}"; } | ssh -T "$host" "$remote" )"
unset token bodies

failed=0; i=0
for four in "$@"; do
  i=$((i + 1))
  code="$(printf '%s\n' "$codes" | sed -n "${i}p")"
  case "$code" in
    200) echo "…$four  imported (200)" ;;
    409) echo "…$four  REFUSED (409): RatelLink already holds different keys for this SIM; they were kept"; failed=1 ;;
    401) echo "…$four  REFUSED (401): the caller key is wrong or disabled"; failed=1 ;;
    *)   echo "…$four  FAILED (${code:-no answer})"; failed=1 ;;
  esac
done
exit "$failed"
