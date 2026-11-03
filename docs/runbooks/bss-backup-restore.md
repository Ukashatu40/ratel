# RatelBSS database: restore from the nightly backup

- **Who:** the project lead, with the holder of the backup's private key
- **When:** (1) once, as a rehearsal, before the demo; (2) after real damage
- **Runs on:** bss-app (to fetch the file), and the machine that holds the **private key** (to decrypt and restore into a scratch database)

The nightly dump (`deploy/bss-app/ratel-bss-backup.sh`) is encrypted with `age` to a **public** key. Whoever holds the matching
**private key** can read it; nobody else can, including anyone on bss-app. A backup nobody can decrypt is not a backup:
the first thing to prove is that the key exists and works.

**TODO(network lead):** where the private key is kept, who holds it, and a second copy of it. Until that is written
down here, treat the backups as unproven. Never put the private key on bss-app, and never paste it in a chat or commit it.

## 1. Fetch the newest file (bss-app to the key holder's machine)

```bash
# on bss-app: the file name and size only
sudo ls -lt /var/backups/ratel-bss | head -3
# on the key holder's machine (replace the name with the one above)
scp -o 'ProxyJump=none' ratelplus-bss-app:/tmp/ratel_bss-<time>.dump.age ~/restore-test/   # after: sudo cp it to /tmp and chmod a+r, then rm it
```
The folder `/var/backups/ratel-bss` is readable by `postgres` only, so copy the one file you need to `/tmp`, make it readable,
`scp` it, and delete the copy in `/tmp` afterwards.

## 2. Decrypt and restore into a scratch database (never over the live one)

On a machine with PostgreSQL 16 client tools and `age`, and the private key at a path only you can read:

```bash
cd ~/restore-test && chmod 700 .
age --decrypt --identity ~/.config/ratel-backup/private.key ratel_bss-<time>.dump.age > rehearsal.dump
pg_restore --list rehearsal.dump | head -5          # a table of contents proves the file is readable
createdb rehearsal && pg_restore --no-owner --no-privileges --dbname rehearsal rehearsal.dump
```

## 3. Compare with a count of rows (table names and counts only, no data)

```bash
Q="select table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by 1"
psql -Atd rehearsal -c "$Q"
```
On bss-app, run the same query against `ratel_bss` (`sudo -u postgres psql -Atd ratel_bss -c "$Q"`). The counts match exactly only if
nothing was written since the dump; a small difference on a live system is expected, a missing table is not.
Write down the date and the result here (a line in the PR or the run log is enough): a restore that was never tried is not proven.

Then delete the scratch data: `dropdb rehearsal && shred -u rehearsal.dump && rm -f ratel_bss-*.dump.age`.

## 4. Restoring for real after damage

1. Stop `ratel-app.service` and the rating and ledger-check timers on bss-app.
2. Restore into a **fresh** database on bss-app (copy the decrypted dump there over a private channel, `pg_restore --no-owner
   --role=...` as the migration owner), check the table counts as in step 3.
3. Switch `DATABASE_URL` to the new database (or rename the databases), start the services, check `healthz` and `readyz`.
4. Delete the decrypted dump from bss-app.

Do not restore over the live database, and do not keep a decrypted dump anywhere longer than the restore takes: it holds
customers' personal data.
