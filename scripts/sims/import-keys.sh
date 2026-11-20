#!/usr/bin/env bash
# Import the keys of chosen SIMs into RatelLink from the laptop, so that RatelDesk can sell them (RatelLink answers
# "Unknown line" at activation until a SIM's keys are in). The key file never leaves the laptop: the chosen rows are read
# here, and the keys travel only inside SSH, on standard input, to `POST /v1/sims` on core-cp. They are never on a command
# line, in a file on the server, on the screen or in this script's output. An import creates no service: a SIM is usable
# only once RatelBSS sells and activates it.
#
#   scripts/sims/import-keys.sh 0455 [0456 ...]       the last four digits of each SIM's IMSI
#   scripts/sims/import-keys.sh --prefix 62100        every row whose IMSI starts with this (five digits or more) and whose
#                                                     Status is Active; add --include-deactivated for the other rows too
#
# It asks for a caller key (hidden), made on core-cp for the session and disabled after it:
#   admin_cli api-key create --id lab-import-<n> --name "lab <n>"    ...    admin_cli api-key disable --id lab-import-<n>
# Chosen by last four digits, every SIM is checked before anything is sent (exactly one row, a 15-digit IMSI, Ki and OPc of 32
# hex characters) and one bad SIM stops them all. Chosen by prefix, a bad or repeated row is left out and counted, and the
# count is shown and confirmed before anything is sent. Sending the same keys again is harmless and changes nothing (200);
# different keys for an IMSI already stored are refused (409) and the stored ones are kept.
#
# Settings: RATEL_SIMS_FILE (default docs/source/sims.csv), RATEL_HOST_CORE_CP (ssh alias, default ratelplus-core-cp),
#           RATEL_LINK_URL (on core-cp, default http://127.0.0.1:8081)
set -euo pipefail

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
[ $# -ge 1 ] || usage
root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
file="${RATEL_SIMS_FILE:-$root/docs/source/sims.csv}"
host="${RATEL_HOST_CORE_CP:-ratelplus-core-cp}"
url="${RATEL_LINK_URL:-http://127.0.0.1:8081}"
[ -r "$file" ] || { echo "import-keys: cannot read the key file ($file)" >&2; exit 2; }
case "$url" in http://127.0.0.1:*|http://localhost:*) ;; *) echo "import-keys: RATEL_LINK_URL must be local to core-cp" >&2; exit 2 ;; esac

prefix=""; deactivated=0; fours=()
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) [ $# -ge 2 ] || usage; prefix="$2"; shift 2 ;;
    --include-deactivated) deactivated=1; shift ;;
    -*) usage ;;
    *) fours+=("$1"); shift ;;
  esac
done
if [ -n "$prefix" ]; then
  [ ${#fours[@]} -eq 0 ] || { echo "import-keys: give either --prefix or last four digits, not both" >&2; exit 2; }
  [[ "$prefix" =~ ^[0-9]{5,15}$ ]] || { echo "import-keys: the prefix must be 5 to 15 digits" >&2; exit 2; }
else
  [ ${#fours[@]} -ge 1 ] || usage
  [ "$deactivated" -eq 0 ] || { echo "import-keys: --include-deactivated goes with --prefix" >&2; exit 2; }
fi

labels=(); bodies=()
if [ -z "$prefix" ]; then
  for four in "${fours[@]}"; do
    [[ "$four" =~ ^[0-9]{4}$ ]] || { echo "import-keys: '$four' is not four digits" >&2; exit 2; }
    rows="$(awk -F, -v f="$four" '{ sub(/\r$/, "") } NR > 1 && substr($2, length($2) - 3) == f' "$file")"
    count="$(printf '%s' "$rows" | grep -c . || true)"
    [ "$count" -eq 1 ] || { echo "import-keys: $four matches $count rows in the key file; nothing was sent" >&2; exit 1; }
    IFS=, read -r _ imsi _ _ _ ki opc _ <<<"$rows"
    [[ "$imsi" =~ ^[0-9]{15}$ ]] || { echo "import-keys: $four: the IMSI is not 15 digits; nothing was sent" >&2; exit 1; }
    [[ "$ki" =~ ^[0-9A-Fa-f]{32}$ && "$opc" =~ ^[0-9A-Fa-f]{32}$ ]] \
      || { echo "import-keys: $four: Ki or OPc is not 32 hex characters; nothing was sent" >&2; exit 1; }
    labels+=("$four")
    bodies+=("$(printf '{"imsi":"%s","ki":"%s","opc":"%s"}' "$imsi" "$ki" "$opc")")
  done
  unset rows imsi ki opc
else
  # One line per row out of awk: OK <last four> <body>, or SKIP <reason>. Keys stay in memory; only counts are printed.
  picked="$(awk -F, -v p="$prefix" -v all="$deactivated" '
    function hex32(s) { return length(s) == 32 && s !~ /[^0-9A-Fa-f]/ }
    { sub(/\r$/, "") }
    NR == 1 { next }
    index($2, p) != 1 { next }
    !all && $8 != "Active" { skipped["not Active"]++; next }
    length($2) != 15 || $2 ~ /[^0-9]/ || !hex32($6) || !hex32($7) { skipped["malformed"]++; next }
    {
      keys = $6 "," $7
      if ($2 in seen) { if (seen[$2] != keys) clash[$2] = 1; skipped["repeated"]++; next }
      seen[$2] = keys; order[++n] = $2
    }
    END {
      for (i = 1; i <= n; i++) {
        imsi = order[i]
        if (imsi in clash) { skipped["repeated with different keys"]++; continue }
        split(seen[imsi], k, ",")
        printf "OK\t%s\t{\"imsi\":\"%s\",\"ki\":\"%s\",\"opc\":\"%s\"}\n", substr(imsi, 12), imsi, k[1], k[2]
      }
      for (r in skipped) printf "SKIP\t%s\t%d\n", r, skipped[r]
    }' "$file")"
  while IFS=$'\t' read -r kind a b; do
    case "$kind" in
      OK) labels+=("$a"); bodies+=("$b") ;;
      SKIP) echo "left out: $b ($a)" >&2 ;;
    esac
  done <<<"$picked"
  unset picked
  [ ${#bodies[@]} -gt 0 ] || { echo "import-keys: no row starts with $prefix; nothing was sent" >&2; exit 1; }
  printf 'import-keys: %d SIMs with an IMSI starting %s will be sent to RatelLink on %s. Type yes to go on: ' \
    "${#bodies[@]}" "$prefix" "$host" >&2
  answer=""; IFS= read -r answer || true
  [ "$answer" = "yes" ] || { echo "import-keys: not confirmed; nothing was sent" >&2; exit 1; }
fi

token=""
printf 'caller key (hidden): ' >&2
IFS= read -rs token || true
echo >&2
[ -n "$token" ] || { echo "import-keys: no caller key; nothing was sent" >&2; exit 2; }

# On core-cp: the first line of standard input is the caller key, then one SIM per line. The header goes to curl through a
# process substitution, so the key is never on a command line there either. Prints one HTTP status per SIM, as it goes, and
# stops at the first 401: a wrong or disabled caller key would be refused for every SIM after it.
remote="bash -c 'IFS= read -r t; while IFS= read -r b; do c=\$(printf %s \"\$b\" | curl -sS -o /dev/null -w \"%{http_code}\" -X POST $url/v1/sims --config <(printf \"header = \\\"Authorization: Bearer %s\\\"\\n\" \"\$t\") -H \"Content-Type: application/json\" --data-binary @-) || c=000; echo \"\$c\"; [ \"\$c\" != 401 ] || exit 0; done'"

total=${#bodies[@]}; bulk=0; [ -z "$prefix" ] || bulk=1
ok=0; refused=0; failed=0; i=0
while IFS= read -r code; do
  four="${labels[$i]}"; i=$((i + 1))
  case "$code" in
    200) ok=$((ok + 1)); [ "$bulk" -eq 1 ] || echo "…$four  imported (200)" ;;
    409) refused=$((refused + 1)); echo "…$four  REFUSED (409): RatelLink already holds different keys for this SIM; they were kept" ;;
    401) failed=$((failed + 1)); echo "…$four  REFUSED (401): the caller key is wrong or disabled" ;;
    *)   failed=$((failed + 1)); echo "…$four  FAILED (${code:-no answer})" ;;
  esac
  if [ "$bulk" -eq 1 ] && [ $((i % 500)) -eq 0 ]; then echo "  $i of $total sent" >&2; fi
done < <( { printf '%s\n' "$token"; printf '%s\n' "${bodies[@]}"; } | ssh -T "$host" "$remote" )
unset token bodies

missing=$((total - i))
[ "$missing" -eq 0 ] || echo "import-keys: no answer for the last $missing SIMs (the connection ended); run the same command again" >&2
if [ "$bulk" -eq 1 ]; then
  echo "done: $ok in RatelLink (new, or already there with the same keys), $refused refused (409), $failed failed, $missing not answered, of $total"
fi
[ "$refused" -eq 0 ] && [ "$failed" -eq 0 ] && [ "$missing" -eq 0 ]
