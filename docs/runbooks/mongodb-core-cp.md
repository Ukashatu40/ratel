# Runbook: MongoDB on core-cp (the core's subscriber database)

Keep it short. Never put a password, key or real subscriber data here.

- **Last verified:** 2026-10-25 for the users and the RatelLink connection (done by the project lead on core-cp); the recovery steps below have **not** been rehearsed
- **Owner:** the network lead (the database and the core), with the project lead for the `ratel_link` and `ratel_admin` users
- **Runs on:** core-cp, `mongod` under systemd, `127.0.0.1:27017` only, authorization enabled, no replica set yet

## Service and purpose

MongoDB holds the core's subscriber database (`open5gs`, which keeps each SIM's Ki and OPc in plaintext, the core's own choice) and RatelLink's own database (`ratel_link`). Open5GS's functions and RatelLink are its only clients. **Nothing else connects to it directly**: not RatelBSS, not the meter agent, not a person's tool, except an administrator for the jobs below.

## Who connects, and with what

| User | Used by | May do | Where its password is |
| ---- | ------- | ------ | --------------------- |
| `open5gs_app` | The core's own services (HSS, PCRF and the others that read subscribers) | What the core needs on `open5gs` | In the core's own configuration, which the network lead owns. TODO(network lead): the file |
| `ratel_link` | RatelLink only | Read and write `ratel_link`; read, insert, update and delete in `open5gs.subscribers`. **Never** delete or change a stored key or an audit entry, create indexes in the core's database, or touch anything else. The roles are `ratelLinkData` and `ratelLinkSubscribers` (`deploy/core-cp/mongo/ratel-link-roles.json`) | `MONGO_URI` in `/etc/ratel-link/ratel-link.env` (the service user, mode 0600) |
| `ratel_admin` | A person doing administration (the `root` role on `admin`) | Everything | `/etc/ratel-secrets/mongo-admin.pass`, root-only. **One copy.** See "A second copy" below |

Never type a password into a command line, a chat or a ticket: it lands in the shell history, `ps` and the scrollback. Anything the network team sent by WhatsApp or similar must be treated as exposed: change it.

## Health checks

```bash
systemctl is-active mongod                 # active
sudo ss -tlnp | grep 27017                 # 127.0.0.1 only. Anything else is a finding
curl -s http://127.0.0.1:8081/readyz       # RatelLink can reach it and its indexes exist (200)
```

An unauthenticated client must be refused. A connection with no credentials can connect, but any read fails with `requires authentication`.

## Open a shell as the administrator, without the password on the screen

```bash
sudo mongosh --quiet --shell "mongodb://127.0.0.1:27017/admin" \
  --eval 'db.auth("ratel_admin", require("fs").readFileSync("/etc/ratel-secrets/mongo-admin.pass","utf8").trim())'
```

The password is read inside `mongosh` from the root-only file. The command line holds only the path. Do not paste the file's content anywhere.

## Common failures

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| RatelLink `readyz` is not 200, or the log says `Authentication failed` | The `ratel_link` password in `ratel-link.env` is not the user's | Re-create the user with a new password (below), put it in `MONGO_URI`, restart `ratel-link` |
| The core's services log authentication errors | `open5gs_app`'s password in the core's config is wrong, or the user was removed | The network lead fixes the user or the config. Do **not** switch authorization off to "make it work" |
| `mongod` will not start after a change to `/etc/mongod.conf` | A syntax error, or a keyFile that does not exist | `journalctl -u mongod -e`; put the previous file back |
| An attach fails after any MongoDB change | The HSS or PCRF lost its connection | `journalctl -u open5gs-hssd -u open5gs-pcrfd -e`; restart them. TODO(network lead): confirm whether they reconnect by themselves |

## Recovery

**Change RatelLink's database password** (also the answer to "I think it leaked"). The script creates the user or updates it:

```bash
cd /path/to/ratel/deploy/core-cp/mongo        # a checkout of the repository, on a machine that can reach MongoDB
RATEL_LINK_DB_PASSWORD="$(openssl rand -base64 33 | tr -d '/+=')" \
  mongosh "<administrator connection string>" --file create-ratel-link-user.js
```
Then put the same password in `MONGO_URI` in `/etc/ratel-link/ratel-link.env` (edit it with a script or `sudo -e`; never print it), and `sudo systemctl restart ratel-link`. Check `readyz`.

**The administrator password is lost** (the file is gone and nobody has it). Anyone with `root` on core-cp can reset it, so losing the file is an inconvenience and not a disaster. This takes MongoDB down for a minute; do it in agreed time with the network lead, and not during a lab session.

1. Stop it: `sudo systemctl stop mongod`.
2. Turn authorization off: comment out `authorization: enabled` in `/etc/mongod.conf`, then `sudo systemctl start mongod`. It still listens on `127.0.0.1` only, and the firewall (`deploy/firewall/`) keeps everything else out, but nothing else on the host should connect meanwhile.
3. In `mongosh`, set a new password for `ratel_admin` (`db.getSiblingDB("admin").updateUser("ratel_admin", {pwd: passwordPrompt()})`), which asks on the terminal.
4. Put the line back in `/etc/mongod.conf`, `sudo systemctl restart mongod`, and write the new password to `/etc/ratel-secrets/mongo-admin.pass` (root-only, mode 0600) without printing it.
5. Check that an attach works and `readyz` is 200 (see the failures table).

## A second copy of the administrator password

**Recommended: no second copy.** The recovery above means the file can always be replaced by someone with `root`, and every extra copy of the database's root password is one more thing to lose or leak. Keep the single root-only file, and make sure two people (the network lead and the project lead) know the recovery steps. Decision: TODO(project lead).

## Not built yet

- A **replica set** with a change stream, which RatelLink's live changes (CHG-6) need. It needs a `keyFile` and a maintenance window of a few minutes with the network lead (proposed: Saturday 2026-10-31). Until then a changed or deactivated line takes effect at its next attach.
- **Encrypted backups** of the `open5gs` database. Any backup that leaves core-cp must be encrypted first, because the database holds Ki and OPc in plaintext (ADR 0006; network team, Week 6, risk R-06). A restore has not been rehearsed.

## Escalation

The network lead first, then the project lead. TODO: contact details are kept off this page.
