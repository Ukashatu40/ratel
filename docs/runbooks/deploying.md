# Runbook: deploying a release (app, desk, meter, calls, link)

Keep it short. Never put a key, a password or a real address in this page. The host names below are the ssh aliases in your
own `~/.ssh/config`.

- **Last verified:** TODO. The tool is tested against fake hosts (`tests/tooling/test_deploy.py`); its first real use is still to
  be done, and the person who does it should write the date here
- **Owner:** the project lead
- **Runs on:** your machine (the script) and the host it deploys to (a second script, run with `sudo`)

## What it does

`scripts/deploy/deploy.sh <target>` replaces the copy-and-paste of the release steps. For one host, in order:

1. Builds the release from `origin/main` (the build scripts refuse any commit that is not on it), prints its SHA-256 and what
   changes, and asks `Deploy this to <host>? [y/N]`.
2. Copies the tarball, the installer and the host's script into a private temporary folder on the host (`mktemp -d`).
3. Runs the host's script with `sudo` (you type the sudo password once, on the host). It checks the checksum, remembers the
   running release, installs, restarts, and waits for the service to say it is up.
4. **If it does not come up, it puts the previous release back and restarts it,** says so, and exits non-zero. A database
   migration is never undone: the output says when one was applied.
5. Writes a line to `~/ratel-releases/deploy-log.tsv` on your machine and to `/var/log/ratel-deploy.log` on the host (who, when,
   from which release to which, ok or failed).

| Target | Host | What it does | "Up" means |
| ------ | ---- | ------------ | ---------- |
| `app` | bss-app | installs the release, runs the migrations as the owner role, restarts `ratel-app.service` | `healthz` answers and `readyz` is 200 |
| `desk` | bss-app | unpacks RatelDesk's files and switches `/var/www/ratel-desk` | the new folder has an `index.html` |
| `meter` | core-up | installs the data agent, restarts `ratel-meter.service` | the journal shows `meter.agent.started` and no `tick_error`, `nft_failed` or traceback |
| `calls` | voice VM | installs the call agent, restarts `ratel-meter-calls.service` | the same |
| `link` | core-cp | installs RatelLink, restarts `ratel-link.service` | `healthz` answers and `readyz` is 200 (it needs MongoDB and the key file); the calls to it fail for the second or two of the restart |

A failure in a tick shows at the next 5-minute boundary, not at the restart: read the journal then.

## One-time setup

```bash
ssh-add --apple-use-keychain ~/.ssh/ratelplus_server     # type the key's passphrase once per login, not once per command
mkdir -p ~/.ssh
```
The tool shares one ssh connection per host for ten minutes, so the passphrase is not asked again within a deploy. The aliases
it uses are `ratelplus-bss-app`, `ratelplus-core-up` and `ratelplus-voice`; set `RATEL_HOST_APP`, `RATEL_HOST_CORE_UP` or
`RATEL_HOST_VOICE` to use other names (`ratelplus-core-cp` and `RATEL_HOST_CORE_CP` for `link`). RatelLink's Python is
`RATEL_LINK_PYTHON`, by default `/opt/python-3.12/bin/python3.12`: check it is right on core-cp before the first `link` deploy
(`readlink -f /opt/ratel-link/current/venv/bin/python`).

## Using it

```bash
git switch main && git pull                  # only what is merged is deployed
scripts/deploy/deploy.sh meter --dry-run     # shows the target, the checksum and the change; touches nothing
scripts/deploy/deploy.sh meter               # asks, then deploys
scripts/deploy/deploy.sh app && scripts/deploy/deploy.sh desk
scripts/deploy/deploy.sh calls
```
Other options: `--commit <ref>` deploys another commit that is on `origin/main` (that is also how you go back to an older
release); `--tarball <file>` deploys a build you already have (a retry after a failed copy); `--yes` skips the question.

**Read the PR before you deploy.** If it adds a setting, a unit, a timer or a sudo rule, do that by hand first (below). A release
that needs a setting the host does not have will fail its "up" check and be rolled back, which is safe but loses the time.

## What it does not do

It never edits an env file, nginx, the firewall, a systemd unit, a sudo rule or a database role, and it does not run the nginx
updater. Those stay manual, from the README of the host: `deploy/bss-app/README.md`,
`deploy/core-up/README.md`, `deploy/voice/README.md`, `deploy/core-cp/README.md`.

## When it fails

| It says | What it means | What to do |
| ------- | ------------- | ---------- |
| `cannot reach <host>` | ssh did not connect | `ssh <host>` by hand; check the VPN or the passphrase |
| `copy to <host> failed` | scp failed; nothing ran | run it again with `--tarball ~/ratel-releases/<file>` (the copy is slow: 3 to 14 MB) |
| `the checksum on the host differs` | the copy was damaged; nothing was installed | run it again |
| `the migration failed; the service was not restarted` | the old release is still running | read the migration's message above it; do not retry blindly |
| `the new release did not come up: rolled back` | the old release runs again | read `journalctl -u ratel-app.service`; if it said a migration was applied, check the old release against the new schema |
| `the new agent did not come up cleanly: rolled back` | the same for an agent | `journalctl -u ratel-meter.service -n 30` (or `ratel-meter-calls.service`) |

## Rollback

It rolls back by itself when the "up" check fails. To go back on purpose, deploy the older commit:
`scripts/deploy/deploy.sh meter --commit <older commit>`. A migration is not undone by an older release
(`alembic downgrade` refuses to drop tables that hold rows): restore from the backup instead
([bss-backup-restore.md](bss-backup-restore.md)).

## Why a script and not CI

The Build Plan wants production changes to be reviewed commits and nobody editing a host by hand. This keeps both and needs
nothing new on the hosts: no agent, no stored credential, no open port. A deploy from CI would need a key on GitHub that can
log in to the hosts; the hosts are only reachable from the office and the VPN, so that is a decision for the network lead.
