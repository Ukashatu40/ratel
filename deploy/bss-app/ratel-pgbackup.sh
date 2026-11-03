#!/usr/bin/env bash
# Nightly dump of RatelBSS's PostgreSQL database. Install as /usr/local/sbin/ratel-pgbackup (root-owned, mode 0755);
# ratel-pgbackup.service runs it as the `postgres` user, which reaches the database over the local socket (no password).
#
# What it does, in order: dump the database in PostgreSQL's custom format to a .partial file, check the dump can be read
# back (pg_restore --list), move it into place under its final name, and only then delete all but the newest N dumps.
# A dump that fails or cannot be read is never kept and never causes an older one to be deleted. Nothing is printed
# but the file name, its size and a count: no row, no table content.
#
# Settings (environment; the defaults are right for bss-app):
#   RATEL_DB           database to dump               (default: ratel_bss)
#   RATEL_BACKUP_DIR   where the dumps go             (default: /var/backups/ratel-bss, mode 0700, owned by postgres)
#   RATEL_BACKUP_KEEP  how many dumps to keep         (default: 14)
#
# These dumps sit on the same VM. They protect against a mistake or a corrupted table, NOT against losing the VM or its
# disk: a copy that leaves the host, encrypted, is still to be decided (deploy/bss-app/README.md, "Backups").
set -euo pipefail
umask 077

db="${RATEL_DB:-ratel_bss}"
dir="${RATEL_BACKUP_DIR:-/var/backups/ratel-bss}"
keep="${RATEL_BACKUP_KEEP:-14}"

if [[ ! "$db" =~ ^[A-Za-z0-9_]+$ ]]; then echo "ratel-pgbackup: refused: the database name must be letters, digits and _" >&2; exit 1; fi
if [[ ! "$keep" =~ ^[0-9]+$ ]] || [ "$keep" -lt 1 ]; then echo "ratel-pgbackup: refused: RATEL_BACKUP_KEEP must be 1 or more" >&2; exit 1; fi
if [ ! -d "$dir" ]; then echo "ratel-pgbackup: refused: $dir does not exist" >&2; exit 1; fi

final="$dir/$db-$(date -u +%Y%m%dT%H%M%SZ).dump"
partial="$final.partial"
trap 'rm -f -- "$partial"' EXIT

pg_dump --format=custom --compress=6 --file="$partial" "$db"
pg_restore --list "$partial" >/dev/null     # the dump can be read back
[ -s "$partial" ]                           # and is not empty
mv -- "$partial" "$final"

# Only now, with a good new dump in place, drop the oldest beyond `keep`.
n=0
while IFS= read -r old; do
  n=$((n + 1))
  if [ "$n" -gt "$keep" ]; then rm -f -- "$old"; fi
done < <(ls -1t -- "$dir/$db"-*.dump)

size="$(wc -c <"$final" | tr -d ' ')"
count="$(ls -1 -- "$dir/$db"-*.dump | wc -l | tr -d ' ')"
echo "ratel-pgbackup: wrote $(basename "$final") ($size bytes); $count kept"
