#!/usr/bin/env bash
# Nightly encrypted dump of RatelBSS's PostgreSQL database (the host's `ratel_bss`, not a container). Install as
# /usr/local/sbin/ratel-bss-backup (root-owned, mode 0755); ratel-bss-backup.service runs it as the `postgres` user, which
# reaches the database over the local socket (no password).
#
# In order: dump the database in PostgreSQL's custom format to a work file, check the dump can be read back
# (pg_restore --list), encrypt it with `age` to the public keys in the recipient file, move the encrypted file into place
# under its final name, delete the work file, and only then delete all but the newest N encrypted dumps. A dump that fails,
# cannot be read or cannot be encrypted is never kept and never causes an older one to be deleted. Nothing is printed but
# the file name, its size and a count: no row, no table content.
#
# The dump holds customers' personal data, so a plain dump is never kept: the work file exists only while the script runs,
# in a folder only `postgres` can enter. Only the holder of the PRIVATE key can read the result, and that key is not on this
# host (docs/runbooks/bss-backup-restore.md). The recipient file holds PUBLIC keys only; the script refuses a file with a
# private key in it.
#
# Settings (environment; the defaults are right for bss-app):
#   RATEL_DB                  database to dump         (default: ratel_bss)
#   RATEL_BACKUP_DIR          where the dumps go       (default: /var/backups/ratel-bss, mode 0700, owned by postgres)
#   RATEL_BACKUP_RECIPIENTS   age public keys          (default: /etc/ratel-backup/age-recipient.txt)
#   RATEL_BACKUP_KEEP         how many dumps to keep   (default: 14)
#
# These dumps sit on the same VM. They protect against a mistake or a corrupted table, NOT against losing the VM or its
# disk: a copy that leaves the host is still to be decided (deploy/bss-app/README.md, "Backups").
set -euo pipefail
umask 077

db="${RATEL_DB:-ratel_bss}"
dir="${RATEL_BACKUP_DIR:-/var/backups/ratel-bss}"
recipients="${RATEL_BACKUP_RECIPIENTS:-/etc/ratel-backup/age-recipient.txt}"
keep="${RATEL_BACKUP_KEEP:-14}"

refuse() { echo "ratel-bss-backup: refused: $1" >&2; exit 1; }

[[ "$db" =~ ^[A-Za-z0-9_]+$ ]] || refuse "the database name must be letters, digits and _"
[[ "$keep" =~ ^[0-9]+$ ]] && [ "$keep" -ge 1 ] || refuse "RATEL_BACKUP_KEEP must be 1 or more"
[ -d "$dir" ] || refuse "$dir does not exist"
command -v age >/dev/null || refuse "age is not installed"
[ -r "$recipients" ] || refuse "the recipient file cannot be read"
grep -q '^age1' "$recipients" || refuse "the recipient file holds no age public key"
if grep -q 'AGE-SECRET-KEY-' "$recipients"; then refuse "the recipient file holds a PRIVATE key: remove it and keep only the public key"; fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
final="$dir/$db-$stamp.dump.age"
work="$dir/.work-$stamp.dump"
partial="$final.partial"
trap 'rm -f -- "$work" "$partial"' EXIT

pg_dump --format=custom --compress=6 --file="$work" "$db"
[ -s "$work" ]                               # not empty
pg_restore --list "$work" >/dev/null         # and can be read back
age --recipients-file "$recipients" --output "$partial" "$work"
[ -s "$partial" ]
mv -- "$partial" "$final"
rm -f -- "$work"                             # the plain dump goes as soon as the encrypted one exists

# Only now, with a good new dump in place, drop the oldest beyond `keep`.
n=0
while IFS= read -r old; do
  n=$((n + 1))
  if [ "$n" -gt "$keep" ]; then rm -f -- "$old"; fi
done < <(ls -1t -- "$dir/$db"-*.dump.age)

size="$(wc -c <"$final" | tr -d ' ')"
count="$(ls -1 -- "$dir/$db"-*.dump.age | wc -l | tr -d ' ')"
echo "ratel-bss-backup: wrote $(basename "$final") ($size bytes); $count kept"
